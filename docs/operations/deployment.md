# Backend deployment and database recovery

Application processes must never create tables, seed accounts, or run migrations at startup. The only schema authority is the committed Alembic chain.

## Environment promotion

1. Merge only after the backend CI workflow passes.
2. Deploy the same commit to staging with a separate PostgreSQL database and secrets.
3. Exercise authentication, checkout, cancellation/refund, payout, and seller review flows.
4. Record a production backup and its restore-verification result.
5. Promote the exact tested commit to production. Do not rebuild from a different branch or working tree.

Required runtime variables include `DATABASE_URL`, a unique `SECRET_KEY`,
`APP_ENV=production`, and explicit production `ALLOWED_ORIGINS`. Service
credentials belong in Railway variables, never source control. Production
startup fails if origins are missing or contain `*`; Swagger, ReDoc, and the
OpenAPI document are disabled in production. Missing origins deny all
cross-origin browser access in non-production environments. Development must
explicitly configure its local frontend origins. API docs are disabled by
default; set `ENABLE_API_DOCS=true` only in a controlled non-production
environment when they are needed.

## Release sequence

Railway runs `python -m scripts.migrate` as its pre-deploy command. The command:

- obtains a PostgreSQL transaction-scoped advisory lock so two releases cannot migrate concurrently;
- applies the committed Alembic chain to `head` in one controlled release phase;
- exits non-zero if the lock, connection, or migration fails, preventing the new deployment from receiving traffic.

The web process then starts without database mutations. Railway calls `/health/ready` and switches traffic only after the database is reachable and `alembic_version` exactly matches the code's migration head. `/health/live` checks only process liveness.

For a controlled manual release, use the same command:

```powershell
python -m scripts.migrate
python -m alembic current
```

Do not run `Base.metadata.create_all()`, ad-hoc `ALTER TABLE` scripts, or seed scripts in any deployed environment.

## Backup and restore verification

Take a provider snapshot and a portable PostgreSQL custom-format backup before a schema release:

```powershell
pg_dump --format=custom --no-owner --no-acl --file=thriftkro-before-release.dump $env:DATABASE_URL
```

Never test a restore over the production database. Restore into a newly created, isolated database and verify both the archive and migration state:

```powershell
createdb thriftkro_restore_verify
pg_restore --exit-on-error --no-owner --no-acl --dbname=thriftkro_restore_verify thriftkro-before-release.dump
$env:DATABASE_URL='postgresql://.../thriftkro_restore_verify'
python -m alembic current
python -m unittest discover -s tests -p "test_*.py" -v
```

Record the backup timestamp, source environment, restore database, verification result, and operator. Delete the isolated restore database only after verification.

## Failed release and rollback

- If the pre-deploy migration fails, keep the previous application deployment active, preserve the database, and diagnose the failed migration. Do not stamp the revision manually.
- Prefer a forward-fix migration. Production downgrades are allowed only when that exact downgrade was tested on a restored copy and no post-release data would be lost.
- Roll back application code only when the resulting schema is backward-compatible with the old version. Expand/contract changes must deploy additive schema first, compatible code second, and destructive cleanup in a later release.
- If data restoration is unavoidable, stop writes, restore the verified backup into a new database, validate it, then atomically switch `DATABASE_URL`. Preserve the failed database for investigation.

## Shutdown and incident checks

Railway sends the process a termination signal during replacement. Uvicorn gets 30 seconds for graceful shutdown, and the FastAPI lifespan handler disposes pooled database connections after in-flight work drains.

After every production release, verify:

- `/health/live` returns `200`;
- `/health/ready` returns `200`;
- `python -m alembic current` reports the expected head;
- login and a read-only catalog request succeed;
- error rate and PostgreSQL connection usage remain normal.

Railway's legacy `railway.json` configuration remains active for the existing service. Railway is retiring that format, so migrate the linked project to `.railway/railway.ts` with `railway config pull` before the platform cutoff; review the generated project/service identities before applying it.
