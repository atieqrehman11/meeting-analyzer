output "container_registry_login_server" {
  description = "The login server for the Azure Container Registry."
  value       = azurerm_container_registry.acr.login_server
}

output "resource_group_name" {
  description = "The resource group all resources were deployed into."
  value       = data.azurerm_resource_group.rg.name
}

output "mcp_app_name" {
  description = "The name of the MCP Container App. Empty before deploy_apps=true."
  value       = length(azurerm_container_app.mcp) > 0 ? azurerm_container_app.mcp[0].name : ""
}

output "bot_app_name" {
  description = "The name of the Bot Container App. Empty before deploy_apps=true."
  value       = length(azurerm_container_app.bot) > 0 ? azurerm_container_app.bot[0].name : ""
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
  description = "The external URL for the MCP Container App. Empty before deploy_apps=true."
  value       = length(azurerm_container_app.mcp) > 0 ? "https://${azurerm_container_app.mcp[0].ingress[0].fqdn}" : ""
}

output "bot_base_url" {
  description = "The external URL for the Teams Bot Container App. Empty before deploy_apps=true."
  value       = length(azurerm_container_app.bot) > 0 ? "https://${azurerm_container_app.bot[0].ingress[0].fqdn}" : ""
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
  description = "The messaging endpoint registered with Azure Bot Service. Empty before deploy_apps=true."
  value       = var.deploy_apps ? "https://${azurerm_container_app.bot[0].latest_revision_fqdn}/api/messages" : ""
}

output "foundry_account_endpoint" {
  description = "The Azure AI Services (Foundry) account endpoint."
  value       = local.foundry_account_endpoint
}

output "azure_ai_project_endpoint" {
  description = "The Azure AI Foundry project endpoint — used by the orchestrator and deploy:agents."
  value       = local.foundry_project_endpoint
}

output "foundry_deployment_name" {
  description = "The GPT-4o model deployment name used by all agents."
  value       = azapi_resource.foundry_gpt4o.name
}
