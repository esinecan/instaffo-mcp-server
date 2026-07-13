"""Command-line entry point.

    instaffo-mcp              # run the MCP server (stdio)
    instaffo-mcp --login      # headed manual login, persist the session
    instaffo-mcp --capture    # record app API traffic (the fork-deciding step)
    instaffo-mcp --auth-status [--deep]   # report session state
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="instaffo-mcp")
    parser.add_argument("--login", action="store_true", help="Headed manual login.")
    parser.add_argument("--capture", action="store_true", help="Record API traffic.")
    parser.add_argument("--auth-status", action="store_true", help="Report session state.")
    parser.add_argument("--deep", action="store_true", help="With --auth-status: validate live.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    _configure_logging(args.log_level)

    if args.login:
        from instaffo_mcp.driver import interactive_login

        ok = asyncio.run(interactive_login())
        raise SystemExit(0 if ok else 1)

    if args.capture:
        from instaffo_mcp.driver import capture_api_traffic

        out = asyncio.run(capture_api_traffic())
        print(f"\n  Capture written to: {out}")
        print("  Inspect it to decide the fork: are the app's data calls JSON")
        print("  (content_type application/json) and do they carry Authorization")
        print("  or just Cookie? That answers scrape-vs-replay.\n")
        return

    if args.auth_status:
        from instaffo_mcp.session import session_status

        result = {"local": session_status().to_dict()}
        if args.deep:
            from instaffo_mcp.driver import deep_auth_check

            result["live"] = asyncio.run(deep_auth_check())
        print(json.dumps(result, indent=2))
        return

    # Default: run the MCP server over stdio.
    from instaffo_mcp.server import create_mcp_server

    create_mcp_server().run()


if __name__ == "__main__":
    main()
