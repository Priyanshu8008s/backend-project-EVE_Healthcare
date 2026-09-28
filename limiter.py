"""
limiter.py — Centralised SlowAPI rate-limiter instance.

Import `limiter` wherever you need to decorate an endpoint, and
wire it into the FastAPI app in main.py.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Key function: rate-limit per client IP address.
# For production behind a reverse proxy, swap to get_ipaddr or a
# custom function that reads X-Forwarded-For.
limiter = Limiter(key_func=get_remote_address)
