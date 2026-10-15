"""
tasks.py — Celery application and async task definitions.

The Celery app is configured via settings (CELERY_BROKER_URL / CELERY_RESULT_BACKEND).
Each task creates its own database session — sessions cannot be shared across
thread/process boundaries.
"""
from celery import Celery
from celery.utils.log import get_task_logger

from config import settings

logger = get_task_logger(__name__)

# ---------------------------------------------------------------------------
# Celery app
# ---------------------------------------------------------------------------
celery_app = Celery(
    "eve_healthcare",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


# ---------------------------------------------------------------------------
# process_webhook_task
# ---------------------------------------------------------------------------
@celery_app.task(bind=True, max_retries=3, name="tasks.process_webhook_task")
def process_webhook_task(self, payload: dict) -> dict:
    """
    Asynchronously process a payment webhook payload.

    Extracted from the HTTP handler so the web server can return 202 immediately
    and this task handles the DB work in the background worker.

    Idempotency guarantee: if a PaymentLog already exists for `transaction_id`,
    the task exits early without touching the booking — safe to re-queue.

    Retry strategy: on any unexpected exception the task retries up to 3 times
    with exponential back-off (60 s, 120 s, 240 s) to survive transient DB errors.

    Args:
        payload: dict with keys `transaction_id`, `booking_id`, `status`.
    """
    # Import here to avoid circular imports at module load time
    from database import SessionLocal
    from models import Booking, BookingStatus, PaymentLog

    transaction_id: str = payload["transaction_id"]
    booking_id: int = payload["booking_id"]
    status: str = payload["status"]

    # Each Celery task creates its own session — never share across threads
    db = SessionLocal()
    try:
        # --- Idempotency guard ------------------------------------------------
        existing_log = (
            db.query(PaymentLog)
            .filter(PaymentLog.transaction_id == transaction_id)
            .first()
        )
        if existing_log:
            logger.info(
                "Webhook already processed, skipping.",
                extra={"transaction_id": transaction_id},
            )
            return {"message": "Webhook already processed"}

        # --- Validate booking -------------------------------------------------
        booking = db.get(Booking, booking_id)
        if not booking:
            # Don't retry for missing bookings — they won't appear on retry either
            logger.error(
                "Booking not found for webhook.",
                extra={"booking_id": booking_id, "transaction_id": transaction_id},
            )
            return {"error": f"Booking {booking_id} not found"}

        # --- Atomic write: log + status update --------------------------------
        new_log = PaymentLog(
            transaction_id=transaction_id,
            booking_id=booking_id,
            status=status,
        )
        db.add(new_log)

        booking.status = (
            BookingStatus.CONFIRMED if status == "SUCCESS" else BookingStatus.FAILED
        )

        db.commit()
        logger.info(
            "Webhook processed successfully.",
            extra={"transaction_id": transaction_id, "new_status": booking.status.value},
        )
        return {
            "message": f"Webhook processed. Booking status updated to {booking.status.value}."
        }

    except Exception as exc:
        db.rollback()
        logger.exception(
            "Webhook task failed, scheduling retry.",
            extra={"transaction_id": transaction_id, "attempt": self.request.retries},
        )
        # Exponential back-off: 60 s, 120 s, 240 s
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        db.close()
