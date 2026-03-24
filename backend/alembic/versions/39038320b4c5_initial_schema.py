"""initial_schema

Revision ID: 39038320b4c5
Revises: 
Create Date: 2026-03-19 19:26:52.746271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '39038320b4c5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline anchor revision. Schema bootstrap is in follow-up Alembic
    # revision a8d9c6b2f1e4.
    pass


def downgrade() -> None:
    # Intentionally no-op for baseline revision.
    pass
