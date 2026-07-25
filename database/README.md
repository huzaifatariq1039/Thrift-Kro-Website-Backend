# 🗄️ Thrift Kro - Database Architecture & Management

This directory contains the database initialization scripts, PostgreSQL schema DDLs, Docker container configurations, and seed scripts for the Thrift Kro backend.

---

## 📁 Directory Structure

```text
database/
├── docker-compose.yml   # Docker Compose setup for PostgreSQL 15 & pgAdmin 4
├── schema.sql           # Raw PostgreSQL DDL script (tables, enums, indexes, constraints)
├── init_db.py           # Programmatic DB initializer (creates tables & seeds data)
├── seed_data.py         # Mock data seeder (users, products, orders, chat, reviews)
└── README.md            # Database management guide
```

---

## ⚡ Option A: Running PostgreSQL via Docker (Recommended)

If you do not have PostgreSQL installed locally on Windows, you can start a fully configured PostgreSQL 15 container + pgAdmin 4 in seconds using Docker:

```bash
# Navigate to the database directory
cd d:/FYP/Backend/database

# Launch PostgreSQL and pgAdmin containers
docker-compose up -d
```

### Container Endpoints:
* **PostgreSQL Database:** `localhost:5432`
  * **Database:** `thriftkro`
  * **User:** `postgres`
  * **Password:** `postgrespassword`
* **pgAdmin 4 Web Console:** `http://localhost:5050`
  * **Email:** `admin@thriftkro.com`
  * **Password:** `adminpassword`

---

## ⚡ Option B: Running Native PostgreSQL on Local Host

If you already have PostgreSQL installed natively on Windows:

1. Open **pgAdmin** or **psql** terminal.
2. Create the database:
   ```sql
   CREATE DATABASE thriftkro;
   ```
3. Ensure `.env` or `app/core/config.py` has your database URI:
   ```env
   DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/thriftkro
   ```

---

## 🛠️ Initializing Tables & Migrations

### 1. Programmatic Initialization & Seeding
Run the initialization script from the root backend directory:

```bash
python database/init_db.py
```

### 2. Alembic Migrations (Schema Revisions)
To generate Alembic migration history and sync the database:

```bash
# Generate migration script from SQLAlchemy models
alembic revision --autogenerate -m "Initial schema setup"

# Apply migrations to PostgreSQL
alembic upgrade head
```

---

## 🔐 Seed User Credentials for Testing

Once seeded, you can use these pre-configured accounts to test authentication and endpoints:

| Role | Email | Password | Details |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@thriftkro.com` | `admin123` | Full administrative permissions, stats access |
| **Verified Seller** | `seller1@thriftkro.com` | `seller123` | Approved seller, shop: *Retro Vibe Closet* |
| **Pending Seller** | `seller2@thriftkro.com` | `seller123` | Unverified seller, shop: *Urban Sneakerhead* |
| **Buyer 1** | `buyer1@thriftkro.com` | `buyer123` | Balance: 25,000 PKR |
| **Buyer 2** | `buyer2@thriftkro.com` | `buyer223` | Balance: 12,000 PKR |
