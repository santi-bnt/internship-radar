from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260731_05_security_ownership.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("security_ownership_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_security_ownership_migration_upgrades_and_downgrades():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table_names = (
        "user_profiles",
        "jobs",
        "applications",
        "notifications",
        "company_sources",
        "target_companies",
        "target_search_runs",
        "search_runs",
    )
    for table_name in table_names:
        sa.Table(table_name, metadata, sa.Column("id", sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    migration = _load_migration()
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = sa.inspect(connection)
        for table_name in table_names:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            assert "owner_user_id" in columns
            indexes = {index["name"] for index in inspector.get_indexes(table_name)}
            assert f"ix_{table_name}_owner_user_id" in indexes

        migration.downgrade()
        inspector = sa.inspect(connection)
        for table_name in table_names:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            assert "owner_user_id" not in columns
