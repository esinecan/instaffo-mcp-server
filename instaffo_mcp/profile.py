"""Profile write provider: all Instaffo profile knowledge lives here.

Built from ``docs/API.md`` (capture dated 2026-08-10). No endpoint, body shape,
or enum in this file was guessed -- each was observed. The three constraints
PASS 2 handed to construction are enforced here:

1. ``Accept: application/json`` strictly (in ``client.py``).
2. **Every write reads back.** The API returns a bare ``{"success": true}`` for
   every write and validates only partially -- a PATCH with required fields
   omitted or wrong-typed values also returns ``{"success": true}``. So the
   response can never be the basis for reporting success.
3. No ``page`` / ``query`` parameters are exposed for job suggestions.

Layer rules: this module does I/O through ``InstaffoClient`` and returns plain
dicts. It never formats for a human and never raises across the MCP boundary --
that is the server's job.
"""

from __future__ import annotations

from typing import Any, Callable

from instaffo_mcp.client import API, InstaffoClient
from instaffo_mcp.errors import INVALID_INPUT, ToolError

# Observed live 2026-08-10. Not from documentation.
SENIORITY = ("none", "junior", "midlevel", "senior")
JOB_SEEKING_ACTIVITY = ("active", "passive")
LANGUAGE_RATINGS = ("A1", "A2", "B1", "B2", "C1", "C2", "native")
CV_WORK = "Candidate::CvStation::Work"
CV_EDUCATION = "Candidate::CvStation::Education"


def _require(value: Any, name: str) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ToolError(INVALID_INPUT, f"{name} is required and was empty.")
    return value


class ProfileWriter:
    """Confirm-gated writes with read-back verification.

    Every method takes ``confirm``. With ``confirm=False`` (the default) it
    makes **no network call** and returns the exact payload that would be sent,
    so a caller can read it back in plain language before committing.
    """

    def __init__(self, client: InstaffoClient) -> None:
        self.c = client

    # -- reading -----------------------------------------------------------
    def candidate(self) -> dict[str, Any]:
        return self.c.get(f"{API}/profile")["candidate"]

    def search_skills(self, query: str) -> list[dict[str, str]]:
        """Look up skill uuids in Instaffo's CLOSED vocabulary.

        Note the path: ``/api/v1/autocompletes/skill/`` sits outside the
        ``/candidate/api/v1`` namespace every other endpoint uses.

        The vocabulary is closed and considerably narrower than a modern CV.
        Verified empty 2026-08-10: "Model Context Protocol", "Datadog",
        "CircleCI", "LangChain", "observability", "platform engineering".
        An empty list means the skill does not exist, not that the query failed.
        """
        _require(query, "query")
        data = self.c.get("/api/v1/autocompletes/skill/", {"q": query})
        return [{"uuid": s["uuid"], "name": s["name"]} for s in data.get("skills", [])]

    # -- the read-back contract -------------------------------------------
    def _commit(
        self,
        *,
        method: str,
        path: str,
        body: dict[str, Any],
        confirm: bool,
        verify: Callable[[dict[str, Any]], Any],
        expected: Any,
        what: str,
    ) -> dict[str, Any]:
        """Send one write, then prove it landed by re-reading the profile.

        ``verify`` projects the field out of a fresh candidate object;
        ``expected`` is what it should equal afterwards. A mismatch is
        ``schema_drift``-adjacent but reported honestly as ``verified: False``
        rather than as an error, because the write may well have been applied
        with server-side normalisation.
        """
        preview = {
            "would_send": {"method": method, "path": path, "body": body},
            "what": what,
            "confirm": False,
            "note": "Nothing was sent. Re-call with confirm=True to apply.",
        }
        if not confirm:
            return preview

        send = self.c.post if method == "POST" else self.c.patch
        response = send(path, body)

        after = self.candidate()
        actual = verify(after)
        verified = actual == expected
        return {
            "what": what,
            "sent": {"method": method, "path": path, "body": body},
            "response": response,
            "verified": verified,
            "value_now": actual,
            "note": (
                "Verified by re-reading GET /profile."
                if verified
                else "WRITE ACCEPTED BUT READ-BACK DIFFERS. The API returns "
                "{'success': true} even when it silently drops or coerces "
                "fields, so trust value_now over the response."
            ),
        }

    # -- about -------------------------------------------------------------
    def set_about(self, aboutme: str, *, confirm: bool = False) -> dict[str, Any]:
        _require(aboutme, "aboutme")
        return self._commit(
            method="POST", path=f"{API}/profile/about",
            body={"aboutme": aboutme}, confirm=confirm,
            verify=lambda c: c["aboutme"], expected=aboutme,
            what="Replace the 'About me' text.",
        )

    # -- contact -----------------------------------------------------------
    def set_contact(
        self, *, first_name: str, last_name: str, phone: str, email: str,
        location_uuid: str, confirm: bool = False,
    ) -> dict[str, Any]:
        for v, n in ((first_name, "first_name"), (last_name, "last_name"),
                     (phone, "phone"), (email, "email"),
                     (location_uuid, "location_uuid")):
            _require(v, n)
        body = {"firstName": first_name, "lastName": last_name, "phone": phone,
                "location_uuid": location_uuid, "email": email}
        return self._commit(
            method="POST", path=f"{API}/profile/base", body=body, confirm=confirm,
            verify=lambda c: [c["firstName"], c["lastName"], c["phone"], c["email"]],
            expected=[first_name, last_name, phone, email],
            what="Replace contact information.",
        )

    # -- languages ---------------------------------------------------------
    def set_languages(
        self, languages: list[dict[str, str]], *, confirm: bool = False
    ) -> dict[str, Any]:
        """``languages`` is ``[{"title": "English", "rating": "C1"}, ...]``."""
        if not languages:
            raise ToolError(INVALID_INPUT, "languages must not be empty.")
        for lang in languages:
            _require(lang.get("title"), "language.title")
            if lang.get("rating") not in LANGUAGE_RATINGS:
                raise ToolError(
                    INVALID_INPUT,
                    f"rating {lang.get('rating')!r} not in {LANGUAGE_RATINGS}.",
                )
        want = [{"title": lang["title"], "rating": lang["rating"]} for lang in languages]
        return self._commit(
            method="POST", path=f"{API}/profile/languages",
            body={"profile": {"languages": want}}, confirm=confirm,
            verify=lambda c: [{"title": x["title"], "rating": x["rating"]}
                              for x in c["languages"]],
            expected=want, what="Replace the language list.",
        )

    # -- skills ------------------------------------------------------------
    def set_skills(
        self, skill_uuids: list[str], *, confirm: bool = False
    ) -> dict[str, Any]:
        """Replace the whole skill set.

        ⚠️ This endpoint **re-derives `topSkills` server-side**. There is no
        `topSkills` field to send and no UI control for it. A save with the set
        unchanged still moved the top three on 2026-08-10. Treat `topSkills` as
        read-only and always report the new trio back to the caller.
        """
        if not skill_uuids:
            raise ToolError(INVALID_INPUT, "skill_uuids must not be empty.")
        want = sorted(set(skill_uuids))
        out = self._commit(
            method="POST", path=f"{API}/profile/skills",
            body={"allSkills": want}, confirm=confirm,
            verify=lambda c: sorted(s["uuid"] for s in c["allSkills"]),
            expected=want,
            what="Replace the skill set (WILL reshuffle topSkills).",
        )
        if confirm:
            after = self.candidate()
            out["top_skills_now"] = [s["name"] for s in after["topSkills"]]
            out["top_skills_warning"] = (
                "topSkills is server-derived and was very likely reshuffled by "
                "this write. It cannot be set directly."
            )
        return out

    # -- industries / links ------------------------------------------------
    def set_industries(
        self, industries: list[str], *, confirm: bool = False
    ) -> dict[str, Any]:
        return self._commit(
            method="POST", path=f"{API}/profile/industries",
            body={"profile": {"industries": industries}}, confirm=confirm,
            verify=lambda c: c["industries"], expected=industries,
            what="Replace industry experience.",
        )

    def set_links(self, links: list[str], *, confirm: bool = False) -> dict[str, Any]:
        return self._commit(
            method="POST", path=f"{API}/profile/links",
            body={"profile": {"links": links}}, confirm=confirm,
            verify=lambda c: [x if isinstance(x, str) else x.get("url")
                              for x in c["links"]],
            expected=links, what="Replace social links.",
        )

    # -- seniority ---------------------------------------------------------
    def set_seniority(self, seniority: str, *, confirm: bool = False) -> dict[str, Any]:
        if seniority not in SENIORITY:
            raise ToolError(INVALID_INPUT, f"seniority must be one of {SENIORITY}.")
        return self._commit(
            method="POST", path=f"{API}/profile/professional_background",
            body={"profile": {"seniority": seniority}}, confirm=confirm,
            verify=lambda c: c["seniority"], expected=seniority,
            what="Set seniority (working experience in target role).",
        )

    # -- factors -----------------------------------------------------------
    def _factor(self, c: dict[str, Any], suffix: str) -> Any:
        for f in c["factors"]:
            if f["type"].endswith(suffix):
                return f
        return None

    def set_salary(
        self, amount: int, *, currency: str = "EUR", confirm: bool = False
    ) -> dict[str, Any]:
        if not isinstance(amount, int) or amount <= 0:
            raise ToolError(INVALID_INPUT, "amount must be a positive integer.")
        return self._commit(
            method="PATCH", path=f"{API}/factors/salary",
            body={"factor": {"currency": currency,
                             "type": "Candidate::Factor::Salary", "value": amount}},
            confirm=confirm,
            verify=lambda c: self._factor(c, "Salary")["value"], expected=amount,
            what=f"Set salary expectation to {amount} {currency}.",
        )

    def set_job_seeking_activity(
        self, value: str, *, confirm: bool = False
    ) -> dict[str, Any]:
        if value not in JOB_SEEKING_ACTIVITY:
            raise ToolError(
                INVALID_INPUT, f"value must be one of {JOB_SEEKING_ACTIVITY}."
            )
        return self._commit(
            method="PATCH", path=f"{API}/factors/job_seeking_activity",
            body={"factor": {"type": "Candidate::Factor::JobSeekingActivity",
                             "value": value}},
            confirm=confirm,
            verify=lambda c: self._factor(c, "JobSeekingActivity")["value"],
            expected=value, what=f"Set job-seeking activity to {value!r}.",
        )

    def set_job_roles(
        self, roles: dict[str, list[str]], *, custom_role: str = "",
        confirm: bool = False,
    ) -> dict[str, Any]:
        """``roles`` maps a category slug to role slugs, e.g.
        ``{"software-engineering": ["backend-developer", "tech-lead"]}``."""
        if not roles:
            raise ToolError(INVALID_INPUT, "roles must not be empty.")
        return self._commit(
            method="PATCH", path=f"{API}/factors/job_roles",
            body={"factor": {"type": "Candidate::Factor::JobRoles",
                             "value": roles, "customRole": custom_role}},
            confirm=confirm,
            verify=lambda c: self._factor(c, "JobRoles")["value"], expected=roles,
            what="Replace target job roles.",
        )

    # -- CV stations -------------------------------------------------------
    def add_cv_station(
        self, *, kind: str, title: str, station_name: str,
        from_year: int | str, from_month: int | str | None = None,
        to_year: int | str | None = None, to_month: int | str | None = None,
        current: bool = False, description: str = "",
        station_type: str | None = None, confirm: bool = False,
    ) -> dict[str, Any]:
        """Create a work or education entry.

        ⚠️ The ``type`` slot sits BESIDE ``cvStation`` on create and INSIDE it
        on update. Do not copy this body to :meth:`update_cv_station`.
        """
        if kind not in ("work", "education"):
            raise ToolError(INVALID_INPUT, "kind must be 'work' or 'education'.")
        _require(title, "title")
        _require(station_name, "station_name")
        _require(from_year, "from_year")
        station: dict[str, Any] = {
            "current": bool(current), "fromYear": str(from_year),
            "stationName": station_name, "title": title,
        }
        if from_month is not None:
            station["fromMonth"] = str(from_month)
        if not current:
            station["toYear"] = str(to_year) if to_year is not None else None
            station["toMonth"] = str(to_month) if to_month is not None else None
        if kind == "work":
            station["description"] = description
        elif station_type:
            station["stationType"] = station_type
        body = {"type": CV_WORK if kind == "work" else CV_EDUCATION,
                "cvStation": station}
        coll = "cvWork" if kind == "work" else "cvEducation"
        return self._commit(
            method="POST", path=f"{API}/cv", body=body, confirm=confirm,
            verify=lambda c: any(
                e.get("stationName") == station_name and e.get("title") == title
                for e in c[coll]),
            expected=True, what=f"Add {kind}: {title} at {station_name}.",
        )

    def update_cv_station(
        self, uuid: str, *, kind: str, confirm: bool = False, **fields: Any
    ) -> dict[str, Any]:
        """Update an entry. ``type`` goes INSIDE ``cvStation`` here."""
        _require(uuid, "uuid")
        if kind not in ("work", "education"):
            raise ToolError(INVALID_INPUT, "kind must be 'work' or 'education'.")
        station = {"type": CV_WORK if kind == "work" else CV_EDUCATION}
        station.update({k: v for k, v in fields.items() if v is not None})
        coll = "cvWork" if kind == "work" else "cvEducation"
        return self._commit(
            method="PATCH", path=f"{API}/cv/{uuid}",
            body={"cvStation": station}, confirm=confirm,
            verify=lambda c: next(
                (e for e in c[coll] if e["uuid"] == uuid), None) is not None,
            expected=True, what=f"Update {kind} entry {uuid}.",
        )

    def delete_cv_station(self, uuid: str, *, confirm: bool = False) -> dict[str, Any]:
        _require(uuid, "uuid")
        before = self.candidate()
        target = next(
            (e for e in before["cvWork"] + before["cvEducation"] if e["uuid"] == uuid),
            None,
        )
        label = (f"{target.get('title')} at {target.get('stationName')}"
                 if target else "(not found in current profile)")
        if not confirm:
            return {
                "would_send": {"method": "DELETE", "path": f"{API}/cv/{uuid}"},
                "what": f"⚠️ PERMANENTLY DELETE: {label}",
                "confirm": False,
                "note": "Nothing was sent. Re-call with confirm=True to delete.",
            }
        response = self.c.delete(f"{API}/cv/{uuid}")
        after = self.candidate()
        gone = not any(
            e["uuid"] == uuid for e in after["cvWork"] + after["cvEducation"])
        return {
            "what": f"Deleted: {label}", "response": response, "verified": gone,
            "note": "Verified by re-reading GET /profile."
            if gone else "DELETE ACCEPTED BUT THE ENTRY IS STILL PRESENT.",
        }
