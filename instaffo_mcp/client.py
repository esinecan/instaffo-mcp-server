"""HTTP client that replays Instaffo's candidate JSON API with the stored session.

Decided by observation (see README): every candidate data call is a JSON endpoint
under ``app.instaffo.com/candidate/api/v1/*`` authenticated purely by the session
cookie (no bearer token). So this is a thin cookie-authenticated ``httpx`` client,
not a browser. The browser (driver.py) is only for minting the session at login.

Reads are plain GETs. Writes (POST) additionally send Rails' CSRF token when the
app exposes one; the token is read once from the app shell's ``csrf-token`` meta.
Any 401/403, or a redirect to the sign-in page, is surfaced as
``InstaffoAuthError`` telling the caller to re-run ``instaffo-mcp --login``.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from instaffo_mcp.config import Config, get_config

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
API = "/candidate/api/v1"


class InstaffoAuthError(RuntimeError):
    """The stored session is missing or no longer accepted by Instaffo."""


class InstaffoClient:
    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or get_config()
        cookie = self._load_cookie_header()
        self._csrf: str | None = None
        self._http = httpx.Client(
            base_url=self.cfg.app_origin,
            timeout=30.0,
            follow_redirects=False,
            headers={
                "User-Agent": _UA,
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.cfg.app_origin}/candidate/job_suggestions/",
                "Cookie": cookie,
            },
        )

    # -- session -----------------------------------------------------------
    def _load_cookie_header(self) -> str:
        state = self.cfg.storage_state_path
        if not state.is_file():
            raise InstaffoAuthError(
                "No Instaffo session on disk. Run `instaffo-mcp --login`."
            )
        try:
            data = json.loads(state.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise InstaffoAuthError(f"Unreadable session file: {exc}") from exc
        parts = [
            f"{c['name']}={c['value']}"
            for c in data.get("cookies", [])
            if "instaffo.com" in str(c.get("domain", "")) and c.get("name")
        ]
        if not any(p.startswith(("_instaffo_session=", "remember_user_token=")) for p in parts):
            raise InstaffoAuthError(
                "Session file has no Instaffo auth cookie. Run `instaffo-mcp --login`."
            )
        return "; ".join(parts)

    def _csrf_token(self) -> str:
        if self._csrf is None:
            try:
                html = self._http.get(
                    "/candidate/job_suggestions/", headers={"Accept": "text/html"}
                ).text
                m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
                self._csrf = m.group(1) if m else ""
            except httpx.HTTPError:
                self._csrf = ""
        return self._csrf

    # -- transport ---------------------------------------------------------
    def _guard(self, r: httpx.Response) -> httpx.Response:
        loc = r.headers.get("location", "")
        if r.status_code in (401, 403) or (
            r.status_code in (301, 302, 303, 307, 308) and "/signin" in loc
        ):
            raise InstaffoAuthError(
                "Instaffo session expired or rejected. Run `instaffo-mcp --login`."
            )
        r.raise_for_status()
        return r

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._guard(self._http.get(path, params=params)).json()

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {}
        token = self._csrf_token()
        if token:
            headers["X-CSRF-Token"] = token
        r = self._guard(self._http.post(path, json=body or {}, headers=headers))
        if not r.content:
            return {"status": r.status_code}
        try:
            return r.json()
        except ValueError:
            return {"status": r.status_code, "text": r.text[:500]}

    def delete(self, path: str) -> Any:
        headers = {}
        token = self._csrf_token()
        if token:
            headers["X-CSRF-Token"] = token
        r = self._guard(self._http.request("DELETE", path, headers=headers))
        if not r.content:
            return {"status": r.status_code}
        try:
            return r.json()
        except ValueError:
            return {"status": r.status_code}

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "InstaffoClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
