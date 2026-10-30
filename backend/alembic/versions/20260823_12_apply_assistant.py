"""add Workday apply assistant sessions and verified application profile

Revision ID: 20260823_12
Revises: 20260819_11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_12"
down_revision = "20260819_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False, server_default=""),
        sa.Column("professional_email", sa.String(320), nullable=False, server_default=""),
        sa.Column("phone", sa.String(80), nullable=False, server_default=""),
        sa.Column("address_line1", sa.String(240), nullable=False, server_default=""),
        sa.Column("address_line2", sa.String(240), nullable=False, server_default=""),
        sa.Column("city", sa.String(140), nullable=False, server_default=""),
        sa.Column("state", sa.String(140), nullable=False, server_default=""),
        sa.Column("postal_code", sa.String(40), nullable=False, server_default=""),
        sa.Column("country", sa.String(100), nullable=False, server_default="Mexico"),
        sa.Column("university", sa.String(240), nullable=False, server_default=""),
        sa.Column("degree", sa.String(240), nullable=False, server_default=""),
        sa.Column("field_of_study", sa.String(240), nullable=False, server_default=""),
        sa.Column("gpa", sa.Float(), nullable=True),
        sa.Column("gpa_scale", sa.Float(), nullable=True),
        sa.Column("education_start_date", sa.Date(), nullable=True),
        sa.Column("expected_graduation_date", sa.Date(), nullable=True),
        sa.Column("languages_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("linkedin_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("github_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("skills_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("projects_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("work_experience_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("academic_project_workaround_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_application_profiles_owner_user_id", "application_profiles", ["owner_user_id"], unique=True)

    op.create_table(
        "application_answer_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("question_key", sa.String(100), nullable=False),
        sa.Column("normalized_question", sa.Text(), nullable=False, server_default=""),
        sa.Column("answer_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("answer_type", sa.String(40), nullable=False, server_default="text"),
        sa.Column("sensitivity", sa.String(30), nullable=False, server_default="CONFIRM_REQUIRED"),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(80), nullable=False, server_default="user_confirmation"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "question_key", name="uq_application_answer_registry_owner_question"),
    )
    for column in ("owner_user_id", "question_key", "sensitivity"):
        op.create_index(f"ix_application_answer_registry_{column}", "application_answer_registry", [column])

    op.create_table(
        "application_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("company", sa.String(180), nullable=False, server_default=""),
        sa.Column("portal_type", sa.String(40), nullable=False, server_default="WORKDAY"),
        sa.Column("application_url", sa.Text(), nullable=False),
        sa.Column("resume_version_id", sa.Integer(), sa.ForeignKey("generated_resumes.id"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="CREATED"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_step", sa.String(120), nullable=False, server_default="Readiness"),
        sa.Column("portal_job_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("confirmed_fields_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("pending_questions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("application_answers_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("profile_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("job_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("project_experience_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("consistency_issues_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("fields_filled_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fields_reviewed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fields_confirmed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_extension_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_page_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("token_nonce", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("safe_error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("owner_user_id", "job_id", "portal_type", "resume_version_id", "status", "portal_job_id", "token_nonce"):
        op.create_index(f"ix_application_sessions_{column}", "application_sessions", [column])

    op.add_column("applications", sa.Column("application_session_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_applications_application_session_id_application_sessions",
        "applications",
        "application_sessions",
        ["application_session_id"],
        ["id"],
    )
    op.create_index("ix_applications_application_session_id", "applications", ["application_session_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_application_session_id", table_name="applications")
    op.drop_constraint("fk_applications_application_session_id_application_sessions", "applications", type_="foreignkey")
    op.drop_column("applications", "application_session_id")
    op.drop_table("application_sessions")
    op.drop_table("application_answer_registry")
    op.drop_table("application_profiles")
