#!/usr/bin/env bash
set -euo pipefail

MIGRATIONS_DIR="backend/supabase/migrations"
BACKUP_DIR="backups"
MAX_BACKUPS=5

# --- Flags ---
DRY_RUN=false
STATUS_ONLY=false
NO_BACKUP=false
FORCE=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)   DRY_RUN=true ;;
    --status)    STATUS_ONLY=true ;;
    --no-backup) NO_BACKUP=true ;;
    --force)     FORCE=true ;;
    --help|-h)
      echo "Usage: ./scripts/migrate.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --dry-run     Show what would be applied without doing it"
      echo "  --status      Show migration status only"
      echo "  --no-backup   Skip pre-migration backup"
      echo "  --force       Apply destructive migrations without confirmation"
      echo "  --help        Show this help"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)"
      exit 1
      ;;
  esac
done

# --- Connection ---
# Load DATABASE_URL from .env if not already set
if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ -f .env ]]; then
    DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
  fi
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL not set. Export it or add to .env"
  exit 1
fi

# Strip +asyncpg driver prefix for psql/pg_dump compatibility
PGURL="${DATABASE_URL//+asyncpg/}"

# --- Prerequisites ---
for cmd in psql sha256sum; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is required but not installed"
    exit 1
  fi
done

if ! command -v pg_dump &>/dev/null && [[ "$NO_BACKUP" == false && "$DRY_RUN" == false && "$STATUS_ONLY" == false ]]; then
  echo "ERROR: pg_dump is required for backups (use --no-backup to skip)"
  exit 1
fi

# --- Ensure schema_migrations table exists ---
# This handles the very first run before 00011 is applied
psql "$PGURL" -q -c "
  CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT now(),
    checksum   TEXT,
    applied_by TEXT DEFAULT current_user
  );
" 2>/dev/null

# --- Read applied migrations ---
APPLIED=$(psql "$PGURL" -t -A -c "SELECT version FROM public.schema_migrations ORDER BY version;" 2>/dev/null || echo "")

# --- Compute pending and modified ---
PENDING=()
MODIFIED=()

for file in "$MIGRATIONS_DIR"/[0-9]*.sql; do
  [[ -f "$file" ]] || continue
  version=$(basename "$file" .sql)
  checksum=$(sha256sum "$file" | cut -d' ' -f1)

  if echo "$APPLIED" | grep -qx "$version"; then
    # Already applied — check for modifications
    stored_checksum=$(psql "$PGURL" -t -A -c "SELECT checksum FROM public.schema_migrations WHERE version = '$version';" 2>/dev/null | tr -d '[:space:]')
    if [[ -n "$stored_checksum" && "$stored_checksum" != "$checksum" ]]; then
      MODIFIED+=("$version")
    fi
  else
    PENDING+=("$file")
  fi
done

# --- Status display ---
applied_count=$(echo "$APPLIED" | grep -c . 2>/dev/null || echo "0")
echo "=== Migration Status ==="
echo "Applied:  $applied_count"
echo "Pending:  ${#PENDING[@]}"
echo "Modified: ${#MODIFIED[@]}"

if [[ ${#MODIFIED[@]} -gt 0 ]]; then
  echo ""
  echo "WARNING: Previously applied migrations have been modified:"
  for m in "${MODIFIED[@]}"; do
    echo "  - $m"
  done
fi

if [[ ${#PENDING[@]} -gt 0 ]]; then
  echo ""
  echo "Pending migrations:"
  for p in "${PENDING[@]}"; do
    echo "  - $(basename "$p" .sql)"
  done
fi

if [[ "$STATUS_ONLY" == true ]]; then
  exit 0
fi

# --- Nothing to do? ---
if [[ ${#PENDING[@]} -eq 0 ]]; then
  echo ""
  echo "Nothing to apply."
  exit 0
fi

# --- Dry run? ---
if [[ "$DRY_RUN" == true ]]; then
  echo ""
  echo "(Dry run — no changes applied)"
  exit 0
fi

# --- Destructive migration guard ---
DESTRUCTIVE_PATTERNS='DROP[[:space:]]+TABLE|DROP[[:space:]]+COLUMN|TRUNCATE|DELETE[[:space:]]+FROM'

for file in "${PENDING[@]}"; do
  basename_f=$(basename "$file" .sql)
  # Check for destructive patterns (case-insensitive, skip SQL comments)
  if grep -iEq "$DESTRUCTIVE_PATTERNS" "$file" 2>/dev/null; then
    echo ""
    echo "WARNING: $basename_f contains potentially destructive operations:"
    grep -inE "$DESTRUCTIVE_PATTERNS" "$file" | head -5 | sed 's/^/  /'
    if [[ "$FORCE" != true ]]; then
      echo ""
      read -rp "Continue? (y/N) " confirm
      if [[ "$confirm" != [yY] ]]; then
        echo "Aborted."
        exit 1
      fi
    fi
  fi
done

# --- Backup ---
if [[ "$NO_BACKUP" == false ]]; then
  mkdir -p "$BACKUP_DIR"
  timestamp=$(date +%Y-%m-%d_%H-%M-%S)
  backup_file="$BACKUP_DIR/backup_${timestamp}.sql.gz"

  echo ""
  echo "Backing up database..."
  if pg_dump "$PGURL" --no-owner --no-privileges | gzip > "$backup_file"; then
    backup_size=$(du -h "$backup_file" | cut -f1)
    echo "Backup saved: $backup_file ($backup_size)"
  else
    echo "ERROR: Backup failed. Aborting migration."
    rm -f "$backup_file"
    exit 1
  fi

  # Prune old backups (keep last MAX_BACKUPS)
  backup_count=$(ls -1 "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null | wc -l)
  if [[ "$backup_count" -gt "$MAX_BACKUPS" ]]; then
    ls -1t "$BACKUP_DIR"/backup_*.sql.gz | tail -n +"$((MAX_BACKUPS + 1))" | xargs rm -f
    echo "Pruned old backups (keeping last $MAX_BACKUPS)"
  fi
fi

# --- Apply migrations ---
echo ""
echo "Applying ${#PENDING[@]} migration(s)..."

applied=0
for file in "${PENDING[@]}"; do
  basename_f=$(basename "$file" .sql)
  checksum=$(sha256sum "$file" | cut -d' ' -f1)

  echo "  Applying $basename_f..."
  if psql "$PGURL" -v ON_ERROR_STOP=1 -f "$file" > /dev/null; then
    # Record in tracking table
    psql "$PGURL" -q -c "
      INSERT INTO public.schema_migrations (version, checksum)
      VALUES ('$basename_f', '$checksum')
      ON CONFLICT (version) DO UPDATE SET checksum = '$checksum', applied_at = now();
    "
    echo "    Done."
    ((applied++))
  else
    echo "    FAILED. Stopping."
    echo ""
    echo "$applied migration(s) applied before failure."
    echo "Fix the issue in $basename_f and re-run."
    exit 1
  fi
done

echo ""
echo "All $applied migration(s) applied successfully."
