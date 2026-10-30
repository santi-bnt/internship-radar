"""add criteria-driven search runs and result membership

Revision ID: 20260819_11
Revises: 20260813_10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260819_11"
down_revision = "20260813_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_runs",
        sa.Column("criteria_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "search_runs",
        sa.Column("progress_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "search_runs",
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "search_runs",
        sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "search_runs",
        sa.Column("verified_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "search_runs",
        sa.Column("history_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_search_runs_history_deleted_at",
        "search_runs",
        ["history_deleted_at"],
    )

    op.create_table(
        "search_run_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column(
            "search_run_id",
            sa.Integer(),
            sa.ForeignKey("search_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("discovered_during_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("matched_criteria", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("technical_score_snapshot", sa.Float(), nullable=False, server_default="0"),
        sa.Column("eligibility_snapshot", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("search_run_id", "job_id", name="uq_search_run_jobs_run_job"),
    )
    for column in ("owner_user_id", "search_run_id", "job_id", "rank", "eligibility_snapshot"):
        op.create_index(f"ix_search_run_jobs_{column}", "search_run_jobs", [column])


def downgrade() -> None:
    op.drop_table("search_run_jobs")
    op.drop_index("ix_search_runs_history_deleted_at", table_name="search_runs")
    for column in (
        "history_deleted_at",
        "verified_count",
        "eligible_count",
        "result_count",
        "progress_json",
        "criteria_json",
    ):
        op.drop_column("search_runs", column)
