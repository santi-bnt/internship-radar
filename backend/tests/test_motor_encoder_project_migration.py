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
    / "20260913_24_motor_encoder_project.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("motor_project_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_adds_only_verified_motor_project_evidence_to_santiago():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    profiles = sa.Table(
        "resume_profiles",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("skills_json", sa.JSON(), nullable=False),
        sa.Column("projects_json", sa.JSON(), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            profiles.insert(),
            [
                {
                    "id": 1,
                    "full_name": "Alex Rivera",
                    "skills_json": ["C++"],
                    "projects_json": [],
                },
                {
                    "id": 2,
                    "full_name": "Joshua Example",
                    "skills_json": ["C++"],
                    "projects_json": [],
                },
            ],
        )
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = {
            row.full_name: row
            for row in connection.execute(sa.select(profiles)).all()
        }

    santiago = rows["Alex Rivera"]
    assert santiago.projects_json == [migration.VERIFIED_PROJECT]
    assert set(migration.VERIFIED_PROJECT["technologies"]) <= set(santiago.skills_json)
    assert rows["Joshua Example"].projects_json == []
