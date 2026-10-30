"""Add scheduling state for staggered discovery sources.

Revision ID: 20260927_30
Revises: 20260925_29
"""
from alembic import op
import sqlalchemy as sa


revision = "20260927_30"
down_revision = "20260925_29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_sources", sa.Column("discovery_group", sa.String(40), nullable=False, server_default="GENERAL"))
    op.add_column("company_sources", sa.Column("geography_scope", sa.String(30), nullable=False, server_default="US_CANADA"))
    op.add_column("company_sources", sa.Column("source_domain", sa.String(255), nullable=False, server_default=""))
    op.add_column("company_sources", sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("company_sources", sa.Column("backoff_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("company_sources", sa.Column("rate_limited_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("company_sources", sa.Column("retry_after_seconds", sa.Integer(), nullable=True))
    op.add_column("company_sources", sa.Column("discovery_checkpoint_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.create_index("ix_company_sources_discovery_group", "company_sources", ["discovery_group"])
    op.create_index("ix_company_sources_geography_scope", "company_sources", ["geography_scope"])
    op.create_index("ix_company_sources_source_domain", "company_sources", ["source_domain"])
    op.create_index("ix_company_sources_next_run_at", "company_sources", ["next_run_at"])
    op.create_index("ix_company_sources_backoff_until", "company_sources", ["backoff_until"])
    op.create_index("ix_company_sources_rate_limited_until", "company_sources", ["rate_limited_until"])


def downgrade() -> None:
    for index in (
        "ix_company_sources_rate_limited_until", "ix_company_sources_backoff_until",
        "ix_company_sources_next_run_at", "ix_company_sources_source_domain",
        "ix_company_sources_geography_scope", "ix_company_sources_discovery_group",
    ):
        op.drop_index(index, table_name="company_sources")
    for column in (
        "discovery_checkpoint_json", "retry_after_seconds", "rate_limited_until",
        "backoff_until", "next_run_at", "source_domain", "geography_scope", "discovery_group",
    ):
        op.drop_column("company_sources", column)
