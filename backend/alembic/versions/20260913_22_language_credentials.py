"""Add canonical language credentials to resume profiles.

Revision ID: 20260913_22
Revises: 20260913_21
"""

from __future__ import annotations

import re
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "20260913_22"
down_revision = "20260913_21"
branch_labels = None
depends_on = None


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parts(value: Any) -> tuple[str, str]:
    parts = re.split(r"\s+(?:—|-)\s+", _clean(value), maxsplit=1)
    return parts[0], parts[1] if len(parts) == 2 else ""


def upgrade() -> None:
    op.add_column(
        "resume_profiles",
        sa.Column(
            "language_credentials_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    profiles = sa.table(
        "resume_profiles",
        sa.column("id", sa.Integer()),
        sa.column("languages_json", sa.JSON()),
        sa.column("certifications_json", sa.JSON()),
        sa.column("language_credentials_json", sa.JSON()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            profiles.c.id,
            profiles.c.languages_json,
            profiles.c.certifications_json,
        )
    ).mappings()

    for row in rows:
        credentials: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for raw in row["languages_json"] or []:
            language, proficiency = _parts(raw)
            if not language:
                continue
            key = language.casefold()
            order.append(key)
            credentials[key] = {
                "language": language,
                "proficiency": proficiency,
                "certificate": "",
                "score": "",
                "verified": bool(proficiency),
            }

        for item in row["certifications_json"] or []:
            if not isinstance(item, dict):
                continue
            text = " ".join(_clean(value) for value in item.values()).casefold()
            language = _clean(item.get("language"))
            if not language and "ielts" in text:
                language = "English"
            if not language:
                continue
            key = language.casefold()
            if key not in credentials:
                order.append(key)
                credentials[key] = {
                    "language": language,
                    "proficiency": "",
                    "certificate": "",
                    "score": "",
                    "verified": False,
                }
            credentials[key].update(
                {
                    "certificate": _clean(item.get("name", item.get("title", ""))),
                    "score": _clean(item.get("score", item.get("result", ""))),
                    "verified": item.get("verified") is True,
                }
            )

        connection.execute(
            sa.update(profiles)
            .where(profiles.c.id == row["id"])
            .values(language_credentials_json=[credentials[key] for key in order])
        )


def downgrade() -> None:
    op.drop_column("resume_profiles", "language_credentials_json")
