"""add multi-portal assistant registry and diagnostics

Revision ID: 20260823_13
Revises: 20260823_12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_13"
down_revision = "20260823_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_portal_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.String(80), nullable=False),
        sa.Column("company_name", sa.String(180), nullable=False),
        sa.Column("known_domains_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("portal_type", sa.String(40), nullable=False),
        sa.Column("application_adapter", sa.String(120), nullable=False),
        sa.Column("company_specific_rules_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("resume_behavior", sa.String(80), nullable=False, server_default="JOB_SPECIFIC"),
        sa.Column("skills_behavior", sa.String(80), nullable=False, server_default="JOB_SPECIFIC_INDIVIDUAL"),
        sa.Column("known_question_aliases_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("support_status", sa.String(30), nullable=False, server_default="BETA"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_company_portal_registry_company_id", "company_portal_registry", ["company_id"], unique=True)
    op.create_index("ix_company_portal_registry_company_name", "company_portal_registry", ["company_name"])
    op.create_index("ix_company_portal_registry_portal_type", "company_portal_registry", ["portal_type"])
    op.create_index("ix_company_portal_registry_support_status", "company_portal_registry", ["support_status"])

    op.add_column(
        "application_sessions",
        sa.Column("portal_detection_evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "application_sessions",
        sa.Column("adapter_diagnostics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "application_sessions",
        sa.Column("adapter_version", sa.String(40), nullable=False, server_default=""),
    )
    op.add_column(
        "application_sessions",
        sa.Column("company_policy_key", sa.String(80), nullable=False, server_default="GENERIC"),
    )
    op.add_column(
        "application_sessions",
        sa.Column("assessment_type", sa.String(60), nullable=False, server_default=""),
    )


def downgrade() -> None:
    for column in (
        "assessment_type",
        "company_policy_key",
        "adapter_version",
        "adapter_diagnostics_json",
        "portal_detection_evidence_json",
    ):
        op.drop_column("application_sessions", column)
    op.drop_table("company_portal_registry")
