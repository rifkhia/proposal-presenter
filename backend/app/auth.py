"""Editor sign-in, with personal accounts or the shared editor password.

Passwords are hashed with PBKDF2-SHA256 in the form
`pbkdf2_sha256:<iterations>:<salt hex>:<hash hex>`: the shared one in EDIT_PASSWORD_HASH,
personal ones in the `users` table. The format deliberately contains no `$` (unlike
bcrypt's `$2b$...`), because docker compose treats `$` in .env files as variable
interpolation and would silently mangle it.

Anyone who knows the shared password can register an account (it acts as the sign-up
code), so accounts never grant more than the shared password already does. Editing is
off, for accounts too, while EDIT_PASSWORD_HASH is unset.

A successful sign-in sets an HttpOnly cookie holding an expiry, the username ("" for the
shared password) and an HMAC of both. The HMAC key mixes a random secret kept in DATA_DIR
with the shared password hash, so sessions survive restarts but are all invalidated when
the shared password changes. Deleting a user from the table ends their sessions.
"""

import functools
import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, Response

from . import db
from .config import DATA_DIR, EDIT_PASSWORD_HASH

log = logging.getLogger("uvicorn.error")

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000  # OWASP 2023 recommendation for PBKDF2-SHA256
COOKIE = "pp_session"
SESSION_SECONDS = 12 * 3600
USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,39}")
MIN_PASSWORD = 8

MAX_FAILURES = 5
FAILURE_WINDOW = 300  # seconds
_failures: dict[str, deque] = defaultdict(deque)


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or ITERATIONS
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


@functools.cache
def _dummy_hash() -> str:
    # Checked against for unknown usernames, so they take as long as wrong passwords.
    return hash_password(secrets.token_hex(16))


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


def _sign(expires: int, username: str) -> str:
    # Shared-password sessions keep the original message, so they survive this upgrade.
    message = f"session:{expires}:{username}" if username else f"session:{expires}"
    return hmac.new(_key(), message.encode(), hashlib.sha256).hexdigest()


def _find_user(username: str):
    with db.connect() as conn:
        return conn.execute(
            "SELECT username, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()


def is_admin(username: str | None) -> bool:
    if not username:
        return False
    with db.connect() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE username = ?", (username,)).fetchone()
    return bool(row and row["is_admin"])


def set_admin(username: str, password: str) -> bool:
    """Creates the account as an admin, or makes an existing one admin with this password.
    Returns True if the account already existed."""
    if not USERNAME.fullmatch(username):
        raise ValueError("Username: 3-40 letters, digits, . _ or -, starting with a letter or digit")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters")
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ?, is_admin = 1 WHERE username = ?",
            (hash_password(password), username),
        )
        if cur.rowcount:
            return True
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (username, hash_password(password)),
        )
        return False


def current_user(request: Request) -> str | None:
    """The signed-in username, "" for the shared password, or None if not signed in."""
    if not enabled():
        return None
    token = request.cookies.get(COOKIE, "")
    expires, _, rest = token.partition(".")
    signature, _, username = rest.partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return None
    if not hmac.compare_digest(signature, _sign(int(expires), username)):
        return None
    if username and _find_user(username) is None:
        return None
    return username


def is_signed_in(request: Request) -> bool:
    return current_user(request) is not None


def require_editor(request: Request) -> str:
    """FastAPI dependency for endpoints that change proposals. Returns the username."""
    if not enabled():
        raise HTTPException(403, "Editing is disabled on this server")
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "Sign in to edit")
    return user


def _client(request: Request) -> str:
    # The backend is only reachable through our nginx, which sets X-Real-IP.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def _attempt(request: Request, ok, message: str) -> None:
    """Runs a password check, blocking a client after MAX_FAILURES failures in FAILURE_WINDOW."""
    if not enabled():
        raise HTTPException(403, "Editing is disabled on this server")
    recent = _failures[_client(request)]
    while recent and recent[0] < time.time() - FAILURE_WINDOW:
        recent.popleft()
    if len(recent) >= MAX_FAILURES:
        wait = int(recent[0] + FAILURE_WINDOW - time.time()) // 60 + 1
        raise HTTPException(429, f"Too many attempts. Try again in {wait} min.")
    if not ok():
        recent.append(time.time())
        raise HTTPException(401, message)
    recent.clear()


def _set_cookie(request: Request, response: Response, username: str) -> None:
    expires = int(time.time()) + SESSION_SECONDS
    response.set_cookie(
        COOKIE,
        f"{expires}.{_sign(expires, username)}.{username}",
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https",
        path="/api",
    )


def sign_in(request: Request, response: Response, password: str, username: str = "") -> str:
    """Signs in with an account, or with the shared password when username is empty.
    Returns the canonical username."""
    if not username:
        _attempt(request, lambda: verify_password(password, EDIT_PASSWORD_HASH), "Wrong password")
        _set_cookie(request, response, "")
        return ""
    user = _find_user(username)
    stored = user["password_hash"] if user else _dummy_hash()
    _attempt(request, lambda: verify_password(password, stored) and user is not None, "Wrong username or password")
    _set_cookie(request, response, user["username"])
    return user["username"]


def register(request: Request, response: Response, username: str, password: str, code: str) -> str:
    """Creates an account (the shared password is the sign-up code) and signs it in."""
    if not USERNAME.fullmatch(username):
        raise HTTPException(400, "Username: 3-40 letters, digits, . _ or -, starting with a letter or digit")
    if len(password) < MIN_PASSWORD:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD} characters")
    _attempt(request, lambda: verify_password(code, EDIT_PASSWORD_HASH), "Wrong sign-up code")
    try:
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, hash_password(password)),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That username is taken")
    log.info("registered user %s", username)
    _set_cookie(request, response, username)
    return username


def sign_out(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/api")
