"""add post_reaction manual

Revision ID: d8c3e5c2b7a9
Revises: bb2b9ae50ead
Create Date: 2026-03-02 19:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision = "d8c3e5c2b7a9"
down_revision = "bb2b9ae50ead"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("post_reaction",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("reaction_type", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["post.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "post_id")
    )

def downgrade():
    op.drop_table("post_reaction")
