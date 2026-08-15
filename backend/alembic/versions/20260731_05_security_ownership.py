"""add stable single-user ownership boundaries

Revision ID: 20260731_05
Revises: 20260731_04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_05"
down_revision = "20260731_04"
branch_labels = None
depends_on = None


OWNED_TABLES = (
    "user_profiles",
    "jobs",
    "applications",
    "notifications",
    "company_sources",
    "target_companies",
    "target_search_runs",
    "search_runs",
)


def upgrade() -> None:
    for table_name in OWNED_TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "owner_user_id",
                sa.String(160),
                nullable=False,
                server_default="primary-user",
            ),
        )
        op.create_index(
            f"ix_{table_name}_owner_user_id",
            table_name,
            ["owner_user_id"],
        )

def downgrade() -> None:
    for table_name in reversed(OWNED_TABLES):
        op.drop_index(f"ix_{table_name}_owner_user_id", table_name=table_name)
        op.drop_column(table_name, "owner_user_id")
