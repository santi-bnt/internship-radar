"""add production search run tracking

Revision ID: 20260731_04
Revises: 20260730_03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_04"
down_revision = "20260730_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress_status", sa.String(80), nullable=False, server_default="Starting"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("companies_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sources_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_expired", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("safe_error_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("trigger", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_runs_search_type", "search_runs", ["search_type"])
    op.create_index("ix_search_runs_status", "search_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_search_runs_status", table_name="search_runs")
    op.drop_index("ix_search_runs_search_type", table_name="search_runs")
    op.drop_table("search_runs")
