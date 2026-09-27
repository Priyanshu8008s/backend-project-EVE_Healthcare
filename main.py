from fastapi import FastAPI
from routers import auth, centres, bookings, payments

app = FastAPI(
    title="EVE Healthcare Diagnostic API",
    description=(
        "Backend API for the EVE Healthcare diagnostic platform. "
        "Provides authentication, diagnostic centre management, test booking, and payment processing."
    ),
    version="0.3.0",
)

# --- Routers ---
app.include_router(auth.router)
app.include_router(centres.router, prefix="/centres", tags=["Centres"])
app.include_router(bookings.router, prefix="/bookings", tags=["Bookings"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])


@app.get("/", tags=["Health"])
def root():
    """Health-check endpoint."""
    return {"status": "ok", "message": "EVE Healthcare API is running."}
