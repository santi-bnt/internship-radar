"""Add a workspace-only candidate display name.

Revision ID: 20260925_28
Revises: 20260925_27
"""
from alembic import op
import sqlalchemy as sa


revision = "20260925_28"
down_revision = "20260925_27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("display_name", sa.String(length=80), nullable=False, server_default=""),
    )
    op.alter_column("user_profiles", "display_name", server_default=None)


def downgrade() -> None:
    op.drop_column("user_profiles", "display_name")
