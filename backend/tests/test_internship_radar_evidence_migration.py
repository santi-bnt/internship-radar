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
    / "20260913_23_internship_radar_evidence.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("radar_evidence_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_updates_only_existing_verified_radar_project():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    profiles = sa.Table(
        "resume_profiles",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("projects_json", sa.JSON(), nullable=False),
    )
    metadata.create_all(engine)
    radar = {
        "name": "Internship Radar",
        "repository_url": "https://github.com/example-candidate/Intership_radar",
        "technologies": ["Python", "FastAPI"],
        "bullets": ["Old fact one.", "Old fact two."],
    }
    unrelated = {
        "name": "Unrelated project",
        "repository_url": "https://example.com/project",
        "technologies": ["C"],
        "bullets": ["Keep one.", "Keep two."],
    }

    with engine.begin() as connection:
        connection.execute(
            profiles.insert().values(id=1, projects_json=[radar, unrelated])
        )
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        stored = connection.execute(
            sa.select(profiles.c.projects_json).where(profiles.c.id == 1)
        ).scalar_one()

    assert stored[0]["bullets"] == migration.VERIFIED_BULLETS
    assert stored[0]["technologies"] == radar["technologies"]
    assert stored[1] == unrelated
