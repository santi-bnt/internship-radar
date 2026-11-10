"""Additive discovery evidence; existing Job/Application identities are retained."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, DDL, event
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def now():
    return datetime.now(timezone.utc)


class OpportunitySourceObservation(Base):
    __tablename__ = "opportunity_source_observations"
    __table_args__ = (UniqueConstraint("job_id", "observation_key", name="uq_job_observation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    observation_key: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(180))
    source_url: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OpportunityDiscoveryState(Base):
    __tablename__ = "opportunity_discovery_state"
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    availability: Mapped[str | None] = mapped_column(String(20), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Historical rows have unknown facts, rather than invented backfill values.
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duplicate_confidence: Mapped[float | None] = mapped_column(nullable=True)
    duplicate_candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class JobDescriptionSnapshot(Base):
    __tablename__ = "job_description_snapshots"
    __table_args__ = (UniqueConstraint("job_id", "content_hash", name="uq_job_description_snapshot"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# Legacy SQLite connections do not enable FK enforcement globally. Preserve
# the new tables' declared cascade semantics without changing older tables'
# constraints or allowing stale metadata to attach to a reused Job ID.
for model in (OpportunitySourceObservation, OpportunityDiscoveryState, JobDescriptionSnapshot):
    table_name = model.__tablename__
    event.listen(model.__table__, "after_create", DDL(
        f"CREATE TRIGGER IF NOT EXISTS cascade_{table_name} AFTER DELETE ON jobs "
        f"BEGIN DELETE FROM {table_name} WHERE job_id = OLD.id; END"
    ).execute_if(dialect="sqlite"))
