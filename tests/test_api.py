"""
Integration tests for the EVE Healthcare Diagnostic API.

These tests use FastAPI's TestClient (backed by httpx) and a separate
in-memory SQLite database so they never touch the production PostgreSQL
instance.  Each test module gets a fresh database via the session-scoped
fixtures below.
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import get_db
from models import Base

# ---------------------------------------------------------------------------
# Test database — SQLite in-memory, isolated from production Postgres
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite:///./test_eve.db"

test_engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Dependency override: yields a test DB session instead of the real one."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Create all tables before the module's tests run; drop them after."""
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="module")
def client():
    """Return a TestClient that uses the in-memory test DB."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def unique_email() -> str:
    """Generate a unique email so tests don't collide on the UNIQUE constraint."""
    return f"test_{uuid.uuid4().hex[:8]}@example.com"


# ===========================================================================
# 1. Authentication flow
# ===========================================================================
class TestAuthFlow:
    """Verify that a user can sign up and that duplicate emails are rejected."""

    def test_signup_returns_201_and_token(self, client: TestClient):
        """POST /auth/signup with a fresh email must return 201 and a bearer token."""
        response = client.post(
            "/auth/signup",
            json={"email": unique_email(), "password": "securepass"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"]) > 0

    def test_signup_duplicate_email_returns_400(self, client: TestClient):
        """Registering the same email twice must return 400."""
        email = unique_email()
        client.post("/auth/signup", json={"email": email, "password": "securepass"})
        response = client.post(
            "/auth/signup",
            json={"email": email, "password": "securepass"},
        )
        assert response.status_code == 400

    def test_login_returns_200_and_token(self, client: TestClient):
        """POST /auth/login with valid credentials must return 200 and a token."""
        email = unique_email()
        client.post("/auth/signup", json={"email": email, "password": "mypassword"})
        response = client.post(
            "/auth/login",
            data={"username": email, "password": "mypassword"},
        )
        assert response.status_code == 200, response.text
        assert "access_token" in response.json()

    def test_login_wrong_password_returns_401(self, client: TestClient):
        """Wrong password must return 401 Unauthorized."""
        email = unique_email()
        client.post("/auth/signup", json={"email": email, "password": "correct"})
        response = client.post(
            "/auth/login",
            data={"username": email, "password": "wrong"},
        )
        assert response.status_code == 401


# ===========================================================================
# 2. Webhook idempotency
# ===========================================================================
class TestWebhookIdempotency:
    """
    Verify the idempotency contract of POST /payments/webhook/:

    - First call with a transaction_id  → 200, booking status updated.
    - Second call with same transaction_id → 200, "already processed" message,
      no duplicate log entry or state change.
    """

    # ---- class-level state ------------------------------------------------
    _shared_payload: dict = {}

    # ---- fixtures ----------------------------------------------------------

    @pytest.fixture(scope="class")
    @classmethod
    def auth_headers(cls, client: TestClient):
        """Sign up a user and return Authorization headers."""
        email = unique_email()
        resp = client.post(
            "/auth/signup", json={"email": email, "password": "webhookpass"}
        )
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.fixture(scope="class")
    @classmethod
    def booking_id(cls, client: TestClient, auth_headers: dict):
        """
        Create the minimal data required for a booking:
        centre → test → booking.  Returns the booking id.
        """
        # Create centre
        centre = client.post(
            "/centres/", json={"name": "Test Centre", "location": "Mumbai"}
        ).json()

        # Add a test to the centre
        test = client.post(
            f"/centres/{centre['id']}/tests/",
            json={"name": "Blood Test", "price": 499.0},
        ).json()

        # Create a booking (authenticated)
        booking = client.post(
            "/bookings/",
            json={
                "test_id": test["id"],
                "centre_id": centre["id"],
                "appointment_date_time": "2026-12-01T10:00:00",
            },
            headers=auth_headers,
        ).json()

        return booking["id"]

    # ---- tests -------------------------------------------------------------

    def test_webhook_first_call_succeeds(
        self, client: TestClient, booking_id: int
    ):
        """A new transaction_id must be accepted and return a success message."""
        payload = {
            "transaction_id": f"txn_{uuid.uuid4().hex}",
            "booking_id": booking_id,
            "status": "SUCCESS",
        }
        # Store on the class dict so the sibling test can reuse it
        TestWebhookIdempotency._shared_payload = payload

        response = client.post("/payments/webhook/", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert "message" in body
        assert "already processed" not in body["message"].lower()

    def test_webhook_duplicate_returns_already_processed(
        self, client: TestClient, booking_id: int
    ):
        """Replaying the exact same transaction_id must return the idempotency message."""
        payload = TestWebhookIdempotency._shared_payload  # same payload as above
        response = client.post("/payments/webhook/", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert "already processed" in body["message"].lower()

    def test_webhook_missing_booking_returns_404(self, client: TestClient):
        """A webhook for a non-existent booking_id must return 404."""
        payload = {
            "transaction_id": f"txn_{uuid.uuid4().hex}",
            "booking_id": 999999,
            "status": "FAILED",
        }
        response = client.post("/payments/webhook/", json=payload)
        assert response.status_code == 404
