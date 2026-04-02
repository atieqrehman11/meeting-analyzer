# ---------------------------------------------------------------------------
# Azure AI Foundry — AI Services account, GPT-4o deployment, and project
#
# Uses the AzAPI provider because azurerm has limited Foundry support:
#   - azurerm cannot manage Foundry projects
#   - azurerm cannot configure capability hosts (required for Agent Service)
#   - AzAPI gives access to all control-plane features including preview APIs
#
# Agent Service setup mode: Basic
#   - Platform-managed thread/file storage (no BYO Cosmos DB / Search needed)
#   - Compatible with OpenAI Assistants API surface
#   - What foundry_client.py uses: agents.threads, agents.runs, agents.messages
#
# What this creates:
#   1. Azure AI Services account  (the Foundry resource)
#   2. GPT-4o model deployment    (named "gpt-4o-meeting-bot" — matches agent YAMLs)
#   3. Azure AI Foundry project   (scoped under the AI Services account)
#   4. RBAC — Azure AI User role  (bot managed identity → Foundry account)
#
# The project endpoint is read from the API response and injected into the
# bot Container App as ORCH_AZURE_AI_PROJECT_ENDPOINT.
# ---------------------------------------------------------------------------

locals {
  foundry_name    = "${local.normalized_name}ai${local.name_suffix}"
  foundry_project = "${local.normalized_name}-project"
}

# ---------------------------------------------------------------------------
# 1. AI Services account (the Foundry resource)
# ---------------------------------------------------------------------------
resource "azapi_resource" "foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-04-01-preview"
  name      = local.foundry_name
  parent_id = data.azurerm_resource_group.rg.id
  location  = data.azurerm_resource_group.rg.location

  schema_validation_enabled = false

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned"
    }
    properties = {
      # Allow both Entra ID and API key auth
      disableLocalAuth = false
      # Required to create projects under this account
      allowProjectManagement = true
      # Custom subdomain is required — used in the DNS name for the endpoint
      customSubDomainName = local.foundry_name
    }
  }

  # Export the endpoint and principal ID from the API response
  response_export_values = ["properties.endpoint", "identity.principalId"]
}

# ---------------------------------------------------------------------------
# 2. GPT-4o model deployment
#    Deployment name matches agents/definitions/*.yaml model field.
#    Override via foundry_deployment_name in terraform.tfvars.
# ---------------------------------------------------------------------------
resource "azapi_resource" "foundry_gpt4o" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview"
  name      = var.foundry_deployment_name
  parent_id = azapi_resource.foundry.id

  depends_on = [azapi_resource.foundry]

  body = {
    sku = {
      name     = var.foundry_model_sku
      capacity = var.foundry_model_capacity
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = var.foundry_model_name
        version = var.foundry_model_version
      }
      versionUpgradeOption = "NoAutoUpgrade"
    }
  }
}

# ---------------------------------------------------------------------------
# 3. AI Foundry project
#    Agents are created within a project — each project is an isolated workspace
# ---------------------------------------------------------------------------
resource "azapi_resource" "foundry_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = local.foundry_project
  parent_id = azapi_resource.foundry.id
  location  = data.azurerm_resource_group.rg.location

  depends_on = [azapi_resource.foundry_gpt4o]

  schema_validation_enabled = false

  body = {
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned"
    }
    properties = {
      displayName = "Meeting Analyzer"
      description = "AI Foundry project for the Meeting Analyzer bot agents"
    }
  }

  # Export the project endpoints map from the API response
  response_export_values = ["properties.endpoints", "properties.projectId"]
}

# ---------------------------------------------------------------------------
# 4. RBAC — grant the bot Container App managed identity the Azure AI User
#    role on the Foundry account so it can create threads, runs, and messages
# ---------------------------------------------------------------------------
resource "azurerm_role_assignment" "bot_foundry_user" {
  scope                = azapi_resource.foundry.id
  role_definition_name = "Azure AI User"
  principal_id         = azurerm_container_app.bot.identity[0].principal_id

  depends_on = [azapi_resource.foundry_project]
}

# ---------------------------------------------------------------------------
# Locals — derive the project endpoint from the AzAPI response
#
# The endpoint is read directly from the API response rather than assembled
# by string concatenation, which avoids region-specific format differences.
#
# Format: https://<account>.services.ai.azure.com/api/projects/<project-name>
# ---------------------------------------------------------------------------
locals {
  foundry_account_endpoint = azapi_resource.foundry.output.properties.endpoint
  foundry_project_endpoint = "${trimsuffix(local.foundry_account_endpoint, "/")}/api/projects/${local.foundry_project}"
}
