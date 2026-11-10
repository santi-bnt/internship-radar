# Unified discovery and adaptive resumes

This public edition contains reusable code and synthetic candidate fixtures. No private repository history, personal projects, production credentials, databases, CVs or operator-curated opportunity collections were copied. `PUBLIC_RELEASE.md` remains authoritative.

## Discovery

The existing refresh pipeline now handles official ATS APIs, optional discovery providers and explicit external/manual imports through normalization, official URL resolution, conservative deduplication, eligibility, existing matching and candidate-scoped storage.

- Greenhouse, Lever and Ashby use public board APIs. SmartRecruiters reuses structured endpoints. Workday remains an experimental tenant-configured source.
- Source observations retain where a posting was discovered while an official employer/ATS URL remains canonical when verified.
- Immutable description snapshots preserve previously observed text. First-seen, posted, seen and checked dates have separate meanings.
- Availability changes require an authoritative complete board snapshot or explicit closure; a filtered search miss cannot close a saved posting.
- Fit and eligibility scores are separate. Unknown sponsorship, international eligibility, funding and dates remain unknown.
- Private installations can run Quick/Deep Search, view source health/history and import external results. Due-source scheduling, request pacing, retry/backoff and independent source failures reuse the existing orchestration.
- Backend-only Tavily discovery requires `OPPORTUNITY_SEARCH_PROVIDER=tavily` and `OPPORTUNITY_SEARCH_API_KEY`. These credentials never belong in frontend variables.
- Freehire is optional and disabled by default. Enable it only under applicable personal/non-commercial or licensed terms using `FREEHIRE_ENABLED` and `FREEHIRE_USE_MODE`. No third-party datasets or repository code were copied.
- JobSpy, USAJobs and large-scale board discovery are not implemented in this release.

The public demo stays read-only: the BFF rejects writes and the backend independently rejects mutations when `PUBLIC_DEMO_MODE=true`. Public UI does not bootstrap an operator's opportunity collection. Scheduled automation remains opt-in and uses only a separate demo database.

New additive schema revisions are `20261101_32` (candidate-owned opportunity metadata) and `20261104_33` (observations, state, description history). Apply with `python -m alembic upgrade head` only against the database for this installation. No private candidate data migration is included.

## Resumes

Role views reuse one project's stored evidence. Planned work cannot contribute implemented evidence. New one-page exports can trial verified project details and relevant coursework when rendered space permits, rolling back optional expansions on overflow or compiler failure. Existing versions are never rewritten. KOSPIE now preserves valid stored live URLs. Ranking explanations use each project's own scores.

Synthetic profile data is demonstration material, never evidence for a real candidate. Configure your own verified profile before generating a real CV. No personal project datasets, including Satzivo, are bundled into the public edition.

## Verification

- 106 targeted backend checks passed: discovery, adapters, normalization/deduplication, import HTTP flow, migrations, isolation, public read-only boundaries and scoped tailoring plans.
- All 69 frontend tests and TypeScript typecheck passed.
- The frontend production build completed. The local Windows build with shared dependencies reported an optional standalone symlink-copy warning; that packaging detail is not claimed as verified on Windows.
- Live external provider availability, configured schedules and production database updates are not enabled or claimed for forks/demo installations.

This targeted result is not a claim that every historical profile-specific test in the public showcase has been executed or repaired.
