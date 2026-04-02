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
    echo ">>> terraform apply"
    terraform -chdir=infra apply -var-file=terraform.tfvars
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
    docker build -f mcp/Dockerfile      -t "${acr}/meeting-analyzer-mcp:${tag}" .
    docker build -f team_bot/Dockerfile -t "${acr}/meeting-analyzer-bot:${tag}" .

    az acr login --name "${acr%%.*}"
    docker push "${acr}/meeting-analyzer-mcp:${tag}"
    docker push "${acr}/meeting-analyzer-bot:${tag}"

    echo ""
    echo "Pushed:"
    echo "  ${acr}/meeting-analyzer-mcp:${tag}"
    echo "  ${acr}/meeting-analyzer-bot:${tag}"
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
    pip install -q azure-ai-projects azure-identity pyyaml
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

    echo "--- Step 1/5: Terraform ---"
    cmd_infra
    echo ""

    echo "--- Step 2/5: Build & Push Docker Images ---"
    cmd_docker "$tag"
    echo ""

    echo "--- Step 3/5: RBAC Assignments ---"
    cmd_rbac
    echo ""

    echo "--- Step 4/5: Verify MCP Server ---"
    cmd_check_mcp
    echo ""

    echo "--- Step 5/5: Register AI Foundry Agents ---"
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
    all)        cmd_all "$TAG" ;;
    infra)      cmd_infra ;;
    docker)     cmd_docker "$TAG" ;;
    rbac)       cmd_rbac ;;
    check-mcp)  cmd_check_mcp ;;
    agents)     cmd_agents ;;
    help|*)
        echo ""
        echo "Usage: ./deploy.sh <command> [--tag <tag>]"
        echo ""
        echo "  all         Full deployment end-to-end (steps 1-5)"
        echo "  infra       terraform init + apply (requires infra/terraform.tfvars)"
        echo "  docker      Build + push images to ACR  [--tag <tag>]"
        echo "  rbac        Assign RBAC roles to Container App managed identities"
        echo "  check-mcp   Verify MCP server is reachable"
        echo "  agents      Register/update agents in Azure AI Foundry"
        echo "  help        Show this message"
        echo ""
        echo "Quick deploy:"
        echo "  cp infra/terraform.tfvars.example infra/terraform.tfvars"
        echo "  # fill in values, then:"
        echo "  ./deploy.sh all"
        echo ""
        echo "Options:"
        echo "  --tag <tag>   Docker image tag (default: latest)"
        echo ""
        echo "Env overrides:"
        echo "  ACR=<login-server>                  Override ACR (skips terraform output lookup)"
        echo "  MCP_SERVER_URL=<url>                Override MCP URL"
        echo "  AZURE_AI_PROJECT_ENDPOINT=<url>     Required for 'agents' if not in tfvars"
        echo ""
        ;;
esac
