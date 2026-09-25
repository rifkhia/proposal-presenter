"""Editor sign-in: one shared password, stored only as a hash in EDIT_PASSWORD_HASH.

The hash is PBKDF2-SHA256 in the form `pbkdf2_sha256:<iterations>:<salt hex>:<hash hex>`.
It deliberately contains no `$` (unlike bcrypt's `$2b$...`), because docker compose
treats `$` in .env files as variable interpolation and would silently mangle it.

A successful sign-in sets an HttpOnly cookie holding an expiry and an HMAC of it. The
HMAC key mixes a random secret kept in DATA_DIR with the password hash, so sessions
survive restarts but are all invalidated when the password changes.
"""

import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, Response

from .config import DATA_DIR, EDIT_PASSWORD_HASH

log = logging.getLogger("uvicorn.error")

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000  # OWASP 2023 recommendation for PBKDF2-SHA256
COOKIE = "pp_session"
SESSION_SECONDS = 12 * 3600

MAX_FAILURES = 5
FAILURE_WINDOW = 300  # seconds
_failures: dict[str, deque] = defaultdict(deque)


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{ALGORITHM}:{iterations}:{salt.hex()}:{digest.hex()}"


def _parse(stored: str):
    try:
        algorithm, iterations, salt, digest = stored.split(":")
        if algorithm != ALGORITHM:
            return None
        return int(iterations), bytes.fromhex(salt), bytes.fromhex(digest)
    except ValueError:
        return None


def verify_password(password: str, stored: str) -> bool:
    parsed = _parse(stored)
    if parsed is None:
        return False
    iterations, salt, expected = parsed
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def enabled() -> bool:
    return _parse(EDIT_PASSWORD_HASH) is not None


def check_config() -> None:
    if EDIT_PASSWORD_HASH and not enabled():
        log.error("EDIT_PASSWORD_HASH is set but not a valid %s hash; editing is disabled", ALGORITHM)
    elif not EDIT_PASSWORD_HASH:
        log.info("EDIT_PASSWORD_HASH not set; editing is disabled")


def _key() -> bytes:
    path = DATA_DIR / "session.key"
    if not path.exists():
        path.write_bytes(secrets.token_bytes(32))
        path.chmod(0o600)
    return hmac.new(path.read_bytes(), EDIT_PASSWORD_HASH.encode(), hashlib.sha256).digest()


def _sign(expires: int) -> str:
    return hmac.new(_key(), f"session:{expires}".encode(), hashlib.sha256).hexdigest()


def is_signed_in(request: Request) -> bool:
    if not enabled():
        return False
    token = request.cookies.get(COOKIE, "")
    expires, _, signature = token.partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return False
    return hmac.compare_digest(signature, _sign(int(expires)))


def require_editor(request: Request) -> None:
    """FastAPI dependency for endpoints that change proposals."""
    if not enabled():
        raise HTTPException(403, "Editing is disabled on this server")
    if not is_signed_in(request):
        raise HTTPException(401, "Sign in to edit")


def _client(request: Request) -> str:
    # The backend is only reachable through our nginx, which sets X-Real-IP.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def sign_in(request: Request, response: Response, password: str) -> None:
    if not enabled():
        raise HTTPException(403, "Editing is disabled on this server")
    client = _client(request)
    recent = _failures[client]
    while recent and recent[0] < time.time() - FAILURE_WINDOW:
        recent.popleft()
    if len(recent) >= MAX_FAILURES:
        wait = int(recent[0] + FAILURE_WINDOW - time.time()) // 60 + 1
        raise HTTPException(429, f"Too many attempts. Try again in {wait} min.")
    if not verify_password(password, EDIT_PASSWORD_HASH):
        recent.append(time.time())
        raise HTTPException(401, "Wrong password")
    recent.clear()
    expires = int(time.time()) + SESSION_SECONDS
    response.set_cookie(
        COOKIE,
        f"{expires}.{_sign(expires)}",
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
        path="/api",
    )


def sign_out(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/api")
