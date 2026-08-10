"""MCP tools for editing the candidate profile.

Thin by design: every tool resolves arguments, calls ``ProfileWriter``, and
returns an envelope. No site knowledge lives here -- it is all in
``instaffo_mcp/profile.py``, which was built from ``docs/API.md``.

Tools **return** errors, never raise: a raise becomes framework prose that no
agent can branch on.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from instaffo_mcp.client import InstaffoClient
from instaffo_mcp.errors import SCHEMA_DRIFT, ToolError, ok
from instaffo_mcp.profile import ProfileWriter

_READBACK = (
    "\n\nEvery write here re-reads GET /profile and reports `verified`. The API "
    "answers `{'success': true}` even when it silently drops or coerces fields, "
    "so `value_now` is the truth and the response is not."
)


def _run(fn, *a, **kw) -> dict[str, Any]:
    try:
        with InstaffoClient() as c:
            return ok(fn(ProfileWriter(c), *a, **kw))
    except ToolError as exc:
        return exc.envelope()
    except Exception as exc:  # unclassifiable => drift, by definition
        return ToolError(
            SCHEMA_DRIFT, f"{type(exc).__name__}: {exc}"
        ).envelope()


def register_profile_write_tools(mcp: FastMCP) -> None:
    @mcp.tool(title="Instaffo: search the skill vocabulary",
              annotations={"openWorldHint": True, "readOnlyHint": True},
              tags={"read"})
    async def instaffo_search_skills(query: str) -> dict[str, Any]:
        """Find skill uuids to pass to instaffo_set_skills. Read-only.

        Instaffo's skill vocabulary is CLOSED and narrower than a modern CV.
        An empty result means the skill does not exist there — it is an answer,
        not a failure. Verified absent 2026-08-10: Model Context Protocol,
        Datadog, CircleCI, LangChain, observability, platform engineering.

        Matching is prefix-ish and case-insensitive; try shorter queries when a
        long one returns nothing ("event driven" finds "Event Driven
        Architecture", "datadog" finds nothing at all).
        """
        return _run(lambda w: w.search_skills(query))

    @mcp.tool(title="Instaffo: set About me", annotations={"openWorldHint": True},
              tags={"write"})
    async def instaffo_set_about(aboutme: str, confirm: bool = False) -> dict[str, Any]:
        """⚠️ BINDING ACTION — replaces the 'About me' text employers read.

        Call with confirm=false first: nothing is sent and you get back the exact
        payload, so you can read it to the account owner before committing.
        """ + _READBACK
        return _run(lambda w: w.set_about(aboutme, confirm=confirm))

    @mcp.tool(title="Instaffo: set skills", annotations={"openWorldHint": True},
              tags={"write"})
    async def instaffo_set_skills(
        skill_uuids: list[str], confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — replaces the ENTIRE skill set (not additive).

        ⚠️ SIDE EFFECT: this endpoint re-derives `topSkills` server-side. There
        is no way to set the top three directly and no UI control for them; a
        save with the set unchanged still reshuffled them on 2026-08-10. The
        result reports `top_skills_now`. Do not call this to "check that it
        works" — it will move the top skills every time.

        Pass uuids from instaffo_get_profile's allSkills.
        """ + _READBACK
        return _run(lambda w: w.set_skills(skill_uuids, confirm=confirm))

    @mcp.tool(title="Instaffo: set languages", annotations={"openWorldHint": True},
              tags={"write"})
    async def instaffo_set_languages(
        languages: list[dict], confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — replaces the whole language list (not additive).

        languages: [{"title": "English", "rating": "C1"}]. Ratings are CEFR
        (A1..C2) or "native".
        """ + _READBACK
        return _run(lambda w: w.set_languages(languages, confirm=confirm))

    @mcp.tool(title="Instaffo: set industries", annotations={"openWorldHint": True},
              tags={"write"})
    async def instaffo_set_industries(
        industries: list[str], confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — replaces industry experience (slugs, not labels).

        Read current slugs from instaffo_get_profile first; they are values like
        "it", "automotive", "marketing_and_pr_and_design".
        """ + _READBACK
        return _run(lambda w: w.set_industries(industries, confirm=confirm))

    @mcp.tool(title="Instaffo: set social links", annotations={"openWorldHint": True},
              tags={"write"})
    async def instaffo_set_links(
        links: list[str], confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — replaces the whole links list (not additive)."""
        return _run(lambda w: w.set_links(links, confirm=confirm))

    @mcp.tool(title="Instaffo: set seniority", annotations={"openWorldHint": True},
              tags={"write"})
    async def instaffo_set_seniority(
        seniority: str, confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — one of: none, junior, midlevel, senior.

        "none" means 'no relevant working experience' and is what the first
        radio in the UI sets. Do not send it by accident.
        """ + _READBACK
        return _run(lambda w: w.set_seniority(seniority, confirm=confirm))

    @mcp.tool(title="Instaffo: set salary expectation",
              annotations={"openWorldHint": True}, tags={"write"})
    async def instaffo_set_salary(
        amount: int, currency: str = "EUR", confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — annual salary expectation, shown to employers."""
        return _run(lambda w: w.set_salary(amount, currency=currency, confirm=confirm))

    @mcp.tool(title="Instaffo: set job-seeking activity",
              annotations={"openWorldHint": True}, tags={"write"})
    async def instaffo_set_job_seeking_activity(
        value: str, confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — "active" or "passive". Visible to employers."""
        return _run(lambda w: w.set_job_seeking_activity(value, confirm=confirm))

    @mcp.tool(title="Instaffo: set target job roles",
              annotations={"openWorldHint": True}, tags={"write"})
    async def instaffo_set_job_roles(
        roles: dict, custom_role: str = "", confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — replaces target roles; drives all matching.

        roles maps category slug to role slugs, e.g.
        {"software-engineering": ["backend-developer", "tech-lead"],
         "data": ["machine-learning-engineer"]}.
        """ + _READBACK
        return _run(
            lambda w: w.set_job_roles(roles, custom_role=custom_role, confirm=confirm)
        )

    @mcp.tool(title="Instaffo: add CV entry", annotations={"openWorldHint": True},
              tags={"write"})
    async def instaffo_add_cv_station(
        kind: str, title: str, station_name: str, from_year: int,
        from_month: int | None = None, to_year: int | None = None,
        to_month: int | None = None, current: bool = False, description: str = "",
        station_type: str | None = None, confirm: bool = False,
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — adds a work or education entry to the public CV.

        kind: "work" or "education". For education, station_type is the degree
        slug (e.g. "bachelor") and description is ignored.
        Set current=true for an ongoing role and leave to_year/to_month unset.
        """ + _READBACK
        return _run(lambda w: w.add_cv_station(
            kind=kind, title=title, station_name=station_name, from_year=from_year,
            from_month=from_month, to_year=to_year, to_month=to_month,
            current=current, description=description, station_type=station_type,
            confirm=confirm))

    @mcp.tool(title="Instaffo: update CV entry", annotations={"openWorldHint": True},
              tags={"write"})
    async def instaffo_update_cv_station(
        uuid: str, kind: str, title: str | None = None,
        station_name: str | None = None, description: str | None = None,
        from_year: int | None = None, from_month: int | None = None,
        to_year: int | None = None, to_month: int | None = None,
        current: bool | None = None, confirm: bool = False,
    ) -> dict[str, Any]:
        """⚠️ BINDING ACTION — edits an existing CV entry in place.

        Send the FULL entry, not just changed fields: the API accepts a partial
        body with {"success": true} and silently drops what you omitted.
        Get the uuid from instaffo_get_profile's cvWork / cvEducation.
        """ + _READBACK
        fields = {"title": title, "stationName": station_name,
                  "description": description, "current": current}
        for k, v in (("fromYear", from_year), ("fromMonth", from_month),
                     ("toYear", to_year), ("toMonth", to_month)):
            fields[k] = str(v) if v is not None else None
        return _run(lambda w: w.update_cv_station(
            uuid, kind=kind, confirm=confirm, **fields))

    @mcp.tool(title="Instaffo: delete CV entry", annotations={"openWorldHint": True},
              tags={"write", "destructive"})
    async def instaffo_delete_cv_station(
        uuid: str, confirm: bool = False
    ) -> dict[str, Any]:
        """⚠️ BINDING, IRREVERSIBLE — permanently removes a CV entry.

        With confirm=false it names the entry it would delete so the account
        owner can check it is the right one. There is no undo.
        """
        return _run(lambda w: w.delete_cv_station(uuid, confirm=confirm))
