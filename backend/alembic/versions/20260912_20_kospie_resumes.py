"""Add owner-scoped KOSPIE resume preferences.

Revision ID: 20260912_20
Revises: 20260908_19
"""
from alembic import op
import sqlalchemy as sa


revision = "20260912_20"
down_revision = "20260908_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kospie_profiles",
        sa.Column("owner_user_id", sa.String(320), primary_key=True),
        sa.Column("program_name", sa.String(180), nullable=False, server_default="KOSPIE 2027-2028"),
        sa.Column("organization", sa.String(240), nullable=False, server_default="DAAD + Tecnológico de Monterrey"),
        sa.Column("program_type", sa.String(120), nullable=False, server_default="International Academic + Professional Program"),
        sa.Column("selected_universities_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("primary_interests_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("kospie_profiles")
