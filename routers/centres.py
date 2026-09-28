from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /centres/
# ---------------------------------------------------------------------------
@router.post(
    "/",
    response_model=schemas.DiagnosticCentreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new diagnostic centre",
)
def create_centre(
    centre_in: schemas.DiagnosticCentreBase,
    db: Session = Depends(get_db),
):
    """
    Register a new diagnostic centre.

    Accepts a name and location, persists the record, and returns the
    newly created centre (with an empty tests list).
    """
    new_centre = models.DiagnosticCentre(
        name=centre_in.name,
        location=centre_in.location,
    )
    db.add(new_centre)
    db.commit()
    db.refresh(new_centre)
    return new_centre


# ---------------------------------------------------------------------------
# GET /centres/
# ---------------------------------------------------------------------------
@router.get(
    "/",
    response_model=List[schemas.DiagnosticCentreResponse],
    summary="List all diagnostic centres",
)
def list_centres(
    skip: int = Query(default=0, ge=0, description="Number of records to skip (offset)"),
    limit: int = Query(default=10, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
):
    """
    Return a paginated list of diagnostic centres with their associated tests.

    - `skip`: offset — how many records to skip (default 0).
    - `limit`: page size — max records to return, capped at 100 (default 10).

    FastAPI serialises the ORM relationship automatically via
    `DiagnosticCentreResponse.tests: List[DiagnosticTestResponse]`.
    """
    return db.query(models.DiagnosticCentre).offset(skip).limit(limit).all()


# ---------------------------------------------------------------------------
# POST /centres/{centre_id}/tests/
# ---------------------------------------------------------------------------
@router.post(
    "/{centre_id}/tests/",
    response_model=schemas.DiagnosticTestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a diagnostic test to a centre",
)
def add_test_to_centre(
    centre_id: int,
    test_in: schemas.DiagnosticTestBase,
    db: Session = Depends(get_db),
):
    """
    Add a new diagnostic test to an existing centre.

    - Returns **404** if the centre does not exist.
    - `price` must be strictly positive (enforced by the schema's `gt=0` validator).
    """
    centre = db.get(models.DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnostic centre with id={centre_id} not found.",
        )

    new_test = models.DiagnosticTest(
        centre_id=centre_id,
        name=test_in.name,
        price=test_in.price,
    )
    db.add(new_test)
    db.commit()
    db.refresh(new_test)
    return new_test
