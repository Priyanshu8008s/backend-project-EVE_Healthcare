import time
from contextlib import asynccontextmanager

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, Request
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

from config import settings
from logger import configure_logging
from limiter import limiter
from routers import auth, centres, bookings, payments

# ---------------------------------------------------------------------------
# Logging — initialise before the app so the first structlog call works
# ---------------------------------------------------------------------------
configure_logging(json_logs=False)  # flip to True in production

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown events
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialise application-wide resources on startup and clean them up on shutdown.

    Currently manages:
    - FastAPICache backed by Redis (for caching GET /centres/).
    """
    redis_client = aioredis.from_url(
        settings.REDIS_URL, encoding="utf-8", decode_responses=True
    )
    FastAPICache.init(RedisBackend(redis_client), prefix="eve-cache")
    log.info("FastAPICache initialised", redis_url=settings.REDIS_URL)
    yield
    # Graceful shutdown — nothing extra needed; aioredis manages its pool
    log.info("Application shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="EVE Healthcare Diagnostic API",
    description=(
        "Backend API for the EVE Healthcare diagnostic platform. "
        "Provides authentication, diagnostic centre management, test booking, and payment processing."
    ),
    version="0.5.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware — order matters; added last = runs outermost first
# ---------------------------------------------------------------------------

# 1. Correlation ID: generates/propagates an X-Correlation-ID header so every
#    request (and its log lines) can be traced end-to-end.
app.add_middleware(CorrelationIdMiddleware)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Structured request/response logger.

    Binds the correlation_id into structlog's context-var store so every log
    line emitted during this request automatically carries the ID without any
    explicit passing.
    """
    from asgi_correlation_id import correlation_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id.get(),
        method=request.method,
        path=request.url.path,
    )

    start = time.perf_counter()
    log.info("request.started")

    response = await call_next(request)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    log.info(
        "request.completed",
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(centres.router, prefix="/centres", tags=["Centres"])
app.include_router(bookings.router, prefix="/bookings", tags=["Bookings"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])


@app.get("/", tags=["Health"])
def root():
    """Health-check endpoint."""
    return {"status": "ok", "message": "EVE Healthcare API is running."}
