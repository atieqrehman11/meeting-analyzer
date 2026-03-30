# Meeting Analyzer Terraform Infrastructure

This folder contains Terraform scripts for provisioning the Azure infrastructure required by the Meeting Analyzer repository.

## What this deploys

- Azure Container Registry (ACR) for application images
- Azure Log Analytics workspace and Container Apps environment
- Azure Container Apps for the MCP server and Teams bot
- Azure Storage account with `transcripts` and `reports` blob containers
- Azure Cosmos DB serverless account with a SQL database and meeting data container

## Prerequisites

- An existing Azure Resource Group provisioned by your IT team
- Azure CLI authenticated and ready to use
- Terraform installed
- Optional: Azure AD app registration created for the Teams bot if you want the bot to run immediately

## Quick start

1. Copy the example file:

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

2. Update `infra/terraform.tfvars` with your resource group name and values.

3. Initialize Terraform:

```bash
cd infra
terraform init
```

4. Review the plan:

```bash
terraform plan -var-file="terraform.tfvars"
```

5. Apply the deployment:

```bash
terraform apply -var-file="terraform.tfvars"
```

## After deployment

Terraform outputs will include:

- `container_registry_login_server`
- `mcp_server_url`
- `bot_base_url`
- `storage_blob_endpoint`
- `cosmosdb_endpoint`

You should build and push Docker images to the deployed ACR before the Container Apps can start successfully.

Example:

```bash
acr_name=$(terraform output -raw container_registry_login_server)
az acr login --name ${acr_name%%.*}

docker build -f mcp/Dockerfile -t ${acr_name}/meeting-analyzer-mcp:latest .
docker push ${acr_name}/meeting-analyzer-mcp:latest

docker build -f team_bot/Dockerfile -t ${acr_name}/meeting-analyzer-bot:latest .
docker push ${acr_name}/meeting-analyzer-bot:latest
```

## Notes

- The Teams bot requires `BOT_APP_ID` and `BOT_APP_PASSWORD`; set them in `terraform.tfvars` or later with Terraform variable overrides.
- `azure_ai_project_endpoint` can be left blank if your Foundry / AI Project workspace is provisioned separately.
- The MCP and bot apps are configured to use the runtime environment provided by Container Apps, ACR, Blob Storage, and Cosmos DB.
