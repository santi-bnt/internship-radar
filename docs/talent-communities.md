# Talent Community resumes

Open **Talent Communities → Boston Dynamics** (or add a company), edit **Target
Areas**, then **Generate Company Resume** to preview the selected projects and
verified skills. The same relevance engine selects up to two verified courses and
shows them in the preview. **Generate Resume** compiles a one-page PDF. Regeneration keeps
separate, user-owned versions; select the version to review/download and use with
**Apply with Assistant**. The extension must already be installed. Final submission
is always manual; confirmed submissions appear in Applications as Talent Community.

Company profiles and resume/session snapshots are separate from job requisitions.
`job_id` is nullable only for this workflow; standard job routes still require an
owned job. Company targeting does not create requirements or candidate evidence.
Boston Dynamics is an editable initial profile, not a special-case ranking branch.
Discovery recognizes talent-community titles and routes them to company profiles
instead of creating internship openings. Generic careers footers are not openings.

## Deployment

Apply Alembic revision `20260908_18` **before** releasing the new API. The scheduled
search workflow has a manual `prepare_only` option that runs migrations and checks
model columns without searches, email, or candidate profile reseeding. This is an
additive migration and preserves existing job-linked records. Roll back application
code if necessary, but leave the additive columns intact: the migration deliberately
refuses a destructive downgrade that would erase job-independent applications.

## Verification

`pytest tests/test_talent_communities.py` covers project/preferences ranking,
verified evidence, owner isolation, real one-page PDF compilation, version-bound
assistant sessions, manual-only submission, application history and schema migration.
Tectonic must be installed (`TECTONIC_PATH` may point to it). The PDF test prints
artifact paths with `pytest -s` for visual inspection. These use test contact data,
not production applications, and are never sent to a company.
