"""Remove no longer needed tables

Revision ID: 2bcaa8f08591
Revises: 078ed2e8c974
Create Date: 2023-11-12 08:34:43.826380

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '2bcaa8f08591'
down_revision: Union[str, None] = '078ed2e8c974'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('api_context_task')
    op.drop_table('comment_query')
    op.drop_table('context_summary_query')
    op.drop_table('api_task')
    op.drop_table('api_comment_task')
    op.drop_table('log_records')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('log_records',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('task_id', sa.INTEGER(), nullable=True),
    sa.Column('time', sa.DATETIME(), nullable=True),
    sa.Column('type', sa.VARCHAR(length=64), nullable=True),
    sa.Column('subtask', sa.VARCHAR(length=64), nullable=True),
    sa.Column('prompt', sa.TEXT(), nullable=True),
    sa.Column('token', sa.TEXT(), nullable=True),
    sa.ForeignKeyConstraint(['task_id'], ['api_task.task_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('api_comment_task',
    sa.Column('comment_id', sa.INTEGER(), nullable=False),
    sa.Column('task_id', sa.INTEGER(), nullable=False),
    sa.ForeignKeyConstraint(['comment_id'], ['comment_query.query_id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['api_task.task_id'], ),
    sa.PrimaryKeyConstraint('comment_id', 'task_id', name='pk_cid_tid'),
    sa.UniqueConstraint('task_id', name='unique_tid')
    )
    op.create_table('api_task',
    sa.Column('task_id', sa.INTEGER(), nullable=False),
    sa.Column('status', sa.INTEGER(), nullable=True),
    sa.Column('response', sa.TEXT(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.Column('updated_at', sa.DATETIME(), nullable=True),
    sa.PrimaryKeyConstraint('task_id')
    )
    op.create_table('context_summary_query',
    sa.Column('query_id', sa.INTEGER(), nullable=False),
    sa.Column('text', sa.TEXT(), nullable=True),
    sa.Column('time', sa.DATETIME(), nullable=True),
    sa.Column('user_name', sa.TEXT(), nullable=True),
    sa.Column('user_character', sa.TEXT(), nullable=True),
    sa.Column('user_goals', sa.TEXT(), nullable=True),
    sa.Column('post_time', sa.DATETIME(), nullable=True),
    sa.PrimaryKeyConstraint('query_id')
    )
    op.create_table('comment_query',
    sa.Column('query_id', sa.INTEGER(), nullable=False),
    sa.Column('time', sa.DATETIME(), nullable=True),
    sa.Column('context', sa.TEXT(), nullable=True),
    sa.Column('history', sqlite.JSON(), nullable=True),
    sa.Column('user_name', sa.TEXT(), nullable=True),
    sa.Column('user_character', sa.TEXT(), nullable=True),
    sa.Column('user_goals', sa.TEXT(), nullable=True),
    sa.Column('user_style_example', sa.TEXT(), nullable=True),
    sa.Column('user_style_description', sa.TEXT(), nullable=True),
    sa.PrimaryKeyConstraint('query_id')
    )
    op.create_table('api_context_task',
    sa.Column('context_id', sa.INTEGER(), nullable=False),
    sa.Column('task_id', sa.INTEGER(), nullable=False),
    sa.ForeignKeyConstraint(['context_id'], ['context_summary_query.query_id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['api_task.task_id'], ),
    sa.PrimaryKeyConstraint('context_id', 'task_id', name='pk_cid_tid'),
    sa.UniqueConstraint('task_id', name='unique_tid')
    )
    # ### end Alembic commands ###
