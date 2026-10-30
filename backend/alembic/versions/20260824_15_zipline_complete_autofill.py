"""add Zipline autofill preferences and job-specific portfolios

Revision ID: 20260824_15
Revises: 20260824_14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_15"
down_revision = "20260824_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_profiles",
        sa.Column("job_discovery_source", sa.String(60), nullable=False, server_default="GOOGLE_SEARCH"),
    )
    op.add_column(
        "application_profiles",
        sa.Column("full_time_summer_availability", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "application_profiles",
        sa.Column("spring_summer_combined_availability", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "application_profiles",
        sa.Column("application_preferences_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE application_profiles SET application_preferences_confirmed_at = CURRENT_TIMESTAMP "
        "WHERE application_preferences_confirmed_at IS NULL"
    )

    op.create_table(
        "generated_portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(320), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="ready"),
        sa.Column("filename", sa.String(320), nullable=False, server_default="Project_Portfolio.pdf"),
        sa.Column("target_role", sa.String(300), nullable=False, server_default=""),
        sa.Column("selected_projects_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("latex_source", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", "version", name="uq_generated_portfolio_version"),
    )
    for column in ("user_id", "job_id", "status", "content_hash"):
        op.create_index(f"ix_generated_portfolios_{column}", "generated_portfolios", [column])

    op.add_column("application_sessions", sa.Column("resume_filename", sa.String(320), nullable=False, server_default=""))
    op.add_column("application_sessions", sa.Column("resume_download_url", sa.Text(), nullable=False, server_default=""))
    op.add_column("application_sessions", sa.Column("portfolio_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_app_sessions_portfolio_version",
        "application_sessions",
        "generated_portfolios",
        ["portfolio_version_id"],
        ["id"],
    )
    op.create_index("ix_application_sessions_portfolio_version_id", "application_sessions", ["portfolio_version_id"])
    op.add_column("application_sessions", sa.Column("portfolio_filename", sa.String(320), nullable=False, server_default=""))
    op.add_column("application_sessions", sa.Column("portfolio_download_url", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    for column in ("portfolio_download_url", "portfolio_filename"):
        op.drop_column("application_sessions", column)
    op.drop_index("ix_application_sessions_portfolio_version_id", table_name="application_sessions")
    op.drop_constraint(
        "fk_app_sessions_portfolio_version",
        "application_sessions",
        type_="foreignkey",
    )
    for column in ("portfolio_version_id", "resume_download_url", "resume_filename"):
        op.drop_column("application_sessions", column)
    op.drop_table("generated_portfolios")
    for column in (
        "application_preferences_confirmed_at",
        "spring_summer_combined_availability",
        "full_time_summer_availability",
        "job_discovery_source",
    ):
        op.drop_column("application_profiles", column)
