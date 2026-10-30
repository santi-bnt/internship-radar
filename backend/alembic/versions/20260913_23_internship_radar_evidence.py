"""Refresh verified Internship Radar project evidence.

Revision ID: 20260913_23
Revises: 20260913_22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260913_23"
down_revision = "20260913_22"
branch_labels = None
depends_on = None


VERIFIED_BULLETS = [
    "Designed and developed a full-stack platform for discovering, evaluating, and tracking technical internship and research opportunities through authenticated backend and frontend workflows.",
    "Implemented resume tailoring that ranks candidate skills, projects, and coursework against opportunity requirements before generating targeted LaTeX and PDF resumes.",
    "Built modular local and optional OpenAI-assisted analysis while preserving canonical profile evidence, immutable resume versions, application history, and database-backed eligibility decisions.",
]


def upgrade() -> None:
    profiles = sa.table(
        "resume_profiles",
        sa.column("id", sa.Integer()),
        sa.column("projects_json", sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(profiles.c.id, profiles.c.projects_json)
    ).mappings()
    for row in rows:
        projects = list(row["projects_json"] or [])
        changed = False
        for project in projects:
            if not isinstance(project, dict):
                continue
            repository = str(
                project.get("repository_url")
                or project.get("github_url")
                or project.get("url")
                or ""
            ).rstrip("/")
            if repository.casefold() != "https://github.com/example-candidate/intership_radar".casefold():
                continue
            project["bullets"] = list(VERIFIED_BULLETS)
            changed = True
        if changed:
            connection.execute(
                sa.update(profiles)
                .where(profiles.c.id == row["id"])
                .values(projects_json=projects)
            )


def downgrade() -> None:
    # Do not discard verified project evidence during a schema rollback.
    pass
