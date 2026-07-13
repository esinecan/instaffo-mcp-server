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

Writes (every write tool takes `confirm`; without it you get a preview and
nothing changes):

| Tool | Effect | Endpoint |
|---|---|---|
| `instaffo_save_job` | bookmark a suggestion (reversible) | `POST .../job_suggestions/{uuid}/favorite` |
| `instaffo_unsave_job` | remove a bookmark | `DELETE .../job_suggestions/{uuid}/favorite` |
| `instaffo_set_skill_experience` | set your years per skill on your profile | `POST .../experience_durations/bulk_save` |

All endpoints above are verified against the live API.

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
