# Thrift Kro Production Readiness Audit

**Audit date:** 2026-10-13  
**Scope:** Current working trees at `D:\FYP\Backend`, `D:\FYP\Website`, `D:\FYP\Database`, and the locally present `D:\FYP\thrift kro vton engine`. Other sibling UI/VTON folders were treated as prototypes because the active Git repositories and integration code do not identify them as the deployed applications.  
**Method:** Read-only repository inspection; backend ORM/OpenAPI/import/Pydantic probes; frontend TypeScript checking and `npm audit`; dependency-manifest review; Git/status/history review; API-contract comparison; database DDL/model/migration comparison; and documentation inspection. No application data or external service was mutated, no dependency was installed, and no source/configuration/schema was changed.  
**Important snapshot note:** Before this report was created, Backend already contained 26 modified tracked files and 4 untracked source/script files, while Website contained 2 modified tracked files and an untracked `scratch/` directory. Findings describe those working trees, not only their last commits.

## 1. Executive Summary

Thrift Kro is an early-stage full-stack marketplace prototype. It has a recognizable FastAPI/React structure and a promising parent-order/vendor-sub-order model. Useful foundations include versioned routers, Pydantic schemas, SQLAlchemy relationships, bcrypt password hashing, expiring JWTs, backend role dependencies, product variants, seller verification, a React SPA with lazy routes, and an attempt to keep multi-vendor checkout atomic.

It is not production-ready. The most serious problems are exploitable or financially unsafe rather than stylistic: a public caller can register as an administrator; known fallback administrator credentials and a fallback JWT secret are active when environment variables are absent; any authenticated account can mint wallet balance; chat WebSockets accept an arbitrary sender identity without authentication; seller-controlled URLs are fetched by the server; migrations do not represent the runtime schema; checkout can oversell under concurrency; refund/cancellation transitions do not return money or stock; and escrow payout can double-credit under concurrent requests.

Several advertised paths are demonstrably broken end-to-end. The web checkout always reports success even when both backend order calls fail; frontend cart and product contracts disagree with the current API; order responses discard line items; chat history cannot satisfy its response model; and AI code references removed product fields. The standalone VTON service is an unauthenticated placeholder with an incompatible API, not the engine the backend calls. Three competing database definitions (Alembic, ORM/runtime `create_all`, and sibling `schema.sql`) describe materially different systems. No automated tests, CI pipeline, dependency health/readiness probe, controlled migration release, or production observability stack is present.

**Production-readiness score: 14/100**

| Area | Score | Rationale |
| --- | ---: | --- |
| Architecture | 32/100 | Reasonable layer names and multi-vendor order shape, but frontend/backend contracts, three schema authorities, and AI deployment paths are not aligned. |
| Backend | 25/100 | The app imports and exposes 53 HTTP paths plus 2 WebSockets, but critical privilege, finance, contract, and workflow defects remain. |
| Frontend | 18/100 | Buyer/seller/admin shells exist and routes are lazy-loaded, but checkout lies about success, core contracts drift, route/auth state is client-trusted, mock data remains user-facing, and TypeScript checking fails. |
| Database | 12/100 | Relational modeling is improving, but Alembic, ORM, and `schema.sql` are incompatible; bootstrap/seed tooling is stale; money uses floats; and essential constraints/indexes are absent. |
| Security | 10/100 | Public admin creation, default secrets/credentials, unauthenticated chat, SSRF, weak abuse controls, and unsafe media paths block launch. |
| Scalability | 22/100 | Pagination exists in a few places, but heavy synchronous AI, blocking I/O, unbounded reads, in-memory sockets, and contention hazards dominate. |
| Reliability | 8/100 | Checkout can falsely succeed, and there is no idempotency, locking, refund compensation, reliable provider handling, truthful readiness, or controlled migration flow. |
| Testing | 0/100 | No unit, integration, API, database, frontend, or end-to-end tests were found. |
| DevOps | 6/100 | Railway/Vercel/local Compose fragments exist, but they do not form a reproducible release; startup mutates schema/security data and there is no CI/CD, rollback, backup, or migration control. |
| Maintainability | 25/100 | Naming and folders are approachable, but cross-repository contract/schema drift, failed type checks, mocks, stale scripts, hardcoded policy, and no test safety net make changes unsafe. |

### Severity totals

| Critical | High | Medium | Low | Total |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 21 | 15 | 3 | 49 |

### Launch decision

**NO.** The current system cannot safely be deployed to production. A deployment would expose immediate administrator takeover and wallet fraud paths; legitimate concurrent commerce can corrupt inventory or balances; and the storefront can tell a customer that checkout succeeded when no order exists.

## 2. Current Technology Stack

| Layer | Detected technology |
| --- | --- |
| Language/runtime | Python; local virtual environment reports Python 3.14.0, while no deployment Python version is pinned |
| Web/API | FastAPI 0.139.2 installed; Uvicorn; REST-like JSON endpoints under `/api/v1`; OpenAPI/Swagger/ReDoc enabled |
| Persistence | PostgreSQL through SQLAlchemy 2.0 ORM and `psycopg2`; synchronous sessions inside FastAPI endpoints |
| Migrations | Alembic 1.18.5, plus ad-hoc SQL alteration scripts |
| Validation | Pydantic 2 and `pydantic-settings` |
| Authentication | Local email/password with Passlib/bcrypt; HS256 JWT bearer access tokens; Google ID/access-token login |
| Media | Cloudinary product-image upload; seller-supplied URLs for listing/KYC media |
| AI | Ultralytics YOLO, OpenCLIP, PyTorch, Pillow, NumPy; CPU/GPU selection at runtime |
| Virtual try-on | `gradio_client` calling a Hugging Face Space |
| Real time | FastAPI/Starlette WebSockets; in-process chat connection dictionary |
| Frontend | React 18, TypeScript 5.6, Vite 6, React Router 7, Zustand 5, Tailwind CSS 4, Recharts, Google OAuth |
| Frontend hosting | Vercel SPA rewrite configuration |
| Standalone VTON | Separate FastAPI/PyTorch/MediaPipe/SAM prototype hardcoded to CUDA; inference implementation is not active |
| Database tooling | PostgreSQL 15 Compose/pgAdmin plus standalone `schema.sql` and Python seeder; these disagree with Backend Alembic/ORM |
| Deployment | Railway/Nixpacks backend command, Vercel frontend configuration, development-only database Compose |
| Tests/quality | Flake8 is installed locally but not declared; Website has TypeScript but no typecheck/lint/test script; no repository has an automated test suite or CI configuration |

Backend `requirements.txt` contains unbounded top-level requirements except `bcrypt==3.2.2`; it is not a lockfile. The inspected virtual environment passed `pip check`, but that only confirms installed dependency consistency, not reproducibility or vulnerability absence. Website has a committed `package-lock.json`, but `npm audit` reported four high and one moderate advisories in the installed graph; applicability varies and is discussed under DEP-002. The VTON manifest also uses broad lower bounds and a live Git dependency.

## 3. Repository Structure

```text
FYP/
|-- Backend/                     Active FastAPI Git repository
|-- app/
|   |-- main.py                 FastAPI construction, CORS, startup schema creation/admin seeding
|   |-- api/
|   |   |-- deps.py             DB session, JWT identity, role/verification dependencies
|   |   `-- v1/
|   |       |-- api.py          Router composition
|   |       `-- routers/        Auth, users, products, categories, orders, wallet,
|   |                           shopping, sellers, admin, reviews, chat, AI, VTO,
|   |                           upload, stores, support
|   |-- core/                   Settings, SQLAlchemy engine/session, password/JWT helpers
|   |-- crud/                   Query and workflow functions; checkout and payouts live here
|   |-- models/                 SQLAlchemy domain tables/enums/relationships
|   |-- schemas/                Pydantic request and response contracts
|   `-- services/               Cloudinary upload and computer-vision services
|-- alembic/                    Alembic environment and three migrations
|-- database/                   Backend-local directory has no source; only ignored cache data
|-- alter_db.py                 Ad-hoc seller-verification schema changes
|-- alter_product_table.py      Untracked ad-hoc product schema changes
|-- railway.json                Nixpacks/Uvicorn deployment command
|-- requirements.txt            Unpinned direct dependencies
|-- .env.example                Example config containing unsafe credential/secret defaults
|-- Thrift_Kro_Backend_Documentation.docx
|                               Stale architecture/API/database documentation
|-- README.md                   One-line project title
|-- PRODUCTION_READINESS_AUDIT.md
|                               This report; the only file created/changed by this audit
|-- Website/                    Active React/Vite Git repository
|   |-- src/features/           Buyer, seller, admin, auth, landing/public pages
|   |-- src/services/api/       Browser API adapters plus legacy `src/services/api.ts`
|   |-- src/store/              Zustand application/UI state with live and mock state mixed
|   |-- src/contexts/           Authentication context
|   |-- src/router.tsx          Public/buyer/seller/admin routes and partial guards
|   |-- package.json / package-lock.json
|   `-- vercel.json             SPA fallback only
|-- Database/                   Standalone, non-Git database bootstrap artifacts
|   |-- schema.sql              Destructive full schema initializer; not equal to ORM/Alembic
|   |-- init_db.py / seed_data.py
|   `-- docker-compose.yml      Local PostgreSQL/pgAdmin with fixed development credentials
`-- thrift kro vton engine/    Separate unfinished FastAPI/CUDA VTON prototype
    |-- main.py                 `/vton`; currently returns a segmentation-mask placeholder
    |-- pipeline/               Preprocessing and incomplete inference implementation
    `-- requirements.txt        Unlocked ML/API dependencies
```

Other sibling folders (`Landing page`, `Thrift Kro Mobile App UI (Copy)`, old website/VTON copies and archives) were not treated as production sources. They are not referenced by the active Website/Backend deployment code and appear to be prototypes or snapshots.

Not present across the active system: CI/CD, tests, queue/worker, cron jobs, cache, payment-provider integration, infrastructure-as-code, monitoring/error tracking, or backup/restore tooling. Compose exists only for local database startup and is not a production deployment definition.

## 4. Current System Architecture

The actual system is a React single-page application in front of a synchronous layered FastAPI monolith, plus a separately developed but not contract-compatible VTON prototype.

```text
Browser
        |
        v
React/Vite SPA -> Zustand/AuthContext -> browser fetch/WebSocket adapters
        |
        v
FastAPI + CORS + OAuth2 bearer dependency
        |
        v
Versioned routers (authorization and some workflow decisions)
        |
        v
CRUD modules (queries + transactions + commerce/finance rules)
        |
        v
Synchronous SQLAlchemy session
        |
        v
PostgreSQL
```

Additional flows:

```text
Verified seller -> Upload API -> Cloudinary public image

Seller -> AI WebSocket -> YOLO/OpenCLIP in API process
                         -> HTTP GET seller-controlled listing URL
                         -> verification log/product flag in PostgreSQL

Authenticated user -> VTO endpoint -> local temp files
                                    -> Hugging Face/Gradio Space
                                    -> file response

Local VTON prototype -> `/vton` -> MediaPipe/SAM preprocessing
                                -> masked-image placeholder
                (not the `/process_vton` Gradio contract called by Backend)

WebSocket client -> in-memory chat manager -> PostgreSQL messages
                 (chat socket has no identity authentication)
```

The browser also maintains a parallel local marketplace state. Cart, KYC, addresses, cards, preferences, seller stock, notifications, and role selection can be mutated locally even when the API rejects or never receives the operation. The routers and CRUD modules are tightly coupled to SQLAlchemy entities and transaction commits. There is no application-service/unit-of-work boundary, generated/shared API contract, payment adapter, ledger boundary, storage abstraction, or background job boundary. This remains suitable for a modular monolith, but it is not safely modular today.

## 5. Current Domain Model

### Implemented model

```text
User
|-- 0..1 SellerProfile --< SellerVerificationRequest
|-- 0..1 Wallet --< Transaction
|-- * UserAddress
|-- * Product
|-- 0..1 CartSession --< CartItem >-- ProductVariant
`-- * WishlistItem >-- Product

Category --< Product --< ProductVariant
                   |--< ProductImage
                   |--< ProductTag
                   `--< VerificationLog

CheckoutOrder (buyer, address reference, payment method, total)
`--< SellerOrder (seller, subtotal, shipping, fee, state)
    |--< OrderItem >-- ProductVariant
    `--< OrderStatusHistory

Review -> User + Product + optional OrderItem
SupportTicket -> User + optional SellerOrder
Message -> sender + receiver + optional SellerOrder
Notification -> User (model only; no delivery/use path)
```

### Multi-vendor fitness

The `CheckoutOrder -> SellerOrder -> OrderItem` split is the correct basic shape for a cart containing multiple vendors. Each sub-order can carry its seller, totals, fulfillment status, tracking data, and payout state. That foundation should be retained.

It is incomplete for production: there is no payment/charge entity, escrow account, immutable accounting entry pair, refund/return entity, payout batch, settlement/reconciliation record, shipment entity, order address snapshot, tax/discount allocation, or idempotency key. Vendor staff and scoped store permissions do not exist; seller ownership is a direct `Product.seller_id -> User` relationship.

### Feature state summary

| Capability | State |
| --- | --- |
| Users/roles, seller profiles, KYC requests | Implemented but security/privacy controls are incomplete |
| Catalog, categories, images, variants, SKU, tags | Implemented; migration and update integrity defects exist |
| Inventory | Single integer per variant; no reservation, warehouse, movement ledger, or locking |
| Cart/wishlist | Authenticated only; no guest merge; uniqueness is not database-enforced |
| Multi-vendor order split | Implemented structurally |
| Wallet/transactions/escrow | Prototype only; not a trustworthy ledger or real funding mechanism |
| Card/COD payments | Enum/state placeholders; no provider or settlement architecture |
| Refunds/cancellations/disputes | Status values only; financial and inventory compensation is missing |
| Commissions/payouts | Hardcoded fee and direct wallet mutation; no payable/reconciliation model |
| Shipping | Flat constant and free-text tracking; no shipment/rate integration |
| Taxes/coupons/promotions/invoices | Missing |
| Reviews/ratings | Implemented with manipulation and concurrency weaknesses |
| Notifications | Table only; no API, producer, or delivery mechanism |
| Search | Database `ILIKE`; no ranking or scalable index |
| Frontend portals | Buyer, seller, and admin shells exist; live API and mock/local behavior are mixed, and critical contracts are broken |

## 6. Critical Issues

### [SEC-001] Public callers can create administrator accounts

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Authentication / Authorization  
**Location:** `app/schemas/user.py:9-22`, `app/api/v1/routers/auth.py:16-21`, `app/api/v1/routers/auth.py:118-125`  
**Related Components:** Registration, Google login, admin APIs

**Problem:** `UserCreate` and `GoogleAuthRequest` accept the complete `RoleEnum`, including `ADMIN`, and both public authentication paths pass the role into user creation. A runtime probe successfully validated public payloads with `role="ADMIN"`.

**Why It Matters:** Any unauthenticated person can obtain full admin access, view KYC data and users/orders/tickets, approve sellers, and deactivate accounts.

**Evidence:** `/auth/register` passes the caller-owned schema directly to `create_user`; Google signup passes `body.role` to `create_google_user`. No allowlist limits public signup to buyer/seller.

**Failure Scenario:** An attacker registers once with an admin role, logs in, then invokes every endpoint guarded by `get_current_admin`.

**Recommended Direction:** Separate public signup commands from privileged role assignment; provision/admin-promote only through a controlled, audited channel.

**Dependencies:** Emergency prerequisite for all other authorization work.

### [SEC-002] Known fallback JWT secret and administrator credentials are active defaults

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Security / Configuration  
**Location:** `.env.example:7-14`, `app/core/config.py:14-22`, `app/main.py:47-67`  
**Related Components:** JWT, admin provisioning, every protected API

**Problem:** Source control contains a reusable JWT secret and administrator password, and runtime settings fall back to the same values. Startup creates the default admin if the configured email is absent. The inspected ignored `.env` does not define `SECRET_KEY`, `ADMIN_EMAIL`, or `ADMIN_PASSWORD`, so this checkout uses the fallbacks. Secrets are redacted here: `SECRET_KEY=09d25e09****`, `ADMIN_PASSWORD=Admin****`.

**Why It Matters:** Knowledge of the secret permits token forgery; knowledge of the default password permits direct administrator login.

**Evidence:** Settings use `os.getenv(..., hardcoded_default)` and startup calls `create_user` with those settings.

**Failure Scenario:** A deployment omits one or more variables; an attacker signs an admin JWT or logs into the auto-provisioned admin.

**Recommended Direction:** Require high-entropy secrets and explicit bootstrap credentials, fail closed, rotate exposed values, and use one-time audited provisioning.

**Dependencies:** Revoke/rotate after SEC-001 is closed; existing tokens/accounts require incident review.

### [PAY-001] Any authenticated user can mint spendable wallet funds

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Payments / Financial Integrity  
**Location:** `app/api/v1/routers/wallet.py:17-21`, `app/crud/wallet.py:15-42`, `app/crud/order.py:175-246`  
**Related Components:** Wallet, checkout, escrow, payouts

**Problem:** `/wallet/deposit` immediately increases the caller's balance and records a completed deposit using only a client-provided amount. There is no payment provider, authorization, settlement, webhook, or admin approval.

**Why It Matters:** Fabricated balances are accepted by checkout as paid funds and later paid to sellers, converting a trivial API call into platform loss.

**Evidence:** `deposit_funds` performs `wallet.balance + amount` and commits `Transaction(status="COMPLETED")`; wallet checkout only compares and deducts that balance.

**Failure Scenario:** An attacker deposits PKR 1,000,000, buys an accomplice's items, marks delivery, and releases escrow to the accomplice wallet.

**Recommended Direction:** Disable self-credit; introduce provider-confirmed funding and an immutable double-entry ledger before wallet payments are accepted.

**Dependencies:** SEC-001/SEC-002, DB-003, PAY-003, PAY-004.

### [SEC-003] Chat WebSocket is unauthenticated and trusts a path sender ID

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Security / Authorization  
**Location:** `app/api/v1/routers/chat.py:32-52`  
**Related Components:** Messaging, users, database, privacy

**Problem:** `/chat/ws/chat/{user_id}` accepts the socket before authentication and stores each message with the path value as `sender_id`. The receiver ID and content are also caller-controlled.

**Why It Matters:** Anyone can impersonate any account, inject persistent messages, harass users, and poison evidence associated with disputes/orders.

**Evidence:** The WebSocket endpoint has no token/dependency validation and directly constructs `Message(sender_id=user_id, receiver_id=receiver_id, ...)`.

**Failure Scenario:** An attacker connects using a seller's UUID and sends fraudulent payment/shipping instructions to buyers.

**Recommended Direction:** Authenticate the socket before acceptance, derive sender identity from the token, authorize the conversation/order, validate payloads, and add abuse controls.

**Dependencies:** AUTH-001, OBS-001.

### [SEC-004] AI verification performs SSRF against seller-controlled URLs

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Security / SSRF  
**Location:** `app/schemas/product.py:10-12`, `app/api/v1/routers/ai.py:290-307`, `app/services/cv_service.py:341-350`  
**Related Components:** Products, AI WebSocket, internal network, cloud metadata

**Problem:** Product image URLs are caller-controlled. The AI workflow fetches each URL with `requests.get` without scheme/host/IP allowlisting, redirect restrictions, response-size limits, or network egress controls.

**Why It Matters:** A verified seller can make the application query loopback, private-network services, or cloud metadata endpoints and may extract data through image parsing/outcome side channels.

**Evidence:** `load_image_from_url(url)` calls `requests.get(url, timeout=10)` directly.

**Failure Scenario:** A seller stores a metadata/private-service URL as a listing image, starts verification, and causes backend-originated network requests.

**Recommended Direction:** Use platform-controlled media identifiers, fetch only approved storage origins, validate resolved addresses and redirects, cap bytes, and isolate media processing egress.

**Dependencies:** UPLOAD-001 and the storage boundary in the target architecture.

### [DB-001] Three incompatible schema authorities make database creation unsafe

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Database / Deployment  
**Location:** `alembic/versions/*.py`, `app/models/*.py`, `../Database/schema.sql`, `../Database/init_db.py`, `../Database/seed_data.py`  
**Related Components:** All persistence and deployments

**Problem:** Alembic creates the old single-product/single-seller design (`orders`, old `products`, old `cart_items`, `messages.timestamp`). Runtime metadata expects categories, variants/images/tags, cart sessions, addresses, checkout/seller orders, line/history tables, transactions, notifications, and renamed columns/enums. Sibling `schema.sql` describes much of the new normalized shape but still omits or disagrees on current fields/tables, including verification logs and seller/KYC/notification fields. Its Python seeder imports the removed `Order` model and populates removed flat product fields. No source is authoritative.

**Why It Matters:** Alembic, Docker SQL initialization, or Python bootstrap each produce a different database. `create_all` cannot alter incompatible existing tables, so startup does not repair drift. `schema.sql` also begins by dropping the entire `public` schema and grants it to `public`, making accidental manual use destructive and overly permissive.

**Evidence:** Runtime metadata contains 23 tables and materially different columns. `Database/docker-compose.yml` mounts only `schema.sql`; `init_db.py` depends on Backend imports but its documented path/working directory is wrong; `seed_data.py` imports `Order` and uses fields absent from current ORM. README documents port 5432 while Compose publishes 5433 and gives conflicting credentials.

**Failure Scenario:** A production database is initialized by one advertised method, then requests or seeding fail with missing tables/columns/enums; an operator tries the raw SQL against an existing database and erases its public schema.

**Recommended Direction:** Establish one verified schema baseline and forward-only migration chain, test it from empty and representative existing databases, and remove runtime DDL authority.

**Dependencies:** Must precede all schema-dependent fixes and deployment automation.

### [INV-001] Checkout can oversell inventory under concurrency

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Inventory / Orders  
**Location:** `app/crud/order.py:105-143`, `app/crud/order.py:217-252`, `app/models/product.py:66-76`  
**Related Components:** Checkout, stock, orders, wallet

**Problem:** Checkout reads stock, later decrements ORM objects, and commits without a row lock, atomic conditional update, serializable retry, or reservation. Negative values are silently clamped to zero, hiding the conflict.

**Why It Matters:** Concurrent buyers can both pass validation and create paid orders for the same unit.

**Evidence:** There is no `FOR UPDATE`/version column/check constraint; `variant.quantity_in_stock -= quantity` occurs after an unlocked read.

**Failure Scenario:** Two requests observe stock `1`; both create orders and deduct funds; both commit, leaving two obligations for one item.

**Recommended Direction:** Define reservation/decrement semantics and enforce them atomically in the database with idempotent checkout behavior.

**Dependencies:** DB-001, ORDER-001, DB-002.

### [PAY-002] Cancellation and refund states do not return money or inventory

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Orders / Payments / Inventory  
**Location:** `app/crud/order.py:34-45`, `app/crud/order.py:331-384`  
**Related Components:** Wallet, stock, status transitions, disputes

**Problem:** The state machine permits `CANCELLED` and `REFUNDED`, including from paid states, but `update_order_status` only changes the status/timestamps/history. It does not restore stock, credit the buyer, reverse fees, or record financial entries.

**Why It Matters:** Administratively cancelling or refunding a paid order loses customer funds and leaves inventory wrong while the UI/database claims resolution.

**Evidence:** Status-specific logic handles only `SHIPPED` and `DELIVERED`.

**Failure Scenario:** Admin resolves a dispute as refunded; the status becomes `REFUNDED`, but the buyer balance remains reduced and seller/platform accounting is unchanged.

**Recommended Direction:** Model refund/cancellation commands with explicit, atomic inventory and ledger compensation plus idempotency.

**Dependencies:** DB-003, PAY-004, INV-001.

### [PAY-003] Concurrent escrow release can double-credit a seller

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Payouts / Concurrency  
**Location:** `app/crud/order.py:389-459`  
**Related Components:** Seller wallet, transactions, order status

**Problem:** `release_escrow` checks `DELIVERED`, reads the seller wallet, increments the balance, inserts a transaction, and changes status without locking or a unique idempotency constraint.

**Why It Matters:** Two simultaneous release requests can both observe `DELIVERED` and pay the same order twice.

**Evidence:** No row lock, version check, unique `(reference_type, reference_id, type)` constraint, payout entity, or conditional status update exists.

**Failure Scenario:** A buyer retries while an admin releases the same escrow; both transactions commit seller credits.

**Recommended Direction:** Create an idempotent payout command backed by row locking/conditional transition and a unique immutable ledger reference.

**Dependencies:** DB-001, DB-003, OBS-001.

### [FE-001] The storefront reports checkout success when no order was created

**Severity:** Critical  
**Confidence:** Confirmed  
**Area:** Frontend / Checkout / Order Integrity  
**Location:** `../Website/src/store/useAppStore.ts:354-375`, `../Website/src/services/api/buyerService.ts:53-77`, `app/api/v1/routers/shopping.py:90-134`, `app/schemas/order.py:9-16`  
**Related Components:** Buyer cart, checkout, inventory, wallet, order confirmation

**Problem:** The primary cart checkout adapter expects `order_ids`, but Backend returns singular `order_id`, so a legitimate successful response does not satisfy the frontend condition. The fallback then posts a legacy body containing `product_id` and free-text `shipping_address`, while the current `OrderCreate` expects `shipping_address_id` and `payment_method`. If either or both calls fail, `checkoutAsync` still clears the cart, opens the purchase-success state, updates local stock/notifications, and returns `true` unconditionally.

**Why It Matters:** The customer can receive a positive purchase confirmation without a persisted order, reserved item, or payment. This is a severe incorrect-order path and can create support disputes, lost sales, and false fulfillment expectations.

**Evidence:** The final statements after both catches are `handlePurchaseComplete(items); return true;`. The frontend and backend response/request contracts were compared directly; no matching `order_ids` response or legacy single-product contract exists.

**Failure Scenario:** A logged-in buyer clicks Checkout while the API returns 422, 500, or is unavailable. The UI empties the cart and shows success, but sellers/admins have no order and the backend stock/balance remains unchanged.

**Recommended Direction:** Treat checkout as a single server-authoritative, versioned contract; confirm success only from the persisted order response; preserve/reconcile the cart on failure; and cover the exact browser-to-API flow with contract and end-to-end tests.

**Dependencies:** ORDER-001, API-001, FE-002, TEST-001.

## 7. High Severity Issues

### [PAY-004] CARD and COD are placeholders, not payment/settlement implementations

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Payments  
**Location:** `app/models/order.py:9-23`, `app/crud/order.py:175-185`, `app/crud/order.py:413-426`  
**Related Components:** Checkout, order state, commission, reconciliation

**Problem:** There is no payment provider, payment entity, webhook, signature verification, or reconciliation. `CARD` and COD orders start `PENDING_PAYMENT`; sellers are only authorized to request `PROCESSING`/`SHIPPED`, while the state machine allows `PENDING_PAYMENT` only to paid/cancelled. COD completion marks payout complete without recording collection or platform commission.

**Why It Matters:** Card orders cannot be paid and normal COD orders cannot enter fulfillment; COD revenue/commission is unaccounted.

**Evidence:** Route inventory contains no payment intent/callback/webhook endpoint.

**Failure Scenario:** A valid COD order remains permanently pending unless an admin manually changes it; the platform later reports completion without settlement evidence.

**Recommended Direction:** Decide supported launch methods and implement provider/COD state, verification, webhook idempotency, settlement, and reconciliation explicitly.

**Dependencies:** PAY-001, DB-003, ORDER-001.

### [AI-001] Sellers can self-assert AI verification and the legacy verifier returns random results

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Product Trust / AI  
**Location:** `app/schemas/product.py:83-89`, `app/api/v1/routers/products.py:126-139`, `app/crud/product.py:94-117`, `app/services/cv_service.py:369-386`  
**Related Components:** Listings, buyer trust, moderation

**Problem:** Product creation accepts client-owned `is_ai_verified` and persists it. The legacy `/ai/verify-product` endpoint labels authenticity and condition using random choices.

**Why It Matters:** Verification badges/results can be fabricated and may mislead buyers or moderation.

**Evidence:** A runtime probe validated `ProductCreate(..., is_ai_verified=True)`; CRUD writes that value directly.

**Failure Scenario:** A verified seller creates a counterfeit listing already marked AI verified without running the pipeline.

**Recommended Direction:** Make verification fields server-owned, remove/mock-label non-production inference, and tie badges to immutable verification events.

**Dependencies:** API-002, SEC-004.

### [ORDER-001] Checkout lacks request idempotency and complete server-side eligibility checks

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Checkout  
**Location:** `app/api/v1/routers/orders.py:24-44`, `app/api/v1/routers/shopping.py:90-134`, `app/crud/order.py:105-173`  
**Related Components:** Cart, products, orders, inventory, wallet

**Problem:** Two checkout endpoints call the same non-idempotent workflow. Retries can create duplicates. Checkout checks deletion/stock but not `Product.status`, seller eligibility, price/version freshness policy, or buyer role. Shipping address is optional.

**Why It Matters:** Network retries can duplicate orders; archived/draft/out-of-stock-status products can be purchased if variant stock remains; incomplete orders can be created.

**Evidence:** No idempotency key/order-attempt record exists; endpoints use `get_current_active_user`, not `get_current_buyer`.

**Failure Scenario:** A client times out after commit and retries, creating another order and deduction; or buys a product archived after it entered the cart.

**Recommended Direction:** Create one idempotent checkout application command with complete eligibility and immutable pricing/shipping inputs.

**Dependencies:** INV-001, DB-003, PAY-004.

### [ORDER-002] Orders do not preserve immutable fulfillment and product snapshots

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Orders / Data Integrity  
**Location:** `app/models/order.py:25-74`, `app/models/user.py:59-76`  
**Related Components:** Fulfillment, disputes, history, privacy

**Problem:** Checkout stores nullable foreign keys to mutable addresses and variants. Order items snapshot only price and quantity, not product/SKU/name/image/tax/discount/currency. Address edits/deletion and catalog changes alter or erase the meaning shown for historical orders.

**Why It Matters:** Shipping, invoices, support, disputes, and accounting require the exact purchase-time data.

**Evidence:** `shipping_address_id` uses `SET NULL`; `OrderItem` contains `product_variant_id`, `price_at_purchase`, and `quantity` only.

**Failure Scenario:** A customer edits an address after ordering or a seller changes/replaces a variant; fulfillment/history no longer represents the purchase.

**Recommended Direction:** Store immutable address and line snapshots, currency, allocations, and provider references on the order domain.

**Dependencies:** DB-001 and business decisions on invoice/tax/shipping.

### [API-001] Order API responses silently omit every line item

**Severity:** High  
**Confidence:** Confirmed  
**Area:** API / Backend  
**Location:** `app/models/order.py:60`, `app/schemas/order.py:44-61`  
**Related Components:** Buyer orders, seller fulfillment, admin orders

**Problem:** ORM relationship is `order_items`, while the response schema expects `items` without an alias/validator. Because `items` defaults to an empty list, serialization succeeds but discards real lines.

**Why It Matters:** Buyers, sellers, and admins cannot reliably see what was ordered, which blocks fulfillment and support.

**Evidence:** Runtime contract probe produced `orm_order_items=1` and `seller_order_items_serialized=0`.

**Failure Scenario:** Seller receives an order response with no items and cannot pack it.

**Recommended Direction:** Align response contracts with domain DTOs and add API contract tests.

**Dependencies:** TEST-001.

### [API-002] AI status and WebSocket flows reference removed product fields

**Severity:** High  
**Confidence:** Confirmed  
**Area:** API / AI  
**Location:** `app/api/v1/routers/ai.py:90-103`, `app/api/v1/routers/ai.py:163-169`, `app/models/product.py:40-64`  
**Related Components:** Product verification

**Problem:** AI code reads `condition_score`, `verified_at`, and `image_url`, which do not exist on the current Product model. `images` is now a relationship of `ProductImage` objects, but the fetcher expects strings; `category` is an ORM object, not the string response expects.

**Why It Matters:** Advertised verification endpoints fail before completing their primary function.

**Evidence:** Runtime attribute probe confirmed the removed attributes; the first `product.image_url` access raises `AttributeError`.

**Failure Scenario:** Status lookup or WebSocket verification for a valid product returns an internal error/disconnect.

**Recommended Direction:** Define one current verification DTO/model and cover both endpoints with integration tests.

**Dependencies:** AI-001, DB-001, TEST-001.

### [DB-002] Monetary values use binary floating point and lack robust database checks

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Database / Finance  
**Location:** `app/models/user.py:102-126`, `app/models/product.py:40-76`, `app/models/order.py:25-74`  
**Related Components:** Prices, balances, fees, totals, transactions

**Problem:** Every monetary field uses `Float`; important non-negative/quantity/fee invariants are not database constraints. Python rounding is applied inconsistently.

**Why It Matters:** Binary rounding and unconstrained writes can create reconciliation drift or invalid balances/totals.

**Evidence:** Wallet balance, transaction amount, price, adjustment, subtotal, shipping, platform fee, and totals are `Float`.

**Failure Scenario:** Repeated fees/payouts accumulate cent-level mismatches, or a future code path persists a negative stock/balance.

**Recommended Direction:** Standardize minor units or fixed-precision numeric types and enforce invariants in the database.

**Dependencies:** DB-001; migrate before ledger/payment launch.

### [DB-003] Wallet transactions are not an auditable or concurrency-safe ledger

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Database / Payments  
**Location:** `app/models/user.py:102-128`, `app/crud/wallet.py`, `app/crud/order.py:232-246`, `app/crud/order.py:428-458`  
**Related Components:** Wallet, escrow, payouts, reconciliation

**Problem:** Balance is a mutable aggregate; transactions are single-sided records with free-text status/reference fields, no uniqueness/idempotency, no counter-account, and no reconciliation invariant. Balance updates are unlocked read-modify-write operations.

**Why It Matters:** Concurrent changes can be lost, entries can duplicate, and the platform cannot prove that assets, liabilities, fees, and payouts balance.

**Evidence:** `reference_id` is not a foreign key and no constraint associates one financial action with exactly one ledger entry.

**Failure Scenario:** Deposit/checkout/payout requests overlap and one balance update overwrites another; transaction rows do not explain the final balance.

**Recommended Direction:** Introduce an immutable, idempotent double-entry ledger/application boundary and derive or transactionally maintain balances.

**Dependencies:** PAY-001 through PAY-004 and DB-002.

### [DB-004] Product updates destructively replace variants referenced by orders/carts

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Database / Catalog  
**Location:** `app/crud/product.py:245-299`, `app/models/order.py:63-75`, `app/models/shopping.py:19-29`  
**Related Components:** Catalog, orders, carts

**Problem:** Updating variants bulk-deletes all existing variants and inserts replacements. Order items use `RESTRICT`, so purchased variants can make updates fail; cart rows use `CASCADE`, so an update can silently remove shoppers' items.

**Why It Matters:** Normal catalog edits can generate 500 errors or destructive side effects and sever stable SKU identity.

**Evidence:** `db.query(ProductVariant)...delete()` runs before replacement without per-variant lifecycle rules.

**Failure Scenario:** Seller edits images and variants on a sold product; the transaction fails on the order FK, or carts disappear on an unsold product.

**Recommended Direction:** Use stable variant identities, explicit create/update/archive semantics, and protect referenced variants.

**Dependencies:** DB-001, ORDER-002.

### [UPLOAD-001] Upload and frame paths allow memory/compute denial of service and weak type validation

**Severity:** High  
**Confidence:** Confirmed  
**Area:** File Upload / Security  
**Location:** `app/services/upload.py:16-54`, `app/api/v1/routers/ai.py:71-85`, `app/services/cv_service.py:320-338`, `app/api/v1/routers/vto.py:54-95`  
**Related Components:** Cloudinary, AI, VTO, API workers

**Problem:** Cloudinary upload reads the complete body before enforcing 5 MB and trusts the client MIME header. AI upload/frames and both VTO images have no byte/pixel/dimension limits; base64 decoding and Pillow/model processing occur in-process.

**Why It Matters:** Large or decompression-bomb images can exhaust memory/CPU. MIME spoofing and provider/parser behavior become the only content defense.

**Evidence:** `await file.read()` precedes size rejection; other paths stream/copy/process without limits.

**Failure Scenario:** A small number of authenticated requests uploads huge images or repeated frames and exhausts the single API process.

**Recommended Direction:** Enforce streaming byte limits, decoded dimension limits, magic-byte validation, safe re-encoding, quotas, and isolated processing.

**Dependencies:** PERF-001, SEC-004.

### [PERF-001] Heavy and blocking AI/VTO work runs inside API request processes

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Performance / Reliability  
**Location:** `app/api/v1/routers/vto.py:37-118`, `app/api/v1/routers/ai.py:71-368`, `app/services/cv_service.py`  
**Related Components:** Event loop, model memory, external providers

**Problem:** Async endpoints call `time.sleep`, synchronous `client.predict`, image downloads, YOLO, and CLIP. Models load lazily in the API process and may download weights at runtime.

**Why It Matters:** One slow inference blocks event-loop capacity, consumes large memory per deployment, and creates unpredictable cold starts/timeouts.

**Evidence:** `time.sleep(2)` and `time.sleep(1.5)` appear inside async handlers; no job boundary or concurrency cap exists.

**Failure Scenario:** A few concurrent AI requests make ordinary auth/cart/order APIs unavailable or crash the instance.

**Recommended Direction:** Apply strict quotas/timeouts now; move truly long-running inference to a bounded worker only when needed, without splitting the whole application into microservices.

**Dependencies:** UPLOAD-001, OBS-001.

### [AUTH-001] Essential authentication lifecycle and abuse controls are absent

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Authentication  
**Location:** `app/api/v1/routers/auth.py`, `app/core/security.py`, `app/api/deps.py`  
**Related Components:** Accounts, login, tokens

**Problem:** There is no login/registration rate limit, lockout, email verification, password reset, account recovery, refresh-token rotation, logout/revocation, session inventory, or security event trail. Access tokens last 24 hours.

**Why It Matters:** Credential stuffing and brute force are unmitigated; compromised tokens remain valid; users cannot securely recover accounts.

**Evidence:** Route inventory contains only register/login/google; token validation checks signature/expiry and current user only.

**Failure Scenario:** Automated login attempts continue indefinitely, or a stolen bearer token remains usable until expiry.

**Recommended Direction:** Define account verification/recovery and token lifecycle, add layered rate limits, and record security events.

**Dependencies:** SEC-001/SEC-002 first.

### [REVIEW-001] Unverified reviews affect seller ratings and ranking

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Reviews / Marketplace Integrity  
**Location:** `app/crud/review.py:14-79`, `app/api/v1/routers/stores.py:10-18`  
**Related Components:** Seller rating, ranking, trust

**Problem:** Purchase verification only sets a flag; every authenticated user's review still updates seller aggregates. Duplicate prevention is application-only and rating updates are unlocked.

**Why It Matters:** Attackers can manipulate seller reputation/ranking across products; concurrent reviews can lose aggregate updates.

**Evidence:** Aggregate recalculation runs regardless of `is_verified`; rankings sort those fields directly.

**Failure Scenario:** Coordinated buyer accounts review unsold products and elevate or damage a store.

**Recommended Direction:** Decide eligibility policy, enforce it and uniqueness in the database, and compute aggregates safely.

**Dependencies:** DB-005, business decision on review eligibility.

### [PRIV-001] KYC identity data lacks a defined private-storage and retention model

**Severity:** High  
**Confidence:** Potential Risk  
**Area:** Privacy / Data Protection  
**Location:** `app/models/user.py:78-100`, `app/models/seller_verification.py`, `app/schemas/seller_verification.py`  
**Related Components:** CNIC, addresses, phone numbers, document URLs

**Problem:** Full CNIC numbers and document URLs are stored and returned to admins; no encryption/tokenization, private object authorization, retention/deletion, consent, access audit, or breach response policy is represented. Seller verification accepts arbitrary externally hosted URLs.

**Why It Matters:** KYC documents are high-impact personal data. A database, URL, admin account, or storage exposure could disclose identity documents.

**Evidence:** Plain strings/JSON contain CNIC and proof URLs; no storage/privacy service or audit table exists.

**Failure Scenario:** A leaked URL or compromised admin exposes permanent public KYC images and full identity fields.

**Recommended Direction:** Confirm legal/business retention rules, use private encrypted object storage with short-lived access, minimize fields, and audit every access.

**Dependencies:** Business/legal decisions and OBS-001.

### [TEST-001] The repository has no automated tests

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Testing / QA  
**Location:** Repository-wide  
**Related Components:** All

**Problem:** No test files/configuration were found for unit, integration, API, database, contract, security, or end-to-end coverage.

**Why It Matters:** Critical financial and authorization behavior can regress silently; current contract/schema defects reached the working tree undetected.

**Evidence:** Relevant-file discovery found zero tests; Flake8 reported issues and runtime probes found broken contracts.

**Failure Scenario:** A role, migration, or payout change is deployed without detecting privilege escalation, double payment, or response breakage.

**Recommended Direction:** Build a risk-led suite after emergency controls/schema baseline: auth/RBAC, vendor isolation, checkout concurrency, payment idempotency, refunds, payouts, migrations, and API contracts first.

**Dependencies:** Stabilize DB/payment contracts enough to test intentionally.

### [DEVOPS-001] Deployment mutates schema and security data at application startup

**Severity:** High  
**Confidence:** Confirmed  
**Area:** DevOps / Reliability  
**Location:** `app/main.py:40-68`, `railway.json`  
**Related Components:** Database, admin, scaling, rollback

**Problem:** Every process calls `Base.metadata.create_all()` and may provision an admin during startup. Railway starts Uvicorn directly with no controlled migration step. There are no health/readiness probes, graceful-shutdown plan, rollback procedure, backup/restore instructions, CI/CD, or environment promotion controls.

**Why It Matters:** Startup side effects race across instances, do not upgrade schemas, and couple availability to unsafe bootstrap behavior.

**Evidence:** `railway.json` contains only a start command and restart policy.

**Failure Scenario:** A new release starts against an incompatible schema, repeatedly restarts, or partially provisions while no safe rollback/migration gate exists.

**Recommended Direction:** Make startup read-only, run tested migrations as an explicit release step, add liveness/readiness, CI gates, rollback, and verified backup/restore.

**Dependencies:** DB-001, SEC-002, TEST-001.

### [OBS-001] Financial, security, and administrative actions are not observable or auditable

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Observability / Audit  
**Location:** Repository-wide; `app/models/order.py:77-86`, `app/crud/order.py:331-384`  
**Related Components:** Admin, orders, payouts, security, support

**Problem:** There are no request IDs, structured application logs, metrics, traces, error tracking, alert rules, security logs, or admin audit log. `actor_id` is accepted during status changes but never stored; order history records only status/notes.

**Why It Matters:** Fraud, double payments, data access, and incidents cannot be reconstructed or alerted on reliably.

**Evidence:** Logging is limited to AI/VTO messages and startup `print`; no observability dependencies/config are present.

**Failure Scenario:** A payout discrepancy or unauthorized admin action occurs and the platform cannot identify the actor, request, before/after state, or correlated provider event.

**Recommended Direction:** Add structured redacted logs, correlation IDs, error tracking, business/security metrics, and append-only actor-aware audit events.

**Dependencies:** Define data/privacy redaction before logging PII.

### [DEP-001] Dependencies and runtime are not reproducible

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Dependencies / Supply Chain  
**Location:** `requirements.txt`, `railway.json`  
**Related Components:** Build, AI, security

**Problem:** Almost every dependency is unpinned, no hash/lock or Python runtime version exists, and large ML weights are not versioned as deployment artifacts. A fresh build can resolve a different framework/ORM/torch stack than the inspected environment.

**Why It Matters:** Builds are non-reproducible and can change behavior or introduce advisories without source changes.

**Evidence:** The local environment contains many transitive packages absent from the manifest. As of the audit date, installed `python-jose==3.5.0` is listed in a [critical GitHub advisory](https://github.com/advisories/GHSA-3qf3-8w2g-rqmx); the described asymmetric-key precondition is not currently present because this app pins JWT decode to HS256 with a symmetric secret, but the package exposure still requires explicit disposition.

**Failure Scenario:** Railway rebuilds after a transitive release and fails import/model loading or changes security behavior.

**Recommended Direction:** Pin Python and resolved packages with hashes, automate vulnerability/license review, and package/model-version AI artifacts deterministically.

**Dependencies:** CI/CD implementation.

### [FE-002] Core frontend adapters implement obsolete backend contracts

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Frontend / API Integration  
**Location:** `../Website/src/services/api/productService.ts:14-87`, `../Website/src/services/api/sellerService.ts:6-58`, `../Website/src/services/api/buyerService.ts:5-77`, `app/schemas/product.py:74-127`, `app/api/v1/routers/shopping.py:37-80`  
**Related Components:** Catalog, listing creation, cart, orders, images, variants

**Problem:** Website still sends/maps the former flat product model (`image_url`, category/department/size strings and string image arrays), while Backend now requires nested images/variants and returns a category object. Cart add posts to `/shopping/cart/add/{productId}` with no body, but Backend requires `/shopping/cart/add` with a variant UUID and quantity; removal sends a product ID where Backend requires a cart-item ID. Buyer-order mapping expects fields that the order DTO does not return.

**Why It Matters:** Browsing falls back to placeholders or malformed categories, listing creation rejects image arrays or creates unusable products without variants/images, cart synchronization fails, and order history cannot represent purchased items accurately.

**Evidence:** Direct contract comparison found different paths, identifiers, payload shapes, and response names. The adapters suppress multiple failures by returning empty arrays, placeholder images, or only console warnings.

**Failure Scenario:** A seller uploads a base64 image and receives a validation error; a buyer sees a local item added to cart while the server cart remains empty; refresh then loses the cart and checkout cannot create the intended order.

**Recommended Direction:** Establish one versioned/generated contract or shared schema, remove the legacy API layer, map explicit DTOs, and add consumer/provider contract tests for all customer/seller/admin flows.

**Dependencies:** API-001, DB-001, TEST-001.

### [FE-003] Authentication, route protection, and KYC state are client-derived and fail open in the UI

**Severity:** High  
**Confidence:** Confirmed  
**Area:** Frontend / Identity / Seller Verification  
**Location:** `../Website/src/contexts/AuthContext.tsx:56-117`, `../Website/src/router.tsx:48-60,150-175`, `../Website/src/store/useAppStore.ts:306-351`, `../Website/src/hooks/useStore.ts:104-123`  
**Related Components:** Buyer/seller/admin portals, role switching, KYC, privacy/profile screens

**Problem:** All buyer routes and several seller profile/KYC routes lack an authentication guard. `SellerGuard` checks only a mutable Zustand verification flag and never requires authentication. Login stores the role selected by the page rather than the server response; `setRole` rewrites the stored user's role locally; admin login marks any successful login as admin in UI state; and a failed KYC network call is displayed as a successfully pending submission.

**Why It Matters:** Backend guards prevent many direct privilege escalations, but the product presents unauthorized or fictitious state, can expose locally cached/profile mock content, and cannot be trusted to guide sensitive seller/admin workflows. This also makes support and audit evidence unreliable.

**Evidence:** Router inspection shows unwrapped `/buyer/*`, `/seller/verify`, and seller profile/privacy routes. KYC's catch-all error branch sets `sellerVerified: "pending"` and shows success. Server role is available in the login response but AuthContext overwrites it with `forRole`.

**Failure Scenario:** An unauthenticated visitor opens account pages; a buyer logs in through the seller/admin UI and sees a privileged shell that API calls later reject; or a seller believes identity documents were submitted when the request never reached Backend.

**Recommended Direction:** Derive identity/role/verification only from authenticated server state, make guards fail closed while restoration is pending, and distinguish durable success from offline/error state. Backend authorization must remain authoritative.

**Dependencies:** SEC-001, AUTH-001, TEST-001.

### [AI-002] The local VTON service is unfinished and incompatible with the backend integration

**Severity:** High  
**Confidence:** Confirmed  
**Area:** AI / Integration / Deployment  
**Location:** `../thrift kro vton engine/main.py:63-91,108-114,149-168,211-249`, `app/api/v1/routers/vto.py:22-31,54-106`  
**Related Components:** Buyer virtual try-on, Hugging Face Space, GPU deployment, uploads

**Problem:** The local engine exposes unauthenticated `POST /vton` returning JSON/base64, while Backend calls a Gradio Space operation named `/process_vton` and expects a returned file path. The inference pipeline is deliberately not loaded; every successful local response is only a preprocessing mask. Startup hardcodes CUDA, upload sizes are unbounded, work is synchronous inside an async route, and `/health` can say `healthy` while `inference_loaded` is false.

**Why It Matters:** The checked-in service cannot satisfy the advertised feature or Backend contract and can exhaust GPU/CPU/memory if exposed. A liveness-only success would route traffic to a nonfunctional model.

**Evidence:** `inference_pipeline.load()` and the inference block are commented out; response metadata explicitly says it is returning a placeholder. No authentication, rate limit, concurrency bound, or deployment manifest exists in that folder.

**Failure Scenario:** The team deploys the local engine believing it backs Backend; Backend cannot call it, or direct callers consume expensive preprocessing while receiving non-try-on output.

**Recommended Direction:** Define one authenticated bounded inference contract, implement truthful readiness, validate deployment GPU requirements and privacy/retention, and only advertise VTON after quality/latency/load tests pass.

**Dependencies:** UPLOAD-001, PERF-001, DEP-001, TEST-001.

## 8. Medium Severity Issues

### [API-003] Chat history endpoint is broken by a model/schema rename

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** API / Chat  
**Location:** `app/api/v1/routers/chat.py:56-63`, `app/models/message.py:8-17`, `app/schemas/chat.py:9-18`  
**Related Components:** Chat history

**Problem:** Query and schema use `Message.timestamp`, while the model field is `created_at`.

**Why It Matters:** Authenticated history requests fail instead of returning messages.

**Evidence:** A runtime schema probe reported missing `timestamp`; the query attribute is absent.

**Failure Scenario:** Any `/chat/history/{contact_id}` request raises an internal error.

**Recommended Direction:** Align persistence and response naming through a tested DTO.

**Dependencies:** SEC-003 first for safe chat behavior.

### [API-004] Collection APIs have inconsistent or missing pagination and bounds

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** API / Performance  
**Location:** `app/api/v1/routers/admin.py:36-45`, `app/crud/order.py:281-310`, `app/api/v1/routers/reviews.py:21-23`, `app/api/v1/routers/chat.py:56-63`  
**Related Components:** Orders, reviews, chat, categories, admin

**Problem:** Admin orders, buyer/seller orders, reviews, chat history, and category lists use `.all()` without paging. Existing `skip/limit` inputs often lack non-negative/max validation; stores accepts an unbounded limit.

**Why It Matters:** Data growth creates large queries/responses and memory pressure.

**Evidence:** Only products/users/tickets/pending KYC have partial offset/limit use.

**Failure Scenario:** A long-lived account requests years of messages/orders and exhausts a worker or times out.

**Recommended Direction:** Standardize bounded cursor/offset pagination and response metadata based on access patterns.

**Dependencies:** DB-005 indexes.

### [DB-005] Essential uniqueness, check constraints, and foreign-key indexes are missing

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Database  
**Location:** `app/models/*.py`  
**Related Components:** Cart, wishlist, reviews, inventory, order queries

**Problem:** There are no composite unique constraints for cart variant, wishlist product, buyer/product review, or primary image; no checks for positive quantities/rating/non-negative stock/money; and many queried FKs lack indexes (`seller_orders.seller_id`, order/cart/product/message relationships).

**Why It Matters:** Races create duplicates/invalid rows and common tenant/order queries degrade into scans.

**Evidence:** ORM metadata inspection showed only primary/UUID helper indexes and a small set of user/KYC indexes.

**Failure Scenario:** Concurrent toggles/adds create duplicate rows, while seller-order history slows as data grows.

**Recommended Direction:** Add constraints/indexes from proven invariants and query plans through tested migrations.

**Dependencies:** DB-001.

### [CART-001] Cart/wishlist duplicate prevention is race-prone and guest carts do not exist

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Cart / Wishlist  
**Location:** `app/crud/shopping.py:18-96`, `app/crud/shopping.py:209-231`, `app/models/shopping.py`  
**Related Components:** Shopping, UX

**Problem:** Code performs check-then-insert without database uniqueness; its `IntegrityError` message assumes a constraint that is absent. Only authenticated one-cart-per-user sessions exist; no guest/merge/expiry model exists.

**Why It Matters:** Concurrent requests can duplicate lines/saved items; common pre-login commerce behavior is unsupported.

**Evidence:** Models contain no relevant composite `UniqueConstraint`.

**Failure Scenario:** Double-click/concurrent add creates two cart rows and checkout charges both.

**Recommended Direction:** Enforce composite uniqueness/upserts; decide whether guest cart is launch-essential.

**Dependencies:** DB-005 and business decision.

### [AUTH-002] Secondary token/OAuth controls are inconsistent

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Authentication  
**Location:** `app/api/v1/routers/auth.py:23-132`, `app/api/v1/routers/ai.py:42-59`, `app/schemas/user.py:35-39`  
**Related Components:** OAuth linking, inactive users, WebSockets, profile email

**Problem:** Login issues tokens to inactive users (later HTTP guards reject them); AI WebSocket auth checks seller role but not active/verified status; JWT is placed in a query parameter; Google access-token calls have no timeout and `email_verified` is not explicitly required; email can be changed without reverification.

**Why It Matters:** Deactivation is not consistently enforced, tokens leak into URLs/logs, and identity-linking/account-change assurance is weak.

**Evidence:** AI uses its own partial authenticator instead of the shared dependency semantics.

**Failure Scenario:** A deactivated seller continues using AI WebSocket capability, or a query-token appears in proxy logs.

**Recommended Direction:** Centralize identity/session policy, use secure socket authentication, and require verified identity for linking/email changes.

**Dependencies:** AUTH-001.

### [SEC-005] Security defaults and error responses expose unnecessary surface

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Security / API  
**Location:** `app/main.py:14-36`, `app/api/v1/routers/products.py:294-302`, `app/services/upload.py:53-54`, `app/api/v1/routers/vto.py:109-122`  
**Related Components:** CORS, errors, API docs

**Problem:** Missing CORS configuration becomes wildcard; Swagger/ReDoc are public; CSV, upload, and VTO responses expose raw exception/provider text.

**Why It Matters:** It aids reconnaissance, leaks internal/provider details, and expands browser/API abuse surface.

**Evidence:** `detail=f"...{str(e)}"` is returned in multiple handlers.

**Failure Scenario:** Provider paths/configuration or database error detail reaches an untrusted client.

**Recommended Direction:** Fail closed on production origins, adopt a stable redacted error envelope, and decide production documentation access policy.

**Dependencies:** ERR-001, OBS-001.

### [ERR-001] Error handling and external-call resilience are inconsistent

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Reliability  
**Location:** Repository-wide; notably `auth.py`, `review.py`, `vto.py`, `upload.py`  
**Related Components:** Database sessions, Google, Cloudinary, Hugging Face

**Problem:** No global exception translation exists. Duplicate review raises `ValueError` and becomes 500; Google userinfo has no timeout/exception mapping; provider retries/circuit limits are absent; `vto.py` can reference `temp_dir` before assignment if temp creation fails.

**Why It Matters:** Expected client/provider failures become unstable 500s, hung workers, or misleading responses.

**Evidence:** Exception strategy varies by endpoint; only some CRUD functions roll back.

**Failure Scenario:** Google or Hugging Face stalls and consumes worker capacity; a duplicate review returns an internal error.

**Recommended Direction:** Define global domain/error mapping, provider timeouts/retry budgets, and transaction ownership.

**Dependencies:** OBS-001.

### [KYC-001] Seller-verification rate limiting is race-prone and inefficient

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Seller Verification  
**Location:** `app/crud/seller_verification.py:45-135`  
**Related Components:** KYC submission

**Problem:** Every check loads all historical requests and counts in Python, then separately inserts. Concurrent submissions can pass together; timezone-aware values are forcibly replaced rather than normalized.

**Why It Matters:** Abuse limits can be bypassed and performance degrades per seller history.

**Evidence:** `.all()` precedes list filtering; no lock/unique pending constraint/transactional quota exists.

**Failure Scenario:** Three parallel requests pass a pre-insert count and exceed the intended limit.

**Recommended Direction:** Query only the window and enforce one pending request/quota transactionally.

**Dependencies:** DB-001, DB-005.

### [REPORT-001] Admin metrics mix units and recognize unearned revenue

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Reporting / Finance  
**Location:** `app/crud/admin.py:14-127`  
**Related Components:** Admin dashboard, GMV, revenue

**Problem:** “Total orders” counts vendor sub-orders rather than checkout orders, excludes some states from totals, excludes admins from total users, and treats platform fees on escrowed/in-progress orders as revenue before settlement/refund resolution.

**Why It Matters:** Operational and financial decisions use misleading figures.

**Evidence:** Counts aggregate `SellerOrder`; revenue includes `PAID_FUNDS_IN_ESCROW` through delivered.

**Failure Scenario:** Multi-vendor checkout is reported as several orders and refundable fees are reported as earned revenue.

**Recommended Direction:** Define metric contracts (order vs sub-order, GMV vs recognized revenue) and derive them from ledger/payment states.

**Dependencies:** DB-003, PAY-004, business accounting decisions.

### [PERF-002] Search, sockets, and synchronous integrations have limited growth headroom

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Performance / Scalability  
**Location:** `app/crud/product.py:56-73`, `app/api/v1/routers/chat.py:11-28`, `app/core/database.py:6-13`  
**Related Components:** Catalog, chat, DB connections

**Problem:** Search uses leading-wildcard `ILIKE` without a matching index; chat connections are process-local and one socket per user; every app process can open up to 40 synchronous DB connections regardless of database capacity.

**Why It Matters:** Search scans grow, messages fail across instances/restarts, and horizontal scaling can exhaust PostgreSQL connections.

**Evidence:** No cache/broker/search index exists; pool sizes are fixed constants.

**Failure Scenario:** Two Railway instances hold different user sockets and cannot deliver to each other while aggregate connection pools exceed DB limits.

**Recommended Direction:** Add measured indexes first, size pools from deployment limits, and introduce a shared pub/sub or managed realtime channel only when multi-instance chat is required.

**Dependencies:** Observability/load testing.

### [DOC-001] Documentation materially contradicts the current implementation

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Documentation / Architecture  
**Location:** `Thrift_Kro_Backend_Documentation.docx`, `../Database/README.md`, `../Website/README.md`, current source trees  
**Related Components:** Onboarding, deployment, database, finance

**Problem:** Backend documentation calls itself a production release and describes old single-product orders, 2% fees/PKR 100 shipping, old fields/enums/endpoints, and behavior no longer present. Current code uses parent/vendor orders, 5% fees/PKR 200 shipping, variants, and different routes. Database README points to a nonexistent Backend-relative database path, documents the wrong published port and conflicting password. Website README still describes a mock/Figma bundle and publishes the known demo administrator credentials.

**Why It Matters:** Operators and developers can execute the wrong migration/deployment and implement incompatible clients.

**Evidence:** Backend-local `database/` source was removed in Git history, while a separate sibling Database folder contains a different generation of scripts. Documentation and source disagree on paths, ports, credentials, schema, API responses, fees, and deployment behavior.

**Failure Scenario:** A new environment follows the document's Alembic/schema instructions and creates an incompatible database.

**Recommended Direction:** After behavior/schema decisions stabilize, regenerate architecture/API/runbooks from verified code and migrations.

**Dependencies:** DB-001 and business rule decisions.

### [MEDIA-001] Uploaded media has no lifecycle, ownership, or privacy controls

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Media / Storage  
**Location:** `app/services/upload.py`, product and seller-verification models  
**Related Components:** Cloudinary, catalog, KYC

**Problem:** Uploads return a URL only; no asset record binds ownership/purpose, no deletion/orphan cleanup exists, and no private/public access policy, transformation/compression policy, or moderation scan is represented.

**Why It Matters:** Deleted/rejected products leave cost/privacy artifacts and URLs can be reused outside their intended object.

**Evidence:** No Cloudinary destroy operation or media table/background cleanup exists.

**Failure Scenario:** A seller uploads many images then abandons drafts; files remain public and billed indefinitely.

**Recommended Direction:** Track assets and ownership, separate public product media from private KYC, and define cleanup/retention.

**Dependencies:** PRIV-001, SEC-004.

### [FE-004] The frontend fails TypeScript checking and has no quality gate

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Frontend / Build Quality  
**Location:** `../Website/package.json`, `../Website/src/features/admin/components/KycModal.tsx`, `../Website/src/features/admin/pages/PageOverview.tsx`, `../Website/src/features/landing/pages/LandingPage.tsx`, `../Website/src/features/seller/pages/SellerListings.tsx`, `../Website/src/hooks/useStore.ts`, `../Website/src/services/api/authService.ts`  
**Related Components:** Deployment, routing, admin, seller listings

**Problem:** `tsc --noEmit` fails across route unions/maps, seller status values, admin chart/overview types, an impossible KYC comparison, and nullable auth roles. `package.json` exposes only `dev`, `build`, and `preview`; Vite's transpilation build does not provide a dedicated typecheck/test gate.

**Why It Matters:** Contract and state errors can be deployed even though the repository contains TypeScript, reducing it to partial editor assistance rather than a release invariant.

**Evidence:** The audit's existing local TypeScript command exited non-zero with errors in all locations listed above. No lint/typecheck/test CI configuration exists.

**Failure Scenario:** A route/status refactor compiles through Vite but fails in an affected user path or leaves a navigation branch unreachable.

**Recommended Direction:** Make a clean typecheck, lint, tests, and production build required release checks after current errors and contracts are intentionally resolved.

**Dependencies:** FE-002, TEST-001, CI implementation.

### [FE-005] Browser session storage and offline fallback can preserve stale authentication

**Severity:** Medium  
**Confidence:** Confirmed  
**Area:** Frontend / Authentication  
**Location:** `../Website/src/services/api/authService.ts:21-49,141-161`, `../Website/src/services/api/apiClient.ts:18-52`, `../Website/src/contexts/AuthContext.tsx:27-53`  
**Related Components:** JWT, logout, XSS impact, session restoration

**Problem:** Bearer tokens and user profiles are duplicated under two keys in `localStorage` or `sessionStorage`. On any profile-fetch failure other than the request client's explicit 401 cleanup, `getCurrentUser` falls back to the stored user, so network/server failures can preserve an apparently authenticated UI. Logout has no server revocation because Backend has no refresh/session registry.

**Why It Matters:** Any future XSS has direct access to bearer tokens, and stale UI identity makes authorization/error handling ambiguous. No executable XSS sink was confirmed in the inspected React source, so this is not rated as a standalone critical exploit.

**Evidence:** Storage reads/writes occur in both the central client and auth service; the catch at `getCurrentUser` returns parsed cached identity without proving token validity.

**Failure Scenario:** Backend is unavailable during reload; the app restores an old user and privileged-looking navigation while subsequent calls fail or use an expired token.

**Recommended Direction:** Use one session model, fail closed on identity restoration, adopt short-lived access/refresh rotation appropriate to the deployment, and apply a strict CSP/XSS defenses before relying on browser-held bearer tokens.

**Dependencies:** AUTH-001, FE-003.

### [DEP-002] The installed frontend dependency graph has unresolved advisories

**Severity:** Medium  
**Confidence:** Confirmed inventory; exploitability varies  
**Area:** Frontend / Supply Chain  
**Location:** `../Website/package.json`, `../Website/package-lock.json`  
**Related Components:** React routing, build tooling, source maps

**Problem:** `npm audit --json` reported four high and one moderate advisories: React Router's RSC action CSRF range, `source-map-js` event-loop denial of service, `nanoid` custom-generator looping, and PostCSS source-map file disclosure. Fixes are available according to the audit output.

**Why It Matters:** The lockfile is reproducible but not currently clean. React Router is direct; the others are transitive. The inspected app is a browser SPA and no RSC action/custom Nano ID usage was found, so advisory severity is not equivalent to demonstrated application exploitability.

**Evidence:** Installed graph: 203 packages, 5 advisories, 0 critical. The audit did not change packages or lockfiles.

**Failure Scenario:** A vulnerable code path becomes reachable after a feature/build change, or production source-map processing consumes attacker-controlled input.

**Recommended Direction:** Triage reachability, apply reviewed lockfile updates, run regression/build tests, and make dependency scanning a CI gate with documented exceptions.

**Dependencies:** TEST-001 and CI implementation.

## 9. Low Severity Issues

### [API-005] Public catalog endpoints can expose deleted/inactive records

**Severity:** Low  
**Confidence:** Confirmed  
**Area:** API  
**Location:** `app/api/v1/routers/products.py:36-64`, `app/crud/product.py:14-27`, `app/api/v1/routers/categories.py:20-32`  
**Related Components:** Catalog

**Problem:** Any caller can set `include_deleted=true`; direct product lookup does not filter deletion; category listing accepts `include_inactive=true` publicly.

**Why It Matters:** Retired content remains discoverable and client behavior becomes inconsistent.

**Evidence:** Flags have no admin/seller guard.

**Failure Scenario:** A removed listing remains accessible by ID or list flag.

**Recommended Direction:** Separate public-live queries from owner/admin archival queries.

**Dependencies:** Product moderation policy.

### [CODE-001] Stale/mocked code and ad-hoc scripts increase operational ambiguity

**Severity:** Low  
**Confidence:** Confirmed  
**Area:** Maintainability  
**Location:** `alter_db.py`, untracked `alter_product_table.py`, VTO/AI legacy endpoints, Flake8 output  
**Related Components:** Maintenance

**Problem:** Manual schema scripts coexist with Alembic; legacy endpoints are mocks; static checks reported numerous unused imports and one redundant f-string. The README is only a title.

**Why It Matters:** Engineers can run the wrong mechanism or mistake mock behavior for production logic.

**Evidence:** Documentation also advertises mocks/obsolete scripts as working production features.

**Failure Scenario:** An operator runs an ad-hoc ALTER script against the wrong schema.

**Recommended Direction:** After schema stabilization, clearly quarantine/remove obsolete paths through normal reviewed changes and document supported commands.

**Dependencies:** DB-001, DOC-001.

### [CODE-002] Several defaults and timestamps are semantically inconsistent

**Severity:** Low  
**Confidence:** Confirmed  
**Area:** Code Quality / Data  
**Location:** Pydantic schemas and SQLAlchemy models  
**Related Components:** Responses, update auditing

**Problem:** Many response fields use literal list/dict defaults; SQLAlchemy JSON columns use literal list defaults; `updated_at` has `onupdate` but no creation value; naming alternates `created_at`/historical `timestamp`.

**Why It Matters:** Pydantic v2 protects most schema defaults, but ORM defaults/naming ambiguity and null update timestamps complicate maintenance and contracts.

**Evidence:** Examples include `ProductVariantResponse.attributes = {}` and `SellerVerificationRequest.shop_photo_urls = Column(JSON, default=[])`.

**Failure Scenario:** Future mutation/serialization changes expose shared/default ambiguity or consumers assume non-null timestamps.

**Recommended Direction:** Standardize factories and timestamp/naming conventions during targeted schema work, not as a standalone rewrite.

**Dependencies:** DB-001.

## 10. Confirmed Bugs

The following are confirmed defects rather than general risks:

| Finding | Current behavior | Expected behavior |
| --- | --- | --- |
| SEC-001 | Public schemas accept `ADMIN` | Public signup cannot assign privileged roles |
| PAY-001 | Deposit creates completed spendable funds | Funds become spendable only after trusted settlement |
| SEC-003 | Socket path controls sender | Authenticated token controls sender |
| API-001 | Real order items serialize as `[]` | Responses include purchased lines |
| API-002 | AI endpoints access removed fields | Endpoints use current product model |
| API-003 | Chat query/schema references missing `timestamp` | History returns model `created_at` consistently |
| PAY-004 | COD cannot transition from pending through seller flow | Supported COD lifecycle progresses validly |
| PAY-002 | Refund/cancel only changes status | Money/stock/fees are compensated atomically |
| DB-004 | Variant replacement deletes referenced entities | Catalog updates preserve stable referenced variants |
| REVIEW-001 | Any review affects seller aggregate | Only policy-eligible reviews affect trusted rating |
| FE-001 | Checkout clears the cart and reports success after both API calls fail | Failure preserves/reconciles cart and no success is shown |
| FE-002 | Cart add path/body and product DTOs do not match Backend | Browser and server use one tested contract |
| FE-003 | Failed KYC submission is shown as pending/success | UI shows durable server result or explicit failure |
| FE-003 | Login/admin/seller roles can be overwritten from page/local state | UI role derives from validated server identity |
| AI-002 | Local VTON returns a mask and incompatible contract | Deployed engine returns a real try-on through the agreed contract |
| DB-001 | Advertised Alembic/SQL/bootstrap methods create different schemas | One migration chain creates the verified runtime schema |
| FE-004 | `tsc --noEmit` exits non-zero | Release candidate passes type checking |

## 11. Business Logic Problems

- Fees and shipping are code constants (`5%`, PKR `200`) rather than versioned commercial rules.
- No tax, discount, coupon, currency, or allocation model exists; the total formula is only subtotal + per-seller flat shipping + fee.
- The buyer pays the platform fee on top of subtotal; seller payout is subtotal + shipping. Whether this is intended is a business decision.
- Checkout calculates current server prices, which is good, but has no quoted-price/version contract or idempotent attempt.
- Stock is decremented at order creation even for unpaid card/COD orders; no expiry/release policy exists.
- Product status is not synchronized to aggregate variant stock after purchase/restock.
- Cancellation, return, dispute, refund, and payout eligibility rules are represented by enum transitions rather than complete workflows.
- Buyers can mark an order delivered; no courier confirmation, delivery evidence, auto-confirm window, or dispute grace period exists.
- COD commission collection and settlement are undefined.
- Seller verification approval and `is_verified` duplicate the same concept and can drift.
- Browser cart/stock/notification success is independently simulated and can diverge from durable server state.
- Addresses, cards, privacy/2FA/biometric preferences, devices, and several seller/admin metrics are local mock state rather than implemented account capabilities.

## 12. Security Findings

Critical controls are tracked in SEC-001 through SEC-004. Additional observations:

- ORM filters and typed UUIDs reduce ordinary SQL-injection exposure; no raw user-composed SQL was found.
- No command execution, pickle/deserialization, or open redirect sink was found in reviewed source.
- CSRF is lower risk for normal bearer-header calls, but tokens are script-readable in local/session storage; the React Router RSC advisory appears lower-reachability for this SPA but remains unresolved.
- Passwords use bcrypt and are not returned by `UserResponse`, which should be retained.
- IDs are UUIDs, but UUID opacity is not authorization; reviewed order/product ownership checks are present in several endpoints and should be preserved.
- Seller product update/delete correctly compares `product.seller_id` to the authenticated seller.
- Order detail checks buyer, involved seller, or admin; sub-order detail applies a similar check.
- Security headers, trusted-host/proxy configuration, payload limits, and global rate limiting are absent.

## 13. Database Findings

DB-001 is the primary blocker. Other database conclusions:

- `CheckoutOrder -> SellerOrder -> OrderItem` is the right multi-vendor relational core.
- UUID primary keys are consistently used, though redundant indexes are generated on many primary keys.
- Foreign-key cascade rules are inconsistent with financial history: deleting a user cascades products/profile/wallet while order rows use restrictive links, potentially making deletion impossible or losing non-order audit data.
- Soft delete exists only for products; there is no retention/anonymization model for users/KYC.
- JSONB variant attributes are pragmatic for flexible attributes, but attribute validation/index needs are undefined.
- Database uniqueness should enforce SKU normalization/case policy, cart/wishlist/review identity, and payout/idempotency keys.
- Timezone-aware columns are used in many models, which is good, but local replacement of tzinfo in KYC logic is unsafe.
- No schema drift check runs in CI because no CI exists.
- Sibling `schema.sql` has useful checks/indexes that ORM/Alembic do not consistently express, but it cannot be used as a second migration system. It destructively resets `public`, exposes broad grants, and still omits current runtime fields/tables.
- Docker Compose uses fixed development database/pgAdmin credentials, publishes PostgreSQL and pgAdmin on host ports, and uses `latest` for pgAdmin. It is suitable only as a hardened/local starting point, not production infrastructure.
- The seed file contains hardcoded demo credentials and realistic-looking CNIC/phone/profile values. Seed data must never run in production and should use clearly synthetic data under an explicit environment guard.

## 14. Frontend Findings

The active `Website` repository is a React/Vite SPA containing customer, seller, and admin experiences. It has positive foundations: feature folders, lazy-loaded route screens, a central request helper, an AuthContext, reusable UI components, explicit loading states in some data pages, and a committed package lock.

Production blockers and gaps:

- FE-001 and FE-002 make checkout, cart synchronization, listings, catalog media/category mapping, and order display unreliable.
- Route protection is incomplete. All buyer routes and seller verification/profile/edit/notification/privacy routes are public; seller guards check mutable local KYC state but not `isAuthenticated`.
- UI role state is page-selected/mutable rather than consistently taken from `/users/me`; this does not bypass Backend RBAC but creates privileged-looking shells and incorrect navigation.
- API abstractions are duplicated (`src/services/api.ts` and `src/services/api/*`) and represent different backend generations.
- Zustand combines durable domain-looking state with ephemeral UI and mock data. Cart, wishlist, seller inventory/notifications, addresses, cards, devices, privacy preferences, and orders can be local-only.
- KYC and checkout catch paths turn failures into success-looking states. Several API adapters turn errors into empty 200-like results, making outage and true emptiness indistinguishable.
- The seller "AI" autofill is a timer that always identifies the same Nike shoe; it is presented as analysis. Uploaded images are retained as base64 in browser memory and sent in JSON against an incompatible product schema.
- Seller chat uses mock contacts/non-UUID IDs. Its WebSocket parser calls `split("|", 1)` and then checks for two parts, which can never succeed; Backend messages also use the broken timestamp contract.
- Addresses/payment cards/security/privacy toggles are mock/local interactions. The UI presents "Secure checkout", buyer protection, 2FA/biometric preferences, and card management without matching backend capabilities.
- Product detail is state-selected at a non-ID route (`/buyer/product`), so refresh/deep link/share behavior is fragile.
- Object URLs for listing/VTON images are not consistently revoked; file count/size validation is mostly text, not enforcement.
- No error boundary, global retry/offline policy, accessibility test, browser test, bundle budget, or image optimization policy was found. Static review found labels on many auth fields, but custom clickable containers and icon-only controls need keyboard/name verification.
- `tsc --noEmit` fails, and no lint/typecheck/test CI gate exists.

## 15. Backend Findings

- The router/CRUD/model/schema structure is understandable and should remain a modular monolith.
- Business workflows are split inconsistently between routers and CRUD functions; direct DB access also appears in routers (`admin.py`, `chat.py`, `stores.py`).
- `create_order_from_cart` is a large transaction script combining validation, pricing, grouping, payment, inventory, persistence, and response loading.
- Provider code has no adapter interfaces, making tests and failure control difficult.
- Synchronous SQLAlchemy is acceptable at this scale if worker/pool sizing is deliberate; labeling it “high-concurrency async” is inaccurate.
- No background processing exists. Email/SMS are absent; AI/VTO are the only immediate candidates for bounded asynchronous jobs. Redis/queues are not otherwise justified yet.

## 16. API Findings

The generated OpenAPI document contains 53 HTTP paths; two additional WebSockets are not represented in OpenAPI.

| Prefix | Major endpoints/capabilities |
| --- | --- |
| `/auth` | register, password login, Google login |
| `/users` | current profile read/update |
| `/products` | list/filter/search, seller list, CRUD, restore, CSV template/import |
| `/categories` | public list/read and admin CRUD/deactivate |
| `/orders` | checkout, buyer list/detail, seller list/detail/status, escrow release |
| `/shopping` | cart get/add/update/remove/clear/checkout; wishlist get/toggle |
| `/wallet` | balance, deposit |
| `/sellers` | KYC submit/status and admin review |
| `/admin` | stats, unbounded orders, users, activation, tickets |
| `/reviews`, `/stores`, `/support` | reviews, rankings, support tickets |
| `/upload` | verified-seller product image upload |
| `/ai` | mock image analysis, status, verification WebSocket |
| `/vto` | mock inference and external generation |
| `/chat` | history and unauthenticated chat WebSocket |

Request validation is strongest on passwords, product price/quantity, and UUID types. Error formats, list envelopes, pagination, idempotency, and status codes are inconsistent. There is no formal API deprecation/version evolution policy beyond the `/v1` prefix.

Website-to-API mismatches are not isolated defects: the browser assumes legacy flat product/order fields, old cart paths, and nonexistent address/card endpoints. A machine-readable contract plus automated consumer/provider validation is required before either repository can be called stable.

## 17. Multi-Vendor Architecture Findings

Strengths:

- One checkout order groups multiple seller sub-orders.
- Each seller sees only sub-orders filtered by their user ID.
- Product mutations check ownership.
- Order detail authorization accounts for buyer, involved seller, and admin.

Gaps:

- A seller is a user, not a store/organization; there is no vendor staff, permission, or multiple-store model.
- Seller order finance combines subtotal, shipping, fee, status, tracking, and payout eligibility in one row.
- No commission rule version or per-line allocation exists.
- No payout entity/batch/bank destination/hold/reserve/reconciliation exists.
- Refund/return allocation across vendor items, shipping, discounts, taxes, and fees is absent.
- Multi-vendor shipping is just a flat fee per seller group.
- Admin reporting confuses parent orders and vendor orders.

## 18. Performance and Scalability Findings

Immediate bottlenecks are correctness and blocking work, not a need for microservices. A modular monolith can support the likely scale after:

1. fixing checkout/payout locking and idempotency;
2. bounding every collection/upload/inference;
3. adding proven indexes and measuring query plans;
4. moving long AI/VTO work behind a bounded execution queue if usage warrants it;
5. sizing DB pools to the actual PostgreSQL limit;
6. replacing process-local chat routing when horizontal scaling is introduced.

Redis, Elasticsearch, Kubernetes, Kafka, CQRS, and service meshes are not justified by current evidence. PostgreSQL search with trigram/full-text indexing is the first pragmatic search step.

## 19. Missing Production Features

### Essential for launch

- Safe role provisioning and secret/bootstrap management.
- Real payment funding/verification or an explicit launch decision to support only a safe subset.
- Immutable ledger, escrow, refunds, cancellations, payout idempotency, and reconciliation.
- Concurrency-safe inventory/reservations and stock restoration.
- Correct migrations and controlled deployment schema evolution.
- Address management and order address/line snapshots.
- Email verification, recovery/reset, abuse/rate controls, and token revocation strategy.
- Private KYC storage/retention/access auditing.
- Shipment/tracking ownership and COD settlement rules.
- Automated tests, health/readiness, monitoring, audit logs, backups, and restore drills.
- Correct browser/backend product, cart, checkout, order, chat, and AI contracts.
- Truthful authentication/KYC/error states and complete protected-route behavior.

### Important for growth

- Returns workflow, partial refunds, disputes/case evidence, and configurable grace periods.
- Vendor staff and scoped store roles.
- Commission rule/version management and payout batches.
- Tax, invoices, promotions/coupons, discount allocation.
- Notification delivery (email/SMS/in-app) with retry/outbox semantics.
- Product moderation and fraud controls.
- Search ranking/indexing, analytics, vendor/admin reporting definitions.
- Guest cart/merge if required by product strategy.
- Managed shipping/rate/carrier integration.

### Optional/Future

- Warehouses/multi-location inventory.
- Advanced recommendations and search service.
- Automated KYC provider.
- Wallet withdrawals if regulatory/business model permits.
- Loyalty/wallet promotions, international currencies/taxes.
- Independently deployed AI inference only if measured load/operational ownership warrants it.

## 20. Testing Gaps

Priority test suites should cover:

1. public role restrictions, default-secret absence, login abuse, inactive users, Google linking;
2. customer/vendor/admin object isolation and negative IDOR cases;
3. product/category ownership, soft deletion, variant lifecycle, KYC approval;
4. cart uniqueness and price/availability changes;
5. simultaneous checkout against one stock unit and repeated idempotency keys;
6. wallet funding verification and ledger balance invariants;
7. card/COD/webhook success, failure, delay, duplicate event, and wrong amount/currency;
8. cancellation/refund/return stock and ledger compensation;
9. payout duplicate/concurrent release and reconciliation;
10. migrations from empty and production-like previous revisions;
11. response-contract tests for nested order/chat/AI payloads;
12. upload byte/dimension/type bombs, SSRF targets, and authorization;
13. frontend component/integration tests for auth restoration, guards, error states, and DTO mapping;
14. browser end-to-end tests for buyer checkout, seller listing/KYC, admin access, chat, and VTON failure/success;
15. contract tests that compare Website requests/responses with generated Backend OpenAPI plus WebSocket message schemas;
16. VTON readiness, load, upload-abuse, privacy, and output-quality acceptance tests.

## 21. DevOps and Deployment Gaps

- No CI checks for lint, tests, migrations, secret scanning, dependency advisories, or build reproducibility.
- A development database Compose exists, but no deployable Backend/VTON image or runtime version pin exists; Nixpacks and GPU/runtime behavior are implicit.
- No release migration command, migration rollback/forward-fix plan, or schema compatibility check.
- No liveness/readiness endpoint; `/` only returns a welcome message and does not verify dependencies.
- No graceful shutdown/drain behavior for sockets/jobs.
- No environment separation or promotion documentation.
- No backup schedule, retention, restore procedure, disaster-recovery objective, or restore test.
- HTTPS/reverse proxy assumptions are delegated to Railway but undocumented.
- No capacity plan for DB connections, ML memory, disk temp space, or external service quotas.
- Vercel config only rewrites SPA routes; no security headers, CSP, preview/production promotion checks, or API compatibility gate is defined.
- Database Compose exposes fixed credentials and host ports and uses a floating pgAdmin image; it must not be treated as production infrastructure.
- VTON has no deployment, GPU scheduling, warmup/readiness, concurrency, or model artifact/version plan.

## 22. Observability Gaps

Production minimums should include:

- structured, redacted logs with request/correlation/user/session IDs;
- latency/error/saturation metrics by route and external dependency;
- security events for login failures, role/account changes, deactivation, KYC access/review;
- business audit events for price/product changes, status transitions, refunds, payouts, and ledger entries;
- alerts for payment webhook failures, reconciliation imbalance, duplicate/idempotency conflicts, negative/low stock, queue lag, provider failures;
- error tracking with source version/environment and PII scrubbing;
- trace/span context for checkout/payment/payout calls if complexity warrants it.

## 23. Technical Debt

- Current behavior is spread across routers and CRUD modules rather than cohesive use-case services.
- Migration history, ORM models, documentation, and ad-hoc scripts represent different system generations.
- Website API adapters, local mock state, and Backend DTOs represent different product generations.
- Hardcoded fee/shipping/business rules have no versioning.
- External integrations are called directly, limiting testability and resiliency.
- Stale imports, old response names, mock endpoints, and comments claiming stronger behavior than implemented reduce trust.
- The dirty working tree includes substantial uncommitted architectural changes, making the audited snapshot difficult to reproduce.
- README/runbooks are insufficient and sometimes actively contradictory for onboarding or operations.

## 24. Recommended Target Architecture

Evolve toward a **transactional modular monolith** on PostgreSQL:

```text
React SPA (buyer/seller/admin)
  |-- generated/validated API client
  |-- server-derived auth and durable state
  |
FastAPI adapters (HTTP/WebSocket, auth, validation, DTOs)
  |
Application use cases
  |-- authorization policy
  |-- transaction/idempotency boundary
  |-- domain commands/events
  |
Domain modules
  |-- catalog/inventory/cart/orders/payments/payouts/...
  |
Infrastructure adapters
  |-- SQLAlchemy repositories + unit of work
  |-- payment provider
  |-- private/public media storage
  |-- notification delivery
  |-- authenticated, bounded AI/VTO adapter
  |
PostgreSQL + bounded worker/outbox only for work that must be asynchronous
```

Keep one core backend deployment initially and one SPA deployment. Use one tested migration chain, generated/validated contracts, database transactions, row locks/conditional updates, uniqueness, an outbox where reliable external side effects are needed, and explicit idempotency keys. Treat VTON as an external bounded adapter; deploy it separately only because GPU/model isolation is a concrete operational boundary, not as a general microservice strategy.

## 25. Proposed Module Boundaries

| Module | Ownership |
| --- | --- |
| Identity | Registration/login/OAuth, verified email, credentials, sessions/tokens, recovery |
| Users and Addresses | Profiles, address book, privacy/export/deletion |
| Vendors and KYC | Store profile, approval, staff/roles later, private KYC and access audit |
| Catalog | Products, variants/SKUs, categories, images, moderation, lifecycle |
| Inventory | Stock, reservations, movements, availability policy |
| Cart | Authenticated/optional guest carts, price preview, merge |
| Checkout | Quote/revalidation, grouping, idempotent order placement orchestration |
| Orders | Parent/vendor orders, snapshots, state policy, history |
| Payments and Ledger | Provider intents/events, wallet/escrow, immutable entries, reconciliation |
| Refunds and Returns | Cancellation, return cases, allocations, compensation |
| Payouts | Eligibility, holds, batches, destinations, provider settlement |
| Shipping | Rates, shipments, tracking, delivery confirmation, COD settlement |
| Reviews | Eligibility, moderation, safe aggregates |
| Support and Disputes | Authorized order linkage, evidence, resolution |
| Notifications | Preferences, templates, outbox, delivery/retry |
| Admin and Reporting | Audited commands and explicitly defined operational/financial metrics |
| AI and VTO | Bounded media processing/inference adapters; no authority over server-owned flags without verified events |

## 26. Priority Matrix

| ID | Issue | Area | Severity | Business Impact | Technical Impact | Effort | Dependency | Suggested Phase |
| -- | ----- | ---- | -------- | --------------- | ---------------- | ------ | ---------- | --------------- |
| SEC-001 | Public admin registration | Auth | Critical | Total platform compromise | RBAC bypass | S | None | 0 |
| SEC-002 | Default secret/admin credentials | Security | Critical | Account/data compromise | JWT/admin bootstrap unsafe | S-M | SEC-001 | 0 |
| PAY-001 | Self-minted wallet deposits | Payments | Critical | Direct financial loss | Untrusted funding | S to disable; L to replace | SEC-001 | 0 |
| SEC-003 | Unauthenticated chat identity | Security | Critical | Impersonation/fraud | Persistent forged messages | M | AUTH-001 | 0 |
| SEC-004 | SSRF through listing images | Security | Critical | Internal/cloud data exposure | Unrestricted server fetch | M | UPLOAD-001 | 0 |
| DB-001 | Three incompatible schema authorities | Database | Critical | Outage/data loss | Non-reproducible/destructive initialization | L | None | 1 |
| INV-001 | Concurrent overselling | Inventory | Critical | Incorrect paid orders | Lost-update race | M-L | DB-001 | 2 |
| PAY-002 | Refund/cancel lacks compensation | Payments | Critical | Customer loss/wrong stock | Incomplete workflow | L | DB-003 | 3 |
| PAY-003 | Double payout race | Payouts | Critical | Duplicate seller payment | No lock/idempotency | M | DB-003 | 3 |
| FE-001 | False checkout success | Frontend/Orders | Critical | Customer believes nonexistent order succeeded | Failure converted to local success | M | FE-002/ORDER-001 | 0 |
| PAY-004 | Card/COD not implemented | Payments | High | Unpayable/unreconciled orders | Missing provider/state flow | L | DB-003 | 3 |
| AI-001 | Client/random verification | Trust | High | Fraudulent badges | Server trust boundary broken | S-M | API-002 | 0 |
| ORDER-001 | Checkout correctness/idempotency gaps | Checkout | High | Duplicate/invalid orders | Incomplete command boundary | L | INV-001 | 2 |
| ORDER-002 | No immutable order snapshots | Orders | High | Fulfillment/dispute failure | Mutable history | M-L | DB-001 | 2 |
| API-001 | Order items omitted | API | High | Orders cannot be fulfilled | DTO/ORM mismatch | S | TEST-001 | 0 |
| API-002 | AI model-field drift | API | High | Verification unavailable | Runtime attribute failures | M | DB-001 | 2 |
| DB-002 | Float money/missing checks | Database | High | Rounding/reconciliation loss | Invalid numeric model | L | DB-001 | 1 |
| DB-003 | Weak wallet ledger | Finance | High | Unprovable balances | Mutable single-sided accounting | L | DB-002 | 3 |
| DB-004 | Destructive variant replacement | Catalog | High | Failed edits/lost carts | FK lifecycle violation | M | DB-001 | 2 |
| UPLOAD-001 | Unbounded/weak media validation | Security | High | DoS/malicious content | In-process memory/CPU risk | M | None | 0 |
| PERF-001 | Blocking in-process AI/VTO | Performance | High | Site-wide latency/outage | Event-loop/model contention | M-L | UPLOAD-001 | 5 |
| AUTH-001 | Missing auth lifecycle/abuse controls | Auth | High | Account takeover/lockout gaps | No verification/recovery/revocation | L | SEC-001/002 | 1 |
| REVIEW-001 | Rating manipulation | Trust | High | Marketplace reputation fraud | Eligibility/aggregate race | M | DB-005 | 4 |
| PRIV-001 | KYC privacy controls missing | Privacy | High | Identity-document breach | No private retention/access model | L | Business/legal | 1 |
| TEST-001 | No tests | QA | High | High regression probability | No safety net | L | Foundations | 1 onward |
| DEVOPS-001 | Unsafe startup/deployment lifecycle | DevOps | High | Failed/unsafe releases | Runtime DDL and bootstrap | M-L | DB-001 | 1 |
| OBS-001 | No audit/monitoring | Operations | High | Fraud/incidents undetectable | No telemetry/actor history | M-L | Privacy rules | 1 |
| DEP-001 | Unreproducible dependencies/runtime | Supply chain | High | Build/security drift | No lock/hash/runtime pin | M | CI | 1 |
| FE-002 | Obsolete frontend/API contracts | Frontend/API | High | Core buying/selling flows fail | Paths and DTOs disagree | L | DB-001/API-001 | 1-2 |
| FE-003 | Client-derived auth/KYC state | Frontend/Auth | High | Misleading unauthorized/seller workflow | Guards and state fail open | M | AUTH-001 | 1 |
| AI-002 | Unfinished incompatible VTON service | AI | High | Advertised feature unavailable/unsafe | Placeholder and contract mismatch | L | UPLOAD-001/PERF-001 | 5 |
| API-003 | Broken chat history schema | API | Medium | Chat history unavailable | Field rename drift | S | SEC-003 | 2 |
| API-004 | Missing pagination/bounds | API | Medium | Slow/failed clients | Unbounded reads | M | DB-005 | 5 |
| DB-005 | Missing constraints/indexes | Database | Medium | Duplicates/slow growth | Invariants not enforced | M | DB-001 | 1 |
| CART-001 | Cart/wishlist race and no guest model | Cart | Medium | Duplicate charges/UX gap | Check-then-insert | M | DB-005 | 2 |
| AUTH-002 | Inconsistent secondary auth controls | Auth | Medium | Deactivation/token leakage risk | Duplicated policy | M | AUTH-001 | 1 |
| SEC-005 | Open defaults/raw errors | Security | Medium | Recon/detail leakage | Inconsistent production surface | S-M | ERR-001 | 1 |
| ERR-001 | Inconsistent error/provider resilience | Reliability | Medium | Hung workers/500s | No common boundary | M | OBS-001 | 4 |
| KYC-001 | Race-prone KYC rate limit | Vendor | Medium | Submission abuse | Non-atomic in-memory counting | M | DB-005 | 4 |
| REPORT-001 | Misleading admin metrics | Reporting | Medium | Wrong business decisions | Mixed/early recognition | M | DB-003/PAY-004 | 4 |
| PERF-002 | Search/socket/pool scaling limits | Scalability | Medium | Degraded growth | Process-local and scans | M | Metrics | 5 |
| DOC-001 | Documentation drift | Documentation | Medium | Wrong operations/integration | Multiple system versions | M | Stabilized behavior | 6 |
| MEDIA-001 | No media lifecycle/ownership | Storage | Medium | Cost/privacy leakage | Orphan/public assets | M | PRIV-001 | 4 |
| FE-004 | Frontend typecheck fails | Frontend/QA | Medium | Defects ship despite TypeScript | No clean quality gate | M | FE-002/CI | 1 |
| FE-005 | Stale/script-readable browser sessions | Frontend/Auth | Medium | Token exposure/stale identity | Duplicated storage and offline fallback | M | AUTH-001/FE-003 | 1 |
| DEP-002 | Frontend dependency advisories | Supply chain | Medium | Conditional security/availability exposure | 5 unresolved audit findings | S-M | TEST-001/CI | 1 |
| API-005 | Deleted/inactive public visibility | API | Low | Retired content exposure | Query policy mismatch | S | Moderation policy | 4 |
| CODE-001 | Stale mocks/scripts/dead code | Maintainability | Low | Operator confusion | Multiple unsupported paths | M | DB-001/DOC-001 | 6 |
| CODE-002 | Default/timestamp inconsistencies | Maintainability | Low | Contract ambiguity | Inconsistent conventions | S-M | DB-001 | 6 |

Effort: S = small, M = medium, L = large relative to this codebase. Effort is directional, not an estimate.

## 27. Recommended Remediation Order

### Phase 0 — Containment

Close public admin creation; remove/fail on fallback secrets and admin credentials; rotate compromised values; disable wallet self-deposit, false-success checkout, client AI flags, unauthenticated chat, and unrestricted URL fetching; bound uploads. Remove published demo admin credentials and treat existing admin accounts/tokens/wallet transactions as potentially untrusted.

### Phase 1 — Trusted foundation

Create the single verified migration baseline; pin runtime/dependencies; make startup read-only; establish CI, migration tests, health probes, structured logs/audits, KYC privacy design, core auth lifecycle, and a generated/validated Website-to-Backend contract. Make frontend auth/KYC/error state fail closed.

### Phase 2 — Commerce correctness

Define order/address/line snapshots, checkout idempotency, product eligibility, stable variants, database constraints, inventory reservation/decrement, and cart uniqueness. Rebuild the buyer/seller adapters against those contracts and add end-to-end checkout/listing tests.

### Phase 3 — Financial integrity

Decide launch payment methods; implement payment events/webhooks and immutable ledger; define commission/COD rules; implement idempotent refunds, cancellations, disputes, payouts, and reconciliation.

### Phase 4 — API and marketplace trust

Repair order/chat/AI contracts and remove customer-facing mock-success behavior; enforce review/KYC rules; standardize errors and pagination; add shipping/support authorization and media lifecycle.

### Phase 5 — Capacity and asynchronous work

Load test, tune indexes/pools, decide whether VTON is a launch feature, then implement one compatible authenticated engine with truthful readiness and bounded concurrency; add a worker/outbox only for verified long-running/retryable tasks, and solve multi-instance realtime routing if required.

### Phase 6 — Launch validation

Run full-system end-to-end/security/concurrency/accessibility/recovery tests, restore a backup in rehearsal, reconcile financial test data, verify frontend/backend dependency advisories, update documentation/runbooks, and perform a final go/no-go review.

## 28. Things That Should NOT Be Changed

- Do not replace the modular monolith with microservices; current risks are correctness and controls, not service count.
- Retain the parent `CheckoutOrder` and per-vendor `SellerOrder` concept.
- Retain backend ownership checks already present on product and order detail mutations.
- Retain bcrypt password hashing and typed/expiring JWT validation while fixing secret/session lifecycle.
- Retain server-side checkout price calculation and single transaction intent; strengthen concurrency/idempotency rather than moving totals to clients.
- Retain Pydantic input bounds for passwords, prices, and quantities and expand them consistently.
- Retain product soft deletion and eager loading where it prevents N+1 queries; fix public query policy and measure large joins.
- Retain PostgreSQL/SQLAlchemy; no evidence justifies a database or framework rewrite.
- Retain Cloudinary or another managed object store for public catalog media if ownership/lifecycle/privacy controls are added.
- Retain React/Vite, feature-level page organization, route lazy loading, and a central API client; the required work is contract/state correctness, not a frontend framework rewrite.
- Retain a committed frontend lockfile and the separation of buyer/seller/admin presentation areas while removing duplicated legacy adapters and mock-success behavior.

## 29. Unknowns / Questions Requiring Business Decisions

1. Which payment methods are truly required at launch: wallet, card, COD, bank transfer, or a subset?
2. Is the wallet regulated stored value, promotional credit, or only an internal escrow display?
3. Who funds wallet balances and how are deposits/withdrawals settled and reconciled?
4. Who pays the platform fee: buyer, seller, or both, and is it refundable?
5. Who receives/pays shipping and fees on cancellation, failed delivery, return, and partial refund?
6. When does vendor payout become eligible: delivery scan, buyer confirmation, grace period, or dispute expiry?
7. Can a buyer or seller cancel independently, and at which states?
8. Are partial fulfillment, partial cancellation, partial return, and partial refund required?
9. How is COD collected, commission withheld, and remitted/reconciled?
10. Is one seller account one store, and will vendor employees/multiple stores be supported?
11. Are unverified-purchase reviews allowed, and do they affect seller ranking?
12. Is AI verification a marketing signal, moderation gate, or guarantee; what false-positive liability is acceptable?
13. What KYC data must be retained, for how long, in which jurisdiction, and who may access it?
14. What are tax/invoice requirements for Pakistan and any future regions?
15. Are guest carts and checkout required?
16. What are target traffic, catalog size, checkout rate, availability objective, RPO, and RTO?
17. Is VTON required at launch, and which implementation/contract is authoritative: the Hugging Face Gradio Space or the local FastAPI prototype?
18. Which frontend account settings are real launch commitments (cards, addresses, 2FA, biometric, privacy, devices) versus design-only placeholders?

## 30. Final Assessment

### Can the current system safely be deployed to production?

**NO.** Immediate privilege escalation and wallet fraud are possible; the storefront reports successful purchases when no order exists; chat impersonation and SSRF are exposed; database creation is non-reproducible and potentially destructive; and legitimate concurrent checkout/payout operations can corrupt orders, stock, or balances. Major product, payment, chat, KYC, and VTON flows are broken, simulated, or placeholders, with no automated tests or operational controls to catch failures.

### The 10 most important things to fix first

1. Prevent public `ADMIN` registration/Google signup and audit existing privileged users.
2. Remove fallback JWT/admin credentials, rotate exposed values, and replace startup admin seeding.
3. Disable self-service wallet credit and define trusted payment funding.
4. Stop false-success checkout and align Website product/cart/order contracts with Backend.
5. Authenticate chat WebSockets and derive identity server-side.
6. Block SSRF and enforce bounded, validated, owned media.
7. Establish one tested migration baseline and retire destructive/stale schema bootstrap paths.
8. Make checkout idempotent and inventory concurrency-safe.
9. Implement an immutable ledger with atomic refund/cancellation and idempotent payout compensation.
10. Add risk-first full-stack tests, audit logs/monitoring, and a controlled deployment/health/backup process.
