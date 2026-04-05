variable "mcp_backend_mode" {
  type        = string
  default     = "mock"
  description = "MCP backend mode: 'mock' skips Storage and Cosmos DB provisioning, 'azure' creates them."

  validation {
    condition     = contains(["mock", "azure"], var.mcp_backend_mode)
    error_message = "mcp_backend_mode must be 'mock' or 'azure'."
  }
}

variable "resource_group_name" {
  type        = string
  description = "The existing Azure resource group name provided by IT."
}

variable "workload_name" {
  type        = string
  default     = "meetingassist"
  description = "Workload identifier used in all resource names. Lowercase alphanumeric, no dashes."

  validation {
    condition     = can(regex("^[a-z0-9]+$", var.workload_name))
    error_message = "workload_name must be lowercase alphanumeric only (no dashes — used in Storage/ACR names)."
  }
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "Deployment environment: dev, staging, or prod."

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "azure_region" {
  type        = string
  default     = "eastus"
  description = "Short Azure region name used in resource names (e.g. eastus, westeurope)."
}

variable "acr_sku" {
  type        = string
  default     = "Basic"
  description = "SKU for the Azure Container Registry."
}

variable "deploy_apps" {
  type        = bool
  default     = false
  description = "Set to true to deploy Container Apps. Must be false on first apply (before images are pushed to ACR)."
}

variable "acr_image_tag" {
  type        = string
  default     = "latest"
  description = "Tag used by container app images in ACR."
}

variable "cosmos_database_name" {
  type        = string
  default     = "meeting-assistant"
  description = "Cosmos DB SQL database name used by the MCP server."
}

variable "mcp_log_level" {
  type    = string
  default = "INFO"
}

variable "bot_log_level" {
  type    = string
  default = "INFO"
}

variable "graph_tenant_id" {
  type        = string
  default     = ""
  description = "Azure AD tenant ID used by Microsoft Graph integration."
}

variable "graph_client_id" {
  type        = string
  default     = ""
  description = "Azure AD client ID used by Microsoft Graph integration."
}

variable "graph_client_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Azure AD client secret for Graph API app-only auth (proactive meeting join)."
}

variable "bot_webhook_secret" {
  type        = string
  default     = "change-me-in-production"
  sensitive   = true
  description = "Shared secret sent with every Graph notification to validate authenticity."
}

variable "bot_service_sku" {
  type        = string
  default     = "F0"
  description = "Azure Bot Service SKU. F0 = free (dev/test), S1 = standard (production)."

  validation {
    condition     = contains(["F0", "S1"], var.bot_service_sku)
    error_message = "bot_service_sku must be 'F0' or 'S1'."
  }
}

variable "bot_secret_expiry_years" {
  type        = number
  default     = 1
  description = "Validity period in years for the bot client secret."
}

# ---------------------------------------------------------------------------
# Azure AI Foundry
# ---------------------------------------------------------------------------

variable "foundry_model_name" {
  type        = string
  default     = "gpt-4o"
  description = "Azure OpenAI model name to deploy (e.g. gpt-4o, gpt-4o-mini, gpt-4.1)."
}

variable "foundry_deployment_name" {
  type        = string
  default     = "gpt-4o-meeting-bot"
  description = "Deployment name in Foundry. Must match the 'model' field in agents/definitions/*.yaml."

  validation {
    condition     = length(var.foundry_deployment_name) > 0
    error_message = "foundry_deployment_name cannot be empty. It must match the 'model' field in agents/definitions/*.yaml."
  }
}

variable "foundry_model_version" {
  type        = string
  default     = "2024-11-20"
  description = "Model version to deploy. Check Azure OpenAI model availability for your region."
}

variable "foundry_model_sku" {
  type        = string
  default     = "GlobalStandard"
  description = "Deployment SKU: Standard (single region) or GlobalStandard (routes across regions, better availability)."

  validation {
    condition     = contains(["Standard", "GlobalStandard"], var.foundry_model_sku)
    error_message = "foundry_model_sku must be 'Standard' or 'GlobalStandard'."
  }
}

variable "foundry_model_capacity" {
  type        = number
  default     = 10
  description = "Token-per-minute capacity in thousands (e.g. 10 = 10K TPM). Increase for production."
}
