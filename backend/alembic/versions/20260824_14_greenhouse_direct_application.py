"""use direct Greenhouse application forms

Revision ID: 20260824_14
Revises: 20260823_13
"""

from urllib.parse import parse_qs, urlencode, urlparse

from alembic import op
import sqlalchemy as sa


revision = "20260824_14"
down_revision = "20260823_13"
branch_labels = None
depends_on = None


jobs = sa.table(
    "jobs",
    sa.column("id", sa.Integer()),
    sa.column("company", sa.String()),
    sa.column("apply_url", sa.Text()),
    sa.column("official_apply_url", sa.Text()),
    sa.column("original_source_url", sa.Text()),
    sa.column("canonical_official_url", sa.Text()),
)


def _zipline_direct_url(value: str) -> str:
    try:
        token = (parse_qs(urlparse(value).query).get("gh_jid") or [""])[0]
    except ValueError:
        return ""
    if not token.isdigit():
        return ""
    return f"https://job-boards.greenhouse.io/embed/job_app?{urlencode({'for': 'flyzipline', 'token': token})}"


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            jobs.c.id,
            jobs.c.apply_url,
            jobs.c.official_apply_url,
            jobs.c.original_source_url,
        ).where(sa.func.lower(sa.func.trim(jobs.c.company)) == "zipline")
    ).mappings()
    for row in rows:
        listing_url = (row["official_apply_url"] or row["apply_url"] or "").strip()
        direct_url = _zipline_direct_url(listing_url)
        if not direct_url:
            continue
        connection.execute(
            jobs.update().where(jobs.c.id == row["id"]).values(
                apply_url=direct_url,
                official_apply_url=direct_url,
                original_source_url=row["original_source_url"] or listing_url,
                canonical_official_url=direct_url,
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(jobs.c.id, jobs.c.original_source_url).where(
            sa.func.lower(sa.func.trim(jobs.c.company)) == "zipline",
            jobs.c.official_apply_url.like("https://job-boards.greenhouse.io/embed/job_app?%"),
        )
    ).mappings()
    for row in rows:
        listing_url = (row["original_source_url"] or "").strip()
        if "gh_jid=" not in listing_url:
            continue
        connection.execute(
            jobs.update().where(jobs.c.id == row["id"]).values(
                apply_url=listing_url,
                official_apply_url=listing_url,
                canonical_official_url=listing_url,
            )
        )
