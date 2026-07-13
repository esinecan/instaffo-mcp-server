"""Configuration and on-disk paths. Pure stdlib, no browser imports.

Everything is overridable by environment variable (a ``.env`` is loaded if
present) so the same code runs headless in a server and headed for a login.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_HOME = Path.home() / ".instaffo-mcp"
_DEFAULT_APP_ORIGIN = "https://app.instaffo.com"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration."""

    home: Path
    app_origin: str
    headless: bool
    login_timeout_min: int

    @property
    def signin_url(self) -> str:
        return f"{self.app_origin}/signin"

    @property
    def profile_dir(self) -> Path:
        """The owned patchright profile. This IS the persisted browser session."""
        return self.home / "profile"

    @property
    def storage_state_path(self) -> Path:
        """Portable cookies + localStorage snapshot (Playwright storageState).

        Fork-agnostic: it carries whatever the app authenticates with, whether
        that is a session cookie or a bearer token stashed in localStorage.
        """
        return self.home / "storage-state.json"

    @property
    def captures_dir(self) -> Path:
        return self.home / "captures"


@lru_cache(maxsize=1)
def get_config() -> Config:
    home = Path(
        os.environ.get("INSTAFFO_MCP_HOME", str(_DEFAULT_HOME))
    ).expanduser()
    return Config(
        home=home,
        app_origin=os.environ.get("INSTAFFO_APP_ORIGIN", _DEFAULT_APP_ORIGIN).rstrip("/"),
        headless=_env_bool("INSTAFFO_HEADLESS", True),
        login_timeout_min=int(os.environ.get("INSTAFFO_LOGIN_TIMEOUT_MIN", "10")),
    )
