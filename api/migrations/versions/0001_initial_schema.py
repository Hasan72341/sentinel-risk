"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("period", sa.String(), nullable=True),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=NOW),
        sa.Column("updated_at", sa.DateTime(), server_default=NOW),
    )
    op.create_table(
        "ratio_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("ratio_name", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("benchmark", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analysis_id", sa.String(), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=NOW),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
    )
    op.create_table(
        "sync_events",
        sa.Column("cursor", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("client_event_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload_ciphertext", sa.Text(), nullable=False),
        sa.Column("payload_digest", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=NOW, nullable=False),
        sa.UniqueConstraint(
            "organization_id", "client_event_id",
            name="uq_sync_events_organization_client_event",
        ),
    )
    op.create_index("ix_sync_events_organization_id", "sync_events", ["organization_id"])
    op.create_index("ix_sync_events_client_event_id", "sync_events", ["client_event_id"])
    op.create_table(
        "settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("ai_config", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=NOW),
    )
    op.create_table(
        "licenses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("license_key", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("machine_id", sa.String(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), server_default=NOW),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("licenses")
    op.drop_table("settings")
    op.drop_index("ix_sync_events_client_event_id", table_name="sync_events")
    op.drop_index("ix_sync_events_organization_id", table_name="sync_events")
    op.drop_table("sync_events")
    op.drop_table("reports")
    op.drop_table("ratio_results")
    op.drop_table("analyses")
