"""add dept tags

Revision ID: 44f092df70a8
Revises: 764cfc5047ca
Create Date: 2024-12-11 00:11:49.522988

"""
from alembic import op
import sqlalchemy as sa



revision = '44f092df70a8'
down_revision = '764cfc5047ca'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('department_tags',
    sa.Column('department_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ),
    sa.PrimaryKeyConstraint('department_id', 'tag_id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('department_tags')
    # ### end Alembic commands ###
