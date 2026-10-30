# Internship Radar

> Public showcase and reusable source code. Candidate data is fictional. This release contains no production database, personal CVs, account credentials, real certification identifiers or private candidate provisioning data.

The public demo is read-only and must use a separate backend/database. Set `PUBLIC_DEMO_MODE=true` and `NEXT_PUBLIC_PUBLIC_DEMO_MODE=true` only for that isolated demo. Hosted demo visitors cannot edit profiles, run discovery/imports, create application sessions or generate CVs. Private installations can enable those features after configuring their own accounts, authentication and secrets. Scheduled workflows require explicit `ENABLE_PUBLIC_AUTOMATION=true` repository configuration.

## October 2026 source update

- Job-specific TailoringPlan, candidate evidence mapping, role-aware project/skill decisions and immutable resume versions.
- Resume Studio, Best Resume, program CVs, verified language/certification evidence and generation queue/reuse controls.
- Add Job by URL with official-source enrichment, deduplication, SSRF protection and candidate-specific state.
- Dashboard filters/sorting/navigation preservation, archive/restore, reversible Applied tracking and freshness revalidation.
- More official employer adapters and conservative source health/retry scheduling.
- User-reviewed local application assistant with split-screen controls and combined HTML + screenshot vision through loopback Ollama. Docker runs the local model; Chromium remains visible on the desktop. See [local setup](local-agent/README.md).

Start local vision on Windows by double-clicking `start-local-assistant.cmd`. Images and form analysis stay on the device; hosted profile/CV services remain part of your configured Radar installation. Missing evidence, legal questions, assessments and final submission require personal review.

Private candidate bootstrap datasets and operator-curated import/override lists are omitted. Data-only personal migrations retain their revision slots as no-ops; generic schema migrations are preserved. The synthetic demo profile is not a source of claims for real candidates.

## Features

- Dashboard with manual search, metrics, priority alerts, and ranked opportunities.
- Job explorer with search, filters, minimum scores, and application status.
- Reusable job-description rendering for HTML, escaped HTML, entities, Markdown, lists, links, and plain text.
- Explainable scoring across technical fit, education, graduation date, authorization, seniority, location, and freshness.
- Independent hard gates for work authorization, university eligibility, degree completion, and restricted special programs.
- Application tracker with status, resume version, referral, deadline, and notes.
- Non-destructive job lifecycle with Active, Saved, Applied, Expired, Not Interested, and Archived states.
- Automatic deadline expiration using a configurable timezone and confidence-aware deadline extraction.
- Submitted-resume preservation: applied jobs retain the exact generated CV version used.
- User-controlled multi-portal Apply Assistant delivered as a private Manifest V3 extension, with verified-profile autofill, country-aware confirmed legal answers, exact session resume and role-specific portfolio preparation, final legal review, consistency checks, assessment pauses, and an absolute final-submit block.
- Official-source adapters for Greenhouse, Lever, Workday, SmartRecruiters, Amazon Jobs, Oracle Recruiting, and selected company career sites.
- Google Careers discovery decodes public job-specific data and paginates sequentially. The scoped `google_import` task adds current technical internships to the primary candidate only, pins the requested US Summer 2027 Hardware/Software postings without changing eligibility, and sends no email.
- Community discovery adapters with official-employer verification, provenance, confidence, health, and per-run metrics.
- Conservative deduplication and repeated verification before a missing job is marked closed.
- Automated production searches and deadline checks through GitHub Actions, with APScheduler available locally.
- Priority-only email notifications through SMTP or a safe console preview.
- Structured, job-specific resume generation with deterministic validation and LaTeX PDF output.
- Resume Studio: Embedded/Firmware, Software, FPGA, Robotics and General portfolio CVs, with evidence-weighted project selection, professional summaries, private immutable versions and PDF/LaTeX downloads. Generate one profile at a time at `/resume-studio`; no vacancy or external AI provider is required.
- PostgreSQL with Docker and SQLite as a local fallback.

## Architecture

```text
Intern/
|-- frontend/                 Next.js App Router + TypeScript
|   |-- app/                  Product pages and API proxy
|   |-- components/           Navigation, job UI, badges, and resume actions
|   `-- lib/                  API client and shared types
|-- backend/                  FastAPI + SQLAlchemy
|   |-- app/main.py           REST API
|   |-- app/models/           Persistent entities
|   |-- app/services/         Scoring, email, seed data, and resume generation
|   |-- app/sources/          Public job-source adapters
|   |-- app/jobs/             Refresh workflow and scheduler
|   |-- app/templates/        LaTeX resume template
|   `-- tests/                Pytest suite
|-- extension/                Private Chromium Manifest V3 Apply Assistant
|   |-- src/content/          Shared assistant core, portal detection, and isolated ATS adapters
|   |-- src/sidepanel/        User-controlled application side panel
|   |-- src/background/       Short-lived token and resume-download broker
|   `-- tests/                DOM, safety, policy, and consistency tests
`-- docker-compose.yml        Frontend, backend, and PostgreSQL
```

The frontend communicates with the backend through a private server-side proxy. The backend fetches permitted public sources, sanitizes HTML, normalizes jobs, verifies official links, and runs explainable analysis.

A first failed verification produces `Needs Verification`, a second produces `Probably Closed`, and the third closes the job. An explicit closure message on the official page closes it immediately.

## Product Tour

| Page | What it provides |
| --- | --- |
| **Dashboard** (`/`) | Weekly totals, Apply Today, priority alerts, review and eligibility counters, important opportunities, company-group tabs, live search progress, and the ranked priority queue. |
| **Jobs** (`/jobs`) | Full-text search, score and eligibility filters, lifecycle tabs for Active, Saved, Applied, Expired, and Not Interested, plus immediate Mark as Applied, Archive, and conditional Restore actions. |
| **Job detail** (`/jobs/{id}`) | Clean structured role content, requirements, decision rationale, education and special-program eligibility, official verification, source provenance, application tracking, and immutable resume versions with PDF Preview, selected skills, changes, keywords, and LaTeX tabs. |
| **Applications** (`/applications`) | Saved and submitted roles plus Apply Assistant history: portal, session state, CV version, confirmed-answer count, consistency findings, source URL, and job snapshot. |
| **Profile** (`/profile`) | Verified resume facts and a dedicated Application Profile for contact, address, education, languages, links, skills, projects, and the opt-in academic-project disclosure policy. |
| **Sources** (`/sources`) | Official ATS feeds and community discovery sources with enablement, trust, health, freshness, parser metrics, errors, manual refresh, and custom source management. |
| **Settings** (`/settings`) | Editable target companies, aliases, priority, preferred roles/locations, individual company searches, and an all-source Search now action. |
| **Account** (`/account`) | Current Google identity, separate professional and notification contact roles, Google account switching, and sign out. |

Authentication screens cover sign-in, access denial, and fail-closed maintenance
mode. The left navigation exposes only authenticated workspace pages.

## Multi-Portal Apply Assistant v2.2

Apply Assistant uses one canonical verified profile and a shared `ApplicationAssistantCore`. Runtime URL and DOM evidence select an isolated adapter; the company registry supplies only aliases and special rules. Intel and GE Aerospace reuse Workday, Zipline uses Greenhouse when that implementation is detected, and Microsoft, Amazon, and Oracle use dedicated beta adapters. Unknown HTTPS career sites fall back to a deliberately limited generic adapter.

| Company / flow | Adapter | Status |
| --- | --- | --- |
| Intel | Workday | Supported with local Review-page fixtures |
| GE Aerospace | Workday + GE compliance aliases | Supported with local Review-page fixtures |
| Zipline | Greenhouse | Current-form regression dry run reaches Review without submitting |
| Microsoft | Microsoft Careers | Beta; saved-profile conflicts require a user choice |
| Amazon / AWS | Amazon Jobs | Beta; all assessments pause automation |
| Oracle | Oracle Careers / detected ATS | Beta; unknown structure fails closed |
| Other HTTPS portals | Generic safe fields only | Beta |
| Lever, Ashby, SmartRecruiters, Google Careers | Detection only | Unsupported until adapter fixtures pass |

The application flow is deliberately user-controlled:

1. Open an active job with a secure official application URL.
2. Select **Apply with Assistant**.
3. Internship Radar verifies eligibility, selects or generates the job-specific Recommended Resume, ranks two or three matching verified projects, ranks 8–20 verified skills, and shows each relevance reason in Application Readiness. The user can remove projects or skills before continuing.
4. **Start Application** creates a database-backed Application Session and a revocable token valid for at most 30 minutes.
5. The web app passes only that scoped token, the session ID, and the public BFF URL to the locally installed extension.
6. On first use for an origin, the side panel asks permission for that career portal only. **Fill This Page** enters the reviewed session snapshot, attaches the exact prepared PDFs where browser security permits, and adds structured skills/languages individually where supported. Academic projects placed in a required Work Experience field are explicitly labeled as non-professional project work.
7. Exact recognized work-authorization, sponsorship, citizenship, source, and seasonal-availability questions may reuse current confirmed profile answers under `AUTO_FILL_REVIEW_REQUIRED`; ambiguous or new legal questions remain pending or manual.
8. **Review Fields** shows all reused legal and eligibility answers together, then compares the visible page with the immutable session snapshots and reports wrong dates, email, location, resume/portfolio version, duplicate address, unverified skills, or misleading project employment.
9. On every portal's Review page—or any assessment—the assistant stops. It never presses Submit, Apply, Complete Application, Certify and Submit, or Send Application.
10. After the user submits manually and the portal displays a recognizable confirmation, the side panel asks the user to **Confirm Applied**. Only then does Internship Radar move the job to Applied and bind the exact CV version to its history.

Field policies are enforced in both the adapter and API workflow:

| Policy | Behavior | Typical fields |
| --- | --- | --- |
| `AUTO_FILL` | May be entered from the verified snapshot | Name, professional email, phone, address, education, GPA, graduation, links, verified skills and languages |
| `AUTO_FILL_REVIEW_REQUIRED` | May reuse an exact, previously confirmed, country-aware profile answer; it remains visible in final legal review | Work authorization, sponsorship, citizenship, Zipline source and confirmed seasonal availability |
| `REVIEW_RECOMMENDED` | May be entered but remains visibly reviewable | Role-specific verified project descriptions, academic experience, availability wording |
| `CONFIRM_REQUIRED` | A suggestion may be shown, but the user must confirm it for this application | Veteran/disability, government, IP, relocation, numerical salary, legal disclosures, and recognized questions without sufficient context |
| `MANUAL_ONLY` | Never automated | Passwords, MFA, CAPTCHA, electronic signature, personal certification, unknown questions, final Submit |

The extension has no backend service secret, Google credential, ATS password, or permanent access token. Tokens are HMAC-signed, bound to one owner and one Application Session, scope-limited, short-lived, stored in `chrome.storage.session`, and revoked when the session closes. Career-site access is optional: the side panel requests only the current HTTPS origin after a user action, injects the assistant there, and never monitors unrelated sites or browsing history.

Each Application Session stores immutable copies of the selected projects, application-ready experience text, selected skills, match reasons, validation warnings, and Recommended Resume version. Later profile or ranking changes do not rewrite an older application record.

### Apply Assistant API

Authenticated web/BFF endpoints:

```text
GET  /api/application-profile
PUT  /api/application-profile
GET  /api/jobs/{job_id}/application-readiness
POST /api/jobs/{job_id}/application-sessions
GET  /api/application-sessions
GET  /api/application-sessions/{session_id}
POST /api/application-sessions/{session_id}/rotate-token
POST /api/application-sessions/{session_id}/revoke
POST /api/application-sessions/{session_id}/abandon
```

Scoped extension-token endpoints:

```text
GET   /api/extension/application-session
PATCH /api/extension/application-session/progress
POST  /api/extension/application-session/confirm-answer
POST  /api/extension/application-session/confirm-submitted
GET   /api/extension/application-session/resume.pdf
GET   /api/extension/application-session/portfolio.pdf
```

The extension BFF path accepts the Application Session bearer token without exposing or requiring `INTERNAL_API_SECRET`. Every extension request is still subject to `APP_ACCESS_ENABLED`, token signature, expiry, scope, owner, session, and revocation checks.

### Build and install the private extension

```powershell
Set-Location .\extension
npm install
npm run typecheck
npm test
npm run build
```

Chrome or Edge:

1. Open `chrome://extensions` in Chrome or `edge://extensions` in Edge.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select the repository's `extension/dist` directory.
5. Pin **Internship Radar Apply Assistant**. Its action opens the side panel.

Opera:

1. Open `opera://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked** and select `extension/dist`.
4. Opera is supported where its Chromium version implements Manifest V3 `sidePanel`.

Do not publish this build to the Chrome Web Store. It is intended for private, local installation. See [`extension/README.md`](extension/README.md) for the test workflow and developer diagnostics.

## Search and Recommendation Flow

1. A manual, scheduled, or company-specific run selects the enabled sources.
2. Official ATS adapters and community discovery adapters fetch permitted public data.
3. Descriptions are decoded, sanitized, normalized, and rendered without exposing raw HTML.
4. Conservative deduplication keeps the official application URL and preserves discovery provenance.
5. Official-page verification checks whether the role is open and whether its application link still works.
6. Work authorization, university, degree-completion, and special-program hard gates run independently.
7. Eligible or reviewable jobs receive the weighted technical, academic, level, logistics, and freshness score.
8. The backend assigns the visible category and excludes applied, expired, dismissed, archived, or blocked jobs from active recommendations.
9. Only a new deduplicated opportunity that satisfies the configured priority-alert rules can trigger production email.

## Quick Start with Docker

Requirements:

- Docker Desktop
- Git

Create the local environment file:

```powershell
Copy-Item .env.example .env
```

Start the complete stack:

```powershell
docker compose up --build
```

Open:

- Application: `http://localhost:3000`
- Safe API health check: `http://localhost:8000/health`

Stop the stack:

```powershell
docker compose down
```

PostgreSQL data is stored in the `postgres_data` Docker volume.

## Local Development on Windows

Requirements:

- Python 3.11 or newer
- Node.js 20 or newer

Backend:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements.txt

Set-Location .\backend
python -m app.jobs.refresh
uvicorn app.main:app --reload
```

Frontend, in another terminal:

```powershell
Set-Location .\frontend
npm install
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
npm run dev
```

Without `DATABASE_URL`, the backend uses `backend/internship_radar.db`.

## Environment Configuration

Copy `.env.example` to `.env` and replace placeholders locally.

Important variables:

```dotenv
DATABASE_URL=postgresql+psycopg://internship:internship@db:5432/internship_radar
FRONTEND_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000

SCHEDULER_ENABLED=true
SCHEDULER_HOUR=7
USER_TIMEZONE=America/Mexico_City

INTERNAL_API_URL=http://backend:8000
INTERNAL_API_SECRET=use-a-long-random-value
USER_IDENTITY_SIGNING_SECRET=use-a-different-long-random-value
PRIMARY_USER_ID=use-a-stable-random-user-id
AUTHORIZED_USER_EMAILS=first@example.com,second@example.com
APP_ACCESS_ENABLED=false

AUTH_SECRET=use-another-long-random-value
AUTH_GOOGLE_ID=
AUTH_GOOGLE_SECRET=
NEXT_PUBLIC_APP_URL=http://localhost:3000

RESUME_GENERATION_PROVIDER=local
OPENAI_API_KEY=
OPENAI_RESUME_MODEL=gpt-5.6
RESUME_GENERATION_LIMIT_PER_HOUR=30
RESUME_GENERATION_GLOBAL_CONCURRENCY=2
TECTONIC_PATH=tectonic

RESUME_EMAIL=resume@example.com
NOTIFICATION_EMAIL=notifications@example.com
```

The local resume provider does not require an OpenAI API key. Set `RESUME_GENERATION_PROVIDER=openai` only when structured OpenAI tailoring is desired.

`RESUME_GENERATION_LIMIT_PER_HOUR` must have the same value in the backend and
the Vercel frontend environment (the default is 30). The backend queue limits
expensive resume/PDF pipelines with `RESUME_GENERATION_GLOBAL_CONCURRENCY`
(default 2); it does not use a simplified generation path.

Never commit `.env`, API keys, SMTP credentials, application passwords, personal contact addresses, generated PDFs, or local databases. These files are excluded by `.gitignore`.

## Privacy and Secret Management

The repository contains neutral example addresses only. Real login, resume, and
notification addresses are runtime configuration and intentionally have separate
roles:

- `AUTHORIZED_USER_EMAILS` controls which Google accounts may sign in.
- `RESUME_EMAIL` is printed on generated resumes.
- `NOTIFICATION_EMAIL` and `EMAIL_RECIPIENT` receive alerts.
- `SMTP_USERNAME` and `SMTP_FROM_EMAIL` identify the sending mailbox.

Store production values in Vercel Environment Variables, Render Environment
Variables, and GitHub Actions Secrets. Do not place them in `render.yaml`, Docker
defaults, workflows, tests, screenshots, issues, or documentation. A committed
secret must be rotated; deleting it in a later commit does not remove it from Git
history.

## Authentication and private access

Internship Radar uses Auth.js with Google OAuth and JWT sessions. It is a
closed, single-user application: every allowed Google identity resolves to one
stable `PRIMARY_USER_ID`. Login email, professional resume email, and
notification email are separate values and OAuth never overwrites either
contact address.

Private traffic follows this path:

1. Auth.js validates the Google account, verified-email claim, and exact
   `AUTHORIZED_USER_EMAILS` allowlist.
2. The browser calls only the Next.js BFF under `/api/backend`.
3. The BFF validates the server-side session and adds both
   `INTERNAL_API_SECRET` and a 60-second HMAC-signed user identity.
4. FastAPI validates the service secret, signature, timestamps, audience,
   purpose, allowlist, and `PRIMARY_USER_ID` before accessing the database.
5. Request-scoped ownership filters prevent records belonging to another
   internal user from being returned.

`GET /health` is the only public FastAPI endpoint. API documentation is disabled
in production. PDF and LaTeX files are streamed only through authenticated
routes and are not stored in the frontend's public directory.

Access fails closed. Keep this setting until OAuth has been configured and
tested:

```dotenv
APP_ACCESS_ENABLED=false
```

When disabled, private pages redirect to `/maintenance`, private BFF and backend
requests return `503`, and no private reads, writes, searches, resume generation,
or downloads are performed.

### Google OAuth setup

1. Create or select a project in Google Cloud Console.
2. Configure the OAuth consent screen. Use **External** only if the accounts are
   outside one Google Workspace organization; add the intended accounts as test
   users while the application remains in testing.
3. Create an **OAuth client ID** with application type **Web application**.
4. Add these Authorized JavaScript origins:
   - `https://your-app.vercel.app`
   - `http://localhost:3000`
5. Add these Authorized redirect URIs:
   - `https://your-app.vercel.app/api/auth/callback/google`
   - `http://localhost:3000/api/auth/callback/google`
6. Copy the client ID to `AUTH_GOOGLE_ID` and the client secret to
   `AUTH_GOOGLE_SECRET` in Vercel. Never commit either value.

Auth.js also requires a separate random `AUTH_SECRET`. Callback redirects are
restricted to the configured application origin (and localhost in development).

## Email Notifications

The production configuration is intentionally priority-only:

- `EMAIL_PRIORITY_ALERTS=true`
- `EMAIL_DAILY_DIGEST=false`
- `EMAIL_DEADLINE_ALERTS=false`
- `EMAIL_FOLLOW_UP_ALERTS=false`
- `EMAIL_STATUS_CHANGE_ALERTS=false`

The service also supports important-company, deadline, digest, follow-up, and
status-change templates, but those channels remain opt-in and disabled in the
current deployment. Existing jobs are not bulk-mailed when notifications start.

To preview messages without sending email:

```dotenv
EMAIL_ENABLED=true
EMAIL_PROVIDER=console
```

For Gmail SMTP:

```dotenv
EMAIL_ENABLED=true
EMAIL_RECIPIENT=your-email@example.com
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=
SMTP_USE_TLS=true
SMTP_FROM_NAME=Internship Radar
SMTP_FROM_EMAIL=your-email@example.com
APP_BASE_URL=http://localhost:3000
```

Enable [Google two-step verification](https://support.google.com/accounts/answer/185839) and create an [application password](https://support.google.com/accounts/answer/185833). Use the application password for `SMTP_PASSWORD`, not the account password.

Every notification attempt is persisted. Deduplication uses the job,
notification type, recipient, and important content. Missing SMTP credentials do
not stop job refreshes, and a provider acceptance is not reported as delivered
without delivery confirmation.

## Job Search and Analysis

Run a manual refresh:

```powershell
Set-Location .\backend
python -m app.jobs.refresh
```

The dashboard triggers the same workflow through `POST /api/jobs/search`. Every
manual or managed search refreshes every enabled automatic source; only an
explicit single-company search narrows the source set. By default, APScheduler
runs it daily at 07:00 in `America/Mexico_City`.

Seeded official sources include Amazon, Google, Meta, NVIDIA, NXP, Oracle, AMD,
Qualcomm, Arm, Synopsys, Cadence, Intel, Micron, Marvell, Broadcom, Rockwell
Automation, Databricks, MongoDB, Cloudflare, Zoox, Bosch, Western Digital,
Anduril, Astranis, Zipline, and SpaceX. Unsupported watchlist entries remain
disabled until a reliable public adapter is configured.

### Community discovery sources

The source registry also seeds five discovery-only integrations:

- SimplifyJobs/Pitt CSC Summer 2027 Internships (`dev/README.md`).
- speedyapply 2027 SWE College Jobs (USA plus `INTERN_INTL.md`).
- FAANG 2027 Internship Tracker.
- ApplyGuy 2027 Internships (`data/internships.json`).
- Community Internship Aggregator category listings.

These sources increase recall but never replace the official employer posting as
the source of truth. A discovered job keeps `discovered_from_source`, all
`discovery_sources`, community sponsorship markers, and a confidence score. The
system follows safe public application links, verifies the official career or ATS
page, and records `verified_from_source` separately. Until that succeeds, work
eligibility remains `UNKNOWN` and the job cannot become an automatic eligible
recommendation.

Mexico, Guadalajara, Zapopan, Tlaquepaque, Mexico City, Monterrey, Querétaro,
Tijuana, remote Mexico, remote LATAM, and global remote listings are processed
first within each community source. Remote U.S.-only roles still pass through the
normal work-authorization gate and are not treated as Mexico-compatible.

The **Discovery Sources** page exposes enablement, registry type, trust, priority,
last check, parser counts, new jobs, duplicates, official verifications, errors,
duration, and health. Repositories older than `COMMUNITY_SOURCE_STALE_DAYS`
(default `90`) are marked `STALE` and automatically receive reduced priority.

## Job Lifecycle and Deadlines

Internship Radar never deletes a job merely because it was submitted, expired, dismissed, or archived. The primary lifecycle states are:

- `active`
- `saved`
- `applied`
- `expired`
- `not_interested`
- `archived`

Active queries and recommendation endpoints include only `active` and `saved` jobs by default. Applied, expired, dismissed, and archived jobs remain available as historical records but are excluded from recommendations, priority alerts, email alerts, and new resume generation.

Marking a job as applied:

- Is idempotent and does not create duplicate application records.
- Stores `applied_at` in UTC.
- Removes the job immediately from active opportunities.
- Associates the latest compiled resume when one exists.
- Preserves every resume version, note, score, analysis, and application update.

Deadline expiration is handled by `expire_past_deadline_jobs()`. A job expires only when:

- Its status is `active` or `saved`.
- It has an `application_deadline`.
- The deadline confidence is high enough for automatic action.
- The deadline's full calendar day has ended in `USER_TIMEZONE`.

Jobs without a deadline, jobs with low-confidence deadlines, future deadlines, and already-applied jobs are never expired automatically. Publication dates are not treated as application deadlines.

Run deadline maintenance manually:

```powershell
Set-Location .\backend
python -m app.jobs.expire_deadlines
```

In the free production architecture, GitHub Actions runs deadline expiration
daily using the same Neon `DATABASE_URL`. The built-in scheduler remains
available for local Docker installations.

## Target Company Search

The Settings page contains an editable target-company list grouped into cloud/data,
semiconductors, and robotics/automotive. Each company can be enabled or disabled,
assigned a high/medium/low priority, and given aliases, career URLs, preferred role
categories, and preferred locations. Oracle aliases include Oracle, Oracle Corp,
Oracle Cloud, OCI, Oracle Labs, and NetSuite.

Target-company priority is a moderate ranking signal, never an eligibility override.
General discovery remains active, and jobs from other companies continue to appear.
Official jobs are preferred during deduplication; alternate aggregator URLs are kept
as source history instead of replacing the official application link.

Run all target companies immediately:

```powershell
Set-Location .\backend
python -m app.jobs.search_target_companies --force
```

This all-company action refreshes every enabled automatic source so general
discovery is not accidentally restricted to the target-company list.

Run one company:

```powershell
python -m app.jobs.search_target_companies --company Oracle --force
```

The scheduler checks targets daily at 06:15 in `USER_TIMEZONE`. High-priority
companies are due daily, medium-priority companies every two days, and low-priority
companies weekly. Each run is recorded with timestamps, companies checked, jobs
discovered/added/updated/expired, and isolated source errors.

The overall score uses:

| Component | Weight |
| --- | ---: |
| Technical fit | 45% |
| Education and graduation | 20% |
| Visa and work authorization | 15% |
| Role level | 10% |
| Location, duration, and work mode | 5% |
| Freshness and status | 5% |

Required skills weigh more than preferred skills. Missing sponsorship information for a United States or Canadian position produces `Review`, not automatic rejection.

Explicit citizenship, clearance, country-specific university enrollment, permanent work authorization, mandatory advanced-degree, and similar restrictions can produce `Not Eligible`.

`Apply Today` additionally requires:

- `official_status=open`
- `verification_status=verified`
- A valid official application link
- `freshness_score >= 50`
- No hard eligibility blocker

## Eligibility Hard Gates

Eligibility is evaluated before ranking bonuses. A high technical score or a
target-company match can never override an explicit hard blocker.

### Work authorization and university eligibility

The verified student profile is based at Tecnológico de Monterrey in Mexico. Jobs in Mexico, the United States, Canada, and remote roles can be evaluated.

Generic requirements such as “currently enrolled at an accredited university” are accepted. Requirements limited to a specific country, institution, participating-university list, or approved co-op program are treated as hard blockers.

University eligibility and work authorization are always evaluated independently.

### Degree completion

The analyzer distinguishes roles open to students who are still completing a
degree from roles that require the degree to be finished before applying or
starting. Explicit completion requirements are compared with the verified degree
status and expected graduation date. Ambiguous language is sent to `Review`; it
is never inferred from the job title or publication date.

### Special programs

Restricted cohorts such as veteran, active-duty, transitioning-service-member,
military-spouse, disability, return-to-work, former-employee, and specific
academic programs are evaluated against explicit profile fields. A mandatory
membership requirement that the profile does not satisfy produces `Not Eligible`.
Title-only or ambiguous signals require verification, while general equal
opportunity language never creates a blocker.

## Resume Generation

Each job detail page contains a **Recommended Resume** section.

The generator:

1. Reads the saved job description and requirements.
2. Uses only verified information from `Profile > Resume Profile`.
3. Classifies the role by technical area.
4. Ranks projects using base relevance, matching technologies, semantic concepts, and responsibilities.
5. Selects job-specific skills, project technologies, and factual bullet variants.
6. Rejects unsupported skills, claims, certifications, links, and experience.
7. Renders a controlled Jinja2 and LaTeX template.
8. Compiles the document with Tectonic.
9. Verifies clean extracted text, one-page output, and target vertical usage.
10. Stores a new immutable resume version.

The Skills section is generated dynamically for every job. A canonical registry
is built from explicit profile skills plus evidence in verified projects,
coursework, and experience. Job requirements are separated into required,
preferred, and contextual matches, then scored against that registry. The final
resume contains two to four ATS-readable categories and normally eight to
sixteen verified skills. Unsupported requirements are refused rather than copied.

Aliases such as `cpp`, `C/C++`, `RTOS`, `Postgres`, and `OOP` are normalized to
one canonical skill. Each generated resume version stores its selected skills,
categories, match explanations, evidence, and verification snapshot, so older
versions do not change when the master profile is edited.

Supported classifications include:

- Software Engineering
- Backend / Data
- Embedded / Firmware
- FPGA / Digital Design
- AI / API Integration
- Robotics / Controls
- Maps / Routing / Geospatial
- Full Stack / Web
- Developer Tools / Productivity

Projects take priority over introductory coursework. The generator normally uses three projects and adds a fourth only when it is relevant, contributes useful skills, and the page remains underfilled. At most two verified courses may be shown.

Private projects do not receive a GitHub link. A live link appears only when a verified URL is configured.

The browser never receives `OPENAI_API_KEY` or `INTERNAL_API_SECRET`.

## Tectonic

[Tectonic](https://tectonic-typesetting.github.io/) compiles the generated LaTeX into PDF.

Confirm a local installation with:

```powershell
tectonic --version
```

Alternatively, set `TECTONIC_PATH` to the executable's absolute path. The backend Docker image installs Tectonic automatically.

## Database Migrations

Apply migrations with:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
```

## Adding a Source

From **Sources**:

1. Choose the supported source type.
2. Enter the company name.
3. Provide the board token, company slug, or official source identifier.
4. Add the official careers URL.
5. Enable the source and select **Refresh enabled**.

The common adapter contract is:

```python
source_name
source_url
await fetch_jobs()
normalize_job(raw)
```

New public adapters belong in `backend/app/sources/` and must be registered in `registry.py`. Adapters must use timeouts, an identifiable User-Agent, isolated error handling, public HTTP(S) URLs, and responsible request limits.

Internship Radar does not bypass CAPTCHAs, authentication, robots restrictions, or access controls.

## Main API

- `GET /health`
- `GET|PUT /api/profile`
- `GET|PUT /api/resume-profile`
- `GET /api/resume-profile/verified-skills`
- `GET /api/jobs`
- `GET /api/jobs/{id}`
- `POST /api/jobs/search`
- `POST /api/jobs/{id}/analyze`
- `POST /api/jobs/analyze-all`
- `POST /api/jobs/{id}/mark-applied`
- `POST /api/jobs/{id}/undo-applied`
- `POST /api/jobs/{id}/restore`
- `POST /api/jobs/{id}/archive`
- `POST /api/jobs/{id}/resume/generate`
- `GET /api/jobs/{id}/resume/latest`
- `GET /api/jobs/{id}/resumes`
- `GET /api/generated-resumes/{id}/pdf`
- `GET /api/generated-resumes/{id}/tex`
- `GET /api/search-runs/latest`
- `GET /api/search-runs/{id}`
- CRUD under `/api/applications`
- CRUD under `/api/sources`
- `POST /api/sources/refresh`
- CRUD under `/api/target-companies`
- `POST /api/target-companies/search`
- `POST /api/target-companies/{id}/search`
- `GET /api/notifications`
- `POST /api/notifications/test-connection`
- `POST /api/notifications/test-email`
- `GET /api/stats`

## Tests and Validation

Backend:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest -q
```

Frontend:

```powershell
Set-Location .\frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Generate and compile the three deterministic resume examples used for visual
validation from inside the backend environment:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m app.jobs.generate_resume_examples
```

The current suite contains 243 backend tests and 11 frontend tests. It covers
scoring, sponsorship, university and degree-completion eligibility, restricted
special programs, seniority, closed jobs, required versus preferred skills,
official verification, community provenance, source adapters, API filters,
notifications, lifecycle transitions, optimistic removal, idempotent application
submission, timezone-aware deadlines, resume preservation, project ranking,
private links, course selection, ATS sanitization, and one-page PDF rules.

## Logs and Local Artifacts

Local `*.log` files, build output, generated artifacts, caches, databases, and
environment files are ignored by Git. Development servers may create temporary
root-level logs when they are launched in the background; these can be removed
after the corresponding process stops. Production diagnostics remain in Vercel,
Render, and GitHub Actions instead of being committed to this repository.

Before publishing, verify the repository remains clean with:

```powershell
git status --short
git ls-files "*.log"
```

## Collection and Safety Boundaries

Internship Radar only uses permitted public endpoints and pages. It does not:

- Sign in to job boards
- Store job-board passwords
- Solve CAPTCHAs
- Scrape LinkedIn or Handshake
- Automate job applications
- Invent resume facts or metrics
- Provide legal or immigration advice

Fetched HTML is converted to text and never executed. Source terms, robots policies, request limits, and accuracy must be reviewed regularly.

## Production Checklist

### Production architecture

- **Vercel:** Next.js frontend and the server-side BFF route.
- **Render Free Web Service:** Dockerized FastAPI backend. It can sleep after
  inactivity and wake on the next request.
- **Neon Free:** persistent managed PostgreSQL, independent of Render's
  ephemeral filesystem.
- **GitHub Actions:** scheduled searches run independently of Render and the
  user's computer.
- **GitHub:** pushes to `main` trigger Render and Vercel deployments.

The repository root contains a free `render.yaml` with one web service. The
workflow `.github/workflows/scheduled-searches.yml` runs these UTC schedules:

| Job | UTC schedule | Command |
| --- | --- | --- |
| High-frequency discovery (all enabled sources) | `15 */6 * * *` | `python -m app.jobs.search_high_priority` |
| General discovery | `30 11 * * *` | `python -m app.jobs.search_general` |
| Active-job verification | `0 12 * * *` | `python -m app.jobs.verify_active_jobs` |
| Deadline expiration | `15 12 * * *` | `python -m app.jobs.expire_deadlines` |

All workflow runs share Neon PostgreSQL and use a database-level lock, so
overlapping searches are skipped safely. GitHub Actions schedules use UTC and
can also be started manually from the Actions tab.

Scheduled jobs are a separate service identity: they run backend commands
directly with the protected Neon `DATABASE_URL` and `PRIMARY_USER_ID`. They do
not use Google cookies, Auth.js sessions, BFF user tokens, or browser headers.

### Create free PostgreSQL on Neon

1. Create a free project at Neon.
2. Open **Connect**, enable the pooled connection option, and copy the connection
   string.
3. In GitHub, open **Settings > Secrets and variables > Actions**.
4. Create the repository secret `DATABASE_URL` with that connection string.
5. Use the same value for `DATABASE_URL` in Render.

Never commit the Neon connection string. Internship Radar normalizes a standard
`postgresql://` URL to the Psycopg SQLAlchemy driver automatically.

### Deploy the free backend on Render

1. Push the repository to GitHub.
2. In Render, select **New > Blueprint** and choose the repository.
3. Review `render.yaml`; it creates only `internship-radar-api` on the Free plan.
4. Fill every variable marked `sync: false`.
5. Paste the Neon pooled URL as `DATABASE_URL`.
6. Use the generated Web Service URL for `FASTAPI_INTERNAL_URL` in Vercel.
7. Set `FRONTEND_URL` and `APP_BASE_URL` to the final Vercel production URL.
8. Database migrations run through `.github/workflows/database-migrations.yml`
   whenever migration or model files reach `main`. The web process stays
   read-only during startup so a migration cannot delay Render's health check.
9. Open `https://YOUR-API.onrender.com/health`; the first free-tier request can
   take about a minute while the service wakes.

Do not use SQLite on Render. The filesystem is ephemeral; resumes are compiled
temporarily from LaTeX stored in PostgreSQL.

### Deploy the frontend on Vercel

1. Import the same GitHub repository in Vercel.
2. Set **Root Directory** to `frontend`.
3. Keep the detected framework as Next.js.
4. Add the frontend variables from `.env.example`.
5. Set `FASTAPI_INTERNAL_URL` to the HTTPS Render backend URL.
6. Use the exact same `INTERNAL_API_SECRET` in Vercel and Render.
7. Deploy, then update Render's `FRONTEND_URL` and `APP_BASE_URL`.
8. Redeploy after changing environment variables.

The browser calls only `/api/backend/...`; the Route Handler adds the private
secret server-side and proxies API and PDF responses to FastAPI.

### Required production variables

Render backend:

```text
DATABASE_URL                         Neon pooled PostgreSQL URL
INTERNAL_API_SECRET                  long random secret
USER_IDENTITY_SIGNING_SECRET         separate long random secret
PRIMARY_USER_ID                      stable internal user identifier
AUTHORIZED_USER_EMAILS               exact comma-separated allowlist
APP_ACCESS_ENABLED=false             keep locked during OAuth setup
RESUME_EMAIL                         professional CV address
NOTIFICATION_EMAIL                   notification destination
FRONTEND_URL                         Vercel production URL
APP_BASE_URL                         Vercel production URL
TECTONIC_PATH=tectonic
SEARCH_SCHEDULER_ENABLED=false       GitHub Actions owns scheduled searches
```

GitHub Actions repository secrets:

```text
DATABASE_URL                         same Neon pooled PostgreSQL URL
PRIMARY_USER_ID                      same stable internal identifier
NOTIFICATION_EMAIL                   alert destination
RESUME_EMAIL                         professional CV address
SMTP_USERNAME                        SMTP account
SMTP_PASSWORD                        SMTP application password
SMTP_FROM_EMAIL                      verified sender address
```

Vercel frontend:

```text
AUTH_SECRET
AUTH_GOOGLE_ID
AUTH_GOOGLE_SECRET
AUTHORIZED_USER_EMAILS
PRIMARY_USER_ID
INTERNAL_API_SECRET
USER_IDENTITY_SIGNING_SECRET
FASTAPI_INTERNAL_URL
NEXT_PUBLIC_APP_URL
APP_ACCESS_ENABLED=false
RESUME_EMAIL
NOTIFICATION_EMAIL
```

`INTERNAL_API_SECRET`, `USER_IDENTITY_SIGNING_SECRET`, `PRIMARY_USER_ID`, and
`AUTHORIZED_USER_EMAILS` must match between Vercel and Render. `AUTH_SECRET` and
the Google client secret exist only in Vercel. GitHub Actions reads all contact
addresses and SMTP credentials from repository secrets; none are hardcoded in
the workflow. OpenAI remains optional. Never commit secret values.

After all variables are saved:

1. Redeploy Render while `APP_ACCESS_ENABLED=false`.
2. Redeploy Vercel while `APP_ACCESS_ENABLED=false`.
3. Confirm `/health` is safe and the site shows maintenance.
4. Change `APP_ACCESS_ENABLED=true` in both services and redeploy both.
5. Test all authorized accounts and one unauthorized account in private browser
   windows.
6. Test logout, Search now, profile updates, PDF download, and the separate
   resume and notification email values.

### Operational verification

Start a manual search with **Search now**. The API returns `202`, creates a
`search_runs` row, and performs the work in the backend. The dashboard polls only
for display; closing the page does not stop the search. Visible stages are
Starting, Searching official sources, Normalizing jobs, Deduplicating jobs,
Scoring matches, Verifying openings, and Completed or Failed.

Verify the latest run:

```text
GET /api/search-runs/latest
GET /api/stats
GET /health
```

`Last source update` comes from the latest completed or partially completed
server execution, never from page-load time.

### Free-tier limitations

This architecture can remain at zero cost within the providers' free quotas.
Render Free sleeps after inactivity, so the first page load can be slow. Scheduled
GitHub Actions still connect directly to Neon and search while Render sleeps.
GitHub schedules can be delayed during busy periods and are disabled after long
repository inactivity according to GitHub's scheduled-workflow policy. Neon and
Vercel usage must remain inside their current free-plan allowances.

- Replace development database credentials.
- Store secrets outside the repository.
- Keep Alembic migrations current.
- Run the scheduler as a single dedicated process.
- Add observability, backups, retry backoff, and distributed rate limits.
- Review every source's terms and maintain adapters as APIs change.
- Require human review for immigration and export-control decisions.

## License

No license has been selected yet. Add one before accepting external contributions or reuse.
