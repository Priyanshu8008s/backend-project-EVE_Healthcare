import random

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
import schemas
from config import settings
from database import get_db
from models import BookingStatus
from routers.auth import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /payments/
# Simulated Payment — protected, randomly succeeds or fails
# ---------------------------------------------------------------------------
@router.post(
    "/",
    response_model=schemas.BookingResponse,
    summary="Simulate a payment for a booking (requires authentication)",
)
def simulate_payment(
    payment_in: schemas.PaymentSimulateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Simulate processing a payment for an existing booking.

    - Returns **404** if the booking does not exist **or** does not belong to
      the current user (avoids leaking booking IDs of other users).
    - Randomly resolves to `SUCCESS` (→ `CONFIRMED`) or `FAILED`.
    - Commits the new booking status and returns the updated record.
    """
    booking = db.get(models.Booking, payment_in.booking_id)

    # 404 for missing bookings; also 404 (not 403) when the booking belongs
    # to a different user — prevents enumeration of other users' booking IDs.
    if not booking or booking.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with id={payment_in.booking_id} not found.",
        )

    # Simulate payment gateway outcome
    outcome = random.choice(["SUCCESS", "FAILED"])
    booking.status = (
        BookingStatus.CONFIRMED if outcome == "SUCCESS" else BookingStatus.FAILED
    )

    db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# POST /payments/webhook/
# ---------------------------------------------------------------------------
@router.post(
    "/webhook/",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive a payment webhook — processed asynchronously via Celery",
)
def payment_webhook(
    payload: schemas.WebhookPayload,
    db: Session = Depends(get_db),
):
    """
    Accept an incoming payment webhook from a payment gateway.

    **Production mode** (`CELERY_ENABLED=True`):
    The payload is dispatched to a Celery worker via `process_webhook_task.delay()`.
    The endpoint returns **202 Accepted** immediately — the actual DB work
    (idempotency check, PaymentLog creation, Booking status update) happens
    in the background worker with up to 3 retries and exponential back-off.

    **Test / development mode** (`CELERY_ENABLED=False`):
    Falls back to synchronous, in-process processing (identical logic to the
    original implementation) and returns **200 OK** so the existing test suite
    continues to pass without a live Redis/Celery instance.

    **Idempotency** is enforced in both paths: replaying the same
    `transaction_id` is safe and returns the "already processed" message.
    """
    if settings.CELERY_ENABLED:
        # ── Async path (production) ─────────────────────────────────────
        from tasks import process_webhook_task

        process_webhook_task.delay(payload.model_dump())
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Webhook accepted and queued for processing.",
                "transaction_id": payload.transaction_id,
            },
        )

    # ── Synchronous fallback (tests / local dev without Redis) ──────────
    # --- Idempotency check -----------------------------------------------
    existing_log = (
        db.query(models.PaymentLog)
        .filter(models.PaymentLog.transaction_id == payload.transaction_id)
        .first()
    )
    if existing_log:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Webhook already processed"},
        )

    # --- New transaction: validate booking --------------------------------
    booking = db.get(models.Booking, payload.booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with id={payload.booking_id} not found.",
        )

    # --- Persist log + update booking in one atomic commit ---------------
    new_log = models.PaymentLog(
        transaction_id=payload.transaction_id,
        booking_id=payload.booking_id,
        status=payload.status,
    )
    db.add(new_log)

    booking.status = (
        BookingStatus.CONFIRMED if payload.status == "SUCCESS" else BookingStatus.FAILED
    )

    db.commit()  # Both writes committed atomically

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"Webhook processed. Booking status updated to {booking.status.value}."
        },
    )
