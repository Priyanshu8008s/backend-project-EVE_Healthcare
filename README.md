# EVE Healthcare — Diagnostic Booking Backend

A production-ready RESTful API built with **FastAPI** and **PostgreSQL** that powers the EVE Healthcare diagnostic appointment platform. It handles user authentication with JWT, management of diagnostic centres and tests, appointment booking, and simulated payment processing with idempotent webhook handling.

---

## Table of Contents

1. [Overview](#overview)
2. [API Endpoints & Example Requests](#api-endpoints--example-requests)
3. [How to Run Locally](#how-to-run-locally)
4. [Database / Schema Design](#database--schema-design)
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

Core capabilities:

- **Auth** — Sign up, log in, and protect routes with Bearer JWT tokens.
- **Centres & Tests** — CRUD for diagnostic centres and the tests they offer.
- **Bookings** — Authenticated appointment booking with server-side price calculation.
- **Payments** — Simulated payment gateway + idempotent webhook receiver.

---

## How to Run Locally

### Prerequisites

- Python 3.11+
- Docker & Docker Compose

### Step-by-step

```bash
# 1. Clone the repository
git clone <repo-url>
cd backend-project-EVE_Healthcare

# 2. Start the PostgreSQL database
docker compose up -d

# 3. Create and activate the virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 4. Install all locked dependencies
pip install -r requirements.txt

# 5. Apply database migrations
alembic upgrade head

# 6. Start the development server
uvicorn main:app --reload
```

The API will be available at **http://127.0.0.1:8000**.

### Run Tests

```bash
pytest tests/test_api.py -v
```

Tests use an in-memory SQLite database — no running Postgres instance required.

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
| `GET` | `/centres/` | — | List all centres with their tests |
| `POST` | `/centres/{id}/tests/` | — | Add a test to a centre |
| `POST` | `/bookings/` | ✅ | Create a booking |
| `POST` | `/payments/` | ✅ | Simulate a payment |
| `POST` | `/payments/webhook/` | — | Receive a payment webhook |

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

| Feature | Rationale |
|---------|-----------|
| **Environment-based configuration** | Move `DATABASE_URL`, `SECRET_KEY`, and `ACCESS_TOKEN_EXPIRE_MINUTES` to a `.env` file loaded via `pydantic-settings`. Eliminates hardcoded secrets. |
| **Redis caching for `GET /centres/`** | The full centre + tests listing is an expensive query that rarely changes. Caching with a short TTL (e.g., 60 s) would dramatically reduce DB load under traffic. |
| **Rate limiting on auth endpoints** | Add `slowapi` middleware to cap signup/login attempts per IP, preventing brute-force attacks. |
| **Celery + Redis for webhook retries** | Instead of processing webhooks synchronously, push them onto a Celery task queue. Failed webhook deliveries would be retried with exponential back-off, making the system resilient to transient DB errors. |
| **Pagination on list endpoints** | `GET /centres/` currently returns all rows. Adding `limit` / `offset` query parameters (or cursor-based pagination) is essential at scale. |
| **Structured logging & request tracing** | Integrate `structlog` with a correlation ID per request so distributed traces can be reconstructed in a log aggregation tool. |
| **Docker Compose for the app itself** | Add a second service to `docker-compose.yml` for the FastAPI app so the entire stack can be started with a single `docker compose up`. |
