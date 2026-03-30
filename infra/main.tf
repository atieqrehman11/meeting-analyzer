data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  normalized_name        = substr(replace(lower(var.environment_name), "-", ""), 0, 10)
  name_suffix            = random_string.suffix.result
  storage_account_name   = "${local.normalized_name}st${local.name_suffix}"
  cosmos_account_name    = "${local.normalized_name}cos${local.name_suffix}"
  acr_name               = "${local.normalized_name}acr${local.name_suffix}"
  container_app_env_name = "${local.normalized_name}-env"
  mcp_app_name           = "${local.normalized_name}-mcp"
  bot_app_name           = "${local.normalized_name}-bot"

  azure_backend         = var.mcp_backend_mode == "azure"
  storage_blob_endpoint = local.azure_backend ? azurerm_storage_account.storage[0].primary_blob_endpoint : ""
  cosmos_endpoint       = local.azure_backend ? azurerm_cosmosdb_account.cosmos[0].endpoint : ""
}

resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${local.normalized_name}-law"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "container_apps_env" {
  name                = local.container_app_env_name
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name

  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id
}

resource "azurerm_container_registry" "acr" {
  name                = local.acr_name
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  sku                 = var.acr_sku
  admin_enabled       = true
}

resource "azurerm_storage_account" "storage" {
  count                    = local.azure_backend ? 1 : 0
  name                     = local.storage_account_name
  resource_group_name      = data.azurerm_resource_group.rg.name
  location                 = data.azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  access_tier              = "Hot"
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_container" "transcripts" {
  count                 = local.azure_backend ? 1 : 0
  name                  = "transcripts"
  storage_account_name  = azurerm_storage_account.storage[0].name
  container_access_type = "private"
}

resource "azurerm_storage_container" "reports" {
  count                 = local.azure_backend ? 1 : 0
  name                  = "reports"
  storage_account_name  = azurerm_storage_account.storage[0].name
  container_access_type = "private"
}

resource "azurerm_cosmosdb_account" "cosmos" {
  count                         = local.azure_backend ? 1 : 0
  name                          = local.cosmos_account_name
  location                      = data.azurerm_resource_group.rg.location
  resource_group_name           = data.azurerm_resource_group.rg.name
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  public_network_access_enabled = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = data.azurerm_resource_group.rg.location
    failover_priority = 0
  }

  capabilities {
    name = "EnableServerless"
  }
}

resource "azurerm_cosmosdb_sql_database" "database" {
  count               = local.azure_backend ? 1 : 0
  name                = var.cosmos_database_name
  resource_group_name = data.azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos[0].name
}

resource "azurerm_cosmosdb_sql_container" "meeting_data" {
  count                 = local.azure_backend ? 1 : 0
  name                  = "meeting-data"
  resource_group_name   = data.azurerm_resource_group.rg.name
  account_name          = azurerm_cosmosdb_account.cosmos[0].name
  database_name         = azurerm_cosmosdb_sql_database.database[0].name
  partition_key_paths   = ["/meeting_id"]
  partition_key_version = 2
}

resource "azurerm_container_app" "mcp" {
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

  template {
    revision_suffix = "v1"
    min_replicas    = 1
    max_replicas    = 2

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
        value = var.graph_tenant_id
      }
      env {
        name  = "MCP_GRAPH_CLIENT_ID"
        value = var.graph_client_id
      }
    }
  }
}

resource "azurerm_container_app" "bot" {
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

  template {
    revision_suffix = "v1"
    min_replicas    = 1
    max_replicas    = 2

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
        value = "https://${azurerm_container_app.mcp.latest_revision_fqdn}"
      }
      env {
        name  = "BOT_LOG_LEVEL"
        value = var.bot_log_level
      }
      env {
        name  = "ORCH_AZURE_AI_PROJECT_ENDPOINT"
        value = var.azure_ai_project_endpoint
      }
      env {
        name  = "ORCH_MCP_SERVER_URL"
        value = "https://${azurerm_container_app.mcp.latest_revision_fqdn}"
      }
      env {
        name        = "BOT_APP_PASSWORD"
        secret_name = "bot-app-password"
      }
    }
  }
}
