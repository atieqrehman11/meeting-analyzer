#!/usr/bin/env bash
set -euo pipefail

# Meeting Analyzer — project management script
# Usage: ./manage.sh <command>

cd "$(dirname "$0")"

REPO_ROOT="$(pwd)"
MCP_DIR="$REPO_ROOT/mcp"
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

setup_team_bot() {
    activate_venv
    install_deps "$TEAM_BOT_DIR/requirements.txt"
    export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/orchestrator:$REPO_ROOT/team_bot"
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
        tmp_summary=$(mktemp)
        run_pytest_module "$tmp_summary" "MCP" "$MCP_DIR/tests" "${@:2}"
        status=$?
        cat "$tmp_summary"
        rm -f "$tmp_summary"
        exit "$status"
        ;;

    test:orchestrator)
        load_env
        setup_mcp
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

    test)
        load_env
        setup_mcp
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
        load_env
        setup_mcp
        setup_team_bot
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
        echo "  test:orchestrator  Run orchestrator tests"
        echo "  test:team-bot  Run team bot tests"
        echo "  test           Run all tests"
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
