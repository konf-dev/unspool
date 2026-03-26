# Deploy Checklist

Run through this every time you push changes to production or modify the database.

## Pre-Push

```bash
# 1. Backend tests
cd backend && .venv/bin/pytest tests/ -v
cd ..

# 2. Frontend checks
cd frontend && npm test && npx tsc --noEmit && npm run build
cd ..

# 3. Migration status (if any DB changes)
./scripts/migrate.sh --dry-run
```

- [ ] All backend tests pass
- [ ] Frontend unit tests pass
- [ ] TypeScript compiles clean
- [ ] Frontend builds without errors
- [ ] No unexpected pending migrations

## Database (if schema changes)

```bash
# 4. Apply migrations (automatic backup + apply)
./scripts/migrate.sh

# Nuclear option — fresh DB (ONLY for dev/staging, never production with real users)
# See docs/v2/testing.md "Database Setup" for the full DROP + reapply sequence
```

- [ ] Migrations applied cleanly
- [ ] Backup created in `backups/`

## Backup (before every production push)

Supabase Free tier backups **cannot be restored**. Local `pg_dump` is your only safety net.

```bash
# 4b. Backup (automatic if running migrate.sh, manual otherwise)
#     migrate.sh creates both the backup AND a manifest with commit, schema, etc.
#     For a manual backup outside of migrations:
./scripts/migrate.sh --status    # this triggers a backup-less run, so use:

source .env
PGURL="${DATABASE_URL//+asyncpg/}"
TS=$(date +%Y-%m-%d_%H-%M-%S)
mkdir -p backups
pg_dump "$PGURL" --no-owner --no-privileges | gzip > "backups/backup_${TS}.sql.gz"

# To restore if something goes wrong:
# gunzip -c backups/backup_XXXX.sql.gz | psql "$PGURL"
```

- [ ] Fresh backup + manifest in `backups/` (either from `migrate.sh` or manual)

## Deploy

```bash
# 5. Commit and push
git add <files>
git commit -m "..."
git push origin main
```

- [ ] Committed with descriptive message
- [ ] Pushed to main
- [ ] Railway build started (check dashboard or `railway status`)
- [ ] Vercel build started (check dashboard or `vercel ls`)

Wait for both deploys to finish before continuing.

## Post-Deploy Verification

```bash
# 6. Quick health check
./scripts/diagnose.sh

# 7. API smoke test (36 tests — auth, chat, admin, GDPR)
cd backend
BASE_URL=https://api.unspool.life \
  EVAL_API_KEY=$EVAL_API_KEY \
  ADMIN_API_KEY=$ADMIN_API_KEY \
  .venv/bin/python ../eval/smoke_test.py
cd ..

# 8. LLM eval (promptfoo regression + Langfuse scoring)
./eval/run_eval.sh

# 9. Frontend E2E
cd frontend && npx playwright test
cd ..
```

- [ ] `diagnose.sh` — all green (CI, backend health, deep health, frontend, migrations)
- [ ] `smoke_test.py` — 36/36 passed
- [ ] `run_eval.sh` — promptfoo regression stable, Langfuse scores acceptable
- [ ] Playwright E2E — all specs pass

## Quick Reference

| What | Command | Time |
|------|---------|------|
| Backend tests | `cd backend && pytest -v` | ~10s |
| Frontend tests | `cd frontend && npm test` | ~5s |
| Migration status | `./scripts/migrate.sh --status` | ~2s |
| Apply migrations | `./scripts/migrate.sh` | ~30s |
| Diagnose prod | `./scripts/diagnose.sh` | ~15s |
| Smoke test | `python eval/smoke_test.py` | ~2min |
| Full eval | `./eval/run_eval.sh` | ~6min |
| E2E tests | `cd frontend && npx playwright test` | ~2min |

## When to Skip Steps

- **No DB changes?** Skip migrations, but still take a backup
- **Backend-only change?** Skip frontend tests and Playwright
- **Frontend-only change?** Skip backend tests, smoke test, and eval
- **Hotfix?** Minimum: backend tests + smoke test + diagnose
- **Prompt/config change?** Run full eval — that's the whole point of it
