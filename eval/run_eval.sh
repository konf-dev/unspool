#!/usr/bin/env bash
set -euo pipefail

# Two-phase eval runner: promptfoo regression + Langfuse scoring
#
# Usage:
#   ./eval/run_eval.sh                    # Full eval
#   ./eval/run_eval.sh --skip-promptfoo   # Only Langfuse scoring
#   ./eval/run_eval.sh --skip-langfuse    # Only promptfoo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

SKIP_PROMPTFOO=false
SKIP_LANGFUSE=false

for arg in "$@"; do
    case $arg in
        --skip-promptfoo) SKIP_PROMPTFOO=true ;;
        --skip-langfuse)  SKIP_LANGFUSE=true ;;
    esac
done

echo "=== Unspool Eval Runner ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# Phase 1: Run promptfoo regression tests
if [ "$SKIP_PROMPTFOO" = false ]; then
    echo "--- Phase 1: Promptfoo regression tests ---"
    cd eval
    npx promptfoo eval
    cd ..
    echo ""
fi

# Wait for cold path processing
echo "--- Waiting 30s for cold path processing ---"
sleep 30

# Phase 2: Run Langfuse LLM-as-judge scoring
if [ "$SKIP_LANGFUSE" = false ]; then
    echo "--- Phase 2: Langfuse LLM-as-judge scoring ---"
    python eval/langfuse_eval.py --limit 20
    echo ""

    echo "--- Phase 2b: Cold path scoring ---"
    python eval/langfuse_eval.py --cold-path --limit 10
    echo ""
fi

# Phase 3: View results
if [ "$SKIP_PROMPTFOO" = false ]; then
    echo "--- Results ---"
    echo "Open promptfoo viewer:"
    echo "  cd eval && npx promptfoo view"
fi

echo ""
echo "=== Eval complete ==="
