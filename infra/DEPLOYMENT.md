# Infrastructure & Deployment Guide

## Overview

The infrastructure is provisioned with Terraform (Azure provider ~4.0) and targets an **existing** Azure resource group. All resources derive their location from that resource group — no region variable needed.

After Terraform, a two-step deployment registers the Docker images and the AI Foundry agents.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Terraform | >= 1.3.0 |
| Azure CLI | any recent |
| Python | >= 3.11 |
| Docker | any recent |

You must be authenticated to Azure before running anything:

```bash
az login
az account set --subscription <subscription-id>
```

---

## What Terraform Provisions

All resources are created inside the resource group you supply. Names are auto-generated using a normalized prefix + a random 6-character suffix to avoid global naming collisions.

| Resource | Purpose |
|----------|---------|
| Log Analytics Workspace | Centralised logs for all Container Apps |
| Container App Environment | Shared hosting environment for both apps |
| Azure Container Registry (ACR) | Stores the MCP and bot Docker images |
| Storage Account (StorageV2, Hot) | Blob containers: `transcripts` and `reports` — **azure mode only** |
| Cosmos DB (Serverless, SQL API) | Meeting data — partitioned by `/meeting_id` — **azure mode only** |
| Container App — `*-mcp` | MCP server, port 8000, external ingress |
| Container App — `*-bot` | Teams bot, port 3978, external ingress |

> Set `mcp_backend_mode = "mock"` to skip Storage and Cosmos DB entirely. The MCP Container App will start with `MCP_BACKEND_MODE=mock` and use in-memory data. Useful for dev/test deployments where you only need the bot and agents wired up.

Both Container Apps use a **SystemAssigned managed identity**, which you should grant RBAC roles to after provisioning (see Post-Provisioning section below).

### Outputs

After `terraform apply` these values are printed and needed in later steps:

| Output | Description |
|--------|-------------|
| `container_registry_login_server` | ACR login server (e.g. `<name>.azurecr.io`) |
| `storage_account_name` | Storage account name |
| `storage_blob_endpoint` | Primary blob endpoint URL |
| `cosmosdb_endpoint` | Cosmos DB endpoint URL |
| `mcp_server_url` | Public HTTPS URL of the MCP Container App |
| `bot_base_url` | Public HTTPS URL of the Teams Bot Container App |

---

## Step 1 — Terraform

### Configure variables

Copy the example tfvars and fill in your values:

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

```hcl
# infra/terraform.tfvars

resource_group_name       = "your-existing-rg"          # required — must already exist
environment_name          = "meeting-analyzer"           # used as name prefix
mcp_backend_mode          = "mock"                       # "mock" skips Storage & Cosmos, "azure" creates them
acr_sku                   = "Basic"                      # Basic | Standard | Premium
acr_image_tag             = "latest"                     # image tag to deploy
cosmos_database_name      = "meeting-analysis"
mcp_log_level             = "INFO"
bot_log_level             = "INFO"
bot_app_id                = "<teams-bot-app-id>"
bot_app_password          = "<teams-bot-client-secret>"  # sensitive
azure_ai_project_endpoint = "https://<account>.services.ai.azure.com/api/projects/<project>"  # sensitive
graph_tenant_id           = "<aad-tenant-id>"
graph_client_id           = "<aad-client-id>"
```

> `bot_app_password` and `azure_ai_project_endpoint` are marked sensitive — they will not appear in plan output or logs.

### Apply

```bash
cd infra
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Capture the outputs for the next steps:

```bash
terraform output -raw mcp_server_url
terraform output -raw container_registry_login_server
terraform output -raw bot_base_url
```

---

## Step 2 — Build & Push Docker Images

Both Container Apps pull images from the ACR provisioned above. Build and push before the apps can start successfully.

```bash
ACR=$(terraform -chdir=infra output -raw container_registry_login_server)
az acr login --name $ACR

# MCP server
docker build -t $ACR/meeting-analyzer-mcp:latest ./mcp
docker push $ACR/meeting-analyzer-mcp:latest

# Teams bot
docker build -t $ACR/meeting-analyzer-bot:latest ./team_bot
docker push $ACR/meeting-analyzer-bot:latest
```

After pushing, restart the Container App revisions to pull the new images:

```bash
az containerapp revision restart \
  --name <mcp-app-name> \
  --resource-group <resource-group>
```

---

## Step 3 — Post-Provisioning RBAC

The Container Apps use managed identities. Grant them the minimum required roles:

**MCP Container App identity:**

```bash
MCP_PRINCIPAL=$(az containerapp show \
  --name <mcp-app-name> --resource-group <rg> \
  --query identity.principalId -o tsv)

# Storage — read/write blobs
az role assignment create \
  --assignee $MCP_PRINCIPAL \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<storage-name>

# Cosmos DB — data contributor
az role assignment create \
  --assignee $MCP_PRINCIPAL \
  --role "Cosmos DB Built-in Data Contributor" \
  --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.DocumentDB/databaseAccounts/<cosmos-name>
```

**Bot Container App identity:**

```bash
BOT_PRINCIPAL=$(az containerapp show \
  --name <bot-app-name> --resource-group <rg> \
  --query identity.principalId -o tsv)

# Azure AI Foundry — agent invocation
az role assignment create \
  --assignee $BOT_PRINCIPAL \
  --role "Azure AI Developer" \
  --scope /subscriptions/<sub>/resourceGroups/<rg>
```

---

## Step 4 — Verify MCP Server

Before registering agents, confirm the MCP server is up:

```bash
MCP_SERVER_URL=$(terraform -chdir=infra output -raw mcp_server_url) \
  ./manage.sh check:mcp
```

This hits `<mcp_server_url>/docs` and exits non-zero if unreachable.

---

## Step 5 — Register AI Foundry Agents

This step creates or updates the three agents in Azure AI Foundry and writes their IDs to `orchestrator/agent_ids.json`, which the orchestrator uses at runtime.

```bash
AZURE_AI_PROJECT_ENDPOINT=<your-foundry-endpoint> \
MCP_SERVER_URL=$(terraform -chdir=infra output -raw mcp_server_url) \
  ./manage.sh deploy:agents
```

The script is idempotent — re-running it updates existing agents rather than creating duplicates.

Agents registered:

| Agent name | Role |
|------------|------|
| `analysis-agent` | Post-meeting analysis, agenda adherence, action items |
| `sentiment-agent` | Sentiment scoring, participation, prosody enrichment |
| `post-meeting-transcription-agent` | Batch audio post-processing, transcript enrichment |

On success, `orchestrator/agent_ids.json` is written:

```json
{
  "analysis-agent": "asst_...",
  "sentiment-agent": "asst_...",
  "post-meeting-transcription-agent": "asst_..."
}
```

---

## Teams App Registration (teams.tf)

The `teams.tf` file is part of the same Terraform root module but manages a separate concern — the Azure AD identity and Bot Service registration. It is applied together with `main.tf` in a single `terraform apply`.

What it provisions:

| Resource | Purpose |
|----------|---------|
| `azuread_application` | Azure AD app registration — the bot's identity |
| `azuread_service_principal` | Service principal for the app |
| `azuread_application_password` | Client secret, auto-rotated by tainting the resource |
| `azurerm_bot_service_azure_bot` | Bot Channels Registration wired to the Container App endpoint |
| `azurerm_bot_channel_ms_teams` | Enables the Teams channel on the bot service |

The bot Container App automatically receives `BOT_APP_ID` and `BOT_APP_PASSWORD` from these resources — no manual copy-paste needed.

After `terraform apply`, retrieve the generated credentials if needed elsewhere:

```bash
terraform output bot_app_id
terraform output -raw bot_app_password   # sensitive
```

### Rotating the client secret

The secret has a configurable expiry (`bot_secret_expiry_years`, default 1 year). To rotate it:

```bash
terraform taint azuread_application_password.bot
terraform apply -var-file=terraform.tfvars
```

### What Terraform cannot do — Teams App Manifest

The `.zip` manifest package that end-users install into Teams must be created and uploaded manually. After `terraform apply`:

1. Create a `manifest.json` using the [Teams manifest schema](https://learn.microsoft.com/en-us/microsoftteams/platform/resources/schema/manifest-schema)
2. Set `"id"` to the value of `terraform output bot_app_id`
3. Set `"bots[0].botId"` to the same value
4. Zip it with your app icons: `zip teams-app.zip manifest.json color.png outline.png`
5. Upload via Teams Admin Center → Manage apps → Upload, or distribute via your org's app catalog

---

## Redeployment & Updates

| Scenario | Action |
|----------|--------|
| Config/variable change | `terraform apply -var-file=terraform.tfvars` |
| New image version | Push new tag to ACR, update `acr_image_tag`, re-apply |
| Agent instruction change | Edit `agents/instructions/*.md`, re-run `deploy:agents` |
| Agent definition change | Edit `agents/definitions/*.yaml`, re-run `deploy:agents` |

---

## Teardown

```bash
terraform destroy -var-file=infra/terraform.tfvars
```

> This does **not** delete the resource group itself, only the resources Terraform created inside it.
