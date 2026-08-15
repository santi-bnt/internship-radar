"""persist verified job-specific resume skills

Revision ID: 20260808_06
Revises: 20260731_05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_06"
down_revision = "20260731_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_resumes",
        sa.Column(
            "selected_skills", sa.JSON(), nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "generated_resumes",
        sa.Column(
            "skill_categories", sa.JSON(), nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "generated_resumes",
        sa.Column(
            "job_skill_matches", sa.JSON(), nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "generated_resumes",
        sa.Column(
            "skill_verification", sa.JSON(), nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("generated_resumes", "skill_verification")
    op.drop_column("generated_resumes", "job_skill_matches")
    op.drop_column("generated_resumes", "skill_categories")
    op.drop_column("generated_resumes", "selected_skills")
