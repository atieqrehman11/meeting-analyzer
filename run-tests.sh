#!/usr/bin/env bash
set -euo pipefail

# Meeting Assistant — test runner
# Usage: ./run-tests.sh [module] [pytest-args...]
#
# Modules: mcp, orchestrator, bot, all (default)

cd "$(dirname "$0")"

REPO_ROOT="$(pwd)"
MCP_DIR="$REPO_ROOT/mcp"
ORCHESTRATOR_DIR="$REPO_ROOT/orchestrator"
TEAM_BOT_DIR="$REPO_ROOT/team_bot"
VENV_DIR="$REPO_ROOT/.venv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

activate_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo "No .venv found — run ./run-dev.sh install first."
        exit 1
    fi
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
}

load_env() {
    if [ -f "$REPO_ROOT/.env" ]; then
        set -o allexport
        # shellcheck disable=SC1091
        source "$REPO_ROOT/.env"
        set +o allexport
    fi
}

install_deps() {
    local pkg_dir="$1"
    pip install -q -e "${pkg_dir}[dev]" 2>/dev/null || pip install -q -e "$pkg_dir"
}

run_module() {
    local name="$1"
    local path="$2"
    shift 2
    local tmp summary status=0

    tmp=$(mktemp)
    echo ">>> ${name}"
    python3 -m pytest "$path" "$@" -v 2>&1 | tee "$tmp" || status=$?

    summary=$(python3 - "$tmp" <<'PY'
import re, sys
from collections import Counter
text = open(sys.argv[1]).read()
counts = Counter()
for m in re.finditer(r'(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)', text):
    count, tag = int(m.group(1)), m.group(2)
    counts['errors' if tag == 'error' else tag] += count
order = ['failed', 'errors', 'passed', 'skipped', 'xfailed', 'xpassed']
print(', '.join(f'{counts[k]} {k}' for k in order if counts[k]))
PY
)
    rm -f "$tmp"
    echo "${name}: ${summary:-no summary}"
    return "$status"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

load_env
activate_venv

MODULE="${1:-all}"
shift 2>/dev/null || true   # remaining args passed to pytest

case "$MODULE" in
    mcp)
        install_deps "$MCP_DIR"
        export PYTHONPATH="$MCP_DIR:$REPO_ROOT"
        run_module "MCP" "$MCP_DIR/tests" "$@"
        ;;

    orchestrator)
        install_deps "$ORCHESTRATOR_DIR"
        export PYTHONPATH="$REPO_ROOT"
        run_module "Orchestrator" "$ORCHESTRATOR_DIR/tests" "$@"
        ;;

    bot)
        pip install -q -e "$REPO_ROOT/shared_models" 2>/dev/null || true
        pip install -q -e "$REPO_ROOT/orchestrator" 2>/dev/null || true
        install_deps "$TEAM_BOT_DIR"
        export PYTHONPATH="$REPO_ROOT"
        run_module "Bot" "$TEAM_BOT_DIR/tests" "$@"
        ;;

    all)
        pip install -q -e "$REPO_ROOT/shared_models" 2>/dev/null || true
        install_deps "$MCP_DIR"
        install_deps "$ORCHESTRATOR_DIR"
        install_deps "$TEAM_BOT_DIR"

        set +e
        overall=0
        summaries=()

        export PYTHONPATH="$MCP_DIR:$REPO_ROOT"
        run_module "MCP" "$MCP_DIR/tests" "$@"
        [ $? -ne 0 ] && overall=1

        export PYTHONPATH="$REPO_ROOT"
        run_module "Orchestrator" "$ORCHESTRATOR_DIR/tests" "$@"
        [ $? -ne 0 ] && overall=1

        run_module "Bot" "$TEAM_BOT_DIR/tests" "$@"
        [ $? -ne 0 ] && overall=1

        set -e
        exit "$overall"
        ;;

    help|*)
        echo ""
        echo "Usage: ./run-tests.sh [module] [pytest-args...]"
        echo ""
        echo "  mcp           Run MCP server tests"
        echo "  orchestrator  Run orchestrator tests"
        echo "  bot           Run Teams bot tests"
        echo "  all           Run all tests (default)"
        echo ""
        echo "Examples:"
        echo "  ./run-tests.sh                     # run everything"
        echo "  ./run-tests.sh mcp                 # MCP only"
        echo "  ./run-tests.sh mcp -k test_consent # filter by name"
        echo "  ./run-tests.sh all --tb=short      # short tracebacks"
        echo ""
        ;;
esac
