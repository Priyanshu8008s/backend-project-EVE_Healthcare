from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import List
from enum import Enum

# Define the suggested booking states
class BookingStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

# --- Authentication Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, description="Minimum length of 6 characters")

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# --- Diagnostic Test Schemas ---
class DiagnosticTestBase(BaseModel):
    name: str
    price: float = Field(gt=0, description="Price must be strictly positive")

class DiagnosticTestResponse(DiagnosticTestBase):
    id: int
    centre_id: int

    model_config = {"from_attributes": True}

# --- Diagnostic Centre Schemas ---
class DiagnosticCentreBase(BaseModel):
    name: str
    location: str

class DiagnosticCentreResponse(DiagnosticCentreBase):
    id: int
    tests: List[DiagnosticTestResponse] = []

    model_config = {"from_attributes": True}

# --- Booking Schemas ---
class BookingCreate(BaseModel):
    test_id: int
    centre_id: int
    appointment_date_time: datetime
    # Note: 'amount' is excluded from creation. The backend should calculate 
    # this using the test_id to prevent users from spoofing the test price.

class BookingResponse(BaseModel):
    id: int
    user_id: int
    test_id: int
    centre_id: int
    appointment_date_time: datetime
    amount: float
    status: BookingStatus

    model_config = {"from_attributes": True}

# --- Payment & Webhook Schemas ---
class PaymentSimulateRequest(BaseModel):
    booking_id: int
    # In a real system, the backend fetches the amount from the DB. 
    # For a simulated request body, taking amount is acceptable.
    amount: float = Field(gt=0)

class WebhookPayload(BaseModel):
    transaction_id: str = Field(..., description="Unique ID to ensure idempotency")
    booking_id: int
    status: str = Field(pattern="^(SUCCESS|FAILED)$")