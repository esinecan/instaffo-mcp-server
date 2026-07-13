"""Unit tests for the browser-free session status logic. Synthetic data only."""

import json
import time

from instaffo_mcp import config, session


def _write_state(tmp_path, cookies, origins=None):
    home = tmp_path / ".instaffo-mcp"
    home.mkdir()
    (home / "storage-state.json").write_text(
        json.dumps({"cookies": cookies, "origins": origins or []})
    )
    return home


def _use_home(monkeypatch, home):
    monkeypatch.setenv("INSTAFFO_MCP_HOME", str(home))
    config.get_config.cache_clear()


def test_no_session(monkeypatch, tmp_path):
    _use_home(monkeypatch, tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    s = session.session_status()
    assert s.present is False
    assert s.logged_in is False


def test_logged_in_ignores_analytics_expiry(monkeypatch, tmp_path):
    # A live Devise auth cookie plus an already-expired 1-minute analytics
    # cookie: the session must read as logged in and NOT expired.
    future = time.time() + 30 * 24 * 3600
    cookies = [
        {"name": "remember_user_token", "value": "x", "domain": ".instaffo.com", "expires": future},
        {"name": "_instaffo_session", "value": "y", "domain": ".instaffo.com", "expires": -1},
        {"name": "_gat_UA-1", "value": "1", "domain": ".instaffo.com", "expires": time.time() - 5},
    ]
    home = _write_state(tmp_path, cookies)
    _use_home(monkeypatch, home)
    s = session.session_status()
    assert s.logged_in is True
    assert s.auth_cookie_expired is False
    assert s.instaffo_cookie_count == 3


def test_expired_auth_cookie(monkeypatch, tmp_path):
    cookies = [
        {"name": "remember_user_token", "value": "x", "domain": ".instaffo.com", "expires": time.time() - 100},
    ]
    home = _write_state(tmp_path, cookies)
    _use_home(monkeypatch, home)
    s = session.session_status()
    assert s.logged_in is False
    assert s.auth_cookie_expired is True


def test_token_like_localstorage_flagged(monkeypatch, tmp_path):
    cookies = [{"name": "remember_user_token", "value": "x", "domain": ".instaffo.com", "expires": time.time() + 1000}]
    origins = [{"origin": "https://app.instaffo.com", "localStorage": [
        {"name": "authToken", "value": "secret"}, {"name": "theme", "value": "dark"}]}]
    home = _write_state(tmp_path, cookies, origins)
    _use_home(monkeypatch, home)
    s = session.session_status()
    assert "authToken" in s.token_like_localstorage_keys
    assert "theme" not in s.token_like_localstorage_keys
