"""Session persistence and a keychain-free, browser-free status check.

The stored artifact is a Playwright ``storageState`` JSON: a ``cookies`` array
plus per-origin ``localStorage``. Reading it tells us cheap things without
launching a browser: is there a signed-in session on disk, is its auth cookie
still live, and does localStorage hold a token-shaped key.

That last point is an early, safe hint at the scrape-vs-API fork: a bearer token
in localStorage means the app authenticates API calls with ``Authorization``.
Observed 2026-07-13: Instaffo has NO such token and authenticates with httpOnly
cookies (``_instaffo_session`` + Devise ``remember_user_token``), so the client
should send cookies, not a bearer header. We report key NAMES only, never values.

The authoritative "is the session still good" test is ``driver.deep_auth_check``
(it actually loads the app). This module is the fast, offline first look.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from instaffo_mcp.config import get_config

# localStorage key-name fragments that commonly hold auth material. Names only
# are inspected; values are never read or logged.
_TOKEN_NAME_HINTS = ("token", "auth", "jwt", "session", "access", "bearer")

# Devise/Rails auth cookies. Presence of a live login cookie means a signed-in
# user; an anonymous visit only gets ``_instaffo_session``. Analytics cookies
# (``_gat`` ~1 min, ``_ga``) must NEVER drive the expiry check — they rotate on
# the order of a minute and would falsely report the whole session as expired.
_LOGIN_COOKIE_NAMES = ("remember_user_token", "user.id")


@dataclass
class SessionStatus:
    present: bool  # any Instaffo cookie on disk (may be anonymous)
    logged_in: bool  # a live Devise auth cookie is present
    instaffo_cookie_count: int
    auth_cookie_expiry: float | None  # unix seconds; None if session-only/absent
    auth_cookie_expired: bool
    token_like_localstorage_keys: list[str]
    storage_state_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_live(expires: Any) -> bool:
    """A cookie is live if it is a session cookie (-1) or expires in the future."""
    if expires == -1:
        return True
    return isinstance(expires, (int, float)) and float(expires) > time.time()


def session_status() -> SessionStatus:
    """Report what the on-disk session looks like, without a browser."""
    cfg = get_config()
    path = cfg.storage_state_path
    data = _load(path)
    if data is None:
        return SessionStatus(
            present=False,
            logged_in=False,
            instaffo_cookie_count=0,
            auth_cookie_expiry=None,
            auth_cookie_expired=False,
            token_like_localstorage_keys=[],
            storage_state_path=str(path),
        )

    cookies = [c for c in data.get("cookies", []) if isinstance(c, dict)]
    instaffo = [c for c in cookies if "instaffo" in str(c.get("domain", ""))]

    login_cookies = [c for c in instaffo if c.get("name") in _LOGIN_COOKIE_NAMES]
    login_expiries = [
        float(c["expires"])
        for c in login_cookies
        if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0
    ]
    auth_expiry = min(login_expiries) if login_expiries else None
    logged_in = any(_is_live(c.get("expires")) for c in login_cookies)
    # Expired only makes sense if we ever had an auth cookie to begin with.
    auth_expired = bool(login_cookies) and not logged_in

    token_keys: list[str] = []
    for origin in data.get("origins", []):
        if not isinstance(origin, dict) or "instaffo" not in str(origin.get("origin", "")):
            continue
        for item in origin.get("localStorage", []):
            name = str(item.get("name", "")) if isinstance(item, dict) else ""
            if any(hint in name.lower() for hint in _TOKEN_NAME_HINTS):
                token_keys.append(name)

    return SessionStatus(
        present=bool(instaffo),
        logged_in=logged_in,
        instaffo_cookie_count=len(instaffo),
        auth_cookie_expiry=auth_expiry,
        auth_cookie_expired=auth_expired,
        token_like_localstorage_keys=sorted(set(token_keys)),
        storage_state_path=str(path),
    )
