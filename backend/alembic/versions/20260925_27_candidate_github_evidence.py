"""Add candidate-owned GitHub evidence records.

Revision ID: 20260925_27
Revises: 20260924_26
"""
from alembic import op
import sqlalchemy as sa


revision = "20260925_27"
down_revision = "20260924_26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resume_profiles",
        sa.Column("github_evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("resume_profiles", "github_evidence_json", server_default=None)


def downgrade() -> None:
    op.drop_column("resume_profiles", "github_evidence_json")
