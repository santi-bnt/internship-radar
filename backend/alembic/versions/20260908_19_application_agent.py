"""Local-first semantic application agent state."""
from alembic import op
import sqlalchemy as sa


revision = "20260908_19"
down_revision = "20260908_18"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_user_settings",
        sa.Column("owner_user_id", sa.String(160), primary_key=True),
        sa.Column("ai_mode", sa.String(40), nullable=False, server_default="BALANCED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_approved_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("portal", sa.String(40), nullable=False, server_default="GENERIC"),
        sa.Column("canonical_field", sa.String(100), nullable=False),
        sa.Column("canonical_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("portal_option", sa.Text(), nullable=False, server_default=""),
        sa.Column("match_type", sa.String(40), nullable=False, server_default="UNKNOWN"),
        sa.Column("approved_by_user", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "portal", "canonical_field", "canonical_value", "portal_option", name="uq_user_approved_mapping"),
    )
    op.create_index("ix_user_approved_mappings_owner_user_id", "user_approved_mappings", ["owner_user_id"])
    op.create_index("ix_user_approved_mappings_portal", "user_approved_mappings", ["portal"])
    op.create_index("ix_user_approved_mappings_canonical_field", "user_approved_mappings", ["canonical_field"])
    op.create_table(
        "candidate_correction_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("scope", sa.String(40), nullable=False, server_default="APPLICATION_ONLY"),
        sa.Column("portal", sa.String(40), nullable=False, server_default=""),
        sa.Column("company", sa.String(180), nullable=False, server_default=""),
        sa.Column("canonical_field", sa.String(100), nullable=False),
        sa.Column("old_value_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("corrected_value_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("application_session_id", sa.Integer(), sa.ForeignKey("application_sessions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_candidate_correction_memory_owner_user_id", "candidate_correction_memory", ["owner_user_id"])
    op.create_index("ix_candidate_correction_memory_scope", "candidate_correction_memory", ["scope"])
    op.create_index("ix_candidate_correction_memory_canonical_field", "candidate_correction_memory", ["canonical_field"])
    op.create_index("ix_candidate_correction_memory_application_session_id", "candidate_correction_memory", ["application_session_id"])
    op.create_table(
        "ai_decision_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("application_session_id", sa.Integer(), sa.ForeignKey("application_sessions.id"), nullable=False),
        sa.Column("field", sa.String(100), nullable=False),
        sa.Column("question_normalized", sa.Text(), nullable=False, server_default=""),
        sa.Column("decision_type", sa.String(60), nullable=False, server_default="MANUAL"),
        sa.Column("provider", sa.String(80), nullable=False, server_default="DETERMINISTIC"),
        sa.Column("execution_location", sa.String(30), nullable=False, server_default="LOCAL"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("selected_value_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("reason_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("user_corrected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_decision_logs_owner_user_id", "ai_decision_logs", ["owner_user_id"])
    op.create_index("ix_ai_decision_logs_application_session_id", "ai_decision_logs", ["application_session_id"])
    op.create_index("ix_ai_decision_logs_field", "ai_decision_logs", ["field"])
    op.create_table(
        "external_ai_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("application_session_id", sa.Integer(), sa.ForeignKey("application_sessions.id"), nullable=True),
        sa.Column("provider", sa.String(80), nullable=False, server_default=""),
        sa.Column("purpose", sa.String(120), nullable=False, server_default=""),
        sa.Column("privacy_classification", sa.String(40), nullable=False, server_default="NORMAL"),
        sa.Column("fields_included_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("fields_redacted_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_external_ai_audits_owner_user_id", "external_ai_audits", ["owner_user_id"])
    op.create_index("ix_external_ai_audits_application_session_id", "external_ai_audits", ["application_session_id"])
    op.execute(sa.text(
        "UPDATE application_profiles SET city = 'Zapopan', state = 'Jalisco', country = 'Mexico' "
        "WHERE full_name = 'Alex Rivera'"
    ))
    op.execute(sa.text(
        "UPDATE resume_profiles SET location = 'Zapopan, Jalisco, Mexico' "
        "WHERE full_name = 'Alex Rivera'"
    ))


def downgrade():
    for table in ("external_ai_audits", "ai_decision_logs", "candidate_correction_memory", "user_approved_mappings", "ai_user_settings"):
        op.drop_table(table)
