"""translation columns on unified_postings, and llm_cache

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NEW_COLUMNS = [
    sa.Column("en_title", sa.String(512)),
    sa.Column("en_job_type", sa.String(256)),
    sa.Column("en_description", sa.Text),
    sa.Column("translation_model", sa.String(128)),
    sa.Column("translated_at", sa.DateTime),
    sa.Column("translation_cost_usd", sa.Float),
    sa.Column("translation_latency_ms", sa.Integer),
]


def upgrade() -> None:
    with op.batch_alter_table("unified_postings") as batch:
        for col in NEW_COLUMNS:
            batch.add_column(col)

    op.create_table(
        "llm_cache",
        sa.Column("cache_key", sa.CHAR(64), primary_key=True),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("response", sa.Text, nullable=False),
        sa.Column("prompt_tokens", sa.Integer),
        sa.Column("completion_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Float),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("llm_cache")
    with op.batch_alter_table("unified_postings") as batch:
        for col in reversed(NEW_COLUMNS):
            batch.drop_column(col.name)
