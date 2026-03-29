#!/usr/bin/env bash
set -euo pipefail

# Meeting Analyzer — project management script
# Usage: ./manage.sh <command>

cd "$(dirname "$0")"

REPO_ROOT="$(pwd)"
MCP_DIR="$REPO_ROOT/mcp"
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
    local req="$1"
    local hash_file="${req%.txt}.sha"
    local current stored=""

    if command -v sha256sum >/dev/null 2>&1; then
        current=$(sha256sum "$req" | awk '{print $1}')
    else
        current=$(cksum "$req" | awk '{print $1}')
    fi

    [ -f "$hash_file" ] && stored=$(cat "$hash_file")

    if [ "$current" != "$stored" ] || ! python3 -c "import fastapi" 2>/dev/null; then
        echo "Installing dependencies from $(basename "$req") ..."
        pip install -q -r "$req"
        echo "$current" > "$hash_file"
    else
        echo "Dependencies up to date."
    fi
}

setup_mcp() {
    activate_venv
    install_deps "$MCP_DIR/requirements.txt"
    export PYTHONPATH="$MCP_DIR:$REPO_ROOT/orchestrator:$REPO_ROOT"
}

cleanup() {
    [ -n "${MCP_PID:-}" ] && kill "$MCP_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

case "${1:-help}" in

    mcp)
        load_env
        setup_mcp
        ensure_port_free "${MCP_PORT:-8000}"
        echo ""
        echo "Starting MCP server ..."
        echo "  Backend : ${MCP_BACKEND_MODE:-mock}"
        echo "  Stage   : ${MCP_ACTIVE_STAGE:-1}"
        echo "  API     : http://localhost:${MCP_PORT:-8000}"
        echo "  Swagger : http://localhost:${MCP_PORT:-8000}/docs"
        echo ""
        echo "Press Ctrl+C to stop."
        echo ""
        python3 "$MCP_DIR/main.py" &
        MCP_PID=$!
        wait
        ;;

    test:mcp)
        load_env
        setup_mcp
        echo "Running MCP server tests..."
        python3 -m pytest "$MCP_DIR/tests" "${@:2}" -v
        ;;

    test:orchestrator)
        load_env
        setup_mcp
        echo "Running orchestrator tests..."
        python3 -m pytest "$REPO_ROOT/orchestrator/tests" "${@:2}" -v
        ;;

    test)
        load_env
        setup_mcp
        echo "Running all tests..."
        python3 -m pytest "$MCP_DIR/tests" "$REPO_ROOT/orchestrator/tests" "${@:2}" -v
        ;;

    deploy:agents)
        load_env
        activate_venv
        pip install -q azure-ai-projects azure-identity pyyaml
        echo "Registering agents in Foundry (endpoint: ${AZURE_AI_PROJECT_ENDPOINT:-not set})..."
        python3 deploy/register_agents.py
        ;;

    check:mcp)
        load_env
        echo "Checking MCP server reachability..."
        python3 deploy/register_mcp.py
        ;;

    install)
        activate_venv
        install_deps "$MCP_DIR/requirements.txt"
        echo "All dependencies installed."
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
        echo "  mcp            Start the MCP server (loads .env)"
        echo "  test:mcp       Run MCP server tests"
        echo "  deploy:agents  Register/update agents in Azure AI Foundry"
        echo "  check:mcp      Verify MCP server URL is reachable"
        echo "  install        Install all dependencies into .venv"
        echo "  env:init       Create .env from .env.example"
        echo "  help           Show this message"
        echo ""
        echo "Quick start:"
        echo "  ./manage.sh env:init   # create .env"
        echo "  ./manage.sh mcp        # start MCP server on :8000"
        echo ""
        echo "Key env vars (set in .env or shell):"
        echo "  MCP_BACKEND_MODE=mock|azure     (default: mock)"
        echo "  MCP_ACTIVE_STAGE=1|2|3          (default: 1)"
        echo "  MCP_PORT=8000                   (default: 8000)"
        echo "  AZURE_AI_PROJECT_ENDPOINT=...   (required for deploy:agents)"
        echo "  MCP_SERVER_URL=...              (required for deploy:agents)"
        echo ""
        ;;
esac
