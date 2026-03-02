from alembic import op
import sqlalchemy as sa

revision = 'c0c85dbbfbfc'
down_revision = 'd8c3e5c2b7a9'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('menu', sa.Column('board_id', sa.Integer(), sa.ForeignKey('board_config.id'), nullable=True))
    op.add_column('menu', sa.Column('page_id', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('menu', 'page_id')
    op.drop_column('menu', 'board_id')
