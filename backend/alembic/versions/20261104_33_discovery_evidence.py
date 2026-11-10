"""Add source observations and description history without replacing Jobs."""
from hashlib import sha256
from alembic import op
import sqlalchemy as sa

revision = "20261104_33"
down_revision = "20261101_32"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "opportunity_source_observations" not in tables:
        op.create_table("opportunity_source_observations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("owner_user_id", sa.String(160), nullable=False),
            sa.Column("observation_key", sa.String(64), nullable=False),
            sa.Column("source", sa.String(180), nullable=False), sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("external_id", sa.String(255), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("job_id", "observation_key", name="uq_job_observation"))
        op.create_index("ix_opportunity_source_observations_job_id", "opportunity_source_observations", ["job_id"])
        op.create_index("ix_opportunity_source_observations_owner_user_id", "opportunity_source_observations", ["owner_user_id"])
    if "opportunity_discovery_state" not in tables:
        op.create_table("opportunity_discovery_state",
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("owner_user_id", sa.String(160), nullable=False),
            sa.Column("availability", sa.String(20), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("facts", sa.JSON(), nullable=True), sa.Column("duplicate_confidence", sa.Float(), nullable=True),
            sa.Column("duplicate_candidate_id", sa.Integer(), nullable=True))
        op.create_index("ix_opportunity_discovery_state_owner_user_id", "opportunity_discovery_state", ["owner_user_id"])
    if "job_description_snapshots" not in tables:
        op.create_table("job_description_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("owner_user_id", sa.String(160), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("description", sa.Text(), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False), sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("job_id", "content_hash", name="uq_job_description_snapshot"))
        op.create_index("ix_job_description_snapshots_job_id", "job_description_snapshots", ["job_id"])
        op.create_index("ix_job_description_snapshots_owner_user_id", "job_description_snapshots", ["owner_user_id"])
    # Backfill only known historical provenance; never manufacture eligibility.
    if bind.dialect.name == "sqlite":
        for table in ("opportunity_source_observations", "opportunity_discovery_state", "job_description_snapshots"):
            bind.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS cascade_{table} AFTER DELETE ON jobs BEGIN DELETE FROM {table} WHERE job_id = OLD.id; END")
    meta = sa.MetaData()
    jobs = sa.Table("jobs", meta, autoload_with=bind)
    observations = sa.Table("opportunity_source_observations", meta, autoload_with=bind)
    snapshots = sa.Table("job_description_snapshots", meta, autoload_with=bind)
    for row in bind.execute(sa.select(jobs)).mappings():
        source, url = row["source_name"] or "Unknown", row["source_url"] or ""
        key = sha256(f"{source}:{url}".encode()).hexdigest()
        if not bind.execute(sa.select(observations.c.id).where(observations.c.job_id == row["id"], observations.c.observation_key == key)).first():
            bind.execute(observations.insert().values(job_id=row["id"], owner_user_id=row["owner_user_id"], observation_key=key, source=source, source_url=url, external_id=row["external_id"], first_seen_at=row["first_seen_at"], last_seen_at=row["last_seen_at"]))
        description = row["description"] or ""
        digest = sha256(description.encode()).hexdigest()
        if description and not bind.execute(sa.select(snapshots.c.id).where(snapshots.c.job_id == row["id"], snapshots.c.content_hash == digest)).first():
            bind.execute(snapshots.insert().values(job_id=row["id"], owner_user_id=row["owner_user_id"], content_hash=digest, description=description, source_url=url, recorded_at=row["last_checked_at"]))


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        for table in ("opportunity_source_observations", "opportunity_discovery_state", "job_description_snapshots"):
            op.execute(f"DROP TRIGGER IF EXISTS cascade_{table}")
    op.drop_table("job_description_snapshots")
    op.drop_table("opportunity_discovery_state")
    op.drop_table("opportunity_source_observations")
