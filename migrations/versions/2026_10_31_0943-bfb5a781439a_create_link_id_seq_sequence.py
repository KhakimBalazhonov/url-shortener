"""create link_id_seq sequence

Revision ID: bfb5a781439a
Revises: 653ca8285ab6
Create Date: 2026-10-31 09:43:43.136637

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'bfb5a781439a'
down_revision: Union[str, Sequence[str], None] = '653ca8285ab6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	"""Создаёт последовательность числовых ID, которые затем кодируются Sqids в короткие ссылки"""
	op.execute("CREATE SEQUENCE link_id_seq START 1 CACHE 1000;")


def downgrade() -> None:
	op.execute("DROP SEQUENCE IF EXISTS link_id_seq;")
