"""store role-specific application experience and skill snapshots

Revision ID: 20260824_16
Revises: 20260824_15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_16"
down_revision = "20260824_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_sessions",
        sa.Column("selected_projects_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "application_sessions",
        sa.Column("generated_experience_text", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "application_sessions",
        sa.Column("selected_skills_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "application_sessions",
        sa.Column("skill_match_reasons_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "application_sessions",
        sa.Column("project_match_reasons_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "application_sessions",
        sa.Column("selection_warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.execute("UPDATE application_sessions SET selected_projects_json = project_experience_json")


def downgrade() -> None:
    for column in (
        "selection_warnings_json",
        "project_match_reasons_json",
        "skill_match_reasons_json",
        "selected_skills_json",
        "generated_experience_text",
        "selected_projects_json",
    ):
        op.drop_column("application_sessions", column)
