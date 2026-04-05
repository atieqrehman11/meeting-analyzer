# Infrastructure & Deployment Guide

## Overview

The infrastructure is provisioned with Terraform (Azure provider ~4.0) and targets an **existing** Azure resource group. All resources derive their location from that resource group — no region variable needed.

All deployment steps are scripted through `deploy.sh` from the repo root. To deploy everything at once:

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
# fill in your values, then:
./deploy.sh all
```

Or run each step individually — see the steps below.

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

> The identity running Terraform needs `Azure AI Account Owner` at the subscription scope to create the Foundry account and project. `Contributor` alone is not sufficient.

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
| Azure AI Services account | Foundry resource — hosts the model deployment and project |
| GPT-4o deployment (`gpt-4o-meeting-bot`) | Model used by all three agents |
| Azure AI Foundry project | Scoped project — endpoint injected into bot Container App |

> Foundry uses **Basic Setup** (platform-managed thread/file storage). No BYO Cosmos DB or Azure AI Search is needed. This is compatible with the `AIProjectClient` agents API used by the orchestrator.

> GPT-4o availability varies by region. If `terraform apply` fails with a quota error, either request a quota increase in the Azure portal or set `foundry_model_sku = "GlobalStandard"` in `terraform.tfvars` which routes across regions.

> All resource names follow the Azure CAF prefix convention: `{type}-{workload}-{env}-{region}`. Storage Account and ACR use a no-dash slug variant (`{type}{workload}{env}{instance}`) due to Azure naming constraints. The workload name defaults to `meetingassist`.

> Set `mcp_backend_mode = "mock"` to skip Storage and Cosmos DB entirely. The MCP Container App will start with `MCP_BACKEND_MODE=mock` and use in-memory data. Useful for dev/test deployments where you only need the bot and agents wired up.



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
| `azure_ai_project_endpoint` | Foundry project endpoint — auto-injected into bot, used by `deploy:agents` |
| `foundry_deployment_name` | GPT-4o deployment name (`gpt-4o-meeting-bot`) |

---

## Step 1 — Configure & Apply Terraform

Copy the example tfvars and fill in your values:

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

Key values to set:

```hcl
resource_group_name  = "your-existing-rg"
workload_name        = "meetingassist"   # used in all resource names
environment          = "dev"             # dev | staging | prod
azure_region         = "eastus"
mcp_backend_mode     = "mock"       # "mock" skips Storage & Cosmos, "azure" creates them
acr_image_tag        = "latest"
graph_tenant_id      = "<aad-tenant-id>"
graph_client_id      = "<aad-client-id>"

# Azure AI Foundry
foundry_model_version  = "2024-11-20"
foundry_model_capacity = 10         # TPM in thousands — increase for production
```

Then apply:

```bash
./deploy.sh infra
```

---

## Step 2 — Build & Push Docker Images

```bash
./deploy.sh docker
# or with a specific tag:
./deploy.sh docker --tag v1.0.0
```

Both images use the repo root as build context — the Dockerfiles copy `shared_models` from a sibling directory.

---

## Step 3 — Assign RBAC Roles

```bash
./deploy.sh rbac
```

Reads all resource names from Terraform outputs and assigns:

- MCP identity → `Storage Blob Data Contributor` on the Storage Account *(azure mode only)*
- MCP identity → `Cosmos DB Built-in Data Contributor` on the Cosmos DB account *(azure mode only)*
- Bot identity → `Azure AI Developer` on the Resource Group

---

## Step 4 — Verify MCP Server

```bash
./deploy.sh check-mcp
```

---

## Step 5 — Register AI Foundry Agents

```bash
./deploy.sh agents
```

Both `AZURE_AI_PROJECT_ENDPOINT` and `MCP_SERVER_URL` are read automatically from Terraform outputs — no manual env vars needed.

The script is idempotent — re-running it updates existing agents rather than creating duplicates.

Agents registered:

| Agent name | Role |
|------------|------|
| `analysis-agent` | Post-meeting analysis, agenda adherence, action items |
| `sentiment-agent` | Sentiment scoring, participation, prosody enrichment |
| `transcript-agent` | Batch audio post-processing, transcript enrichment |

On success, `orchestrator/agent_ids.json` is written:

```json
{
  "analysis-agent": "asst_...",
  "sentiment-agent": "asst_...",
  "transcript-agent": "asst_..."
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

The `.zip` manifest package that end-users install into Teams must be created and uploaded manually.

See the full step-by-step guide: [`docs/teams-app-registration.md`](../docs/teams-app-registration.md)

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
