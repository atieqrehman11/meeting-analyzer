# ---------------------------------------------------------------------------
# Container Apps — MCP server and Teams bot
#
# Controlled by var.deploy_apps (default: false).
# Set deploy_apps = true only after images have been pushed to ACR.
#
# deploy.sh handles this automatically:
#   ./deploy.sh infra    → apply with deploy_apps=false (skips Container Apps)
#   ./deploy.sh docker   → push images, then apply with deploy_apps=true
# ---------------------------------------------------------------------------

resource "azurerm_container_app" "mcp" {
  count                        = var.deploy_apps ? 1 : 0
  name                         = local.mcp_app_name
  resource_group_name          = data.azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.container_apps_env.id
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }
  secret {
    name  = "mcp-graph-client-secret"
    value = azuread_application_password.bot.value
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "mcp"
      image  = "${azurerm_container_registry.acr.login_server}/meeting-analyzer-mcp:${var.acr_image_tag}"
      cpu    = 0.5
      memory = "1.0Gi"

      env {
        name  = "MCP_BACKEND_MODE"
        value = var.mcp_backend_mode
      }
      env {
        name  = "MCP_LOG_LEVEL"
        value = var.mcp_log_level
      }
      env {
        name  = "MCP_AZURE_STORAGE_ACCOUNT_URL"
        value = local.storage_blob_endpoint
      }
      env {
        name  = "MCP_COSMOS_ENDPOINT"
        value = local.cosmos_endpoint
      }
      env {
        name  = "MCP_AZURE_REGION"
        value = data.azurerm_resource_group.rg.location
      }
      env {
        name  = "MCP_COSMOS_DATABASE"
        value = var.cosmos_database_name
      }
      env {
        name  = "MCP_GRAPH_TENANT_ID"
        value = data.azurerm_client_config.current.tenant_id
      }
      env {
        name  = "MCP_GRAPH_CLIENT_ID"
        value = azuread_application.bot.client_id
      }
      env {
        name        = "MCP_GRAPH_CLIENT_SECRET"
        secret_name = "mcp-graph-client-secret"
      }
    }
  }
}

resource "azurerm_container_app" "bot" {
  count                        = var.deploy_apps ? 1 : 0
  name                         = local.bot_app_name
  resource_group_name          = data.azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.container_apps_env.id
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled = true
    target_port      = 3978
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }
  secret {
    name  = "bot-app-password"
    value = azuread_application_password.bot.value
  }
  secret {
    name  = "bot-graph-client-secret"
    value = azuread_application_password.bot.value
  }
  secret {
    name  = "bot-webhook-secret"
    value = random_password.webhook_secret.result
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "bot"
      image  = "${azurerm_container_registry.acr.login_server}/meeting-analyzer-bot:${var.acr_image_tag}"
      cpu    = 0.5
      memory = "1.0Gi"

      env {
        name  = "BOT_APP_ID"
        value = azuread_application.bot.client_id
      }
      env {
        name  = "BOT_MCP_SERVER_URL"
        value = "https://${azurerm_container_app.mcp[0].ingress[0].fqdn}"
      }
      env {
        name  = "BOT_LOG_LEVEL"
        value = var.bot_log_level
      }
      env {
        name  = "ORCH_AZURE_AI_PROJECT_ENDPOINT"
        value = local.foundry_project_endpoint
      }
      env {
        name  = "ORCH_MCP_SERVER_URL"
        value = "https://${azurerm_container_app.mcp[0].ingress[0].fqdn}"
      }
      env {
        name  = "BOT_GRAPH_TENANT_ID"
        value = data.azurerm_client_config.current.tenant_id
      }
      env {
        name  = "BOT_WEBHOOK_BASE_URL"
        value = var.bot_webhook_base_url
      }
      env {
        name  = "BOT_GRAPH_CLIENT_ID"
        value = azuread_application.bot.client_id
      }
      env {
        name        = "BOT_APP_PASSWORD"
        secret_name = "bot-app-password"
      }
      env {
        name        = "BOT_GRAPH_CLIENT_SECRET"
        secret_name = "bot-graph-client-secret"
      }
      env {
        name        = "BOT_WEBHOOK_SECRET"
        secret_name = "bot-webhook-secret"
      }
    }
  }
}
