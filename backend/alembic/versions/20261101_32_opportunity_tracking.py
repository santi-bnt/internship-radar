"""Candidate-owned opportunity dashboard metadata, preserving existing jobs."""
from alembic import op
import sqlalchemy as sa

revision = "20261101_32"
down_revision = "20260928_31"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "opportunity_tracking",
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_opportunity_tracking_owner_user_id", "opportunity_tracking", ["owner_user_id"])


def downgrade():
    op.drop_index("ix_opportunity_tracking_owner_user_id", table_name="opportunity_tracking")
    op.drop_table("opportunity_tracking")
