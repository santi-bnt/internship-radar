"""add deterministic special program eligibility

Revision ID: 20260813_10
Revises: 20260812_09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260813_10"
down_revision = "20260812_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    profile_columns = (
        sa.Column("veteran_status", sa.String(30), nullable=False, server_default="NOT_VETERAN"),
        sa.Column("military_status", sa.String(40), nullable=False, server_default="NONE"),
        sa.Column("military_spouse", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("disability_status", sa.String(40), nullable=False, server_default="NO_DISABILITY"),
        sa.Column("current_service_member", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    for column in profile_columns:
        op.add_column("user_profiles", column)

    job_columns = (
        sa.Column("special_program_type", sa.String(50), nullable=False, server_default="NONE"),
        sa.Column("special_program_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("special_program_evidence", sa.Text(), nullable=False, server_default=""),
    )
    for column in job_columns:
        op.add_column("jobs", column)
    op.create_index("ix_jobs_special_program_type", "jobs", ["special_program_type"])
    op.create_index("ix_jobs_special_program_required", "jobs", ["special_program_required"])

    op.add_column(
        "job_analyses",
        sa.Column(
            "special_program_eligibility_status",
            sa.String(30),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "job_analyses",
        sa.Column(
            "special_program_eligibility_reason",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("job_analyses", "special_program_eligibility_reason")
    op.drop_column("job_analyses", "special_program_eligibility_status")

    op.drop_index("ix_jobs_special_program_required", table_name="jobs")
    op.drop_index("ix_jobs_special_program_type", table_name="jobs")
    for column in (
        "special_program_evidence",
        "special_program_required",
        "special_program_type",
    ):
        op.drop_column("jobs", column)

    for column in (
        "current_service_member",
        "disability_status",
        "military_spouse",
        "military_status",
        "veteran_status",
    ):
        op.drop_column("user_profiles", column)
