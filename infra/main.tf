data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 3
  lower   = true
  upper   = false
  numeric = true
  special = false
}

resource "random_password" "webhook_secret" {
  length  = 32
  special = false
}

locals {
  # ---------------------------------------------------------------------------
  # Naming convention — Azure CAF prefix pattern
  #
  # Pattern (dash-allowed resources):  {type}-{workload}-{env}-{region}
  # Pattern (no-dash resources):       {type}{workload}{env}{instance}
  #
  # workload = "meetingassist" (fixed — derived from var.workload_name)
  # env      = var.environment  e.g. "dev", "prod"
  # region   = var.azure_region e.g. "eastus"
  # instance = 3-char random suffix for globally unique names
  # ---------------------------------------------------------------------------
  workload = var.workload_name                          # "meetingassist"
  env      = var.environment                            # "dev" | "prod"
  region   = var.azure_region                          # "eastus"
  sfx      = random_string.suffix.result               # e.g. "a3k"

  # Base segment used in dash-allowed names
  base = "${local.workload}-${local.env}-${local.region}"

  # Slug — no dashes, for Storage / ACR / Foundry subdomain
  slug = "${local.workload}${local.env}${local.sfx}"

  # Resource names
  log_analytics_name     = "log-${local.base}"
  container_app_env_name = "cae-${local.base}"
  acr_name               = "cr${local.slug}"            # no dashes, alphanumeric only
  storage_account_name   = "st${local.slug}"            # no dashes, max 24 chars
  cosmos_account_name    = "cosmos-${local.base}-${local.sfx}"
  mcp_app_name           = "ca-${local.workload}-mcp-${local.env}-${local.region}"
  bot_app_name           = "ca-${local.workload}-bot-${local.env}-${local.region}"

  azure_backend         = var.mcp_backend_mode == "azure"
  storage_blob_endpoint = local.azure_backend ? azurerm_storage_account.storage[0].primary_blob_endpoint : ""
  cosmos_endpoint       = local.azure_backend ? azurerm_cosmosdb_account.cosmos[0].endpoint : ""
}

resource "azurerm_log_analytics_workspace" "logs" {
  name                = local.log_analytics_name
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
  storage_account_id    = azurerm_storage_account.storage[0].id
  container_access_type = "private"
}

resource "azurerm_storage_container" "reports" {
  count                 = local.azure_backend ? 1 : 0
  name                  = "reports"
  storage_account_id    = azurerm_storage_account.storage[0].id
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
    zone_redundant    = false
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
