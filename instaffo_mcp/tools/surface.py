"""Tool surface map: what is implemented, and what is deliberately supervised.

Implemented and registered (see tools/reads.py and tools/writes.py):

  reads:
    instaffo_whoami
    instaffo_get_profile
    instaffo_list_job_suggestions
    instaffo_get_job_suggestion
    instaffo_list_conversations
  writes (confirm-gated, endpoints verified against the live API):
    instaffo_save_job          POST   /candidate/api/v1/job_suggestions/{uuid}/favorite
    instaffo_unsave_job        DELETE /candidate/api/v1/job_suggestions/{uuid}/favorite
    instaffo_set_skill_experience  POST /candidate/api/v1/experience_durations/bulk_save
  auth:
    instaffo_auth_status
    instaffo_login (instructions; real login is `instaffo-mcp --login`)

Supervised, NOT implemented on purpose:

  instaffo_apply_to_job
  instaffo_message_recruiter

Applying is a multi-step wizard that writes lasting self-representations to the
real profile (skill-year sliders, AI-tools used, AI-skills, salary expectation)
and then submits. Its final submit endpoint only appears once that flow is
completed, and completing it commits real, outward-facing choices. Messaging a
recruiter is only possible after an application opens a chat, so its send
endpoint is likewise unobserved. Both are left for a supervised session so the
account owner approves the self-representation and the message before they fire,
rather than building them against a guessed endpoint. The observed apply
sub-steps (experience_durations/bulk_save) and the wizard shape are documented
in the README for when that session happens.
"""

from __future__ import annotations

SUPERVISED_TOOLS: dict[str, str] = {
    "instaffo_apply_to_job": "Submit a job application (multi-step profile-writing wizard; needs owner review).",
    "instaffo_message_recruiter": "Send a chat message to a recruiter (only exists after an application opens a chat).",
}
