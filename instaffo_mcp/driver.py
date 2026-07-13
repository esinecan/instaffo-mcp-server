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
import time
from pathlib import Path
from typing import Any

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


async def capture_api_traffic(cfg: Config | None = None) -> Path:
    """Record XHR/fetch traffic while the human clicks around the app.

    This is the inspection instrument. It logs, per request, the method, URL,
    resource type, and whether an ``Authorization`` header and/or ``Cookie`` was
    sent (the scrape-vs-API tell), plus a short post-body sample; and per
    response, the status and content-type (does the endpoint return JSON?).
    Values of cookies and tokens are never recorded.
    """
    cfg = cfg or get_config()
    cfg.captures_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg.captures_dir / f"capture-{int(time.time())}.jsonl"

    pw, context = await _launch(cfg, headless=False)
    records: list[dict[str, Any]] = []

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

    def on_response(response: Any) -> None:
        req = response.request
        if req.resource_type not in ("xhr", "fetch"):
            return
        records.append(
            {
                "kind": "response",
                "url": response.url,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
            }
        )

    context.on("request", on_request)
    context.on("response", on_response)

    try:
        page = context.pages[0] if context.pages else await context.new_page()
        target = cfg.app_origin if _has_session(cfg) else cfg.signin_url
        await page.goto(target, wait_until="domcontentloaded")
        print(
            "\n  Capturing Instaffo API traffic.\n"
            "  Sign in if needed, then open your matches, a job, and a chat.\n"
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
    return out_path


def _has_session(cfg: Config) -> bool:
    return cfg.storage_state_path.is_file()
