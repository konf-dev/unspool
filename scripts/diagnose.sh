#!/usr/bin/env bash
set -euo pipefail

# Always target production unless --local is passed
if [[ "${1:-}" == "--local" ]]; then
    API_URL="${API_URL:-http://localhost:8000}"
    FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"
else
    API_URL="https://api.unspool.life"
    FRONTEND_URL="https://unspool.life"
fi

for cmd in curl jq; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is required but not installed"
        exit 1
    fi
done

if [[ -z "${ADMIN_API_KEY:-}" ]]; then
    echo "ERROR: ADMIN_API_KEY not set. Export it or add to .env"
    exit 1
fi

EXPECTED_SHA=$(git rev-parse --short=8 HEAD 2>/dev/null || echo "unknown")

passed=0
failed=0
warnings=0
skipped=0

pass()  { ((passed++))  || true; printf "  [PASS] %s\n" "$1"; }
fail()  { ((failed++))  || true; printf "  [FAIL] %s\n" "$1"; }
warn()  { ((warnings++)) || true; printf "  [WARN] %s\n" "$1"; }
skip()  { ((skipped++)) || true; printf "  [SKIP] %s\n" "$1"; }

echo ""
echo "=== Unspool Production Diagnostics ==="
echo "Expected commit: $EXPECTED_SHA"
echo ""

# --- 1. GitHub Actions CI ---
if command -v gh &>/dev/null; then
    ci_json=$(gh run list --branch main --limit 1 --json status,conclusion,headSha 2>/dev/null || echo "")
    if [[ -n "$ci_json" && "$ci_json" != "[]" ]]; then
        ci_conclusion=$(echo "$ci_json" | jq -r '.[0].conclusion // "pending"')
        ci_sha=$(echo "$ci_json" | jq -r '.[0].headSha // ""' | cut -c1-8)
        if [[ "$ci_conclusion" == "success" ]]; then
            pass "CI: passed for $ci_sha"
        elif [[ "$ci_conclusion" == "pending" || "$ci_conclusion" == "null" ]]; then
            warn "CI: still running for $ci_sha"
        else
            fail "CI: $ci_conclusion for $ci_sha"
        fi
    else
        warn "CI: could not fetch status"
    fi
else
    skip "CI: gh CLI not installed"
fi

# --- 2. Backend health ---
health_json=$(curl -sf --max-time 10 "$API_URL/health" 2>/dev/null || echo "")
if [[ -n "$health_json" ]]; then
    health_status=$(echo "$health_json" | jq -r '.status // "unknown"')
    backend_sha=$(echo "$health_json" | jq -r '.git_sha // "unknown"')
    if [[ "$health_status" == "ok" ]]; then
        pass "Backend health: ok"
    else
        fail "Backend health: $health_status"
    fi
    if [[ "$backend_sha" == "$EXPECTED_SHA" ]]; then
        pass "Backend SHA: $backend_sha (matches)"
    elif [[ "$backend_sha" == "unknown" ]]; then
        warn "Backend SHA: not reported (old deploy?)"
    else
        fail "Backend SHA: $backend_sha (expected $EXPECTED_SHA)"
    fi
else
    fail "Backend health: unreachable"
    backend_sha="unreachable"
fi

# --- 3. Deep health ---
deep_json=$(curl -sf --max-time 30 -H "X-Admin-Key: $ADMIN_API_KEY" "$API_URL/admin/health/deep" 2>/dev/null || echo "")
if [[ -n "$deep_json" ]]; then
    for svc in db redis qstash llm langfuse; do
        svc_status=$(echo "$deep_json" | jq -r ".services.${svc}.status // \"missing\"")
        svc_latency=$(echo "$deep_json" | jq -r ".services.${svc}.latency_ms // \"\"")
        svc_error=$(echo "$deep_json" | jq -r ".services.${svc}.error // \"\"")
        svc_reason=$(echo "$deep_json" | jq -r ".services.${svc}.reason // \"\"")

        label="$svc"
        [[ -n "$svc_latency" ]] && label="$svc (${svc_latency}ms)"

        case "$svc_status" in
            ok)      pass "$label" ;;
            skipped) skip "$svc: $svc_reason" ;;
            error)   fail "$svc: $svc_error" ;;
            *)       warn "$svc: $svc_status" ;;
        esac
    done
else
    fail "Deep health: unreachable (is ADMIN_API_KEY correct?)"
fi

# --- 4. Recent errors ---
errors_json=$(curl -sf --max-time 10 -H "X-Admin-Key: $ADMIN_API_KEY" "$API_URL/admin/errors/summary" 2>/dev/null || echo "")
if [[ -n "$errors_json" ]]; then
    error_count=$(echo "$errors_json" | jq 'length')
    if [[ "$error_count" -eq 0 ]]; then
        pass "Errors (24h): 0"
    else
        total_errors=$(echo "$errors_json" | jq '[.[].count] | add')
        warn "Errors (24h): $total_errors across $error_count types"
    fi
else
    warn "Errors: could not fetch summary"
fi

# --- 5. Frontend version ---
version_json=$(curl -sfL --max-time 10 "$FRONTEND_URL/version.json" 2>/dev/null || echo "")
if [[ -n "$version_json" ]] && echo "$version_json" | jq . &>/dev/null; then
    frontend_sha=$(echo "$version_json" | jq -r '.git_sha // "unknown"' | cut -c1-8)
    if [[ "$frontend_sha" == "$EXPECTED_SHA" ]]; then
        pass "Frontend SHA: $frontend_sha (matches)"
    elif [[ "$frontend_sha" == "dev" ]]; then
        warn "Frontend SHA: dev build (no VERCEL_GIT_COMMIT_SHA)"
    else
        fail "Frontend SHA: $frontend_sha (expected $EXPECTED_SHA)"
    fi
else
    warn "Frontend version.json: not found (deploy may predate this feature)"
fi

# --- 6. Railway status ---
if command -v railway &>/dev/null; then
    railway_out=$(railway deployment list 2>/dev/null | head -3 || echo "")
    if [[ -n "$railway_out" ]]; then
        echo ""
        echo "  Railway deployments:"
        echo "$railway_out" | sed 's/^/    /'
    else
        warn "Railway: could not fetch deployments"
    fi
else
    skip "Railway CLI: not installed"
fi

# --- 7. Vercel status ---
if command -v vercel &>/dev/null; then
    vercel_out=$(vercel ls 2>/dev/null | head -3 || echo "")
    if [[ -n "$vercel_out" ]]; then
        echo ""
        echo "  Vercel deployments:"
        echo "$vercel_out" | sed 's/^/    /'
    else
        warn "Vercel: could not fetch deployments"
    fi
else
    skip "Vercel CLI: not installed"
fi

# --- Summary ---
echo ""
echo "=== $passed passed, $failed failed, $warnings warnings, $skipped skipped ==="

if [[ "$failed" -gt 0 ]]; then
    exit 1
fi
exit 0
