# Thrift Kro Backend

FastAPI and PostgreSQL backend for the Thrift Kro multi-vendor marketplace.
This repository is the authority for API behavior and database migrations. The
sibling `D:\FYP\Database` folder contains legacy development assets and must
not be used to create, reset, migrate, or seed an application database.

## Current architecture

- FastAPI application mounted under `/api/v1`
- SQLAlchemy models backed by PostgreSQL
- Alembic as the only schema authority
- Buyer checkout represented by `CheckoutOrder`, split into one `SellerOrder`
  per seller with immutable `OrderItem` snapshots
- Fixed-precision PKR accounting and an immutable double-entry wallet ledger
- Session-bound access tokens, rotating refresh tokens, and backend-enforced
  buyer, seller, verified-seller, and administrator authorization
- Authenticated chat WebSockets with order-participant authorization
- Railway deployment gated by migrations and `/health/ready`

AI product verification and virtual try-on are not approved production
capabilities in this phase. Product-verification inference reports unavailable;
the existing VTON routes are legacy integration code and must not be presented
as a supported release feature.

## Local setup

The project targets the Python version in `.python-version` and installs from a
hash-locked dependency file.

```powershell
Copy-Item .env.example .env
python -m pip install --require-hashes -r requirements.txt
python -m scripts.migrate
python -m uvicorn app.main:app --reload
```

Set `DATABASE_URL`, a unique `SECRET_KEY` of at least 32 characters, and local
`ALLOWED_ORIGINS` in `.env`. Never commit live credentials. API documentation
is disabled by default; use `ENABLE_API_DOCS=true` only in a controlled
non-production environment.

### Existing pgAdmin database

For the existing local database, inspect migration state before doing anything:

```powershell
python -m alembic current
python -m alembic heads
```

If `alembic_version` already exists, run `python -m scripts.migrate`. If an old
database has application tables but no `alembic_version`, first take a backup,
then run the adoption checker in read-only mode:

```powershell
python -m scripts.adopt_existing_database
```

Use `--apply` only after the checker reports an exact compatible schema and the
database name is confirmed. Do not run `Base.metadata.create_all()`, raw schema
scripts, or seed scripts against an existing database.

## Commerce rules

- Checkout requires an `Idempotency-Key` header and locks cart and inventory
  rows before decrementing stock.
- Each seller order charges a 5 percent platform fee and PKR 200 shipping.
- Wallet payments are held and later settled through the ledger.
- Cash on delivery is recorded without creating fictitious wallet movement.
- Card checkout remains unavailable until a verified provider is integrated.
- Cancellation and refund transitions restore inventory and compensate wallet
  payments atomically.

## Quality checks

Run the complete suite against a disposable PostgreSQL database:

```powershell
$env:DATABASE_URL='postgresql://user:password@localhost:5432/postgres'
python -m scripts.run_postgres_tests
```

The script creates a database with a guarded `thriftkro_test_` name, applies all
migrations, runs contract and PostgreSQL integration tests, and removes only
that temporary database.

## Operations and reference material

- `Thrift_Kro_Backend_Documentation.docx` contains the verified architecture,
  API map, data model, and operator procedures.
- `docs/operations/deployment.md` defines release, readiness, backup, restore,
  and rollback procedures.
- `docs/operations/dependencies.md` defines dependency locking and audit rules.
- `docs/operations/observability.md` defines request correlation and audit-event
  handling.
- `docs/operations/kyc-data-protection.md` defines the fail-closed KYC policy.
- `docs/operations/media-lifecycle.md` defines upload ownership, public/private
  separation, retention, cleanup, and provider deletion procedures.
- `PRODUCTION_READINESS_AUDIT.md` is the historical audit and remediation
  backlog, not a description of current behavior.
