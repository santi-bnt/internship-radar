"""Add candidate-scoped Force Apply Now overrides.

Revision ID: 20260925_29
Revises: 20260925_28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from app.core.config import settings
from app.services.force_apply import apply_requested_santiago_overrides


revision = "20260925_29"
down_revision = "20260925_28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_job_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=160), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("force_apply_now", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_user_id", "job_id", name="uq_candidate_job_override_owner_job"),
    )
    op.create_index(
        "ix_candidate_job_overrides_owner_user_id",
        "candidate_job_overrides",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_candidate_job_overrides_job_id",
        "candidate_job_overrides",
        ["job_id"],
    )
    op.create_index(
        "ix_candidate_job_overrides_force_apply_now",
        "candidate_job_overrides",
        ["force_apply_now"],
    )

    # Enable only the explicitly requested, already-discovered active records.
    # The service identifies a posting by official ID first and never creates a
    # job or revives an expired/closed application.
    session = Session(bind=op.get_bind())
    try:
        apply_requested_santiago_overrides(
            session,
            settings.effective_primary_user_id,
            commit=False,
        )
    finally:
        session.close()


def downgrade() -> None:
    op.drop_index("ix_candidate_job_overrides_force_apply_now", table_name="candidate_job_overrides")
    op.drop_index("ix_candidate_job_overrides_job_id", table_name="candidate_job_overrides")
    op.drop_index("ix_candidate_job_overrides_owner_user_id", table_name="candidate_job_overrides")
    op.drop_table("candidate_job_overrides")
