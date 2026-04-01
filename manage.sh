#!/usr/bin/env bash
set -euo pipefail

# Meeting Analyzer — project management script
# Usage: ./manage.sh <command>

cd "$(dirname "$0")"

REPO_ROOT="$(pwd)"
MCP_DIR="$REPO_ROOT/mcp"
ORCHESTRATOR_DIR="$REPO_ROOT/orchestrator"
TEAM_BOT_DIR="$REPO_ROOT/team_bot"
VENV_DIR="$REPO_ROOT/.venv"

# ---------------------------------------------------------------------------
# Load .env if present (local dev only — never used in CI/CD or Azure)
# ---------------------------------------------------------------------------
load_env() {
    clear
    echo "Loading .env ..."
    if [ -f "$REPO_ROOT/.env" ]; then
        # Export each non-comment, non-empty line
        set -o allexport
        # shellcheck disable=SC1091
        source "$REPO_ROOT/.env"
        set +o allexport
        echo "Loaded .env"
    fi
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ensure_port_free() {
    local port=$1
    if lsof -Pi :"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "Port $port in use — clearing..."
        lsof -ti:"$port" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

activate_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating virtual environment at .venv ..."
        python3 -m venv "$VENV_DIR"
    fi
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
}

install_deps() {
    local pkg_dir="$1"
    local req="${pkg_dir}/requirements.txt"
    local hash_file="${req%.txt}.sha"
    local pyproject="${pkg_dir}/pyproject.toml"
    local current stored=""

    if command -v sha256sum >/dev/null 2>&1; then
        current=$(sha256sum "$pyproject" "$req" 2>/dev/null | sha256sum | awk '{print $1}')
    else
        current=$(cksum "$pyproject" "$req" 2>/dev/null | cksum | awk '{print $1}')
    fi

    [ -f "$hash_file" ] && stored=$(cat "$hash_file")

    if [ "$current" != "$stored" ] || ! python3 -c "import fastapi" 2>/dev/null; then
        echo "Installing $(basename "$pkg_dir") ..."
        pip install -q -e "${pkg_dir}[dev]" 2>/dev/null || pip install -q -e "$pkg_dir"
        echo "$current" > "$hash_file"
    else
        echo "$(basename "$pkg_dir") up to date."
    fi
}

setup_mcp() {
    activate_venv
    pip install -q -e "$REPO_ROOT/shared_models" 2>/dev/null || true
    install_deps "$MCP_DIR"
    export PYTHONPATH="$MCP_DIR:$REPO_ROOT"
}

setup_orchestrator() {
    activate_venv
    pip install -q -e "$REPO_ROOT/shared_models" 2>/dev/null || true
    install_deps "$ORCHESTRATOR_DIR"
    export PYTHONPATH="$MCP_DIR:$REPO_ROOT"
}

setup_team_bot() {
    activate_venv
    pip install -q -e "$REPO_ROOT/shared_models" 2>/dev/null || true
    pip install -q -e "$REPO_ROOT/orchestrator" 2>/dev/null || true
    install_deps "$TEAM_BOT_DIR"
    export PYTHONPATH="$REPO_ROOT:$TEAM_BOT_DIR"
}

run_pytest_module() {
    local summary_file=$1
    local module_name=$2
    local test_path=$3
    shift 3
    local tmp_output
    tmp_output=$(mktemp)

    echo "Running ${module_name} tests..."
    if python3 -m pytest "$test_path" "$@" -v 2>&1 | tee "$tmp_output"; then
        local status=0
    else
        local status=$?
    fi

    local summary
    summary=$(python3 - "$tmp_output" <<'PY'
import re
import sys
from collections import Counter
text = open(sys.argv[1], 'r', encoding='utf-8').read()
counts = Counter()
for m in re.finditer(r'(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)', text):
    count = int(m.group(1))
    tag = m.group(2)
    if tag == 'error':
        tag = 'errors'
    counts[tag] += count
order = ['failed', 'errors', 'passed', 'skipped', 'xfailed', 'xpassed']
parts = [f'{counts[k]} {k}' for k in order if counts[k]]
print(', '.join(parts))
PY
)

    if [ -n "$summary" ]; then
        printf '%s: %s\n' "$module_name" "$summary" > "$summary_file"
    else
        printf '%s: no summary available\n' "$module_name" > "$summary_file"
    fi

    rm -f "$tmp_output"
    return "$status"
}

cleanup() {
    [ -n "${MCP_PID:-}" ] && kill "$MCP_PID" 2>/dev/null || true
    [ -n "${BOT_PID:-}" ] && kill "$BOT_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

case "${1:-help}" in

    mcp|start:mcp)
        load_env
        setup_mcp
        ensure_port_free "${MCP_PORT:-8000}"
        echo ""
        echo "Starting MCP server ..."
        echo "  Backend : ${MCP_BACKEND_MODE:-mock}"
        echo "  API     : http://localhost:${MCP_PORT:-8000}"
        echo "  Swagger : http://localhost:${MCP_PORT:-8000}/docs"
        echo ""
        echo "Press Ctrl+C to stop."
        echo ""
        python3 "$MCP_DIR/main.py" &
        MCP_PID=$!
        wait
        ;;

    bot|start:bot)
        load_env
        setup_team_bot
        ensure_port_free "${BOT_PORT:-3978}"
        echo ""
        echo "Starting Team Bot service ..."
        echo "  API : http://localhost:${BOT_PORT:-3978}"
        echo ""
        echo "Press Ctrl+C to stop."
        echo ""
        reload_arg=""
        if [ "${BOT_RELOAD:-false}" = "true" ] || [ "${BOT_RELOAD:-1}" = "true" ]; then
            reload_arg="--reload"
        fi
        python3 -m uvicorn "team_bot.main:app" --host "${BOT_HOST:-0.0.0.0}" --port "${BOT_PORT:-3978}" $reload_arg &
        BOT_PID=$!
        wait
        ;;

    orchestrator)
        load_env
        echo "Orchestrator is a library component, not a standalone server."
        echo "Use './manage.sh bot' to launch the Teams bot, which uses the orchestrator internally."
        echo "Use './manage.sh test:orchestrator' to run orchestrator tests."
        ;;

    all|start:all)
        load_env
        setup_mcp
        setup_orchestrator
        setup_team_bot
        ensure_port_free "${MCP_PORT:-8000}"
        ensure_port_free "${BOT_PORT:-3978}"
        echo ""
        echo "Starting all services ..."
        echo "  MCP API : http://localhost:${MCP_PORT:-8000}"
        echo "  Bot API : http://localhost:${BOT_PORT:-3978}"
        echo ""
        echo "Press Ctrl+C to stop."
        echo ""
        python3 "$MCP_DIR/main.py" &
        MCP_PID=$!
        python3 -m uvicorn "team_bot.main:app" --host "${BOT_HOST:-0.0.0.0}" --port "${BOT_PORT:-3978}" &
        BOT_PID=$!
        wait
        ;;

    test:mcp)
        load_env
        setup_mcp
        tmp_summary=$(mktemp)
        run_pytest_module "$tmp_summary" "MCP" "$MCP_DIR/tests" "${@:2}"
        status=$?
        cat "$tmp_summary"
        rm -f "$tmp_summary"
        exit "$status"
        ;;

    test:orchestrator)
        load_env
        setup_orchestrator
        tmp_summary=$(mktemp)
        run_pytest_module "$tmp_summary" "Orchestrator" "$REPO_ROOT/orchestrator/tests" "${@:2}"
        status=$?
        cat "$tmp_summary"
        rm -f "$tmp_summary"
        exit "$status"
        ;;

    test:team-bot)
        load_env
        setup_team_bot
        tmp_summary=$(mktemp)
        run_pytest_module "$tmp_summary" "Team Bot" "$REPO_ROOT/team_bot/tests" "${@:2}"
        status=$?
        cat "$tmp_summary"
        rm -f "$tmp_summary"
        exit "$status"
        ;;

    test|test:all)
        load_env
        setup_mcp
        setup_orchestrator
        setup_team_bot
        echo "Running all tests..."
        set +e
        overall_status=0
        summaries=()

        tmp_summary=$(mktemp)
        run_pytest_module "$tmp_summary" "MCP" "$MCP_DIR/tests" "${@:2}"
        status=$?
        summaries+=("$(cat "$tmp_summary")")
        rm -f "$tmp_summary"
        [ "$status" -ne 0 ] && overall_status=1

        tmp_summary=$(mktemp)
        run_pytest_module "$tmp_summary" "Orchestrator" "$REPO_ROOT/orchestrator/tests" "${@:2}"
        status=$?
        summaries+=("$(cat "$tmp_summary")")
        rm -f "$tmp_summary"
        [ "$status" -ne 0 ] && overall_status=1

        tmp_summary=$(mktemp)
        run_pytest_module "$tmp_summary" "Team Bot" "$REPO_ROOT/team_bot/tests" "${@:2}"
        status=$?
        summaries+=("$(cat "$tmp_summary")")
        rm -f "$tmp_summary"
        [ "$status" -ne 0 ] && overall_status=1

        echo "\nSummary:"
        for s in "${summaries[@]}"; do
            echo "$s"
        done
        set -e
        exit "$overall_status"
        ;;

    deploy:all|deploy:infra|deploy:rbac|deploy:agents|check:mcp|infra:apply)
        # Delegate all deployment commands to deploy.sh
        case "${1}" in
            deploy:all)    DEPLOY_CMD="all" ;;
            infra:apply)   DEPLOY_CMD="infra" ;;
            deploy:rbac)   DEPLOY_CMD="rbac" ;;
            check:mcp)     DEPLOY_CMD="check-mcp" ;;
            deploy:agents) DEPLOY_CMD="agents" ;;
        esac
        exec "$REPO_ROOT/deploy.sh" "$DEPLOY_CMD" "${@:2}"
        ;;

    install)
        load_env
        activate_venv
        echo "Installing all packages in editable mode..."
        pip install -q -e "$REPO_ROOT/shared_models"
        pip install -q -e "$REPO_ROOT/orchestrator[dev]"
        pip install -q -e "$REPO_ROOT/mcp[dev]"
        pip install -q -e "$REPO_ROOT/team_bot[dev]"
        echo "All packages installed."
        ;;

    docker:build)
        # Usage: ./manage.sh docker:build [--tag <tag>]
        TAG="${3:-${DOCKER_TAG:-latest}}"
        if [[ "${2:-}" == "--tag" ]]; then TAG="$3"; fi
        echo ""
        echo "Building Docker images (tag: ${TAG}) ..."
        echo ""
        docker build -f mcp/Dockerfile      -t "meeting-analyzer-mcp:${TAG}" .
        docker build -f team_bot/Dockerfile -t "meeting-analyzer-bot:${TAG}" .
        echo ""
        echo "Built:"
        echo "  meeting-analyzer-mcp:${TAG}"
        echo "  meeting-analyzer-bot:${TAG}"
        echo ""
        ;;

    docker:push)
        # Usage: ./manage.sh docker:push [--tag <tag>]
        # Reads ACR from terraform output unless ACR env var is set.
        TAG="${3:-${DOCKER_TAG:-latest}}"
        if [[ "${2:-}" == "--tag" ]]; then TAG="$3"; fi

        if [ -z "${ACR:-}" ]; then
            echo "Reading ACR login server from Terraform outputs..."
            ACR=$(terraform -chdir=infra output -raw container_registry_login_server)
        fi

        echo ""
        echo "Building and pushing images to ${ACR} (tag: ${TAG}) ..."
        echo ""
        docker build -f mcp/Dockerfile      -t "${ACR}/meeting-analyzer-mcp:${TAG}" .
        docker build -f team_bot/Dockerfile -t "${ACR}/meeting-analyzer-bot:${TAG}" .

        az acr login --name "${ACR%%.*}"
        docker push "${ACR}/meeting-analyzer-mcp:${TAG}"
        docker push "${ACR}/meeting-analyzer-bot:${TAG}"

        echo ""
        echo "Pushed:"
        echo "  ${ACR}/meeting-analyzer-mcp:${TAG}"
        echo "  ${ACR}/meeting-analyzer-bot:${TAG}"
        echo ""
        ;;

    env:init)
        if [ -f "$REPO_ROOT/.env" ]; then
            echo ".env already exists — not overwriting."
        else
            cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
            echo "Created .env from .env.example — fill in your values."
        fi
        ;;

    help|*)
        echo ""
        echo "Usage: ./manage.sh <command>"
        echo ""
        echo "  mcp|start:mcp   Start the MCP server (loads .env)"
        echo "  bot|start:bot   Start the Teams bot service"
        echo "  orchestrator    Show orchestrator status / usage guidance"
        echo "  all|start:all   Start MCP and bot together on different ports"
        echo "  test:mcp        Run MCP server tests"
        echo "  test:orchestrator  Run orchestrator tests"
        echo "  test:team-bot   Run team bot tests"
        echo "  test           Run all tests"
        echo "  test:all       Run all tests"
        echo "  docker:build/push  See deploy.sh for Docker image commands"
        echo "  infra:apply     terraform init + apply"
        echo "  deploy:rbac     Assign RBAC roles to Container App managed identities"
        echo "  deploy:agents   Register/update agents in Azure AI Foundry"
        echo "  deploy:all      Run full Azure deployment sequence (steps 1-5)"
        echo "  check:mcp       Verify MCP server URL is reachable"
        echo "  (all deploy commands delegate to deploy.sh)"
        echo "  install         Install all dependencies into .venv"
        echo "  env:init        Create .env from .env.example"
        echo "  help            Show this message"
        echo ""
        echo "Quick start (local dev):"
        echo "  ./manage.sh env:init   # create .env"
        echo "  ./manage.sh all        # start MCP and bot on separate ports"
        echo "  ./manage.sh mcp        # start MCP server on :8000"
        echo ""
        echo "Deployment sequence (Azure):"
        echo "  1. cp infra/terraform.tfvars.example infra/terraform.tfvars  # fill in values"
        echo "  2. ./manage.sh deploy:all             # run full deployment end-to-end"
        echo ""
        echo "  Or step by step:"
        echo "  2a. ./manage.sh infra:apply           # provision all Azure infra"
        echo "  2b. ./manage.sh docker:push           # build + push images to ACR"
        echo "  2c. ./manage.sh deploy:rbac           # assign RBAC to managed identities"
        echo "  2d. ./manage.sh check:mcp             # verify MCP server is up"
        echo "  2e. ./manage.sh deploy:agents         # register agents in AI Foundry"
        echo ""
        echo "Key env vars (set in .env or shell):"
        echo "  MCP_BACKEND_MODE=mock|azure     (default: mock)"
        echo "  MCP_PORT=8000                   (default: 8000)"
        echo "  AZURE_AI_PROJECT_ENDPOINT=...   (required for deploy:agents)"
        echo "  MCP_SERVER_URL=...              (required for deploy:agents)"
        echo ""
        ;;
esac
