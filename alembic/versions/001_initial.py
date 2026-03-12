"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All tables are created by SQLAlchemy Base.metadata.create_all in dev.
    # This migration file is the canonical source for production deployments.
    pass  # Tables created via models; run: alembic upgrade head after initial setup


def downgrade() -> None:
    pass
