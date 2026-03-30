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

variable "azure_ai_project_endpoint" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Azure AI Foundry project endpoint used by the orchestrator."
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
