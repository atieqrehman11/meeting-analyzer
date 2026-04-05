#!/usr/bin/env bash
set -euo pipefail

# Meeting Assistant — local development script
# Usage: ./run-dev.sh <command>

cd "$(dirname "$0")"

REPO_ROOT="$(pwd)"
MCP_DIR="$REPO_ROOT/mcp"
ORCHESTRATOR_DIR="$REPO_ROOT/orchestrator"
TEAM_BOT_DIR="$REPO_ROOT/team_bot"
VENV_DIR="$REPO_ROOT/.venv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

load_env() {
    if [ -f "$REPO_ROOT/.env" ]; then
        set -o allexport
        # shellcheck disable=SC1091
        source "$REPO_ROOT/.env"
        set +o allexport
        echo "Loaded .env"
    fi
}

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

setup_team_bot() {
    activate_venv
    pip install -q -e "$REPO_ROOT/shared_models" 2>/dev/null || true
    pip install -q -e "$REPO_ROOT/orchestrator" 2>/dev/null || true
    install_deps "$TEAM_BOT_DIR"
    export PYTHONPATH="$REPO_ROOT:$TEAM_BOT_DIR"
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

    mcp)
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
        python3 "$MCP_DIR/main.py" &
        MCP_PID=$!
        wait
        ;;

    bot)
        load_env
        setup_team_bot
        ensure_port_free "${BOT_PORT:-3978}"
        echo ""
        echo "Starting Teams bot ..."
        echo "  API     : http://localhost:${BOT_PORT:-3978}"
        echo "  Swagger : http://localhost:${BOT_PORT:-3978}/docs"
        echo ""
        echo "Press Ctrl+C to stop."
        reload_arg=""
        [ "${BOT_RELOAD:-false}" = "true" ] && reload_arg="--reload"
        python3 -m uvicorn "team_bot.main:app" \
            --host "${BOT_HOST:-0.0.0.0}" \
            --port "${BOT_PORT:-3978}" \
            $reload_arg &
        BOT_PID=$!
        wait
        ;;

    all)
        load_env
        setup_mcp
        setup_team_bot
        ensure_port_free "${MCP_PORT:-8000}"
        ensure_port_free "${BOT_PORT:-3978}"
        echo ""
        echo "Starting all services ..."
        echo "  MCP : http://localhost:${MCP_PORT:-8000}"
        echo "  Bot : http://localhost:${BOT_PORT:-3978}"
        echo ""
        echo "Press Ctrl+C to stop."
        python3 "$MCP_DIR/main.py" &
        MCP_PID=$!
        python3 -m uvicorn "team_bot.main:app" \
            --host "${BOT_HOST:-0.0.0.0}" \
            --port "${BOT_PORT:-3978}" &
        BOT_PID=$!
        wait
        ;;

    install)
        load_env
        activate_venv
        echo "Installing all packages..."
        pip install -q -e "$REPO_ROOT/shared_models"
        pip install -q -e "$REPO_ROOT/orchestrator[dev]"
        pip install -q -e "$REPO_ROOT/mcp[dev]"
        pip install -q -e "$REPO_ROOT/team_bot[dev]"
        echo "Done."
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
        echo "Usage: ./run-dev.sh <command>"
        echo ""
        echo "  mcp        Start the MCP server on :8000"
        echo "  bot        Start the Teams bot on :3978"
        echo "  all        Start MCP and bot together"
        echo "  install    Install all packages into .venv"
        echo "  env:init   Create .env from .env.example"
        echo "  help       Show this message"
        echo ""
        echo "Quick start:"
        echo "  ./run-dev.sh env:init   # create .env"
        echo "  ./run-dev.sh install    # install dependencies"
        echo "  ./run-dev.sh all        # start everything"
        echo ""
        echo "Key env vars (set in .env):"
        echo "  MCP_BACKEND_MODE=mock|azure   (default: mock)"
        echo "  MCP_PORT=8000"
        echo "  BOT_PORT=3978"
        echo "  BOT_RELOAD=true               (hot reload for bot)"
        echo ""
        ;;
esac
