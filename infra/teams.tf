# ---------------------------------------------------------------------------
# Teams Bot — Azure AD app registration + Azure Bot Service
#
# This file is OPTIONAL. Only apply it if you want Terraform to manage the
# bot's Azure AD identity and Bot Channels Registration.
#
# Prerequisites:
#   - The caller must have Azure AD permissions to create app registrations
#     (Application Administrator or equivalent).
#   - The main stack (main.tf) must have been applied first so that
#     bot_base_url is available via the azurerm_container_app.bot resource.
#
# What this creates:
#   1. Azure AD application registration for the bot
#   2. A client secret (rotatable via var.bot_secret_expiry_years)
#   3. Azure Bot Service resource wired to the Container App messaging endpoint
#   4. Teams channel enabled on the bot service
# ---------------------------------------------------------------------------

locals {
  bot_messaging_endpoint = var.deploy_apps ? "https://${azurerm_container_app.bot[0].ingress[0].fqdn}/api/messages" : "https://placeholder-update-after-deploy/api/messages"
}

# 1. Azure AD app registration
# sign_in_audience = AzureADMultipleOrgs allows users from any tenant's Teams
# to interact with the bot. The Bot Service itself stays SingleTenant (required
# by Azure — multitenant Bot Service creation is deprecated).
resource "azuread_application" "bot" {
  display_name     = "app-${local.workload}-bot-${local.env}"
  sign_in_audience = "AzureADMyOrg"

  web {
    redirect_uris = ["https://token.botframework.com/.auth/web/redirect"]
  }

  # ---------------------------------------------------------------------------
  # Microsoft Graph application permissions — required for proactive meeting join
  #
  # Resource app ID for Microsoft Graph is always 00000003-0000-0000-c000-000000000000
  #
  # Permission IDs (application type — no user sign-in required):
  #   Calendars.Read            = 798ee544-9d2d-430c-a058-570e29e34338
  #   OnlineMeetings.Read.All   = c1684f21-1984-47fa-9d61-2dc8c296bb70
  #   OnlineMeetings.ReadWrite.All = a7a681dc-756e-4909-b988-f160edc6655f
  # ---------------------------------------------------------------------------
  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000" # Microsoft Graph

    resource_access {
      id   = "798ee544-9d2d-430c-a058-570e29e34338" # Calendars.Read
      type = "Role"
    }
    resource_access {
      id   = "c1684f21-1984-47fa-9d61-2dc8c296bb70" # OnlineMeetings.Read.All
      type = "Role"
    }
    resource_access {
      id   = "a7a681dc-756e-4909-b988-f160edc6655f" # OnlineMeetings.ReadWrite.All
      type = "Role"
    }
  }
}

# 2. Service principal for the app
resource "azuread_service_principal" "bot" {
  client_id = azuread_application.bot.client_id
}

# 3. Client secret
resource "azuread_application_password" "bot" {
  application_id = azuread_application.bot.id
  display_name   = "bot-secret"
  end_date       = timeadd(timestamp(), "${var.bot_secret_expiry_years * 8760}h")

  lifecycle {
    ignore_changes = [end_date]
    replace_triggered_by = [azuread_application.bot]
    # If destroy fails with 404 (app deleted out-of-band), remove from state manually:
    #   terraform -chdir=infra state rm azuread_application_password.bot
    #   terraform -chdir=infra state rm azuread_application.bot
    #   terraform -chdir=infra state rm azuread_service_principal.bot
  }
}

# 4. Azure Bot Service — SingleTenant (multitenant is deprecated)
resource "azurerm_bot_service_azure_bot" "bot" {
  name                = "bot-${local.base}-${local.sfx}"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = "global"
  microsoft_app_id    = azuread_application.bot.client_id
  microsoft_app_type  = "SingleTenant"
  microsoft_app_tenant_id = data.azurerm_client_config.current.tenant_id
  sku                 = var.bot_service_sku
  endpoint            = local.bot_messaging_endpoint

  tags = {
    workload    = var.workload_name
    environment = var.environment
    region      = var.azure_region
  }

  lifecycle {
    ignore_changes = []
  }
}

# 5. Teams channel
resource "azurerm_bot_channel_ms_teams" "teams" {
  bot_name            = azurerm_bot_service_azure_bot.bot.name
  location            = azurerm_bot_service_azure_bot.bot.location
  resource_group_name = data.azurerm_resource_group.rg.name
}
