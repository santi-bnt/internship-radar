"""Keep an audit trail for reversible application statuses.

Revision ID: 20260924_26
Revises: 20260914_25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_26"
down_revision = "20260914_25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("status_history", sa.JSON(), nullable=True))
    applications = sa.table("applications", sa.column("status_history", sa.JSON()))
    op.execute(applications.update().values(status_history=[]))
    op.alter_column("applications", "status_history", nullable=False)


def downgrade() -> None:
    op.drop_column("applications", "status_history")
