"""add community discovery registry, provenance, health, and metrics

Revision ID: 20260812_08
Revises: 20260812_07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_08"
down_revision = "20260812_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    job_columns = (
        sa.Column("discovered_from_source", sa.String(180), nullable=False, server_default=""),
        sa.Column("verified_from_source", sa.String(180), nullable=False, server_default=""),
        sa.Column("discovery_sources", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("source_confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("community_sponsorship_signal", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("community_markers", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("company_normalized", sa.String(180), nullable=False, server_default=""),
        sa.Column("title_normalized", sa.String(300), nullable=False, server_default=""),
        sa.Column("ats_requisition_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("canonical_official_url", sa.Text(), nullable=False, server_default=""),
    )
    for column in job_columns:
        op.add_column("jobs", column)
    for column in ("source_confidence_score", "community_sponsorship_signal", "company_normalized", "title_normalized", "ats_requisition_id"):
        op.create_index(f"ix_jobs_{column}", "jobs", [column])

    source_columns = (
        sa.Column("registry_type", sa.String(40), nullable=False, server_default="OTHER"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("base_priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("trust_level", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("refresh_frequency", sa.String(40), nullable=False, server_default="daily"),
        sa.Column("supports_structured_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_confidence_score", sa.Float(), nullable=False, server_default="50"),
        sa.Column("reference_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_successful_fetch", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_repository_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_parse", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_new_job_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parsed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_jobs_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_jobs_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("officially_verified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unverified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    for column in source_columns:
        op.add_column("company_sources", column)
    for column in ("registry_type", "priority", "trust_level", "source_status"):
        op.create_index(f"ix_company_sources_{column}", "company_sources", [column])
    op.add_column("search_runs", sa.Column("source_metrics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    op.drop_column("search_runs", "source_metrics")
    for column in ("source_status", "trust_level", "priority", "registry_type"):
        op.drop_index(f"ix_company_sources_{column}", table_name="company_sources")
    for column in (
        "duration_ms", "error_count", "unverified_count", "officially_verified_count",
        "duplicate_count", "updated_jobs_count", "new_jobs_count", "parsed_count",
        "fetched_count", "source_status", "last_new_job_seen", "last_successful_parse",
        "last_repository_update", "last_successful_fetch", "reference_only",
        "source_confidence_score", "notes", "supports_structured_data",
        "refresh_frequency", "trust_level", "base_priority", "priority", "registry_type",
    ):
        op.drop_column("company_sources", column)
    for column in ("ats_requisition_id", "title_normalized", "company_normalized", "community_sponsorship_signal", "source_confidence_score"):
        op.drop_index(f"ix_jobs_{column}", table_name="jobs")
    for column in (
        "canonical_official_url", "ats_requisition_id", "title_normalized",
        "company_normalized", "community_markers", "community_sponsorship_signal",
        "source_confidence_score", "discovery_sources", "verified_from_source",
        "discovered_from_source",
    ):
        op.drop_column("jobs", column)
