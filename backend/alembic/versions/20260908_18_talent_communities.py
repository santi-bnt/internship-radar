"""Company talent profiles and job-independent resumes/applications."""
from alembic import op
import sqlalchemy as sa

revision = "20260908_18"
down_revision = "20260827_18"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_talent_profiles",
        sa.Column("company_id", sa.String(80), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), primary_key=True),
        sa.Column("company_name", sa.String(180), nullable=False),
        *[sa.Column(n, sa.Text(), nullable=False, server_default="") for n in ("company_summary", "source_url", "talent_community_url", "talent_community_description")],
        *[sa.Column(n, sa.JSON(), nullable=False, server_default=sa.text("'[]'")) for n in ("technical_areas", "common_role_categories", "preferred_project_categories", "preferred_skill_categories")],
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    for table in ("generated_resumes", "application_sessions", "applications"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column("job_id", existing_type=sa.Integer(), nullable=True)
            batch.add_column(sa.Column("application_type", sa.String(40), nullable=False, server_default="STANDARD_JOB"))
            batch.add_column(sa.Column("company_id", sa.String(80), nullable=True))
            if table != "application_sessions":
                batch.add_column(sa.Column("company", sa.String(180), nullable=False, server_default=""))
            batch.add_column(sa.Column("company_profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
            batch.add_column(sa.Column("talent_community_url", sa.Text(), nullable=False, server_default=""))
            batch.add_column(sa.Column("target_role_categories", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.create_index("ix_generated_resumes_company_id", "generated_resumes", ["company_id"])
    op.create_index("uq_company_resume_version", "generated_resumes", ["user_id", "company_id", "version"], unique=True)


def downgrade():
    # A downgrade cannot represent jobless applications; refuse data loss.
    raise RuntimeError("Export Talent Community records before downgrading this migration.")
