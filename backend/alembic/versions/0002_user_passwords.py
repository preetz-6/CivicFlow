"""username + password login

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: 0001 builds from the current models, so a fresh database already has the column.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(160)")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")
