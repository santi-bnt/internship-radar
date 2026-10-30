from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260913_22_language_credentials.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("language_credentials_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_connects_legacy_ielts_to_the_language_profile():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    profiles = sa.Table(
        "resume_profiles",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("languages_json", sa.JSON(), nullable=False),
        sa.Column("certifications_json", sa.JSON(), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            profiles.insert().values(
                id=1,
                languages_json=["Spanish - Native", "English - Fluent"],
                certifications_json=[{
                    "name": "IELTS Academic",
                    "language": "English",
                    "score": "6.5",
                    "type": "language",
                    "verified": True,
                }],
            )
        )
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        stored = connection.exec_driver_sql(
            "SELECT language_credentials_json FROM resume_profiles WHERE id = 1"
        ).scalar_one()

    import json

    credentials = json.loads(stored)
    english = next(item for item in credentials if item["language"] == "English")
    assert english == {
        "language": "English",
        "proficiency": "Fluent",
        "certificate": "IELTS Academic",
        "score": "6.5",
        "verified": True,
    }

