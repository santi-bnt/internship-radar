"""add deterministic degree completion eligibility

Revision ID: 20260812_09
Revises: 20260812_08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_09"
down_revision = "20260812_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    profile_columns = (
        sa.Column("degree_level_current", sa.String(30), nullable=False, server_default="BACHELORS"),
        sa.Column("degree_status", sa.String(40), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("expected_graduation_date", sa.Date(), nullable=True),
        sa.Column(
            "degree_field",
            sa.String(240),
            nullable=False,
            server_default="Robotics and Digital Systems Engineering",
        ),
    )
    for column in profile_columns:
        op.add_column("user_profiles", column)
    op.execute(
        "UPDATE user_profiles SET expected_graduation_date = graduation_date "
        "WHERE expected_graduation_date IS NULL"
    )

    job_columns = (
        sa.Column("minimum_degree_level", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("accepted_degree_levels", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("degree_completion_required", sa.String(40), nullable=False, server_default="UNKNOWN"),
        sa.Column("currently_enrolled_allowed", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("graduation_before_start_required", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("accepted_degree_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("student_status_required", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("required_graduation_start", sa.Date(), nullable=True),
        sa.Column("required_graduation_end", sa.Date(), nullable=True),
        sa.Column("degree_requirement_evidence", sa.Text(), nullable=False, server_default=""),
    )
    for column in job_columns:
        op.add_column("jobs", column)
    op.create_index("ix_jobs_minimum_degree_level", "jobs", ["minimum_degree_level"])
    op.create_index(
        "ix_jobs_degree_completion_required", "jobs", ["degree_completion_required"]
    )

    analysis_columns = (
        sa.Column("degree_level_match", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("degree_field_match", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("degree_completion_match", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("graduation_window_match", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("student_status_match", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("education_eligibility_status", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("education_eligibility_reason", sa.Text(), nullable=False, server_default=""),
    )
    for column in analysis_columns:
        op.add_column("job_analyses", column)


def downgrade() -> None:
    for column in (
        "education_eligibility_reason",
        "education_eligibility_status",
        "student_status_match",
        "graduation_window_match",
        "degree_completion_match",
        "degree_field_match",
        "degree_level_match",
    ):
        op.drop_column("job_analyses", column)

    op.drop_index("ix_jobs_degree_completion_required", table_name="jobs")
    op.drop_index("ix_jobs_minimum_degree_level", table_name="jobs")
    for column in (
        "degree_requirement_evidence",
        "required_graduation_end",
        "required_graduation_start",
        "student_status_required",
        "accepted_degree_fields",
        "graduation_before_start_required",
        "currently_enrolled_allowed",
        "degree_completion_required",
        "accepted_degree_levels",
        "minimum_degree_level",
    ):
        op.drop_column("jobs", column)

    for column in (
        "degree_field",
        "expected_graduation_date",
        "degree_status",
        "degree_level_current",
    ):
        op.drop_column("user_profiles", column)
