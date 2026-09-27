import random

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
import schemas
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
# Idempotent Webhook — public, no auth
# ---------------------------------------------------------------------------
@router.post(
    "/webhook/",
    summary="Receive a payment webhook (idempotent, no auth required)",
)
def payment_webhook(
    payload: schemas.WebhookPayload,
    db: Session = Depends(get_db),
):
    """
    Process an incoming payment webhook from a payment gateway.

    **Idempotency guarantee:**  If a `PaymentLog` record already exists for
    `transaction_id`, the request is a duplicate — return immediately without
    touching the booking or creating a second log entry.

    **Single-transaction write:** The new `PaymentLog` row and the `Booking`
    status update are committed together, so a partial failure cannot leave
    the database in an inconsistent state.
    """
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

    return {"message": f"Webhook processed. Booking status updated to {booking.status.value}."}
