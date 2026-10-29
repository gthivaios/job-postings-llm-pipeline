"""posted is free text on some portals: store it as text, index scraped instead

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_unified_posted", table_name="unified_postings")
    # batch mode: plain ALTER on MariaDB, table rebuild on SQLite (tests)
    with op.batch_alter_table("unified_postings") as batch:
        batch.alter_column("posted", type_=sa.String(128), existing_type=sa.DateTime)
    op.create_index("ix_unified_scraped", "unified_postings", ["scraped"])


def downgrade() -> None:
    op.drop_index("ix_unified_scraped", table_name="unified_postings")
    with op.batch_alter_table("unified_postings") as batch:
        batch.alter_column("posted", type_=sa.DateTime, existing_type=sa.String(128))
    op.create_index("ix_unified_posted", "unified_postings", ["posted"])
