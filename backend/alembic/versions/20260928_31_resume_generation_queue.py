"""Persist generated PDFs and queue metadata for resume generations.

Revision ID: 20260928_31
Revises: 20260927_30
"""
from alembic import op
import sqlalchemy as sa


revision = "20260928_31"
down_revision = "20260927_30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generated_resumes", sa.Column("compiled_pdf", sa.LargeBinary(), nullable=True))
    op.add_column("generated_resumes", sa.Column("compiled_pdf_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("generated_resumes", sa.Column("source_input_hash", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("generated_resumes", sa.Column("active_generation_owner", sa.String(length=320), nullable=True))
    op.create_index("ix_generated_resumes_source_input_hash", "generated_resumes", ["source_input_hash"])
    op.create_unique_constraint("uq_generated_resume_active_generation_owner", "generated_resumes", ["active_generation_owner"])


def downgrade() -> None:
    op.drop_constraint("uq_generated_resume_active_generation_owner", "generated_resumes", type_="unique")
    op.drop_index("ix_generated_resumes_source_input_hash", table_name="generated_resumes")
    op.drop_column("generated_resumes", "active_generation_owner")
    op.drop_column("generated_resumes", "source_input_hash")
    op.drop_column("generated_resumes", "compiled_pdf_at")
    op.drop_column("generated_resumes", "compiled_pdf")
