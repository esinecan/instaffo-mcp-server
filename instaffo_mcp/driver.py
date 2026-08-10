"""Patchright (stealth Playwright) driver: login, deep auth check, capture.

This is the runnable core. It owns a single browser profile at
``<home>/profile`` and never touches the user's daily-driver browser. Two of its
three jobs unblock everything else:

- ``interactive_login`` opens a headed browser at the signin page, waits for the
  human to sign in (SSO included), then snapshots the session to storageState.
- ``capture_api_traffic`` records the XHR/fetch calls the app fires while you
  click around. That recording is the one observation that decides whether the
  domain tools should replay a JSON API or drive the page.

``deep_auth_check`` is the authoritative "is the session still good" test: it
actually loads the app and sees whether it lands on a signed-in page.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from patchright.async_api import BrowserContext, async_playwright

from instaffo_mcp.config import Config, get_config

logger = logging.getLogger(__name__)


def _is_signed_out(url: str) -> bool:
    """True when the URL is an auth gate rather than an app page.

    Locale-independent: keys off path only, never button text.
    """
    return "/signin" in url or "/signup" in url or "/login" in url


async def _launch(cfg: Config, *, headless: bool) -> tuple[Any, BrowserContext]:
    """Launch a persistent context on the owned profile. Caller closes both."""
    cfg.profile_dir.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(cfg.profile_dir),
        headless=headless,
        viewport=None if not headless else {"width": 1440, "height": 900},
    )
    return pw, context


async def _snapshot_storage_state(cfg: Config, context: BrowserContext) -> None:
    cfg.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(cfg.storage_state_path))
    # Session material is private; lock it down.
    try:
        cfg.storage_state_path.chmod(0o600)
    except OSError:
        pass
    logger.info("Wrote session snapshot to %s", cfg.storage_state_path)


async def interactive_login(cfg: Config | None = None) -> bool:
    """Open a headed browser, wait for a manual login, persist the session.

    Returns True once the app leaves the auth gate, False on timeout.
    """
    cfg = cfg or get_config()
    timeout_s = cfg.login_timeout_min * 60
    pw, context = await _launch(cfg, headless=False)
    try:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(cfg.signin_url, wait_until="domcontentloaded")
        print(
            f"\n  A browser opened at {cfg.signin_url}\n"
            f"  Sign in to Instaffo. Waiting up to {cfg.login_timeout_min} min...\n"
        )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not _is_signed_out(page.url):
                body = await page.evaluate("() => document.body?.innerText || ''")
                if isinstance(body, str) and body.strip():
                    await _snapshot_storage_state(cfg, context)
                    print("  Login captured.\n")
                    return True
            await asyncio.sleep(1)
        print("  Timed out waiting for login.\n")
        return False
    finally:
        await context.close()
        await pw.stop()


async def deep_auth_check(cfg: Config | None = None) -> dict[str, Any]:
    """Load the app on the owned profile and report whether it is signed in."""
    cfg = cfg or get_config()
    if not cfg.profile_dir.exists() or not any(cfg.profile_dir.iterdir()):
        return {"authenticated": False, "reason": "no profile on disk", "url": None}
    pw, context = await _launch(cfg, headless=cfg.headless)
    try:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(cfg.app_origin, wait_until="domcontentloaded")
        await asyncio.sleep(2)  # let the SPA settle any auth redirect
        signed_in = not _is_signed_out(page.url)
        if signed_in:
            await _snapshot_storage_state(cfg, context)  # refresh rolling session
        return {
            "authenticated": signed_in,
            "reason": "landed on app page" if signed_in else "redirected to auth gate",
            "url": page.url,
        }
    finally:
        await context.close()
        await pw.stop()


_REDACT_HEADERS = {
    "cookie",
    "set-cookie",
    "authorization",
    "x-csrf-token",
    "x-xsrf-token",
}
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)


def _redact(headers: dict[str, str]) -> dict[str, str]:
    """Keep header *names* (auth-vs-telemetry needs them); drop secret values."""
    return {
        k: (f"<redacted {len(v)} chars>" if k.lower() in _REDACT_HEADERS else v)
        for k, v in headers.items()
    }


def _slug(method: str, url: str) -> str:
    """Stable fixture basename: uuids and numeric ids collapse to placeholders."""
    path = urlparse(url).path.strip("/")
    path = path.replace("candidate/api/v1/", "")
    path = _UUID_RE.sub("uuid", path)
    path = re.sub(r"/\d+(?=/|$)", "/id", path)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").lower()
    return f"{method.lower()}-{slug}"[:70] if slug else method.lower()


_TELEMETRY_HOSTS = (
    "plausible.io",
    "sentry.io",
    "segment.",
    "datadoghq.",
    "amplitude.",
    "google-analytics.",
    "googletagmanager.",
    "hotjar.",
    "intercom.",
)
_TELEMETRY_PATHS = ("/event", "/collect", "/track", "/beacon", "/envelope")


def _is_contract_traffic(url: str, app_origin: str) -> bool:
    """Keep the site's own API; drop telemetry.

    The skill's filter-validation rule: a non-empty result is not a working
    filter. Third-party beacons match ``/api/`` too (plausible ``/api/event``,
    sentry ``/api/<id>/envelope/``), and Instaffo fires its own ``/api/v1/event``
    beacon. Host-scope first, then drop beacon paths.
    """
    u = urlparse(url)
    if u.netloc != urlparse(app_origin).netloc:
        return False
    if any(h in u.netloc for h in _TELEMETRY_HOSTS):
        return False
    return not any(u.path.rstrip("/").endswith(p) for p in _TELEMETRY_PATHS)


def _ext_for(content_type: str) -> str:
    """Extension tells the truth about framing (skill: wire format section)."""
    ct = (content_type or "").lower()
    if "json" in ct:
        return "json"
    if "html" in ct:
        return "html"
    return "txt"


async def capture_api_traffic(
    cfg: Config | None = None,
    *,
    fixtures_dir: Path | None = None,
    case: str = "happy",
) -> Path:
    """Record XHR/fetch traffic while the human clicks around the app.

    Two instruments in one, chosen by ``fixtures_dir``:

    - ``fixtures_dir=None`` (default) — the original diagnostic. Per request:
      method, URL, whether ``Authorization`` and/or ``Cookie`` was sent (the
      scrape-vs-API tell) and a short post-body sample; per response: status and
      content-type. Enough to decide the fork, not enough to build against.
    - ``fixtures_dir=<path>`` — contract-grade capture. Full request headers and
      body, full response headers and body, written byte-exact to
      ``<fixtures_dir>/<method>-<path>-<case>.<ext>``. This is what
      site-as-tool construction consumes.

    Secret header *values* (cookie, authorization, csrf) are redacted in both
    modes; the header names survive, because separating auth from telemetry
    needs the name list.
    """
    cfg = cfg or get_config()
    cfg.captures_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg.captures_dir / f"capture-{int(time.time())}.jsonl"
    if fixtures_dir is not None:
        fixtures_dir = Path(fixtures_dir)
        fixtures_dir.mkdir(parents=True, exist_ok=True)

    pw, context = await _launch(cfg, headless=False)
    records: list[dict[str, Any]] = []
    seen: dict[str, int] = {}

    def _fixture_path(method: str, url: str, part: str, ext: str) -> Path:
        base = _slug(method, url)
        n = seen.get(base, 0)
        suffix = "" if n <= 1 else f"-{n}"
        name = f"{base}-{case}{suffix}{'-request' if part == 'request' else ''}.{ext}"
        return fixtures_dir / name  # type: ignore[union-attr]

    def on_request(request: Any) -> None:
        if request.resource_type not in ("xhr", "fetch"):
            return
        headers = request.headers  # already lowercased keys
        records.append(
            {
                "kind": "request",
                "method": request.method,
                "url": request.url,
                "resource_type": request.resource_type,
                "has_authorization": "authorization" in headers,
                "has_cookie": "cookie" in headers,
                "post_data_sample": (request.post_data or "")[:300],
            }
        )

    async def on_response(response: Any) -> None:
        req = response.request
        if req.resource_type not in ("xhr", "fetch"):
            return
        content_type = response.headers.get("content-type", "")
        rec: dict[str, Any] = {
            "kind": "response",
            "url": response.url,
            "status": response.status,
            "content_type": content_type,
        }
        if fixtures_dir is not None and _is_contract_traffic(
            response.url, cfg.app_origin
        ):
            base = _slug(req.method, response.url)
            seen[base] = seen.get(base, 0) + 1
            rec["request_headers"] = _redact(await req.all_headers())
            rec["response_headers"] = _redact(await response.all_headers())
            body = req.post_data
            if body:
                p = _fixture_path(req.method, response.url, "request", "json")
                p.write_text(body, encoding="utf-8")
                rec["request_fixture"] = p.name
            try:
                raw = await response.body()
            except Exception as exc:  # discarded, redirect, or no body
                rec["response_body_error"] = f"{type(exc).__name__}: {exc}"
            else:
                p = _fixture_path(
                    req.method, response.url, "response", _ext_for(content_type)
                )
                p.write_bytes(raw)
                rec["response_fixture"] = p.name
                rec["response_bytes"] = len(raw)
        records.append(rec)

    context.on("request", on_request)
    context.on("response", on_response)

    try:
        page = context.pages[0] if context.pages else await context.new_page()
        target = cfg.app_origin if _has_session(cfg) else cfg.signin_url
        await page.goto(target, wait_until="domcontentloaded")
        if fixtures_dir is None:
            print(
                "\n  Capturing Instaffo API traffic.\n"
                "  Sign in if needed, then open your matches, a job, and a chat.\n"
                "  CLOSE THE BROWSER WINDOW when done to finish the capture.\n"
            )
        else:
            print(
                f"\n  Contract capture (case={case}) -> {fixtures_dir}\n"
                "  Perform ONE intent, changing ONE variable, then close the window.\n"
                "  CLOSE THE BROWSER WINDOW when done to finish the capture.\n"
            )
        # Run until the human closes the window (no stdin needed, so this works
        # when launched in the background), capped by the login timeout.
        deadline = time.monotonic() + cfg.login_timeout_min * 60
        snapshotted = False
        while time.monotonic() < deadline:
            try:
                pages = context.pages
            except Exception:
                break  # context torn down
            if not pages:
                break  # window(s) closed
            if not snapshotted and not _is_signed_out(pages[0].url):
                try:
                    await _snapshot_storage_state(cfg, context)
                    snapshotted = True
                except Exception:
                    pass
            await asyncio.sleep(1)
    finally:
        # Response handlers are coroutines; give in-flight body reads a moment
        # to land before the context goes away and they start throwing.
        await asyncio.sleep(1.5)
        for event, handler in (("request", on_request), ("response", on_response)):
            try:
                context.remove_listener(event, handler)
            except Exception:
                pass
        try:
            await context.close()
        except Exception:
            pass
        await pw.stop()

    out_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    logger.info("Wrote %d traffic records to %s", len(records), out_path)

    if fixtures_dir is not None:
        index = fixtures_dir / "index.jsonl"
        api = [
            r
            for r in records
            if r.get("kind") == "response"
            and _is_contract_traffic(r.get("url", ""), cfg.app_origin)
        ]
        with index.open("a", encoding="utf-8") as fh:
            for r in api:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        written = sum(1 for r in api if r.get("response_fixture"))
        logger.info(
            "Contract capture: %d API responses, %d fixtures -> %s",
            len(api),
            written,
            fixtures_dir,
        )
    return out_path


def _has_session(cfg: Config) -> bool:
    return cfg.storage_state_path.is_file()
