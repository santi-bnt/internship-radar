"""add editable target companies and search runs

Revision ID: 20260730_03
Revises: 20260728_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_03"
down_revision = "20260728_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "target_companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_name", sa.String(180), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("careers_domains", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(80), nullable=False, server_default="Other"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("custom", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preferred_locations", sa.JSON(), nullable=False),
        sa.Column("preferred_role_categories", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_result_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_jobs_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_target_companies_company_name", "target_companies", ["company_name"], unique=True)
    op.create_index("ix_target_companies_category", "target_companies", ["category"])
    op.create_index("ix_target_companies_priority", "target_companies", ["priority"])
    op.create_index("ix_target_companies_enabled", "target_companies", ["enabled"])

    op.create_table(
        "target_search_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("companies_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_expired", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("trigger", sa.String(30), nullable=False, server_default="manual"),
    )

    job_columns = [
        sa.Column("discovered_from", sa.String(100), nullable=False, server_default=""),
        sa.Column("official_domain", sa.String(255), nullable=False, server_default=""),
        sa.Column("alternate_sources", sa.JSON(), nullable=False),
        sa.Column("is_target_company", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("target_company_category", sa.String(80), nullable=False, server_default=""),
        sa.Column("company_priority", sa.String(20), nullable=False, server_default=""),
        sa.Column("company_priority_bonus", sa.Float(), nullable=False, server_default="0"),
    ]
    for column in job_columns:
        op.add_column("jobs", column)
    op.create_index("ix_jobs_is_target_company", "jobs", ["is_target_company"])
    op.create_index("ix_jobs_target_company_category", "jobs", ["target_company_category"])
    op.create_index("ix_jobs_company_priority", "jobs", ["company_priority"])


def downgrade() -> None:
    op.drop_index("ix_jobs_company_priority", table_name="jobs")
    op.drop_index("ix_jobs_target_company_category", table_name="jobs")
    op.drop_index("ix_jobs_is_target_company", table_name="jobs")
    for name in [
        "company_priority_bonus",
        "company_priority",
        "target_company_category",
        "is_target_company",
        "alternate_sources",
        "official_domain",
        "discovered_from",
    ]:
        op.drop_column("jobs", name)
    op.drop_table("target_search_runs")
    op.drop_index("ix_target_companies_enabled", table_name="target_companies")
    op.drop_index("ix_target_companies_priority", table_name="target_companies")
    op.drop_index("ix_target_companies_category", table_name="target_companies")
    op.drop_index("ix_target_companies_company_name", table_name="target_companies")
    op.drop_table("target_companies")
