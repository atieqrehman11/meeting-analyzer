output "container_registry_login_server" {
  description = "The login server for the Azure Container Registry."
  value       = azurerm_container_registry.acr.login_server
}

output "storage_account_name" {
  description = "The deployed Azure Storage account name. Empty when mcp_backend_mode is 'mock'."
  value       = length(azurerm_storage_account.storage) > 0 ? azurerm_storage_account.storage[0].name : ""
}

output "storage_blob_endpoint" {
  description = "The primary blob endpoint for the Azure Storage account. Empty when mcp_backend_mode is 'mock'."
  value       = length(azurerm_storage_account.storage) > 0 ? azurerm_storage_account.storage[0].primary_blob_endpoint : ""
}

output "cosmosdb_endpoint" {
  description = "The Cosmos DB endpoint URL. Empty when mcp_backend_mode is 'mock'."
  value       = length(azurerm_cosmosdb_account.cosmos) > 0 ? azurerm_cosmosdb_account.cosmos[0].endpoint : ""
}

output "mcp_server_url" {
  description = "The external URL for the MCP Container App."
  value       = "https://${azurerm_container_app.mcp.latest_revision_fqdn}"
}

output "bot_base_url" {
  description = "The external URL for the Teams Bot Container App."
  value       = "https://${azurerm_container_app.bot.latest_revision_fqdn}"
}

output "bot_app_id" {
  description = "Azure AD application (client) ID for the Teams bot."
  value       = azuread_application.bot.client_id
}

output "bot_app_password" {
  description = "Generated client secret for the Teams bot. Use this as BOT_APP_PASSWORD."
  value       = azuread_application_password.bot.value
  sensitive   = true
}

output "bot_messaging_endpoint" {
  description = "The messaging endpoint registered with Azure Bot Service."
  value       = local.bot_messaging_endpoint
}
