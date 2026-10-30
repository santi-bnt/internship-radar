"""add authorized accounts and multi-user profile metadata

Revision ID: 20260827_18
Revises: 20260826_17
"""
from alembic import op
import sqlalchemy as sa

revision = "20260827_18"
down_revision = "20260826_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authorized_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(160), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="google"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "email", name="uq_authorized_account_provider_email"),
    )
    op.create_index("ix_authorized_accounts_user_id", "authorized_accounts", ["user_id"])
    op.create_index("ix_authorized_accounts_email", "authorized_accounts", ["email"])
    op.create_index("ix_authorized_accounts_is_active", "authorized_accounts", ["is_active"])
    columns = (
        sa.Column("gpa_scale_status", sa.String(40), nullable=False, server_default="CONFIRMED"),
        sa.Column("current_semester", sa.Integer(), nullable=True),
        sa.Column("official_degree_name", sa.String(240), nullable=True),
        sa.Column("official_degree_name_status", sa.String(40), nullable=False, server_default="CONFIRMED"),
        sa.Column("citizenship_status", sa.String(40), nullable=False, server_default="CONFIRMED"),
        sa.Column("us_authorization_conflict_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("work_authorization_raw_statement", sa.Text(), nullable=False, server_default=""),
        sa.Column("minimum_hours_per_week", sa.Integer(), nullable=True),
        sa.Column("github_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("linkedin_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("onboarding_status", sa.String(40), nullable=False, server_default="PROFILE_READY"),
        sa.Column("profile_warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    for column in columns:
        op.add_column("user_profiles", column)
    op.alter_column("user_profiles", "gpa_scale", existing_type=sa.Float(), nullable=True)
    op.drop_index("ix_target_companies_company_name", table_name="target_companies")
    op.create_index("ix_target_companies_company_name", "target_companies", ["company_name"])
    op.create_unique_constraint(
        "uq_target_company_owner_name", "target_companies", ["owner_user_id", "company_name"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_target_company_owner_name", "target_companies", type_="unique")
    op.drop_index("ix_target_companies_company_name", table_name="target_companies")
    op.create_index(
        "ix_target_companies_company_name", "target_companies", ["company_name"], unique=True
    )
    op.alter_column("user_profiles", "gpa_scale", existing_type=sa.Float(), nullable=False)
    for name in (
        "profile_warnings", "onboarding_status", "linkedin_url", "github_url",
        "minimum_hours_per_week", "work_authorization_raw_statement",
        "us_authorization_conflict_detected", "citizenship_status",
        "official_degree_name_status", "official_degree_name", "current_semester",
        "gpa_scale_status",
    ):
        op.drop_column("user_profiles", name)
    op.drop_table("authorized_accounts")
