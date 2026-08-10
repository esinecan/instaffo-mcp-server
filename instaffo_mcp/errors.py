"""The six-kind error taxonomy, reproduced standalone.

Deliberately not imported from a shared package: this repo is portable on
purpose, so the taxonomy lives here in full even though other site-as-tool
repos carry their own copy.

Kinds (closed set):

    auth_expired  the session is gone or was never accepted
    blocked       an anti-bot / WAF interstitial stood in the way
    schema_drift  the site changed shape, or we cannot positively classify
    transient     retryable: timeout, 429, 5xx
    invalid_input the request was well-formed but wrong
    empty         a SUCCESS shape, not an error: the answer is "nothing"

Classification happens at exactly two choke points, both in ``client.py``:
the HTTP status table, and the 200-with-in-band-error path. Nothing else in
this repo classifies.

The default rule is load-bearing: **anything we cannot positively classify is
``schema_drift``**, because in a site-as-tool repo the dominant source of
surprise is the site moving. That makes drift loud, which maintenance depends
on.
"""

from __future__ import annotations

from typing import Any

AUTH_EXPIRED = "auth_expired"
BLOCKED = "blocked"
SCHEMA_DRIFT = "schema_drift"
TRANSIENT = "transient"
INVALID_INPUT = "invalid_input"
EMPTY = "empty"

KINDS = (AUTH_EXPIRED, BLOCKED, SCHEMA_DRIFT, TRANSIENT, INVALID_INPUT, EMPTY)

# CLI exit codes. 0 covers success and `empty` -- `empty` is an answer.
EXIT_CODES = {
    None: 0,
    EMPTY: 0,
    INVALID_INPUT: 2,
    AUTH_EXPIRED: 3,
    BLOCKED: 4,
    SCHEMA_DRIFT: 5,
    TRANSIENT: 6,
}

# Markers that mean "a challenge page", not "your session died".
_CHALLENGE_MARKERS = (
    "datadome",
    "captcha",
    "cf-challenge",
    "cf_chl",
    "just a moment",
    "attention required",
    "awswaf",
    "px-captcha",
)


class ToolError(Exception):
    """An error that crosses the MCP boundary as a value, never as a raise."""

    def __init__(self, kind: str, message: str, **detail: Any) -> None:
        super().__init__(message)
        if kind not in KINDS:
            raise ValueError(f"unknown taxonomy kind: {kind!r}")
        self.kind = kind
        self.message = message
        self.detail = detail

    def envelope(self) -> dict[str, Any]:
        env: dict[str, Any] = {"ok": False, "kind": self.kind, "error": self.message}
        if self.detail:
            env["detail"] = self.detail
        return env

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.kind]


def ok(data: Any, **meta: Any) -> dict[str, Any]:
    env: dict[str, Any] = {"ok": True, "data": data}
    if meta:
        env.update(meta)
    return env


def looks_like_challenge(body: str) -> bool:
    low = body[:4000].lower()
    return any(m in low for m in _CHALLENGE_MARKERS)


def classify_status(status: int, body: str = "") -> str:
    """Choke point 1: the HTTP status table.

    Instaffo specifics verified 2026-08-10 (docs/API.md, PASS 2):

    - **302** is an auth failure, not a redirect to follow. An unauthenticated
      request with a browser-ish ``Accept`` returns 302 to ``/signin``; follow
      it and you get HTTP **200 carrying an HTML login page**, which is the
      success-shaped failure this whole taxonomy exists to catch.
    - **403** on this API is `{"errors":{"base":"not_allowed"}}` -- an auth
      failure, not a challenge. Sniff for challenge markers before assuming
      ``blocked``.
    - **404 / 400 / 422** all carry `{"errors": {...}}` and are input errors.
    """
    if status in (301, 302, 303, 307, 308):
        return AUTH_EXPIRED
    if status == 401:
        return AUTH_EXPIRED
    if status == 403:
        return BLOCKED if looks_like_challenge(body) else AUTH_EXPIRED
    if status in (400, 404, 409, 422):
        return INVALID_INPUT
    if status in (408, 429) or status >= 500:
        return TRANSIENT
    return SCHEMA_DRIFT


def classify_body(status: int, content_type: str, body: str) -> str | None:
    """Choke point 2: a 2xx that is not actually a success.

    Returns a kind when the *payload* betrays a failure the status hid, or
    ``None`` when the response really is a success.

    The one that bites on Instaffo: HTML served where JSON is the contract.
    Per the taxonomy spec that is ``blocked`` when it is a challenge and
    ``auth_expired`` when it is a login page -- never ``schema_drift``, and
    never success.
    """
    if 200 <= status < 300:
        ct = (content_type or "").lower()
        if "html" in ct or body.lstrip()[:9].lower().startswith("<!doctype"):
            return BLOCKED if looks_like_challenge(body) else AUTH_EXPIRED
    return None
