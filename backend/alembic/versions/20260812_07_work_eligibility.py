"""add hard work-authorization and remote eligibility signals

Revision ID: 20260812_07
Revises: 20260808_06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_07"
down_revision = "20260808_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("citizenship_country", sa.String(100), nullable=False, server_default="Mexico"))
    op.add_column("user_profiles", sa.Column("work_authorized_countries", sa.JSON(), nullable=False, server_default=sa.text("'[\"Mexico\"]'")))
    op.add_column("user_profiles", sa.Column("us_work_authorized", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_profiles", sa.Column("requires_us_employment_sponsorship", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.add_column("jobs", sa.Column("remote_scope", sa.String(40), nullable=False, server_default="UNKNOWN"))
    op.add_column("jobs", sa.Column("physical_work_country_required", sa.String(100), nullable=False, server_default="Unknown"))
    op.add_column("jobs", sa.Column("can_work_from_mexico", sa.String(20), nullable=False, server_default="UNKNOWN"))
    op.add_column("jobs", sa.Column("job_requires_work_in_us", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("jobs", sa.Column("sponsorship_status", sa.String(30), nullable=False, server_default="UNKNOWN"))
    op.add_column("jobs", sa.Column("sponsorship_evidence_text", sa.Text(), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("sponsorship_source_url", sa.Text(), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("sponsorship_last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_jobs_remote_scope", "jobs", ["remote_scope"])
    op.create_index("ix_jobs_can_work_from_mexico", "jobs", ["can_work_from_mexico"])
    op.create_index("ix_jobs_job_requires_work_in_us", "jobs", ["job_requires_work_in_us"])
    op.create_index("ix_jobs_sponsorship_status", "jobs", ["sponsorship_status"])

    op.add_column("job_analyses", sa.Column("effective_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("job_analyses", sa.Column("remote_eligibility_bonus", sa.Float(), nullable=False, server_default="0"))
    op.execute("UPDATE job_analyses SET effective_score = overall_score")
    op.create_index("ix_job_analyses_effective_score", "job_analyses", ["effective_score"])


def downgrade() -> None:
    op.drop_index("ix_job_analyses_effective_score", table_name="job_analyses")
    op.drop_column("job_analyses", "remote_eligibility_bonus")
    op.drop_column("job_analyses", "effective_score")
    op.drop_index("ix_jobs_sponsorship_status", table_name="jobs")
    op.drop_index("ix_jobs_job_requires_work_in_us", table_name="jobs")
    op.drop_index("ix_jobs_can_work_from_mexico", table_name="jobs")
    op.drop_index("ix_jobs_remote_scope", table_name="jobs")
    for column in (
        "sponsorship_last_verified_at", "sponsorship_source_url",
        "sponsorship_evidence_text", "sponsorship_status",
        "job_requires_work_in_us", "can_work_from_mexico",
        "physical_work_country_required", "remote_scope",
    ):
        op.drop_column("jobs", column)
    for column in (
        "requires_us_employment_sponsorship", "us_work_authorized",
        "work_authorized_countries", "citizenship_country",
    ):
        op.drop_column("user_profiles", column)
