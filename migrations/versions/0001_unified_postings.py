"""create unified_postings

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unified_postings",
        sa.Column("uid", sa.CHAR(16), primary_key=True),
        sa.Column("portal", sa.String(64), nullable=False),
        sa.Column("source_id", sa.Integer, nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("location", sa.String(256)),
        sa.Column("posted", sa.DateTime),
        sa.Column("scraped", sa.DateTime),
        sa.Column("company", sa.String(256)),
        sa.Column("description", sa.Text),
        sa.Column("job_type", sa.String(64)),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("portal", "source_id", name="uq_portal_source"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_unified_posted", "unified_postings", ["posted"])


def downgrade() -> None:
    op.drop_index("ix_unified_posted", table_name="unified_postings")
    op.drop_table("unified_postings")
