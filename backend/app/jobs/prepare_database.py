"""Prepare a new or legacy create_all database for Alembic-managed deployments."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.config import BACKEND_DIR
from app.db.init_db import init_db
from app.db.session import Base, engine


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def _verify_model_schema() -> None:
    schema = inspect(engine)
    actual_tables = set(schema.get_table_names())
    problems: list[str] = []
    for table in Base.metadata.tables.values():
        if table.name not in actual_tables:
            problems.append(f"missing table {table.name}")
            continue
        actual_columns = {column["name"] for column in schema.get_columns(table.name)}
        missing = set(table.columns.keys()) - actual_columns
        if missing:
            problems.append(f"{table.name} missing columns: {', '.join(sorted(missing))}")
    if problems:
        raise RuntimeError("Database schema verification failed: " + "; ".join(problems))


def main() -> int:
    config = _alembic_config()
    schema = inspect(engine)
    if "alembic_version" in schema.get_table_names():
        command.upgrade(config, "head")
        print("Database upgraded to the latest Alembic revision.")
        return 0

    # Older Internship Radar releases used create_all without an Alembic version.
    # Build missing tables/columns, verify every mapped column, then establish the
    # migration baseline. Refuse to stamp if verification is incomplete.
    init_db()
    _verify_model_schema()
    command.stamp(config, "head")
    print("Database schema verified and registered at the latest Alembic revision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
