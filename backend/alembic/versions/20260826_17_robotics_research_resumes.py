"""add robotics research opportunity and resume target context

Revision ID: 20260826_17
Revises: 20260824_16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260826_17"
down_revision = "20260824_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("opportunity_type", sa.String(40), nullable=False, server_default="job"))
    op.add_column("jobs", sa.Column("lab", sa.String(240), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("supervisor", sa.String(240), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("research_areas", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("jobs", sa.Column("research_url", sa.Text(), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("research_notes", sa.Text(), nullable=False, server_default=""))
    op.create_index("ix_jobs_opportunity_type", "jobs", ["opportunity_type"])
    op.add_column("generated_resumes", sa.Column("resume_target", sa.String(80), nullable=False, server_default="recommended"))


def downgrade() -> None:
    op.drop_column("generated_resumes", "resume_target")
    op.drop_index("ix_jobs_opportunity_type", table_name="jobs")
    for column in ("research_notes", "research_url", "research_areas", "supervisor", "lab", "opportunity_type"):
        op.drop_column("jobs", column)
