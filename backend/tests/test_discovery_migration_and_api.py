import importlib.util
from pathlib import Path
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from app.db.session import Base
from app.models import Job, JobDescriptionSnapshot, OpportunityDiscoveryState, OpportunitySourceObservation, SearchRun


def test_discovery_migration_backfills_provenance_without_replacing_jobs():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table in (JobDescriptionSnapshot.__table__, OpportunitySourceObservation.__table__, OpportunityDiscoveryState.__table__):
            table.drop(conn)
    with Session(engine) as db:
        job = Job(owner_user_id="old-owner", source_name="Official", source_url="https://example.edu/program", company="University", title="Research Internship", apply_url="https://example.edu/apply", description="Original saved research description", status="applied", raw_data_hash="old-hash")
        db.add(job); db.commit()
        identity = job.id
    path = Path(__file__).parents[1] / "alembic/versions/20261104_33_discovery_evidence.py"
    spec = importlib.util.spec_from_file_location("discovery_migration", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
        module.upgrade()  # Safe with additive runtime-created tables/backfill.
    with Session(engine) as db:
        job = db.get(Job, identity)
        assert job.status == "applied" and job.raw_data_hash == "old-hash"
        assert len(db.scalars(select(Job)).all()) == 1
        observations = db.scalars(select(OpportunitySourceObservation)).all()
        snapshots = db.scalars(select(JobDescriptionSnapshot)).all()
        assert len(observations) == len(snapshots) == 1
        assert observations[0].owner_user_id == "old-owner"
        assert snapshots[0].description == job.description
        assert db.scalars(select(OpportunityDiscoveryState)).all() == []  # Eligibility wasn't guessed.
    engine.dispose()


def test_run_history_and_results_are_owner_scoped():
    from app.discovery_api import run_status, history
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        private_run = SearchRun(owner_user_id="other-owner", search_type="discovery_quick")
        db.add(private_run); db.commit()
        with pytest.raises(HTTPException) as error:
            run_status(private_run.id, "santiago", db)
        assert error.value.status_code == 404
        assert history("santiago", db) == []
    engine.dispose()


def test_annual_program_cycles_are_not_merged_by_reused_url():
    from app.services.dedupe import same_job
    first = {"title": "Summer Research 2026", "company": "University", "apply_url": "https://example.edu/apply"}
    second = first | {"title": "Summer Research 2027"}
    assert not same_job(first, second)
