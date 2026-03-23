"""Initial migration

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE taskstatus AS ENUM ('pending', 'processing', 'completed', 'failed')")
    op.execute("CREATE TYPE risklevel AS ENUM ('high', 'medium', 'low')")

    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'processing', 'completed', 'failed', name='taskstatus', create_type=False), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('supplier_name', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=512), nullable=False),
        sa.Column('stored_path', sa.String(length=512), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_documents_task_id', 'documents', ['task_id'])

    op.create_table(
        'reports',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('similarity_matrix', sa.Text(), nullable=True),
        sa.Column('risk_items', sa.Text(), nullable=True),
        sa.Column('overall_risk', postgresql.ENUM('high', 'medium', 'low', name='risklevel', create_type=False), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id')
    )
    op.create_index('idx_reports_task_id', 'reports', ['task_id'])


def downgrade() -> None:
    op.drop_index('idx_reports_task_id', table_name='reports')
    op.drop_table('reports')
    op.drop_index('idx_documents_task_id', table_name='documents')
    op.drop_table('documents')
    op.drop_table('tasks')
    op.execute("DROP TYPE taskstatus")
    op.execute("DROP TYPE risklevel")
