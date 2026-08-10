"""Offline contract tests: pin the classification rules and the body shapes.

These prove the parser and the taxonomy. They cannot tell you the site moved --
that is what a live contract test is for. Everything asserted here traces to a
finding in docs/API.md dated 2026-08-10.
"""

from __future__ import annotations

import httpx
import pytest

from instaffo_mcp.errors import (
    AUTH_EXPIRED,
    BLOCKED,
    INVALID_INPUT,
    SCHEMA_DRIFT,
    TRANSIENT,
    ToolError,
    classify_body,
    classify_status,
)
from instaffo_mcp.profile import ProfileWriter


class TestClassifyStatus:
    """Choke point 1 -- the status table, with Instaffo's observed bodies."""

    @pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
    def test_redirect_is_auth_not_a_hop_to_follow(self, status):
        # PASS 2: unauth + browser Accept -> 302 /signin. Following it yields a
        # 200 HTML login page, which is the trap.
        assert classify_status(status) == AUTH_EXPIRED

    def test_403_is_auth_when_it_is_the_api_envelope(self):
        assert classify_status(403, '{"errors":{"base":"not_allowed"}}') == AUTH_EXPIRED

    def test_403_is_blocked_only_with_challenge_markers(self):
        assert classify_status(403, "<html>Just a moment... cf_chl</html>") == BLOCKED

    @pytest.mark.parametrize("status", [400, 404, 409, 422])
    def test_4xx_input_errors(self, status):
        assert classify_status(status, '{"errors":{"base":"not_found"}}') == INVALID_INPUT

    @pytest.mark.parametrize("status", [408, 429, 500, 502, 503])
    def test_transient(self, status):
        assert classify_status(status) == TRANSIENT

    def test_unclassifiable_defaults_to_drift(self):
        assert classify_status(418) == SCHEMA_DRIFT


class TestClassifyBody:
    """Choke point 2 -- a 2xx that is not a success."""

    def test_html_on_a_json_endpoint_is_auth_expired_not_success(self):
        # The exact PASS 2 shape: 200 + text/html + a login page.
        kind = classify_body(200, "text/html; charset=utf-8", "<!doctype html><html>")
        assert kind == AUTH_EXPIRED

    def test_html_with_challenge_markers_is_blocked(self):
        kind = classify_body(200, "text/html", "<html>DataDome captcha</html>")
        assert kind == BLOCKED

    def test_real_json_success_is_not_flagged(self):
        assert classify_body(200, "application/json", '{"success":true}') is None


class _FakeClient:
    """Records writes and serves a canned candidate object."""

    def __init__(self, candidate):
        self._candidate = candidate
        self.calls = []

    def get(self, path, params=None):
        return {"candidate": self._candidate}

    def post(self, path, body=None):
        self.calls.append(("POST", path, body))
        return {"success": True}

    def patch(self, path, body=None):
        self.calls.append(("PATCH", path, body))
        return {"success": True}

    def delete(self, path):
        self.calls.append(("DELETE", path, None))
        return {"success": True}


@pytest.fixture
def candidate():
    return {
        "aboutme": "original text",
        "seniority": "senior",
        "industries": ["it"],
        "links": ["https://linkedin.com/in/esinecan"],
        "languages": [{"title": "English", "rating": "C1"}],
        "allSkills": [{"uuid": "u1", "name": "Python"}],
        "topSkills": [{"uuid": "u1", "name": "Python"}],
        "cvWork": [{"uuid": "w1", "title": "Eng", "stationName": "ACME"}],
        "cvEducation": [],
        "factors": [
            {"type": "Candidate::Factor::Salary", "value": 110000, "currency": "EUR"},
            {"type": "Candidate::Factor::JobSeekingActivity", "value": "passive"},
        ],
    }


class TestConfirmGate:
    """confirm=False must make NO network call at all."""

    def test_preview_sends_nothing(self, candidate):
        c = _FakeClient(candidate)
        out = ProfileWriter(c).set_about("new text")
        assert c.calls == []
        assert out["confirm"] is False
        assert out["would_send"]["body"] == {"aboutme": "new text"}

    def test_delete_preview_names_the_target(self, candidate):
        c = _FakeClient(candidate)
        out = ProfileWriter(c).delete_cv_station("w1")
        assert c.calls == []
        assert "Eng at ACME" in out["what"]


class TestBodyShapes:
    """Each shape traces to a captured fixture; the nesting is inconsistent."""

    def test_about_is_flat(self, candidate):
        c = _FakeClient(candidate)
        ProfileWriter(c).set_about("original text", confirm=True)
        assert c.calls[0][:2] == ("POST", "/candidate/api/v1/profile/about")
        assert c.calls[0][2] == {"aboutme": "original text"}

    def test_languages_nest_under_profile(self, candidate):
        c = _FakeClient(candidate)
        ProfileWriter(c).set_languages(
            [{"title": "English", "rating": "C1"}], confirm=True)
        assert c.calls[0][2] == {"profile": {"languages": [
            {"title": "English", "rating": "C1"}]}}

    def test_salary_is_a_patch_on_factors(self, candidate):
        c = _FakeClient(candidate)
        ProfileWriter(c).set_salary(110000, confirm=True)
        assert c.calls[0][0] == "PATCH"
        assert c.calls[0][1] == "/candidate/api/v1/factors/salary"
        assert c.calls[0][2]["factor"]["type"] == "Candidate::Factor::Salary"

    def test_cv_create_puts_type_beside_cvstation(self, candidate):
        c = _FakeClient(candidate)
        ProfileWriter(c).add_cv_station(
            kind="work", title="Eng", station_name="ACME",
            from_year=2025, current=True, confirm=True)
        body = c.calls[0][2]
        assert body["type"] == "Candidate::CvStation::Work"
        assert "type" not in body["cvStation"]

    def test_cv_update_puts_type_inside_cvstation(self, candidate):
        c = _FakeClient(candidate)
        ProfileWriter(c).update_cv_station("w1", kind="work", title="Eng", confirm=True)
        body = c.calls[0][2]
        assert "type" not in body
        assert body["cvStation"]["type"] == "Candidate::CvStation::Work"


class TestReadBack:
    """The response is never the basis for success -- the re-read is."""

    def test_verified_true_when_readback_matches(self, candidate):
        c = _FakeClient(candidate)
        out = ProfileWriter(c).set_about("original text", confirm=True)
        assert out["verified"] is True

    def test_verified_false_when_the_api_lied(self, candidate):
        # The API answers {"success": true} while storing nothing. The fake
        # candidate still reports the old text, so read-back must catch it.
        c = _FakeClient(candidate)
        out = ProfileWriter(c).set_about("a value that will not stick", confirm=True)
        assert out["response"] == {"success": True}
        assert out["verified"] is False
        assert "READ-BACK DIFFERS" in out["note"]

    def test_skills_write_reports_the_reshuffled_top_skills(self, candidate):
        c = _FakeClient(candidate)
        out = ProfileWriter(c).set_skills(["u1"], confirm=True)
        assert out["top_skills_now"] == ["Python"]
        assert "cannot be set directly" in out["top_skills_warning"]


class TestInputValidation:
    @pytest.mark.parametrize("bad", ["expert", "SENIOR", ""])
    def test_seniority_enum_enforced(self, candidate, bad):
        with pytest.raises(ToolError) as e:
            ProfileWriter(_FakeClient(candidate)).set_seniority(bad)
        assert e.value.kind == INVALID_INPUT

    def test_language_rating_enum_enforced(self, candidate):
        with pytest.raises(ToolError) as e:
            ProfileWriter(_FakeClient(candidate)).set_languages(
                [{"title": "English", "rating": "fluent"}])
        assert e.value.kind == INVALID_INPUT

    def test_empty_about_rejected_before_any_call(self, candidate):
        c = _FakeClient(candidate)
        with pytest.raises(ToolError):
            ProfileWriter(c).set_about("   ")
        assert c.calls == []


class TestEnvelope:
    def test_tool_error_envelope_shape(self):
        env = ToolError(INVALID_INPUT, "bad", field="x").envelope()
        assert env == {"ok": False, "kind": INVALID_INPUT, "error": "bad",
                       "detail": {"field": "x"}}

    def test_exit_codes_are_stable(self):
        assert ToolError(AUTH_EXPIRED, "x").exit_code == 3
        assert ToolError(SCHEMA_DRIFT, "x").exit_code == 5

    def test_unknown_kind_rejected(self):
        with pytest.raises(ValueError):
            ToolError("banana", "x")


def test_client_sends_strict_accept():
    """The single most load-bearing header in the repo (PASS 2)."""
    import instaffo_mcp.client as mod
    src = (mod.__file__)
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert '"Accept": "application/json"' in text
    assert '"application/json, text/plain, */*"' not in text.split("# STRICT")[0]


def test_guard_turns_html_200_into_auth_expired():
    from instaffo_mcp.client import InstaffoClient
    req = httpx.Request("GET", "https://app.instaffo.com/candidate/api/v1/profile")
    resp = httpx.Response(
        200, headers={"content-type": "text/html; charset=utf-8"},
        text="<!doctype html><html>sign in</html>", request=req)
    with pytest.raises(ToolError) as e:
        InstaffoClient._guard(object.__new__(InstaffoClient), resp)
    assert e.value.kind == AUTH_EXPIRED
