# EVE Healthcare — Diagnostic Booking Backend

A production-ready RESTful API built with **FastAPI** and **PostgreSQL** that powers the EVE Healthcare diagnostic appointment platform. It handles user authentication with JWT, management of diagnostic centres and tests, appointment booking, and simulated payment processing with idempotent webhook handling.

---

## Table of Contents

1. [Overview](#overview)
2. [How to Run Locally](#how-to-run-locally)
3. [Database / Schema Design](#database--schema-design)
4. [API Endpoints & Example Requests](#api-endpoints--example-requests)
5. [Important Assumptions](#important-assumptions)
6. [What I Would Improve With More Time](#what-i-would-improve-with-more-time)

---

## Overview

| Attribute | Detail |
|-----------|--------|
| **Framework** | FastAPI 0.141 |
| **Database** | PostgreSQL 15 (via Docker) + SQLAlchemy 2 ORM |
| **Auth** | JWT (PyJWT / HS256) + bcrypt password hashing |
| **Migrations** | Alembic |
| **Testing** | pytest + httpx (in-memory SQLite override) |
| **Rate Limiting** | SlowAPI — 20 req/min per IP on auth endpoints |
| **Structured Logging** | structlog + asgi-correlation-id (JSON-ready, per-request trace IDs) |
| **Caching** | fastapi-cache2 + Redis (60 s TTL on `GET /centres/`) |
| **Task Queue** | Celery + Redis (async webhook processing, 3 retries, exponential back-off) |
| **Configuration** | pydantic-settings — all secrets loaded from `.env` / environment variables |
| **Containerisation** | Full Docker Compose stack (db, redis, web, celery_worker) |

Core capabilities:

- **Auth** — Sign up, log in, and protect routes with Bearer JWT tokens.
- **Centres & Tests** — CRUD for diagnostic centres and the tests they offer.
- **Bookings** — Authenticated appointment booking with server-side price calculation.
- **Payments** — Simulated payment gateway + idempotent webhook receiver.
- **Pagination** — `GET /centres/` supports `skip` / `limit` query parameters.
- **Rate Limiting** — Auth endpoints are protected against brute-force via SlowAPI.
- **Structured Logging** — Every request emits a structured log with a correlation ID, method, path, status code, and elapsed time.

---

## How to Run Locally

### Prerequisites

- Docker & Docker Compose (recommended — runs the entire stack)
- *or* Python 3.11+ for local venv development

---

### Option A — Full Docker stack (recommended)

This is the primary way to run the application. A single command builds and
starts all four services: **PostgreSQL**, **Redis**, **FastAPI**, and the
**Celery worker**. Migrations are applied automatically on startup.

```bash
# Clone the repository
git clone <repo-url>
cd backend-project-EVE_Healthcare

# (Optional) set a strong SECRET_KEY before starting
export SECRET_KEY=your-super-secret-key

# Build images and start all services
docker compose up --build
```

The API will be available at **http://127.0.0.1:8000**.
Swagger UI: **http://127.0.0.1:8000/docs**

To stop all services:
```bash
docker compose down
```

---

### Option B — Local virtual environment (development)

Use this if you want hot-reload. You still need Docker running for PostgreSQL and Redis.

```bash
# 1. Start only the infrastructure services
docker compose up -d db redis

# 2. Create and activate the virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install all locked dependencies
pip install -r requirements.txt

# 4. Apply database migrations
alembic upgrade head

# 5. Start the FastAPI dev server
uvicorn main:app --reload

# 6. (Optional) Start a local Celery worker in a second terminal
celery -A tasks worker --loglevel=info
```

### Run Tests

```bash
pytest tests/test_api.py -v
```

Tests use an in-memory SQLite database and an in-memory cache backend —
no running Postgres, Redis, or Celery instance required.

---
## Database / Schema Design

### Entity-Relationship Overview
<img width="1025" height="551" alt="Screenshot 2026-09-27 at 4 44 44 PM" src="https://github.com/user-attachments/assets/9894ac7e-2362-4390-a008-348e1eb2683b" />

```
users ──< bookings >── diagnostic_tests >── diagnostic_centres
                │
                └──< payment_logs
```

### Table Descriptions

| Table | Purpose |
|-------|---------|
| `users` | Stores registered patients. `hashed_password` uses bcrypt; `email` has a unique constraint. |
| `diagnostic_centres` | Physical locations offering diagnostic services. |
| `diagnostic_tests` | Individual tests offered by a centre, each with a fixed `price`. |
| `bookings` | Links a user, test, and centre for a given `appointment_date_time`. `amount` is always copied from the test's price at creation time to prevent spoofing. `status` tracks the payment lifecycle (`PENDING` → `CONFIRMED` / `FAILED`). |
| `payment_logs` | **Idempotency log** for the webhook endpoint. Every processed `transaction_id` is recorded here. Before updating any booking, the webhook handler checks this table first — if the `transaction_id` already exists, the request is acknowledged and discarded without any DB writes. This prevents duplicate state mutations if the payment gateway retries a webhook. |

### Why `PaymentLog` Is Critical

Without the `PaymentLog` table, a retried webhook could flip a booking's status multiple times (e.g., `CONFIRMED` → `FAILED` → `CONFIRMED`). The log table acts as a **deduplication guard**: the first delivery writes the log and updates the booking atomically; all subsequent deliveries see the existing log entry and short-circuit immediately.

---
## API Endpoints & Example Requests

Interactive documentation (Swagger UI) is auto-generated at:
**http://127.0.0.1:8000/docs**

Use the **Authorize 🔒** button in Swagger to authenticate with a bearer token.

### Full Endpoint Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/signup` | — | Register a new user |
| `POST` | `/auth/login` | — | Obtain a JWT token |
| `POST` | `/centres/` | — | Create a diagnostic centre |
| `GET` | `/centres/` | — | List all centres with their tests. Supports pagination: `?skip=0&limit=10` (max `limit=100`). Response cached in Redis for 60 s. |
| `POST` | `/centres/{id}/tests/` | — | Add a test to a centre |
| `POST` | `/bookings/` | ✅ | Create a booking |
| `POST` | `/payments/` | ✅ | Simulate a payment |
| `POST` | `/payments/webhook/` | — | Accept a webhook — returns **202 Accepted** immediately; processing is handled asynchronously by the Celery worker |

### Example `curl` Commands

**1. Sign up a new user**

```bash
curl -X POST http://127.0.0.1:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "patient@example.com", "password": "secure123"}'
```

Expected response (`201 Created`):
```json
{
  "access_token": "<jwt-token>",
  "token_type": "bearer"
}
```

**2. Create a booking (authenticated)**

```bash
# First, log in to get a token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -d "username=patient@example.com&password=secure123" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Then create the booking
curl -X POST http://127.0.0.1:8000/bookings/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "test_id": 1,
    "centre_id": 1,
    "appointment_date_time": "2026-12-15T09:30:00"
  }'
```


---

## Important Assumptions

1. **Test prices are immutable after creation.** The system does not account for price changes after a test is listed. Bookings always capture the price at the time of creation — there is no recalculation logic.

2. **Webhook `transaction_id` values are globally unique.** The idempotency mechanism relies on the payment gateway providing a unique, stable ID per transaction. The system does not validate or generate these IDs itself.

3. **One user per email.** Email addresses are treated as the primary identity. There is no email verification flow — a valid email format is sufficient to register.

4. **A booking must match a test to its owning centre.** A request to book `test_id=5` under `centre_id=2` will be rejected if test 5 actually belongs to centre 3. This prevents logically inconsistent bookings.

---

## What I Would Improve With More Time

### ✅ Bonus Features Already Implemented

The following production-grade improvements were proactively built beyond the core requirements:

| Feature | Implementation |
|---------|----------------|
| **Pagination on list endpoints** | `GET /centres/` accepts `?skip=0&limit=10` (capped at 100). Enforced at the Pydantic/FastAPI layer — invalid values return `422` before reaching the DB. |
| **Rate limiting on auth endpoints** | `POST /auth/signup` and `POST /auth/login` are decorated with `@limiter.limit("20/minute")` via SlowAPI. Exceeding the limit returns `429 Too Many Requests`. |
| **Structured logging & request tracing** | Every HTTP request logs method, path, status code, and elapsed time via structlog. A `X-Correlation-ID` header is generated per request by `asgi-correlation-id` and bound into every log line automatically. Flip `json_logs=True` in `main.py` for production JSON output. |
| **Environment-based configuration** | All secrets (`DATABASE_URL`, `SECRET_KEY`, `REDIS_URL`, etc.) are loaded from `.env` via `pydantic-settings`. No hardcoded credentials. |
| **Redis caching** | `GET /centres/` responses are cached in Redis for 60 seconds via `fastapi-cache2`. Cache is initialised on application startup via the FastAPI lifespan event. |
| **Celery async webhooks** | `POST /payments/webhook/` returns **202 Accepted** immediately and enqueues `process_webhook_task` on a Redis broker. The Celery worker processes the payload with idempotency checks, up to 3 retries, and exponential back-off (60 s, 120 s, 240 s). |
| **Full Dockerisation** | A `Dockerfile` and updated `docker-compose.yml` orchestrate all four services (db, redis, web, celery_worker). `docker compose up --build` is the single command to run the entire stack. |

---

### 🔭 Further Improvements With More Time

| Feature | Rationale |
|---------|-----------|
| **Cache invalidation strategy** | Currently the Redis cache expires after 60 s TTL. Adding explicit key invalidation on `POST /centres/` or `POST /centres/{id}/tests/` mutations would make the list endpoint immediately consistent. |
| **Webhook dead-letter queue** | After 3 Celery retries the task is silently dropped. Routing failed tasks to a dead-letter queue (e.g., a separate Redis list or a monitoring tool like Flower) would make failures observable and re-processable. |
| **Role-based access control (RBAC)** | Currently any authenticated user can create centres and tests. Adding an `is_admin` flag to `User` and enforcing it on write endpoints would harden the permission model. |
| **Booking cancellation endpoint** | There is no `DELETE /bookings/{id}` or status-transition endpoint. Adding one with appropriate business rules (e.g., cannot cancel a confirmed + paid booking) would make the system more complete. |
