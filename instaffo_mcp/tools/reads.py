"""Read-only candidate tools, wired to the confirmed JSON endpoints.

Each tool returns a trimmed, faithful view of the API response (long HTML blurbs
are converted to plain text and capped) so the model gets signal, not noise.
"""

from __future__ import annotations

import html
import re
from typing import Any

from fastmcp import FastMCP

from instaffo_mcp.client import InstaffoAuthError, InstaffoClient


def _text(raw: Any, limit: int = 4000) -> str:
    """Strip HTML tags and unescape entities from an API rich-text field."""
    if not isinstance(raw, str):
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    collapsed = re.sub(r"\s+", " ", html.unescape(no_tags)).strip()
    return collapsed[:limit]


def _names(items: Any) -> list[str]:
    """Extract display names from a list of skill/tag objects or strings."""
    out: list[str] = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                name = it.get("name") or it.get("title")
                if name:
                    out.append(str(name))
            elif isinstance(it, str):
                out.append(it)
    return out


def _salary(job: dict[str, Any]) -> str | None:
    lo, hi = job.get("salaryMin"), job.get("salaryMax")
    cur = job.get("currency") or "EUR"
    if lo and hi:
        return f"{lo}-{hi} {cur}"
    if lo:
        return f"from {lo} {cur}"
    return None


def _work_mode(job: dict[str, Any]) -> str:
    if job.get("remote"):
        return "remote"
    if job.get("hybrid"):
        return "hybrid"
    if job.get("onsite"):
        return "onsite"
    return "unspecified"


def _suggestion_row(s: dict[str, Any]) -> dict[str, Any]:
    job = s.get("job", {})
    return {
        "job_uuid": job.get("uuid"),
        "title": job.get("name"),
        "company": (job.get("company") or {}).get("name"),
        "location": (s.get("location") or {}).get("fullName"),
        "work_mode": _work_mode(job),
        "salary": _salary(job),
        "seniorities": job.get("seniorities"),
        "contract_type": job.get("contractType"),
        "top_skills": _names(job.get("topSkills")),
        "preferred": s.get("preferred"),
        "seen": s.get("seen"),
    }


def register_read_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        title="Instaffo: who am I",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"read"},
    )
    async def instaffo_whoami() -> dict[str, Any]:
        """Return the signed-in candidate's basic identity."""
        try:
            with InstaffoClient() as c:
                u = c.get("/candidate/api/v1/me").get("user", {})
        except InstaffoAuthError as e:
            return {"error": "auth", "detail": str(e)}
        return {
            "name": f"{u.get('firstName', '')} {u.get('lastName', '')}".strip(),
            "email": u.get("email"),
            "job_title": u.get("jobTitle"),
            "user_type": u.get("userType"),
            "email_confirmed": u.get("emailConfirmed"),
        }

    @mcp.tool(
        title="Instaffo: get my profile",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"read"},
    )
    async def instaffo_get_profile() -> dict[str, Any]:
        """Return the candidate's Instaffo profile: seniority, location, skills, CV."""
        try:
            with InstaffoClient() as c:
                p = c.get("/candidate/api/v1/profile")
        except InstaffoAuthError as e:
            return {"error": "auth", "detail": str(e)}
        cand = p.get("candidate", p)
        return {
            "name": cand.get("name"),
            "email": cand.get("email"),
            "seniority": cand.get("seniority"),
            "status": cand.get("status"),
            "location": cand.get("location"),
            "about": _text(cand.get("aboutme"), 1500),
            "top_skills": _names(cand.get("topSkills")),
            "skills": _names(cand.get("skills")),
            "programming_languages": _names(cand.get("programmingLanguages")),
            "frameworks": _names(cand.get("frameworks")),
            "tech_stacks": _names(cand.get("techStacks")),
            "languages": _names(cand.get("languages")),
            "links": cand.get("links"),
            "termination_period": cand.get("terminationPeriod"),
        }

    @mcp.tool(
        title="Instaffo: list job suggestions",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"read"},
    )
    async def instaffo_list_job_suggestions() -> dict[str, Any]:
        """List the candidate's current job suggestions (the matches shown in-app)."""
        try:
            with InstaffoClient() as c:
                data = c.get("/candidate/api/v1/job_suggestions")
                counters = c.get("/candidate/api/v1/job_suggestions/counters")
        except InstaffoAuthError as e:
            return {"error": "auth", "detail": str(e)}
        rows = [_suggestion_row(s) for s in data.get("jobSuggestions", [])]
        return {"counters": counters.get("counters"), "suggestions": rows}

    @mcp.tool(
        title="Instaffo: get one job suggestion",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"read"},
    )
    async def instaffo_get_job_suggestion(job_uuid: str) -> dict[str, Any]:
        """Full detail for one job suggestion, by its job_uuid (from the list tool).

        Includes the role description, requirements, process, salary band, skills,
        and the screening questions that applying will require answering.
        """
        try:
            with InstaffoClient() as c:
                data = c.get(f"/candidate/api/v1/job_suggestions/{job_uuid}")
        except InstaffoAuthError as e:
            return {"error": "auth", "detail": str(e)}
        s = data.get("jobSuggestion", data)
        job = s.get("job", s)
        return {
            "job_uuid": job.get("uuid"),
            "title": job.get("name"),
            "company": (job.get("company") or {}).get("name"),
            "company_about": _text((job.get("company") or {}).get("description"), 1500),
            "location": (s.get("location") or job.get("locations", [{}])[0] or {}).get("fullName")
            or (job.get("locations") or [{}])[0].get("city"),
            "work_mode": _work_mode(job),
            "salary": _salary(job),
            "seniorities": job.get("seniorities"),
            "about_job": _text(job.get("aboutJob")),
            "about_tasks": _text(job.get("aboutTasks")),
            "about_requirements": _text(job.get("aboutRequirements")),
            "about_team": _text(job.get("aboutTeam")),
            "about_process": _text(job.get("aboutProcess")),
            "top_skills": _names(job.get("topSkills")),
            "programming_languages": _names(job.get("programmingLanguages")),
            "frameworks": _names(job.get("frameworks")),
            "screening_questions": job.get("screeningQuestions"),
        }

    @mcp.tool(
        title="Instaffo: list conversations",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"read"},
    )
    async def instaffo_list_conversations() -> dict[str, Any]:
        """List chats: company requests (inbound interest) and your job applications."""
        try:
            with InstaffoClient() as c:
                data = c.get("/candidate/api/v1/chats")
        except InstaffoAuthError as e:
            return {"error": "auth", "detail": str(e)}
        chats = data.get("chats", data)
        return {
            "company_requests": chats.get("companyRequests", []),
            "job_applications": chats.get("jobApplications", []),
        }
