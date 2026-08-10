# Instaffo candidate API — capture contract

**Handoff verdict: READY for construction of the 13 endpoints in the PASS 1
table.** PASS 0, PASS 1 and PASS 2 complete for those. Four intents remain
uncaptured and are listed as gaps at the end of this file — do not build tools
for them from this document.

Construction must carry three constraints out of PASS 2: send
`Accept: application/json` strictly, read back `GET /profile` after every write
before reporting success, and expose neither `page` nor `query` on
`/job_suggestions`.

| | |
|---|---|
| **Site** | `https://app.instaffo.com` (candidate side) |
| **Verified** | 2026-08-10 |
| **Fixtures** | `docs/fixtures/2026-08-10/` |
| **Tier target** | **advanced** — every editable field, including delete paths, file uploads and factors. Declared before PASS 0; re-checked after (see below). |
| **Signed-in identity** | The repository owner's own candidate account, verified by reading the signed-in name and email off `/candidate/profile` during PASS 0 and confirming they matched the account holder. Identity values are deliberately not reproduced here: this file is the *structural* contract and is public, while the fixtures it was derived from are personal and stay local (see Legal / etiquette). |
| **Egress** | Residential, Germany (Berlin). Anti-bot verdicts below are scoped to that exit and predict nothing about a datacentre IP. |
| **Capture vehicle** | The repo's own `instaffo-mcp --capture --fixtures DIR --case CASE`, driving the owned patchright profile at `~/.instaffo-mcp/profile`. **Not** web-surfer-llm — see "Vehicle" below. |

## Vehicle, and why not web-surfer-llm

The site-as-tool-capture skill's default vehicle is web-surfer-llm. It was
rejected here on two grounds, both checked rather than assumed:

1. Its browser profile is `~/.browser-data`, which is not logged in to Instaffo.
   Using it would mean a second manual sign-in on a browser the skill itself
   documents as having **no working stealth** (its 12-arg anti-detection list is
   exported through env vars nothing in playwright-core reads).
2. This repo already owns an authenticated patchright profile and a traffic
   recorder. Extending the recorder to emit byte-exact fixtures was ~60 lines
   and leaves the repo able to re-capture on drift without any external tool.

**Limits that actually bit:**

- **Git Bash mangles leading-slash arguments** into Windows paths
  (`/candidate/profile` → `C:/Program Files/Git/candidate/profile`). Every
  capture invocation needs `MSYS_NO_PATHCONV=1`. Cost: one failed run.
- **`[class*=modal]` is a false-positive magnet on this app.** It matches a
  118×32 nav dropdown (`_modal_jut48_34`) before the real editor. The real
  editor is a native `<dialog>`. Selecting the candidate with the most form
  fields and a sane bounding box is the reliable rule. Cost: one full inventory
  pass returning `fields=0` for all 15 editors.
- **The default `"api|graphql|\.json"` filter fails the skill's own validation
  test here.** Of 9 API-shaped hits on a cold profile load, 3 were telemetry:
  `plausible.io/api/event`, `sentry.io/api/<id>/envelope/`, and Instaffo's own
  first-party `app.instaffo.com/api/v1/event` beacon. A non-empty result is not
  a working filter. `driver._is_contract_traffic` now host-scopes first, then
  drops beacon paths.

## Anti-bot verdict

**No challenge observed** across roughly 40 navigations and ~120 requests from a
residential German IP on the owned patchright profile, headless and headed. No
interstitial, no CAPTCHA, no 403. Evidence: every `--auth-status --deep` run
landed on `/candidate/job_suggestions/`; every PASS 0 navigation returned the
app shell. This is an observation, not a guarantee, and it is exit-scoped.

**Attestation: none found on read paths.** No kilobyte-scale opaque token
appears in any captured request. Auth is the session cookie alone — no bearer
token, no WAA-style payload. Marked **hypothesis, not result** for write paths
until PASS 1 inspects their bodies.

## PASS 0 — affordance inventory (2026-08-10)

Recursed into every toggled state, as the advanced tier requires. On this app
that means clicking each opener, because **the form fields do not exist in the
DOM until the modal opens** — the base page carries 0 visible inputs.

**Tier re-check after PASS 0: advanced confirmed, unchanged.** The surface is 15
editors across 2 tabs plus 2 upload paths — large enough that a lower tier would
have left most of the profile unwritable.

**Reconciliation gate:** `roleCount=0` vs `geometricCount=2` on the tab strip.
The two tabs are `<button role=radio>`, which a `menuitem|menuitemcheckbox|
menuitemradio|option|tab` sweep does not match. The geometric pass caught
surface the ARIA pass could not see — exactly the failure mode the skill
documents. `radio` added to the sweep selector.

### Tab: Profile details (10 editors)

| # | Modal title | Fields observed | Submit |
|---|---|---|---|
| 1 | Contact information | `firstName`, `lastName`, location combobox, `phoneCountry` (select, ~250 ISO options), `phone`, `email` | Save |
| 2 | Tell us about yourself | `aboutme` (textarea) | Save |
| 3 | Edit languages | 4× combobox (language + level pairs) | Add language / Save |
| 4 | Edit Skills | 1 combobox + 20 skill chips as toggle buttons | — |
| 5 | Add work experience | `title`, `stationName`, 4× combobox (dates/location), `current` (checkbox), `description` (textarea) | Back / Save |
| 6 | Add education | `title`, `stationName`, 3× combobox, `current` (checkbox) | Back / Save |
| 7 | Industry experience | 24 fields | **Verify & save** |
| 8 | Termination period | 0 form fields (custom controls) | **Confirm** |
| 9 | How actively are you looking for a job? | 3 fields | Save |
| 10 | Social links | `links.0.url`, `links.1.url` | Add link / Save |

### Tab: Search Preferences (5 editors)

| # | Modal title | Fields observed | Submit |
|---|---|---|---|
| 1 | Contact information | (same modal as above — the shared header card) | Save |
| 2 | Which type of roles are you interested in? | 13 checkboxes across 13 category groups; counts in labels (`Software Engineering (3)`, `Data & AI (1)`) | Save |
| 3 | What is your working experience in your target role? | 4 fields (seniority) | Save |
| 4 | What is your annual salary expectation? | `salaryCurrency.amount`, currency combobox, `role=slider` | Save |
| 5 | What type of work are you searching for? | 0 form fields (custom controls; remote/hybrid/onsite) | **Confirm** |

### Upload paths

| Path | Mechanism | Location |
|---|---|---|
| CV replace | hidden `input[type=file] accept=".pdf"` | `/candidate/profile` |
| Profile picture | clickable avatar `_avatar_klksb_5 _cursorPointer_klksb_9` at (245,100) | `/candidate/profile` |

`/candidate/settings` carries **no** file inputs and no CV surface. Uploads live
on the profile page only.

### Delete paths

No page-level delete controls exist. Removal is in-modal: skill chips toggle,
language and link rows carry a per-row remove. **Hypothesis for PASS 1:** these
are collection-level PATCH/PUT of the whole array rather than per-item DELETE
endpoints. Not yet confirmed — do not build against this until PASS 1 says so.

## Intent list

Derived from the PASS 0 inventory above, not from documentation.

**Server-mapped, in tier — PASS 1 pending (17):** contact information · about me
· languages · skills · top skills · add work experience · edit work experience ·
delete work experience · add education · edit education · delete education ·
industry experience · termination period · job-seeking activity · social links ·
job roles · seniority · salary expectation · work policy · CV upload · picture
upload.

**Explicitly unmapped (client-side only):** tab switching between Profile
details and Search Preferences (no request fires); modal open/close.

**Out of tier scope:** the apply-to-job wizard and recruiter messaging. These
remain deliberately unimplemented for the reasons in the README — they write
lasting self-representations and their submit endpoint only materialises at the
end of a multi-step flow. Unchanged by this capture.

## Read endpoints (already shipped, re-verified 2026-08-10)

| Method | Path | Notes |
|---|---|---|
| GET | `/candidate/api/v1/me` | 1317 B; identity |
| GET | `/candidate/api/v1/profile` | 9942 B; `candidate` object, 49 fields. Baseline fixture is the restore point for PASS 1. |
| POST | `/candidate/api/v1/job_suggestions` | listing — **the UI POSTs a filter body**; a plain GET (and a POST with no location filter) returns only the location-matching *preferred* subset, not all open. See finding 3, corrected 2026-08-10. |
| GET | `/candidate/api/v1/job_suggestions/counters` | counters |
| GET | `/candidate/api/v1/job_suggestions/{uuid}` | one role |
| GET | `/candidate/api/v1/job_suggestions/requests` | inbound interest |
| GET | `/candidate/api/v1/chats` | conversations |
| GET | `/candidate/api/v1/survey_responses` | **newly observed in PASS 0**, not yet exposed as a tool |

Telemetry, excluded from the contract: `app.instaffo.com/api/v1/event`,
`plausible.io/api/event`, `sentry.io/api/<id>/envelope/`.

## PASS 1 — write endpoints

**In progress.** Method: snapshot → junk values → restore, per the account
owner's explicit decision on 2026-08-10. Baseline for restore is
`docs/fixtures/2026-08-10/profile-baseline-happy.json` (12,230 B, 49 fields,
taken before any write).

### Transport verdict — settled, and it is the good outcome

**The write path needs no browser.** Confirmed 2026-08-10 by out-of-browser
replay: the captured `POST /candidate/api/v1/profile/about` was re-fired through
the repo's plain `httpx` client and succeeded, round-tripping `aboutme` back to
its byte-exact 908-character baseline.

This is a *result*, not a hypothesis — it is the external-vehicle replay the
skill asks for, not an in-browser `fetch`. Consequences:

- **No client-generated attestation** anywhere in the write payload. No
  kilobyte-scale opaque token, no per-request nonce.
- **No CSRF token.** The observed request headers are `accept`, `content-type`,
  `cookie`, `origin`, `referer`, `user-agent`, `sec-ch-ua*` — and nothing else.
  No `X-CSRF-Token`, no `X-Requested-With`. Auth is the session cookie alone.
- The constructed tools can be pure `httpx`. The browser is needed **only** for
  the one-time login, exactly as the existing read tools already assume.

### Confirmed write endpoints (13)

Two families, and the split is not guessable — `/profile/*` is **POST**,
`/factors/*` is **PATCH**. `experience_durations/bulk_save`, already shipped,
follows neither.

| Intent | Method | Path | Body shape |
|---|---|---|---|
| Contact information | POST | `/profile/base` | flat: `{firstName, lastName, phone, location_uuid, email}` |
| About me | POST | `/profile/about` | flat: `{aboutme}` |
| Languages | POST | `/profile/languages` | `{profile:{languages:[{title, rating}]}}` |
| Skills | POST | `/profile/skills` | `{allSkills:[uuid]}` — **see field trap below** |
| Industries | POST | `/profile/industries` | `{profile:{industries:[slug]}}` |
| Social links | POST | `/profile/links` | `{profile:{links:[url]}}` |
| Seniority | POST | `/profile/professional_background` | `{profile:{seniority}}` |
| Salary | PATCH | `/factors/salary` | `{factor:{type, currency, value}}` |
| Job roles | PATCH | `/factors/job_roles` | `{factor:{type, value:{<group>:[slug]}, customRole}}` |
| Job-seeking activity | PATCH | `/factors/job_seeking_activity` | `{factor:{type, value}}` |
| CV station create | POST | `/cv` | `{type, cvStation:{...}}` |
| CV station update | PATCH | `/cv/{uuid}` | `{cvStation:{type, ...}}` |
| CV station delete | DELETE | `/cv/{uuid}` | — |

Every one returns `{"success": true}` and **nothing else**.

**Trap — the `type` slot moves between create and update.** On create it is a
sibling of `cvStation`; on update it lives *inside* `cvStation`. Sending the
create shape to the update endpoint, or vice versa, is the obvious mistake and
the uniform `{"success":true}` response will not tell you that you made it.

```
create:  {"type": "Candidate::CvStation::Work", "cvStation": {...}}
update:  {"cvStation": {"type": "Candidate::CvStation::Work", ...}}
```

**Collection limits, discovered by hitting them 2026-08-10:**

| Field | Max | Note |
|---|---|---|
| `allSkills` | **23 items** | the hard ceiling |
| `skills` | **20 items** | derived; `allSkills` − `topSkills` |
| `topSkills` | 3 | server-owned, not settable |

**The error message lies about the unit.** Exceeding the cap returns 422 with
`{"skills": "Skills is too long (maximum is 20 characters)", "allSkills": "All
skills is too long (maximum is 23 characters)"}` — it says **characters** but
the unit is **items**. A tool that trusts that wording will look for a long
string and find nothing. The two limits are coupled: 23 = 20 + 3.

**The skill vocabulary endpoint (captured 2026-08-10, second pass):**

```
GET /api/v1/autocompletes/skill/?q=<term>   ->  {"skills":[{"uuid","name"}, ...]}
```

Note the path: it sits **outside** `/candidate/api/v1`, like
`skill_recommendations`. Prefix-ish, case-insensitive, caps at ~5 results.

**The vocabulary is CLOSED and narrower than a modern CV.** Verified to return
`{"skills":[]}`: `model context protocol`, `datadog`, `circleci`, `langchain`,
`observability`, `platform engineering`. An empty list is an *answer* — the
skill does not exist on Instaffo — not a failed query. Present and useful:
`Microservices`, `Event Driven Architecture`, `CI/CD`, `Distributed Systems`,
`Software Architecture`, `Machine Learning`, `Artificial Intelligence`,
`Prompt Engineering`, `Elasticsearch`, `RabbitMQ`, `Terraform`, `Grafana`,
`Prometheus`, `Quarkus`, `Devops`.

**UI corroboration of the 23 cap:** at the ceiling the modal's search input is
rendered `disabled`, so the combobox cannot even be focused. A capture attempt
that assumes it is clickable will time out on an invisible element — free a slot
first.

**No certificate vocabulary endpoint exists** at the obvious paths — all four of
`/api/v1/autocompletes/{certificate,certificates,cv_certificate,title}/` return
404. The certificate title list remains uncaptured, so `cvCertificate` stays a
gap.

**Certificates: reachable, but the title is a closed vocabulary.**
`Candidate::CvStation::Certificate` is accepted as a `type` on `POST /cv` — the
400 that comes back complains about the *title*, not the type:
`{"title": "Title is not included in the list"}`. So certificates are a
cvStation like work and education, but their titles come from a controlled list
that this capture never enumerated. **Recorded as a gap — do not build a
certificate tool against a guessed title.**

**Education `stationType` is a closed list too**, and a short one: `bachelor`
is confirmed; `highschool`, `high_school` and `abitur` are all rejected with
`{"stationType": "Station type is not included in the list"}`. **Omitting
`stationType` entirely is accepted** and is the correct move for a non-degree
entry (verified: a secondary-school entry was created that way).

**Enums observed live (never from documentation):**

- `seniority`: `none` · `junior` · `midlevel` · `senior`
- `Candidate::Factor::JobSeekingActivity.value`: `active` · `passive` · (a third,
  "just browsing", not exercised)
- `type` on `/cv`: `Candidate::CvStation::Work` · `Candidate::CvStation::Education`
- `cvEducation.stationType`: `bachelor` (others unexercised)

**`POST /api/v1/skill_recommendations`** is a helper, not a write: it takes the
current skill set and returns suggestions. Note it sits on `/api/v1/`, **not**
`/candidate/api/v1/`. Harmless, but it fires from several modals and will show
up in any capture.

### Confirmed: about me

| | |
|---|---|
| **Method / path** | `POST /candidate/api/v1/profile/about` |
| **Request body** | `{"aboutme": "<string>"}` |
| **Response** | `{"success": true}` — **16 bytes** |
| **Fixtures** | `post-profile-about-happy-request.json`, `post-profile-about-happy.json` |

**Field trap — the response tells you nothing.** The endpoint returns a bare
`{"success":true}` and **not** the updated profile. A tool cannot confirm what
landed from the response body; it must re-`GET /candidate/api/v1/profile` and
compare. Every write tool built against this API needs that read-back, and the
read-back is the only honest basis for reporting success to the caller.

This also makes the app a prime candidate for the success-shaped failure: a
200 + `{"success":true}` shape leaves no room to express a validation error, so
either the error arrives as a different status or it arrives as
`{"success":false}` with the write silently dropped. **PASS 2 must resolve
which** before any tool reports success. Until then, treat `{"success":true}` as
"request accepted", never as "value stored".

**Naming pattern (hypothesis, 1 of 17 confirmed):** section endpoints hang off
`/candidate/api/v1/profile/<section>`. Do not build against this for the other
sections until each is observed — `experience_durations/bulk_save`, already
shipped, does *not* follow it.

### Field trap: `POST /profile/skills` silently rewrites `topSkills`

**This one cost real profile state and must be in the tool's docstring.**

`allSkills` (16) partitions into `topSkills` (3) + `skills` (13). The write
endpoint accepts **only** `{"allSkills": [<uuid>, ...]}` — there is no
`topSkills` field, and the Edit Skills modal has no top-skills control of any
kind (verified by screenshot: selected chips and suggested chips, nothing else).

Saving that editor **re-derives the 3/13 split server-side**. A save with the
skill set completely unchanged moved `topSkills` from
`[Generative AI, LLM, MongoDB]` to `[Spring Boot, System Architecture, LLM]` on
2026-08-10.

Established by experiment, not inference:

- **Not read-time rotation.** Three consecutive GETs returned the same trio.
- **Not re-rolled per write.** Three further identical POSTs left it unchanged.
- **Not driven by `experience_durations`** — `GET /candidate/api/v1/experience_durations`
  returns `{"experienceDurations": []}` for this account.
- **Not positional** in the `allSkills` array (the chosen indices were 9, 10, 14;
  the previous trio sat at 7, 14, 15, and array order was byte-identical before
  and after).

So the selection is deterministic given the payload, but its input is not
visible from any observed surface, and **the previous value is not recoverable
through the API.** Consequences for construction:

- The skills write tool must warn that `topSkills` will change, and must
  read-back and report the new trio to the caller.
- Treat `topSkills` as **read-only, server-owned** — never present it as
  settable.
- Do not call the skills endpoint as a no-op "touch". There is no such thing
  here; every call re-derives the split.

## PASS 2 — probes (2026-08-10)

Vehicle: `httpx` **outside the browser** — the true shape a headless client
hits, and the only honest vehicle for the stripped-auth probe. Every mutating
probe was aimed at a throwaway `cvStation` created for the run and deleted
after; no real profile field was targeted.

### Classification table

| Probe | Request | Result | Kind |
|---|---|---|---|
| bad id | `PATCH /cv/{zero-uuid}` | 404 `{"errors":{"base":"not_found"}}` | `invalid_input` |
| bad id | `DELETE /cv/{zero-uuid}` | 404, same envelope | `invalid_input` |
| bad id | `GET /job_suggestions/{zero-uuid}` | 404, same envelope | `invalid_input` |
| bad discriminator | `type: "Candidate::CvStation::NotAThing"` | 400 `{"errors":{"type":"Type is not included in the list"}}` | `invalid_input` |
| empty body | `PATCH /cv/{uuid}` with `{}` | 422 `{"errors":{"base":"parameter missing: cv_station"}}` | `invalid_input` |
| **missing required** | `cvStation` with only `type` | **200 `{"success":true}`** | **success-shaped failure** |
| **wrong types** | `title: 12345`, `stationName: [..]`, `current: "maybe"` | **200 `{"success":true}`** | **success-shaped failure** |
| stripped auth | no cookie, `Accept: application/json` | 403 `{"errors":{"base":"not_allowed"}}` | `auth_expired` |
| stripped auth | no cookie, browser `Accept`, no follow | 302, 0 bytes, `Location: /signin` | `auth_expired` |
| **stripped auth** | no cookie, browser `Accept`, **following redirects** | **200 `text/html`, 10 643 bytes** | **`auth_expired`, never success** |
| stale token | `_instaffo_session` corrupted alone | 200, full profile | — (see below) |
| stale token | `remember_user_token` corrupted alone | 200, full profile | — |
| stale token | **both** corrupted | 302 → `/signin` | `auth_expired` |
| overflow | `GET /job_suggestions?page=9999` | **200, same 2 rows, `meta.page: 9999`** | **success-shaped failure** |
| nonsense query | `?query=zzzzqqqq-no-such-role` | **200, same 2 rows, unfiltered** | **success-shaped failure** |

### The three findings that must reach the tools

**1. The `Accept` header decides whether a dead session looks like an error.**

This is the highest-value line in the file. The same unauthenticated request
returns three different shapes depending on headers the caller controls:

```
Accept: application/json                      -> 403 JSON  {"errors":{"base":"not_allowed"}}
Accept: application/json, text/plain, */*     -> 302 -> /signin
  ... and with follow_redirects=True          -> 200 text/html  (a login page)
```

**The shipped client sends the browser-ish `Accept`** (`client.py`), and is
saved only by `follow_redirects=False`. Flip that one flag and every expired
session becomes an HTTP **200** carrying HTML, which `.json()` then fails to
parse with a message that says nothing about auth. Per the taxonomy, a 200
serving HTML where JSON is the contract is `auth_expired`/`blocked` — never
success. **Constructed tools should send `Accept: application/json` strictly**,
which collapses the whole class into a clean, classifiable 403.

**2. Validation is partial, and the gaps are silent.**

`PATCH /cv/{uuid}` rejects a bad `type` (400) and a missing wrapper (422), but
**accepts a body with required fields omitted and with wrong-typed values, both
returning `{"success":true}`**. There is no response field that distinguishes
"stored as sent" from "stored after silently coercing or dropping". Combined
with the write endpoints' uniform 16-byte `{"success":true}`, this means:

> **A write tool may never report success from the response alone.** It must
> re-`GET /candidate/api/v1/profile` and compare the field it just wrote. That
> read-back is the only honest basis for a success message.

**3. Listing is a POST with a filter body; the GET returns only the *preferred*
slice; pagination is a cursor. (CORRECTED 2026-08-10 — this is the fix for the
"only 2 of 6 shown" bug.)**

The first capture recorded `GET /job_suggestions` returning "matches" and stopped
there. That GET (and a POST filtered on `jobStatus:open` alone) returns **only the
2 suggestions that match the candidate's *preferred* location** — never the full
open set. The counters say `open.total: 6, open.preferred: 2`; the missing 4 are
open suggestions in *non-preferred* locations, and they are reachable only by the
POST the SPA actually fires:

- **Preferred bucket (location matches):** `POST /candidate/api/v1/job_suggestions`
  body `{"filters":{"jobStatus":"open"},"perPage":N}` → the 2. The server applies
  the candidate's preferred-location filter implicitly even when no
  `locationFactors` is sent.
- **Everything else:** the same POST with the location wrapped in `neg_filters`.
  The in-app view issues the positive query **and** a `neg_filters` query and
  concatenates them. Negating an *impossible* location returns the whole open set
  in one call:
  `{"filters":{"jobStatus":"open","neg_filters":{"locationFactors":{"value":"specific","cities":[{"city":"Nowhereville","country":"Nowhere","geo":{"lat":0,"lon":0}}]}}},"perPage":N}`
  → all 6. **Caveat:** in that neg-filtered response the per-row `preferred` flag
  reads `true` for every row — it is **query-relative, not a stable property**. To
  label rows correctly, take the true preferred set from the positive query and
  merge: `preferred = uuid ∈ preferred_set`.
- **Pagination is an Elasticsearch cursor, not `page`.** `meta.page` **echoes
  whatever you send** (`page=9999` → `meta.page: 9999`, same rows) and `totalPages`
  is always `null`. Real paging: pass `meta.searchAfter` (array) back in the POST
  body as `searchAfter`; a page shorter than `perPage`, an empty page, or a
  repeated cursor is the end. (`pitId` is echoed too but is not required — the
  `searchAfter` array alone advances the cursor. Snake-case `search_after[]` as a
  query param is also honoured but empties the default query; the body `searchAfter`
  on the POST is the shape the UI uses.)
- **No server-side text search.** A `query` param is ignored; a nonsense term
  returns the full list, not an empty one. Do not expose `page` or `query`.

The shipped `instaffo_list_job_suggestions` implements this: paginate the
neg-impossible query for the full set, paginate the positive query for the
preferred uuids, merge, list preferred first.

### Auth model, corrected

Auth is carried by **two redundant cookies**, `_instaffo_session` and
`remember_user_token`. Corrupting **either one alone still authenticates**; only
corrupting both produces the 302. This is why the naive stale-token probe (which
mangled a Hotjar cookie, `_hjSessionUser_*`) proved nothing and had to be re-run
against the named pair.

Practical consequence: the ~24 h expiry observed on the session cookie does not
by itself predict when the tool stops working, because `remember_user_token`
can carry the session on its own. Treat `--auth-status --deep` as the
authority, not the cookie expiry.

### Not probed

`transient` (5xx) — not reproducible without hammering the service, which the
etiquette section forbids. `schema_drift` — nothing to compare against until a
second dated capture exists. Both are recorded as gaps rather than passes.

## Gaps — captured surface that is NOT in this contract

Recorded as gaps, not as passes. Building against guesses for any of these is
exactly what this document exists to prevent.

| Intent | Why not captured |
|---|---|
| Termination period | Modal has zero standard form controls; its options are custom elements the option-detector could not classify. Never submitted. |
| Work policy (remote/hybrid/onsite) | Same — `Candidate::Factor::Location` is visible in `GET /profile` but its write was never observed. |
| CV document upload | Hidden `input[type=file] accept=".pdf"` located in PASS 0, never exercised. |
| Profile picture upload | Avatar control located in PASS 0, never exercised. |

Two further recorded absences:

- **`transient` and `schema_drift` probes** were not run (see PASS 2).
- **No previous capture exists**, so the PASS 0 inventory diff the skill
  requires on re-capture has no baseline. The next capture must diff against
  this one.

## State of the account after this capture

The capture wrote to a live, publicly-visible candidate profile and restored
from `profile-baseline-happy.json`. Verified by full field diff on 2026-08-10,
**three fields did not return to baseline**:

| Field | Baseline | After | Cause |
|---|---|---|---|
| `topSkills` | Generative AI, LLM, MongoDB | Spring Boot, System Architecture, LLM | `POST /profile/skills` re-derives the split; not recoverable via the API (see field trap) |
| `skills` | (13, complement of above) | (13, complement of above) | same cause |
| `confirmedIndustryExperience` | `false` | `true` | the Industry experience modal's submit is **Verify & save**, which asserts confirmation as a side effect of saving |

Everything else — `aboutme`, `cvWork` (5), `cvEducation` (1), `languages`,
`industries`, `links`, `seniority`, and all four `factors` — is byte-identical
to baseline, and no probe strings survive anywhere in the profile.

## Legal / etiquette

Owner decision, recorded not assumed: this is a personal tool operating on the
account owner's own candidate account, at human click rates, reading and writing
only his own data. No third-party candidate data is touched, no republication.
Probes are a handful of extra requests, not a fuzzing run.
