#!/usr/bin/env bash
set -euo pipefail

# Meeting Analyzer — Azure deployment script
# Usage: ./deploy.sh <command> [options]
#
# Commands:
#   all             Run full deployment end-to-end (steps 1-5)
#   infra           terraform init + apply
#   docker          Build + push Docker images to ACR
#   rbac            Assign RBAC roles to Container App managed identities
#   check-mcp       Verify MCP server is reachable
#   agents          Register/update agents in Azure AI Foundry
#   help            Show this message

cd "$(dirname "$0")"
REPO_ROOT="$(pwd)"
VENV_DIR="$REPO_ROOT/.venv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

activate_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
    fi
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
}

tf_output() {
    terraform -chdir=infra output -raw "$1" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_infra() {
    if [ ! -f "infra/terraform.tfvars" ]; then
        echo "ERROR: infra/terraform.tfvars not found."
        echo "  cp infra/terraform.tfvars.example infra/terraform.tfvars"
        echo "Then fill in your values."
        exit 1
    fi
    echo ">>> terraform init"
    terraform -chdir=infra init
    echo ""
    echo ">>> terraform apply (base infra — Container Apps skipped until images are pushed)"
    terraform -chdir=infra apply -var-file=terraform.tfvars -var="deploy_apps=false"
    echo ""
    echo "Base infra ready. Next: ./deploy.sh docker"
}

cmd_infra_apps() {
    # Deploy Container Apps — run after images are pushed to ACR
    echo ">>> terraform apply (Container Apps — deploy_apps=true)"
    terraform -chdir=infra apply -var-file=terraform.tfvars -var="deploy_apps=true"

    # Set BOT_WEBHOOK_BASE_URL now that the FQDN is known
    local bot_url rg bot_app
    bot_url=$(tf_output bot_base_url)
    rg=$(tf_output resource_group_name)
    bot_app=$(tf_output bot_app_name)

    if [ -n "$bot_url" ] && [ -n "$bot_app" ]; then
        echo ""
        echo ">>> Setting BOT_WEBHOOK_BASE_URL=${bot_url}"
        az containerapp update \
            --name "$bot_app" \
            --resource-group "$rg" \
            --set-env-vars "BOT_WEBHOOK_BASE_URL=${bot_url}"
    fi
}

cmd_docker() {
    local tag="${1:-${DOCKER_TAG:-latest}}"
    local acr="${ACR:-$(tf_output container_registry_login_server)}"

    if [ -z "$acr" ]; then
        echo "ERROR: Could not resolve ACR login server."
        echo "  Run infra first, or set ACR=<login-server> in your environment."
        exit 1
    fi

    echo ""
    echo ">>> Building and pushing images to ${acr} (tag: ${tag})"
    echo ""
    docker build --no-cache -f mcp/Dockerfile      -t "${acr}/meeting-analyzer-mcp:${tag}" .
    docker build --no-cache -f team_bot/Dockerfile -t "${acr}/meeting-analyzer-bot:${tag}" .

    az acr login --name "${acr%%.*}"
    docker push "${acr}/meeting-analyzer-mcp:${tag}"
    docker push "${acr}/meeting-analyzer-bot:${tag}"

    echo ""
    echo "Pushed:"
    echo "  ${acr}/meeting-analyzer-mcp:${tag}"
    echo "  ${acr}/meeting-analyzer-bot:${tag}"

    # Deploy Container Apps now that images exist in ACR
    echo ""
    echo ">>> Deploying Container Apps..."
    cmd_infra_apps
}

cmd_rbac() {
    local subscription rg mcp_app bot_app storage cosmos
    subscription=$(az account show --query id -o tsv)
    rg=$(tf_output resource_group_name)

    if [ -z "$rg" ]; then
        echo "ERROR: Could not read resource_group_name from Terraform outputs."
        echo "  Run './deploy.sh infra' first."
        exit 1
    fi

    mcp_app=$(tf_output mcp_app_name)
    bot_app=$(tf_output bot_app_name)
    storage=$(tf_output storage_account_name)
    cosmos=$(az cosmosdb list -g "$rg" --query "[0].name" -o tsv 2>/dev/null || true)

    echo ">>> Fetching managed identity principal IDs..."
    local mcp_principal bot_principal scope_rg
    mcp_principal=$(az containerapp show --name "$mcp_app" --resource-group "$rg" --query identity.principalId -o tsv)
    bot_principal=$(az containerapp show --name "$bot_app" --resource-group "$rg" --query identity.principalId -o tsv)
    scope_rg="/subscriptions/${subscription}/resourceGroups/${rg}"

    if [ -n "$storage" ]; then
        echo ">>> Storage Blob Data Contributor → MCP identity"
        az role assignment create \
            --assignee "$mcp_principal" \
            --role "Storage Blob Data Contributor" \
            --scope "${scope_rg}/providers/Microsoft.Storage/storageAccounts/${storage}"
    fi

    if [ -n "$cosmos" ]; then
        echo ">>> Cosmos DB Built-in Data Contributor → MCP identity"
        az role assignment create \
            --assignee "$mcp_principal" \
            --role "Cosmos DB Built-in Data Contributor" \
            --scope "${scope_rg}/providers/Microsoft.DocumentDB/databaseAccounts/${cosmos}"
    fi

    echo ">>> Azure AI Developer → Bot identity"
    az role assignment create \
        --assignee "$bot_principal" \
        --role "Azure AI Developer" \
        --scope "$scope_rg"

    # Azure AI User on the Foundry account — required for Agent Service
    # (threads, runs, messages). Terraform also sets this, but we assign
    # here too so it works if foundry.tf is applied separately.
    local foundry_account
    foundry_account=$(az cognitiveservices account list -g "$rg" --query "[?kind=='AIServices'].name | [0]" -o tsv 2>/dev/null || true)
    if [ -n "$foundry_account" ]; then
        echo ">>> Azure AI User → Bot identity (Foundry account)"
        az role assignment create \
            --assignee "$bot_principal" \
            --role "Azure AI User" \
            --scope "${scope_rg}/providers/Microsoft.CognitiveServices/accounts/${foundry_account}" \
            2>/dev/null || echo "    (already assigned — skipping)"
    fi

    echo ""
    echo "RBAC assignments complete."
}

cmd_graph_consent() {
    # Grant admin consent for the Graph API permissions declared in teams.tf.
    # Required permissions:
    #   Calendars.Read            — read calendar events to detect meeting start
    #   OnlineMeetings.Read.All   — read online meeting details from Graph
    #   OnlineMeetings.ReadWrite.All — join meetings proactively as the bot
    #
    # Admin consent requires a Global Administrator or Privileged Role Administrator.
    local app_id
    app_id=$(tf_output bot_app_id)

    if [ -z "$app_id" ]; then
        echo "ERROR: Could not read bot_app_id from Terraform outputs."
        echo "  Run './deploy.sh infra' first."
        exit 1
    fi

    echo ">>> Granting admin consent for Graph permissions on app: ${app_id}"
    az ad app permission admin-consent --id "$app_id"

    echo ""
    echo "Verifying granted permissions..."
    az ad app permission list-grants --id "$app_id" --query "[].{scope:scope, consentType:consentType}" -o table 2>/dev/null || true

    echo ""
    echo "Graph admin consent complete."
    echo "Note: permissions may take a few minutes to propagate."
}

cmd_destroy() {
    if [ ! -f "infra/terraform.tfvars" ]; then
        echo "ERROR: infra/terraform.tfvars not found."
        exit 1
    fi

    echo ""
    echo "WARNING: This will destroy all provisioned Azure resources."
    echo "The resource group itself will NOT be deleted."
    echo ""
    read -r -p "Type 'yes' to confirm: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi

    # Remove Azure AD resources from state first — they are sometimes deleted
    # out-of-band (e.g. via portal) which causes a 404 during destroy.
    # Removing from state is safe: it just tells Terraform to stop tracking them.
    echo ">>> Cleaning up Azure AD state entries to avoid 404 errors..."
    terraform -chdir=infra state rm azuread_application_password.bot 2>/dev/null || true
    terraform -chdir=infra state rm azuread_application.bot          2>/dev/null || true
    terraform -chdir=infra state rm azuread_service_principal.bot    2>/dev/null || true

    terraform -chdir=infra destroy -var-file=terraform.tfvars
}

cmd_check_mcp() {
    local url="${MCP_SERVER_URL:-$(tf_output mcp_server_url)}"
    if [ -z "$url" ]; then
        echo "ERROR: MCP_SERVER_URL not set and could not be read from Terraform outputs."
        exit 1
    fi
    export MCP_SERVER_URL="$url"
    echo ">>> Checking MCP server: ${url}"
    python3 deploy/register_mcp.py
}

cmd_agents() {
    local endpoint="${AZURE_AI_PROJECT_ENDPOINT:-$(tf_output azure_ai_project_endpoint)}"
    local mcp_url="${MCP_SERVER_URL:-$(tf_output mcp_server_url)}"

    if [ -z "$endpoint" ]; then
        echo "ERROR: Could not resolve AZURE_AI_PROJECT_ENDPOINT."
        echo "  Ensure infra has been applied (foundry.tf provisions this automatically)."
        exit 1
    fi

    export AZURE_AI_PROJECT_ENDPOINT="$endpoint"
    export MCP_SERVER_URL="$mcp_url"

    activate_venv
    pip install -q azure-ai-projects azure-ai-agents azure-identity pyyaml
    echo ">>> Registering agents (endpoint: ${endpoint})"
    python3 deploy/register_agents.py
}

cmd_all() {
    local tag="${1:-${DOCKER_TAG:-latest}}"

    echo ""
    echo "========================================"
    echo " Meeting Analyzer — Full Azure Deploy"
    echo "========================================"
    echo ""
    echo "NOTE: Steps 3 (rbac) and 4 (graph-consent) require elevated"
    echo "      Azure permissions. If you don't have them, run steps 1-2"
    echo "      and 5-6 yourself, then share the admin-checklist output"
    echo "      with your Azure administrator."
    echo ""

    echo "--- Step 1/6: Terraform ---"
    cmd_infra
    echo ""

    echo "--- Step 2/6: Build & Push Docker Images ---"
    cmd_docker "$tag"
    echo ""

    echo "--- Step 3/6: RBAC Assignments (requires Owner / RBAC Admin on RG) ---"
    cmd_rbac
    echo ""

    echo "--- Step 4/6: Graph Admin Consent (requires Global Administrator) ---"
    cmd_graph_consent
    echo ""

    echo "--- Step 5/6: Verify MCP Server ---"
    cmd_check_mcp
    echo ""

    echo "--- Step 6/6: Register AI Foundry Agents ---"
    cmd_agents
    echo ""

    echo "========================================"
    echo " Deployment complete."
    echo ""
    echo "  MCP server : $(tf_output mcp_server_url)"
    echo "  Bot URL    : $(tf_output bot_base_url)"
    echo "  Bot App ID : $(tf_output bot_app_id)"
    echo "========================================"
    echo ""
}

cmd_deploy_self() {
    # Steps you can run without elevated permissions (after admin completes their steps).
    local tag="${1:-${DOCKER_TAG:-latest}}"

    echo ""
    echo "========================================"
    echo " Meeting Analyzer — Self-Service Deploy"
    echo " (steps that do NOT require admin access)"
    echo "========================================"
    echo ""

    echo "--- Step 1/4: Terraform (infra only) ---"
    cmd_infra
    echo ""

    echo "--- Step 2/4: Build & Push Docker Images ---"
    cmd_docker "$tag"
    echo ""

    echo "--- Step 3/4: Verify MCP Server ---"
    cmd_check_mcp
    echo ""

    echo "--- Step 4/4: Register AI Foundry Agents ---"
    cmd_agents
    echo ""

    echo "========================================"
    echo " Self-service steps complete."
    echo ""
    echo "Remaining steps for your Azure administrator:"
    echo "  ./deploy.sh admin-checklist"
    echo "========================================"
    echo ""
}

cmd_admin_checklist() {
    # Print a ready-to-run checklist for the Azure administrator.
    # Values are read from Terraform outputs so the admin gets exact resource names.
    local subscription rg mcp_app bot_app app_id storage cosmos foundry_account scope_rg
    subscription=$(az account show --query id -o tsv 2>/dev/null || echo "<subscription-id>")
    rg=$(tf_output resource_group_name)
    mcp_app=$(tf_output mcp_app_name)
    bot_app=$(tf_output bot_app_name)
    app_id=$(tf_output bot_app_id)
    storage=$(tf_output storage_account_name)
    cosmos=$(az cosmosdb list -g "$rg" --query "[0].name" -o tsv 2>/dev/null || true)
    foundry_account=$(az cognitiveservices account list -g "$rg" --query "[?kind=='AIServices'].name | [0]" -o tsv 2>/dev/null || true)
    scope_rg="/subscriptions/${subscription}/resourceGroups/${rg}"

    echo ""
    echo "========================================"
    echo " Admin Checklist — Meeting Analyzer"
    echo "========================================"
    echo ""
    echo "The following steps require elevated Azure permissions."
    echo "Please run these commands or ask your Azure administrator."
    echo ""
    echo "--- A. Azure RBAC Role Assignments ---"
    echo "Required role: Owner or Role Based Access Control Administrator on the resource group"
    echo ""
    echo "# Get managed identity principal IDs"
    echo "MCP_PRINCIPAL=\$(az containerapp show --name ${mcp_app} --resource-group ${rg} --query identity.principalId -o tsv)"
    echo "BOT_PRINCIPAL=\$(az containerapp show --name ${bot_app} --resource-group ${rg} --query identity.principalId -o tsv)"
    echo ""
    if [ -n "$storage" ]; then
        echo "# Storage Blob Data Contributor → MCP identity"
        echo "az role assignment create \\"
        echo "  --assignee \$MCP_PRINCIPAL \\"
        echo "  --role 'Storage Blob Data Contributor' \\"
        echo "  --scope '${scope_rg}/providers/Microsoft.Storage/storageAccounts/${storage}'"
        echo ""
    fi
    if [ -n "$cosmos" ]; then
        echo "# Cosmos DB Built-in Data Contributor → MCP identity"
        echo "az role assignment create \\"
        echo "  --assignee \$MCP_PRINCIPAL \\"
        echo "  --role 'Cosmos DB Built-in Data Contributor' \\"
        echo "  --scope '${scope_rg}/providers/Microsoft.DocumentDB/databaseAccounts/${cosmos}'"
        echo ""
    fi
    echo "# Azure AI Developer → Bot identity"
    echo "az role assignment create \\"
    echo "  --assignee \$BOT_PRINCIPAL \\"
    echo "  --role 'Azure AI Developer' \\"
    echo "  --scope '${scope_rg}'"
    echo ""
    if [ -n "$foundry_account" ]; then
        echo "# Azure AI User → Bot identity (Foundry Agent Service)"
        echo "az role assignment create \\"
        echo "  --assignee \$BOT_PRINCIPAL \\"
        echo "  --role 'Azure AI User' \\"
        echo "  --scope '${scope_rg}/providers/Microsoft.CognitiveServices/accounts/${foundry_account}'"
        echo ""
    fi
    echo "--- B. Graph API Admin Consent ---"
    echo "Required role: Global Administrator or Privileged Role Administrator"
    echo ""
    echo "Option 1 — Azure CLI:"
    echo "  az ad app permission admin-consent --id ${app_id}"
    echo ""
    echo "Option 2 — Azure Portal (if CLI is not available):"
    echo "  1. Go to: https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/CallAnAPI/appId/${app_id}"
    echo "  2. Click 'Grant admin consent for <tenant>'"
    echo "  3. Confirm the dialog"
    echo ""
    echo "Permissions being consented:"
    echo "  - Calendars.Read            (read calendar events)"
    echo "  - OnlineMeetings.Read.All   (read meeting details)"
    echo "  - OnlineMeetings.ReadWrite.All (proactive bot join)"
    echo ""
    echo "--- C. Teams App Manifest ---"
    echo "Required: Teams Administrator or sideload permission"
    echo ""
    echo "  See: docs/teams-app-registration.md"
    echo "  Bot App ID to use in manifest: ${app_id}"
    echo "  Bot URL: $(tf_output bot_base_url 2>/dev/null || echo '<bot-url>')"
    echo ""
    echo "========================================"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

TAG="latest"
POSITIONAL=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --tag) TAG="$2"; shift 2 ;;
        *)     POSITIONAL+=("$1"); shift ;;
    esac
done

COMMAND="${POSITIONAL[0]:-help}"

case "$COMMAND" in
    all)              cmd_all "$TAG" ;;
    self)             cmd_deploy_self "$TAG" ;;
    infra)            cmd_infra ;;
    infra-apps)       cmd_infra_apps ;;
    destroy)          cmd_destroy ;;
    docker)           cmd_docker "$TAG" ;;
    rbac)             cmd_rbac ;;
    graph-consent)    cmd_graph_consent ;;
    admin-checklist)  cmd_admin_checklist ;;
    check-mcp)        cmd_check_mcp ;;
    agents)           cmd_agents ;;
    help|*)
        echo ""
        echo "Usage: ./deploy.sh <command> [--tag <tag>]"
        echo ""
        echo "Commands you can run yourself:"
        echo "  self            Steps that don't require admin access (infra + docker + agents)"
        echo "  infra           terraform init + apply (base infra, excludes Container Apps)"
        echo "  infra-apps      Deploy Container Apps (run after docker push)"
        echo "  destroy         Destroy all provisioned Azure resources (keeps resource group)"
        echo "  docker          Build + push images to ACR, then deploy Container Apps  [--tag <tag>]"
        echo "  check-mcp       Verify MCP server is reachable"
        echo "  agents          Register/update agents in Azure AI Foundry"
        echo ""
        echo "Commands that require elevated permissions:"
        echo "  rbac            Assign RBAC roles (requires Owner / RBAC Admin on RG)"
        echo "  graph-consent   Grant Graph API admin consent (requires Global Admin)"
        echo ""
        echo "Helpers:"
        echo "  admin-checklist Print ready-to-run commands for your Azure administrator"
        echo "  all             Full end-to-end deployment (all steps, all permissions)"
        echo "  help            Show this message"
        echo ""
        echo "Typical workflow without admin access:"
        echo "  1. cp infra/terraform.tfvars.example infra/terraform.tfvars  # fill in values"
        echo "  2. ./deploy.sh self                  # run what you can"
        echo "  3. ./deploy.sh admin-checklist       # send output to your admin"
        echo "  4. ./deploy.sh agents                # run after admin completes their steps"
        echo ""
        echo "Options:"
        echo "  --tag <tag>   Docker image tag (default: latest)"
        echo ""
        echo "Env overrides:"
        echo "  ACR=<login-server>               Override ACR login server"
        echo "  MCP_SERVER_URL=<url>             Override MCP URL"
        echo "  AZURE_AI_PROJECT_ENDPOINT=<url>  Override Foundry endpoint"
        echo ""
        ;;
esac
