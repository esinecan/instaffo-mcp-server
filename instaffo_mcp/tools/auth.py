"""Auth-facing MCP tools.

``instaffo_auth_status`` does the cheap, browser-free local check by default and
only spends a browser launch when the caller asks for a deep validation. Login
is interactive (it needs a real human and possibly SSO), which cannot happen
inside a stdio tool call, so the tool reports status and points at the CLI.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from instaffo_mcp.session import session_status


def register_auth_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        title="Instaffo Auth Status",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"auth"},
    )
    async def instaffo_auth_status(deep: bool = False) -> dict[str, Any]:
        """Report whether a usable Instaffo session is present.

        Args:
            deep: When true, launch a browser and confirm the session against
                the live app (authoritative but slow). When false (default),
                only read the on-disk session snapshot (fast, no browser).

        Returns:
            The local session summary, plus a ``live`` block when ``deep`` is set.
            If no session is present, ``next_step`` explains how to create one.
        """
        status = session_status().to_dict()
        result: dict[str, Any] = {"local": status}

        if not status["logged_in"]:
            result["next_step"] = (
                "No signed-in session on disk. Run `instaffo-mcp --login` in a "
                "terminal to sign in once; the session is then reused."
            )
            return result

        if deep:
            from instaffo_mcp.driver import deep_auth_check

            result["live"] = await deep_auth_check()
        return result

    @mcp.tool(
        title="Instaffo Login Instructions",
        annotations={"readOnlyHint": True},
        tags={"auth"},
    )
    async def instaffo_login() -> dict[str, Any]:
        """Explain how to establish a session (interactive, runs in a terminal)."""
        return {
            "status": "manual",
            "instructions": (
                "Login needs a real browser and possibly SSO, so it runs outside "
                "the MCP call. In a terminal run: `instaffo-mcp --login`. A browser "
                "opens at the Instaffo signin page; sign in and the session is "
                "captured automatically."
            ),
        }
