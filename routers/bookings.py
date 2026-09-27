from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from routers.auth import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /bookings/
# ---------------------------------------------------------------------------
@router.post(
    "/",
    response_model=schemas.BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new booking (requires authentication)",
)
def create_booking(
    booking_in: schemas.BookingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Book a diagnostic test for the currently authenticated user.

    **Edge-case validation:**
    - Returns **404** if `test_id` does not exist.
    - Returns **400** if the test does not belong to the requested `centre_id`
      (prevents mismatched centre/test combinations).

    **Security:** The booking `amount` is always taken from the database record
    for the test — never from user-supplied input — to prevent price spoofing.
    """
    # 1. Verify the test exists
    test = db.get(models.DiagnosticTest, booking_in.test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnostic test with id={booking_in.test_id} not found.",
        )

    # 2. Verify the test belongs to the requested centre
    if test.centre_id != booking_in.centre_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Test id={booking_in.test_id} does not belong to "
                f"centre id={booking_in.centre_id}."
            ),
        )

    # 3. Create the booking — amount comes from the DB, not the request body
    new_booking = models.Booking(
        user_id=current_user.id,
        test_id=booking_in.test_id,
        centre_id=booking_in.centre_id,
        appointment_date_time=booking_in.appointment_date_time,
        amount=test.price,                      # server-side price calculation
        status=models.BookingStatus.PENDING,    # explicit default
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    return new_booking
