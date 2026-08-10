# instaffo-mcp-server

An MCP server that gives an AI assistant access to your own
[Instaffo](https://app.instaffo.com) candidate account, authenticated with your
own browser session. Personal job-search tooling. Runs fully local.

Instaffo is a two-sided recruiting marketplace (candidates are matched with
companies). This server exposes the candidate side: read your profile and job
suggestions, read conversations, and perform reversible write actions, from an
MCP client.

## How it works

Instaffo has no public candidate API, so the server authenticates with a real
logged-in session. Its candidate web app talks to a clean JSON API under
`app.instaffo.com/candidate/api/v1/*`, authenticated purely by the session
cookie (no bearer token). So the server is a thin cookie-authenticated `httpx`
client, not a scraper. A browser (via `patchright`) is used only once, to mint
the session at login.

```
MCP client ── stdio ──> instaffo-mcp-server ──cookie──> app.instaffo.com JSON API
                              │
                     storage-state.json  (cookies, written 0600, git-ignored)
                              ▲
                     instaffo-mcp --login  (one-time browser sign-in)
```

## Setup

```bash
uv sync
uv run patchright install chromium     # one-time, for login only
uv run instaffo-mcp --login            # opens a browser; sign in once
uv run instaffo-mcp --auth-status      # confirm the session is stored
```

Register it with your MCP client (stdio):

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/instaffo-mcp-server", "instaffo-mcp"]
}
```

## Tools

Reads (no side effects):

| Tool | What it returns |
|---|---|
| `instaffo_whoami` | your identity (name, email, job title) |
| `instaffo_get_profile` | your profile: seniority, location, skills, CV summary |
| `instaffo_list_job_suggestions` | your current matches, with counters |
| `instaffo_get_job_suggestion` | one role in full: description, requirements, salary, screening questions |
| `instaffo_list_conversations` | company requests (inbound interest) and your applications |
| `instaffo_auth_status` | is a session present (`--deep` validates it live) |
| `instaffo_search_skills` | look up skill uuids in Instaffo's closed vocabulary |

Writes (every write tool takes `confirm`; without it **no network call is made**
and you get back the exact payload that would be sent):

| Tool | Effect | Endpoint |
|---|---|---|
| `instaffo_save_job` / `instaffo_unsave_job` | bookmark a suggestion | `POST\|DELETE .../job_suggestions/{uuid}/favorite` |
| `instaffo_set_about` | replace the About me text | `POST .../profile/about` |
| `instaffo_set_skills` | replace the skill set | `POST .../profile/skills` |
| `instaffo_set_languages` | replace the language list | `POST .../profile/languages` |
| `instaffo_set_industries` | replace industry experience | `POST .../profile/industries` |
| `instaffo_set_links` | replace social links | `POST .../profile/links` |
| `instaffo_set_seniority` | set working experience level | `POST .../profile/professional_background` |
| `instaffo_set_salary` | annual salary expectation | `PATCH .../factors/salary` |
| `instaffo_set_job_roles` | target roles (drives matching) | `PATCH .../factors/job_roles` |
| `instaffo_set_job_seeking_activity` | active / passive | `PATCH .../factors/job_seeking_activity` |
| `instaffo_add_cv_station` | add a work or education entry | `POST .../cv` |
| `instaffo_update_cv_station` | edit an entry in place | `PATCH .../cv/{uuid}` |
| `instaffo_delete_cv_station` | remove an entry (irreversible) | `DELETE .../cv/{uuid}` |
| `instaffo_set_skill_experience` | years per skill | `POST .../experience_durations/bulk_save` |

All endpoints are observed, never guessed. The contract they were built from is
[`docs/API.md`](docs/API.md), dated and derived from a recorded capture.

### Why every write reads back

This API returns a bare `{"success": true}` for **every** write, and validates
only partially — a `PATCH` with required fields omitted, or with wrong-typed
values, also returns `{"success": true}`. The response therefore cannot tell you
what was stored. Each write tool re-reads `GET /profile` and reports `verified`
plus `value_now`; trust those, not the response.

Two field traps worth knowing before you call anything:

- **`instaffo_set_skills` re-derives `topSkills` server-side.** There is no
  `topSkills` field to send and no UI control for it. A save with the skill set
  unchanged still moved the top three.
- **Skills cap at 23** (`skills` 20 + `topSkills` 3). Exceeding it returns
  `"maximum is 20 characters"` — the message says characters, the unit is items.

## Supervised, on purpose: apply and message

Two actions are intentionally **not** implemented as fire-and-forget tools:
applying to a job, and messaging a recruiter.

Applying is not one request. It is a multi-step wizard that writes lasting
self-representations to your real profile before it submits:

1. a skill self-assessment (year sliders per required skill, e.g. 0-5), which
   auto-saves to your profile via `experience_durations/bulk_save`,
2. your salary expectation (pre-filled from your profile),
3. an "AI tools you use" and "AI skills" multi-select,
4. a final submit that creates the application and opens a chat with the
   recruiter.

Because those are real, outward-facing choices about how you present yourself,
and the final submit endpoint only appears once the whole flow is completed, the
apply and message tools are left for a supervised session where the account
owner approves the inputs. They are not built against a guessed endpoint. The
observed sub-steps and wizard shape are recorded here so that session is quick.

## Commands

```bash
instaffo-mcp                 # run the MCP server (stdio)
instaffo-mcp --login         # headed manual login, persist the session
instaffo-mcp --capture       # record app API traffic to a JSONL (diagnostics)
instaffo-mcp --auth-status [--deep]
```

## Security and privacy

- Session material (`profile/`, `storage-state.json`, `captures/`, `.env`) lives
  under `~/.instaffo-mcp`, is written `0600`, and is git-ignored. It is never
  committed.
- Write tools are confirm-gated and only touch reversible surfaces.
- This is a personal, local tool for your own account. It stores no one else's
  data and talks only to Instaffo with your own session.

## Prior art

The session-capture and browser patterns are adapted in spirit from
[stickerdaniel/linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server)
(Apache-2.0), which authenticates a personal LinkedIn session the same way.
