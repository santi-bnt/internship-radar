"""Add verified resume profiles and generated resume versions."""

from alembic import op
import sqlalchemy as sa

revision = "20260727_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(320), nullable=False, unique=True),
        sa.Column("full_name", sa.String(160), nullable=False, server_default=""),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("phone", sa.String(80), nullable=False, server_default=""),
        sa.Column("location", sa.String(240), nullable=False, server_default=""),
        sa.Column("linkedin_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("github_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("headline", sa.String(300), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("education_json", sa.JSON(), nullable=False),
        sa.Column("skills_json", sa.JSON(), nullable=False),
        sa.Column("experience_json", sa.JSON(), nullable=False),
        sa.Column("projects_json", sa.JSON(), nullable=False),
        sa.Column("coursework_json", sa.JSON(), nullable=False),
        sa.Column("certifications_json", sa.JSON(), nullable=False),
        sa.Column("languages_json", sa.JSON(), nullable=False),
        sa.Column("forbidden_claims_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_resume_profiles_user_id", "resume_profiles", ["user_id"], unique=True)
    op.create_table(
        "generated_resumes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(320), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("target_role", sa.String(300), nullable=False),
        sa.Column("tailored_content_json", sa.JSON(), nullable=False),
        sa.Column("latex_source", sa.Text(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("keywords_json", sa.JSON(), nullable=False),
        sa.Column("changes_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("generation_model", sa.String(120), nullable=False),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", "version", name="uq_generated_resume_version"),
    )
    op.create_index("ix_generated_resumes_user_id", "generated_resumes", ["user_id"])
    op.create_index("ix_generated_resumes_job_id", "generated_resumes", ["job_id"])
    op.create_index("ix_generated_resumes_status", "generated_resumes", ["status"])


def downgrade() -> None:
    op.drop_table("generated_resumes")
    op.drop_table("resume_profiles")
