#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Meeting Assistant — Admin Setup Script
#
# Run this script as an Azure administrator to complete the post-deployment
# steps that require elevated permissions.
#
# Prerequisites:
#   - Azure CLI installed and authenticated (az login)
#   - Global Administrator or Privileged Role Administrator (for Graph consent)
#   - Owner or Role Based Access Control Administrator on the resource group
#
# Usage:
#   ./admin-setup.sh                        # interactive — prompts for values
#   ./admin-setup.sh --resource-group <rg>  # skip prompt for RG
#
# Or set env vars to skip all prompts:
#   RESOURCE_GROUP=rg-meeting-assistant-dev-eastus \
#   BOT_APP_ID=<app-id> \
#   ./admin-setup.sh
# =============================================================================

echo ""
echo "========================================"
echo " Meeting Assistant — Admin Setup"
echo "========================================"
echo ""

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
RESOURCE_GROUP="${RESOURCE_GROUP:-}"
BOT_APP_ID="${BOT_APP_ID:-}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --resource-group|-g) RESOURCE_GROUP="$2"; shift 2 ;;
        --bot-app-id)        BOT_APP_ID="$2";       shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Verify Azure CLI is authenticated
# ---------------------------------------------------------------------------
echo ">>> Checking Azure CLI authentication..."
SUBSCRIPTION=$(az account show --query id -o tsv 2>/dev/null) || {
    echo "ERROR: Not authenticated. Run: az login"
    exit 1
}
TENANT=$(az account show --query tenantId -o tsv)
echo "    Subscription : $SUBSCRIPTION"
echo "    Tenant       : $TENANT"
echo ""

# ---------------------------------------------------------------------------
# Collect required values
# ---------------------------------------------------------------------------
# Auto-populate from Terraform outputs if available and not already set
if [ -z "$RESOURCE_GROUP" ] && [ -f "infra/terraform.tfvars" ]; then
    RESOURCE_GROUP=$(terraform -chdir=infra output -raw resource_group_name 2>/dev/null || true)
fi
if [ -z "$BOT_APP_ID" ] && [ -f "infra/terraform.tfvars" ]; then
    BOT_APP_ID=$(terraform -chdir=infra output -raw bot_app_id 2>/dev/null || true)
fi

# Fall back to prompts only if still empty
if [ -z "$RESOURCE_GROUP" ]; then
    read -r -p "Resource group name: " RESOURCE_GROUP
fi

if [ -z "$BOT_APP_ID" ]; then
    read -r -p "Bot App ID (Azure AD application client ID): " BOT_APP_ID
fi

SCOPE_RG="/subscriptions/${SUBSCRIPTION}/resourceGroups/${RESOURCE_GROUP}"

echo ""
echo "Resource group : $RESOURCE_GROUP"
echo "Bot App ID     : $BOT_APP_ID"
echo ""

# ---------------------------------------------------------------------------
# Resolve managed identity principal IDs
# ---------------------------------------------------------------------------
echo ">>> Resolving Container App managed identities..."

# Try Terraform outputs first, fall back to name-pattern discovery
MCP_APP=$(terraform -chdir=infra output -raw mcp_app_name 2>/dev/null || \
    az containerapp list -g "$RESOURCE_GROUP" \
        --query "[?contains(name, 'mcp')].name | [0]" -o tsv 2>/dev/null || true)
BOT_APP=$(terraform -chdir=infra output -raw bot_app_name 2>/dev/null || \
    az containerapp list -g "$RESOURCE_GROUP" \
        --query "[?contains(name, 'bot')].name | [0]" -o tsv 2>/dev/null || true)

if [ -z "$MCP_APP" ] || [ -z "$BOT_APP" ]; then
    echo "ERROR: Could not find Container Apps in resource group '$RESOURCE_GROUP'."
    echo "  Ensure the deployment has been run first (./deploy.sh infra + ./deploy.sh docker)."
    exit 1
fi

MCP_PRINCIPAL=$(az containerapp show --name "$MCP_APP" --resource-group "$RESOURCE_GROUP" \
    --query identity.principalId -o tsv)
BOT_PRINCIPAL=$(az containerapp show --name "$BOT_APP" --resource-group "$RESOURCE_GROUP" \
    --query identity.principalId -o tsv)

echo "    MCP app      : $MCP_APP  (principal: $MCP_PRINCIPAL)"
echo "    Bot app      : $BOT_APP  (principal: $BOT_PRINCIPAL)"
echo ""

# ---------------------------------------------------------------------------
# Step A — Azure RBAC role assignments
# ---------------------------------------------------------------------------
echo "========================================"
echo " Step A — RBAC Role Assignments"
echo "========================================"
echo ""

assign_role() {
    local assignee="$1" role="$2" scope="$3" label="$4"
    echo ">>> $label"
    az role assignment create \
        --assignee "$assignee" \
        --role "$role" \
        --scope "$scope" \
        2>/dev/null && echo "    Assigned." || echo "    Already assigned — skipping."
}

# Storage (only if a storage account exists in the RG)
STORAGE=$(az storage account list -g "$RESOURCE_GROUP" \
    --query "[0].name" -o tsv 2>/dev/null || true)
if [ -n "$STORAGE" ]; then
    assign_role "$MCP_PRINCIPAL" \
        "Storage Blob Data Contributor" \
        "${SCOPE_RG}/providers/Microsoft.Storage/storageAccounts/${STORAGE}" \
        "Storage Blob Data Contributor → MCP identity"
fi

# Cosmos DB (only if a Cosmos account exists in the RG)
COSMOS=$(az cosmosdb list -g "$RESOURCE_GROUP" \
    --query "[0].name" -o tsv 2>/dev/null || true)
if [ -n "$COSMOS" ]; then
    assign_role "$MCP_PRINCIPAL" \
        "Cosmos DB Built-in Data Contributor" \
        "${SCOPE_RG}/providers/Microsoft.DocumentDB/databaseAccounts/${COSMOS}" \
        "Cosmos DB Built-in Data Contributor → MCP identity"
fi

# Azure AI Developer on the resource group (bot needs this for Foundry)
assign_role "$BOT_PRINCIPAL" \
    "Azure AI Developer" \
    "$SCOPE_RG" \
    "Azure AI Developer → Bot identity"

# Azure AI User on the Foundry account (required for Agent Service threads/runs)
FOUNDRY=$(az cognitiveservices account list -g "$RESOURCE_GROUP" \
    --query "[?kind=='AIServices'].name | [0]" -o tsv 2>/dev/null || true)
if [ -n "$FOUNDRY" ]; then
    assign_role "$BOT_PRINCIPAL" \
        "Azure AI User" \
        "${SCOPE_RG}/providers/Microsoft.CognitiveServices/accounts/${FOUNDRY}" \
        "Azure AI User → Bot identity (Foundry Agent Service)"
fi

echo ""
echo "RBAC assignments complete."
echo ""

# ---------------------------------------------------------------------------
# Step B — Graph API admin consent
# ---------------------------------------------------------------------------
echo "========================================"
echo " Step B — Graph API Admin Consent"
echo "========================================"
echo ""
echo "Permissions to consent:"
echo "  - Calendars.Read              (read calendar events)"
echo "  - OnlineMeetings.Read.All     (read meeting details)"
echo "  - OnlineMeetings.ReadWrite.All (proactive bot join)"
echo ""
echo "Required role: Global Administrator or Privileged Role Administrator"
echo ""

read -r -p "Grant admin consent now? [y/N] " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    echo ">>> Granting admin consent for app: $BOT_APP_ID"
    az ad app permission admin-consent --id "$BOT_APP_ID"
    echo ""
    echo "Verifying..."
    az ad app permission list-grants --id "$BOT_APP_ID" \
        --query "[].{scope:scope, consentType:consentType}" -o table 2>/dev/null || true
    echo ""
    echo "Graph admin consent complete."
    echo "Note: permissions may take a few minutes to propagate."
else
    echo ""
    echo "Skipped. To grant consent manually:"
    echo ""
    echo "  Option 1 — CLI:"
    echo "    az ad app permission admin-consent --id $BOT_APP_ID"
    echo ""
    echo "  Option 2 — Portal:"
    echo "    https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/CallAnAPI/appId/$BOT_APP_ID"
    echo "    Click 'Grant admin consent for <tenant>'"
fi

echo ""
echo "========================================"
echo " Admin setup complete."
echo ""
echo "Next steps (run by the developer):"
echo "  ./deploy.sh agents    — register AI Foundry agents"
echo "  ./deploy.sh check-mcp — verify MCP server is reachable"
echo "  See docs/teams-app-registration.md to upload the Teams manifest"
echo "========================================"
echo ""
