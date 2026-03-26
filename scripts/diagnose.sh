#!/usr/bin/env bash
set -euo pipefail

# Always target production unless --local is passed
if [[ "${1:-}" == "--local" ]]; then
    API_URL="${API_URL:-http://localhost:8000}"
    FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"
else
    API_URL="https://api.unspool.life"
    FRONTEND_URL="https://www.unspool.life"
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

EXPECTED_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
EXPECTED_SHA_SHORT="${EXPECTED_SHA:0:8}"

passed=0
failed=0
warnings=0
skipped=0

pass()  { ((passed++))  || true; printf "  [PASS] %s\n" "$1"; }
fail()  { ((failed++))  || true; printf "  [FAIL] %s\n" "$1"; }
warn()  { ((warnings++)) || true; printf "  [WARN] %s\n" "$1"; }
skip()  { ((skipped++)) || true; printf "  [SKIP] %s\n" "$1"; }

echo ""
echo "=== Unspool Production Diagnostics (v2) ==="
echo "Expected commit: $EXPECTED_SHA_SHORT"
echo "Backend:  $API_URL"
echo "Frontend: $FRONTEND_URL"
echo ""

# --- 1. GitHub Actions CI ---
echo "-- CI --"
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

# --- 2. Backend health (Railway) ---
echo ""
echo "-- Backend (Railway) --"
health_json=$(curl -sf --max-time 10 "$API_URL/health" 2>/dev/null || echo "")
if [[ -n "$health_json" ]]; then
    health_status=$(echo "$health_json" | jq -r '.status // "unknown"')
    backend_sha=$(echo "$health_json" | jq -r '.git_sha // "unknown"')
    if [[ "$health_status" == "ok" ]]; then
        pass "Backend health: ok"
    else
        fail "Backend health: $health_status"
    fi
    if [[ "$backend_sha" == "$EXPECTED_SHA" || "${backend_sha:0:8}" == "$EXPECTED_SHA_SHORT" ]]; then
        pass "Backend SHA: ${backend_sha:0:8} (matches)"
    elif [[ "$backend_sha" == "unknown" ]]; then
        warn "Backend SHA: not reported (CLI deploy — RAILWAY_GIT_COMMIT_SHA not set)"
    else
        fail "Backend SHA: ${backend_sha:0:8} (expected $EXPECTED_SHA_SHORT)"
    fi
else
    fail "Backend health: unreachable"
    backend_sha="unreachable"
fi

# --- 3. Deep health ---
echo ""
echo "-- Deep Health --"
deep_json=$(curl -sf --max-time 30 -H "X-Admin-Key: $ADMIN_API_KEY" "$API_URL/admin/health/deep" 2>/dev/null || echo "")
if [[ -n "$deep_json" ]]; then
    # Services from health_checks.py: db, redis, qstash, langfuse
    for svc in db redis qstash langfuse; do
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
            missing) warn "$svc: not in response" ;;
            *)       warn "$svc: $svc_status" ;;
        esac
    done
else
    fail "Deep health: unreachable (is ADMIN_API_KEY correct?)"
fi

# --- 4. Recent errors ---
echo ""
echo "-- Errors --"
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

# --- 5. Frontend version (Vercel) ---
echo ""
echo "-- Frontend (Vercel) --"

# Check the site is reachable
http_code=$(curl -so /dev/null -w '%{http_code}' --max-time 10 "$FRONTEND_URL" 2>/dev/null || echo "000")
if [[ "$http_code" == "200" ]]; then
    pass "Frontend reachable: $http_code"
else
    fail "Frontend reachable: HTTP $http_code"
fi

version_json=$(curl -sfL --max-time 10 "$FRONTEND_URL/version.json" 2>/dev/null || echo "")
if [[ -n "$version_json" ]] && echo "$version_json" | jq . &>/dev/null; then
    frontend_sha=$(echo "$version_json" | jq -r '.git_sha // "unknown"')
    frontend_sha_short="${frontend_sha:0:8}"
    built_at=$(echo "$version_json" | jq -r '.built_at // "unknown"')
    if [[ "$frontend_sha" == "$EXPECTED_SHA" || "$frontend_sha_short" == "$EXPECTED_SHA_SHORT" ]]; then
        pass "Frontend SHA: $frontend_sha_short (matches, built $built_at)"
    elif [[ "$frontend_sha" == "dev" ]]; then
        warn "Frontend SHA: dev build (no VERCEL_GIT_COMMIT_SHA)"
    else
        fail "Frontend SHA: $frontend_sha_short (expected $EXPECTED_SHA_SHORT, built $built_at)"
    fi
else
    warn "Frontend version.json: not found (deploy may predate this feature)"
fi

# --- 6. Railway status ---
echo ""
echo "-- Deployment Status --"
if command -v railway &>/dev/null; then
    railway_status=$(railway status 2>/dev/null || echo "")
    if [[ -n "$railway_status" ]]; then
        echo "  Railway:"
        echo "$railway_status" | sed 's/^/    /'
    else
        warn "Railway: could not fetch status"
    fi
else
    skip "Railway CLI: not installed"
fi

# --- 7. Vercel status ---
if command -v vercel &>/dev/null; then
    vercel_out=$(vercel ls 2>/dev/null | head -5 || echo "")
    if [[ -n "$vercel_out" ]]; then
        echo ""
        echo "  Vercel:"
        echo "$vercel_out" | sed 's/^/    /'
    else
        warn "Vercel: could not fetch deployments"
    fi
else
    skip "Vercel CLI: not installed"
fi

# --- 8. Migration Status ---
echo ""
echo "-- Migrations --"

# Load DATABASE_URL from .env
if [[ -z "${DATABASE_URL:-}" && -f .env ]]; then
    DB_URL=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
else
    DB_URL="${DATABASE_URL:-}"
fi

if [[ -n "$DB_URL" ]] && command -v psql &>/dev/null; then
    # Strip +asyncpg for psql compatibility
    DB_URL="${DB_URL//+asyncpg/}"

    # Check if schema_migrations table exists
    table_exists=$(psql "$DB_URL" -t -A -c "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='schema_migrations');" 2>/dev/null || echo "false")

    if [[ "$table_exists" == "t" ]]; then
        applied_versions=$(psql "$DB_URL" -t -A -c "SELECT version FROM public.schema_migrations ORDER BY version;" 2>/dev/null || echo "")
        applied_count=$(echo "$applied_versions" | grep -c . 2>/dev/null || echo "0")

        # Count local migration files
        local_count=0
        pending_list=()
        modified_list=()
        for file in backend/supabase/migrations/[0-9]*.sql; do
            [[ -f "$file" ]] || continue
            ((local_count++))
            basename_f=$(basename "$file" .sql)
            if ! echo "$applied_versions" | grep -qx "$basename_f"; then
                pending_list+=("$basename_f")
            elif command -v sha256sum &>/dev/null; then
                checksum=$(sha256sum "$file" | cut -d' ' -f1)
                stored=$(psql "$DB_URL" -t -A -c "SELECT checksum FROM public.schema_migrations WHERE version = '$basename_f';" 2>/dev/null | tr -d '[:space:]')
                if [[ -n "$stored" && "$stored" != "$checksum" ]]; then
                    modified_list+=("$basename_f")
                fi
            fi
        done

        pass "Applied: $applied_count / $local_count migrations"

        if [[ ${#pending_list[@]} -gt 0 ]]; then
            warn "Pending: ${pending_list[*]}"
        fi

        if [[ ${#modified_list[@]} -gt 0 ]]; then
            warn "Modified since applied: ${modified_list[*]}"
        fi
    else
        warn "schema_migrations table not found (run migration 00011 to bootstrap)"
    fi
elif [[ -z "$DB_URL" ]]; then
    skip "Migrations: DATABASE_URL not set"
else
    skip "Migrations: psql not installed"
fi

# --- Summary ---
echo ""
echo "=== $passed passed, $failed failed, $warnings warnings, $skipped skipped ==="

if [[ "$failed" -gt 0 ]]; then
    exit 1
fi
exit 0
