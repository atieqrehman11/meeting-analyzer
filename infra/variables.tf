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

variable "environment_name" {
  type        = string
  default     = "meeting-analyzer"
  description = "Short name prefix used for resource naming."
}

variable "acr_sku" {
  type        = string
  default     = "Basic"
  description = "SKU for the Azure Container Registry."
}

variable "acr_image_tag" {
  type        = string
  default     = "latest"
  description = "Tag used by container app images in ACR."
}

variable "cosmos_database_name" {
  type        = string
  default     = "meeting-analysis"
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
