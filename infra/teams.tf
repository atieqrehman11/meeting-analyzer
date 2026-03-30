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
  bot_messaging_endpoint = "https://${azurerm_container_app.bot.latest_revision_fqdn}/api/messages"
}

# 1. Azure AD app registration
resource "azuread_application" "bot" {
  display_name = "${local.normalized_name}-bot"

  web {
    redirect_uris = ["https://token.botframework.com/.auth/web/redirect"]
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
    # Prevent replacement on every apply due to timestamp() being re-evaluated.
    # Rotate manually by tainting this resource.
    ignore_changes = [end_date]
  }
}

# 4. Azure Bot Service (Bot Channels Registration)
resource "azurerm_bot_service_azure_bot" "bot" {
  name                = "${local.normalized_name}-bot-svc"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = "global" # Bot Service is always global
  microsoft_app_id    = azuread_application.bot.client_id
  sku                 = var.bot_service_sku
  endpoint            = local.bot_messaging_endpoint

  tags = {
    environment = var.environment_name
  }
}

# 5. Teams channel
resource "azurerm_bot_channel_ms_teams" "teams" {
  bot_name            = azurerm_bot_service_azure_bot.bot.name
  location            = azurerm_bot_service_azure_bot.bot.location
  resource_group_name = data.azurerm_resource_group.rg.name
}
