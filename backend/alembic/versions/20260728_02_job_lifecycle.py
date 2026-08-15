"""add non-destructive job lifecycle

Revision ID: 20260728_02
Revises: 20260727_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_02"
down_revision = "20260727_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("status", sa.String(length=30), nullable=False, server_default="active"))
    op.add_column("jobs", sa.Column("application_deadline", sa.Date(), nullable=True))
    op.add_column("jobs", sa.Column("deadline_source", sa.String(length=100), nullable=True))
    op.add_column("jobs", sa.Column("deadline_confidence", sa.Float(), nullable=True))
    op.add_column("jobs", sa.Column("submitted_resume_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_submitted_resume_id",
        "jobs",
        "generated_resumes",
        ["submitted_resume_id"],
        ["id"],
    )
    op.add_column("jobs", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_application_deadline", "jobs", ["application_deadline"])
    op.create_index("ix_jobs_submitted_resume_id", "jobs", ["submitted_resume_id"])
    op.add_column("applications", sa.Column("submitted_resume_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_applications_submitted_resume_id",
        "applications",
        "generated_resumes",
        ["submitted_resume_id"],
        ["id"],
    )
    op.create_index("ix_applications_submitted_resume_id", "applications", ["submitted_resume_id"])

    op.execute(
        """
        UPDATE jobs
        SET application_deadline = CAST(expires_at AS DATE)
        WHERE expires_at IS NOT NULL AND application_deadline IS NULL
        """
    )
    op.execute(
        """
        UPDATE jobs
        SET deadline_source = 'structured_source', deadline_confidence = 1.0
        WHERE application_deadline IS NOT NULL AND deadline_confidence IS NULL
        """
    )
    op.execute(
        """
        UPDATE jobs
        SET status = 'applied',
            applied_at = (
                SELECT MAX(applications.applied_at)
                FROM applications
                WHERE applications.job_id = jobs.id
                  AND LOWER(applications.status) = 'applied'
            )
        WHERE EXISTS (
            SELECT 1 FROM applications
            WHERE applications.job_id = jobs.id
              AND LOWER(applications.status) = 'applied'
        )
        """
    )
    op.execute(
        """
        UPDATE jobs
        SET status = 'expired'
        WHERE status = 'active' AND LOWER(official_status) = 'expired'
        """
    )
    op.execute(
        """
        UPDATE jobs
        SET status = 'archived', archived_at = CURRENT_TIMESTAMP
        WHERE status = 'active'
          AND (is_active = FALSE OR LOWER(official_status) IN ('closed', 'unavailable'))
        """
    )


def downgrade() -> None:
    op.drop_index("ix_applications_submitted_resume_id", table_name="applications")
    op.drop_constraint("fk_applications_submitted_resume_id", "applications", type_="foreignkey")
    op.drop_column("applications", "submitted_resume_id")
    op.drop_index("ix_jobs_submitted_resume_id", table_name="jobs")
    op.drop_constraint("fk_jobs_submitted_resume_id", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_application_deadline", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_column("jobs", "updated_at")
    op.drop_column("jobs", "archived_at")
    op.drop_column("jobs", "expired_at")
    op.drop_column("jobs", "applied_at")
    op.drop_column("jobs", "application_deadline")
    op.drop_column("jobs", "submitted_resume_id")
    op.drop_column("jobs", "deadline_confidence")
    op.drop_column("jobs", "deadline_source")
    op.drop_column("jobs", "status")
