"""Write tools, each behind a confirm gate.

Only endpoints verified against the live API are exposed here:

- save / unsave a job     POST | DELETE /candidate/api/v1/job_suggestions/{uuid}/favorite
- set skill experience    POST        /candidate/api/v1/experience_durations/bulk_save

The two consequential, one-way actions (apply to a job, message a recruiter) are
deliberately NOT implemented: their final submit endpoints only appear on a
completed apply flow, and the apply flow writes lasting self-representations to
the real profile. They are left as a supervised step (see tools/surface.py and
the README) rather than built against a guessed endpoint or fired unattended.

Every tool takes ``confirm``. Without it, the tool returns a preview of what it
would do and changes nothing.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from instaffo_mcp.client import API, InstaffoAuthError, InstaffoClient


def register_write_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        title="Instaffo: save a job",
        annotations={"openWorldHint": True},
        tags={"write"},
    )
    async def instaffo_save_job(job_uuid: str, confirm: bool = False) -> dict[str, Any]:
        """Bookmark (favorite) a job suggestion. Reversible with instaffo_unsave_job.

        Args:
            job_uuid: the job's uuid (from instaffo_list_job_suggestions).
            confirm: must be true to perform the write; false returns a preview.
        """
        if not confirm:
            return {"preview": f"Would bookmark job {job_uuid}.", "note": "call again with confirm=true"}
        try:
            with InstaffoClient() as c:
                r = c.post(f"{API}/job_suggestions/{job_uuid}/favorite", {})
        except InstaffoAuthError as e:
            return {"error": "auth", "detail": str(e)}
        return {"saved": True, "job_uuid": job_uuid, "result": r}

    @mcp.tool(
        title="Instaffo: unsave a job",
        annotations={"openWorldHint": True},
        tags={"write"},
    )
    async def instaffo_unsave_job(job_uuid: str, confirm: bool = False) -> dict[str, Any]:
        """Remove a job from your bookmarks. Reverses instaffo_save_job.

        Args:
            job_uuid: the job's uuid.
            confirm: must be true to perform the write; false returns a preview.
        """
        if not confirm:
            return {"preview": f"Would remove bookmark on job {job_uuid}.", "note": "call again with confirm=true"}
        try:
            with InstaffoClient() as c:
                r = c.delete(f"{API}/job_suggestions/{job_uuid}/favorite")
        except InstaffoAuthError as e:
            return {"error": "auth", "detail": str(e)}
        return {"unsaved": True, "job_uuid": job_uuid, "result": r}

    @mcp.tool(
        title="Instaffo: set skill experience",
        annotations={"openWorldHint": True},
        tags={"write"},
    )
    async def instaffo_set_skill_experience(
        skills: list[dict] = Field(
            description='List of {"uuid": <skill uuid>, "duration": <years 0-5>}. '
            "Skill uuids come from a job's screening/prequalification data."
        ),
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Set your years-of-experience for one or more skills on your profile.

        This writes to your real profile. Durations are 0-5 (5 means 5+). Only
        submit truthful values. Without confirm=true it returns a preview.
        """
        clean = [
            {"uuid": str(s["uuid"]), "duration": int(s["duration"])}
            for s in skills
            if isinstance(s, dict) and s.get("uuid") is not None and s.get("duration") is not None
        ]
        if not clean:
            return {"error": "input", "detail": "skills must be [{uuid, duration}]"}
        if not confirm:
            return {"preview": "Would set skill experience.", "skills": clean, "note": "call again with confirm=true"}
        try:
            with InstaffoClient() as c:
                r = c.post(f"{API}/experience_durations/bulk_save", {"experienceDurations": clean})
        except InstaffoAuthError as e:
            return {"error": "auth", "detail": str(e)}
        return {"updated": True, "skills": clean, "result": r}
