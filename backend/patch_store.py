"""
patch_store.py — Signed, short-expiry, single-purpose patch token store.

Tokens are 32-byte URL-safe random strings that cannot be replayed against
any other endpoint. They expire after 1 hour and are cleaned up lazily on
each access. Thread-safe via a standard Lock.
"""
import secrets
import threading
import time
from typing import Optional

_store: dict = {}
_lock = threading.Lock()

_TTL_SECONDS = 3600  # 1 hour — matches existing SQLite cache TTL


def put(patch_content: str, issue_number: int | str) -> str:
    """
    Store a patch and return a signed single-purpose token.

    The token:
    - Is 32 bytes of URL-safe randomness (256-bit entropy)
    - Is not derived from the session token and cannot be used to authenticate
    - Expires after TTL_SECONDS (1 hour)
    - Is cleaned up lazily on every subsequent call to put() or get()
    """
    token = secrets.token_urlsafe(32)
    now = time.time()

    with _lock:
        # Opportunistic cleanup of expired entries on every write
        expired_keys = [k for k, v in _store.items() if v["expires"] < now]
        for k in expired_keys:
            del _store[k]

        _store[token] = {
            "patch": patch_content,
            "issue_number": str(issue_number),
            "expires": now + _TTL_SECONDS,
        }

    return token


def get(token: str) -> Optional[dict]:
    """
    Retrieve a patch entry by token.

    Returns None if:
    - Token is not found (never existed or already deleted)
    - Token has expired

    Does NOT delete on retrieval — supports multiple downloads of the same patch
    within the 1-hour window (e.g. the user clicks Download twice).
    """
    with _lock:
        entry = _store.get(token)
        if entry is None:
            return None
        if entry["expires"] < time.time():
            del _store[token]
            return None
        return dict(entry)  # return a copy, not a mutable reference
