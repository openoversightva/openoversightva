"""multiple_upstream_changes

Revision ID: c3d19b3ddbd2
Revises: 3bf4b2e7d54e
Create Date: 2023-10-09 18:03:36.180979

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

import uuid
from OpenOversight.app.models.database import User

revision = 'c3d19b3ddbd2'
down_revision = '3bf4b2e7d54e'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('start_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_index('ix_assignments_star_date')
        batch_op.create_index(batch_op.f('ix_assignments_start_date'), ['start_date'], unique=False)
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE assignments
            SET start_date = star_date
        """
    )

    with op.batch_alter_table('assignments', schema=None) as batch_op:
        batch_op.drop_column('star_date')


    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('state', sa.String(length=2), server_default='', nullable=False))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_index('ix_departments_name')
        batch_op.create_unique_constraint('departments_name_state', ['name', 'state'])
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('descriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_constraint('descriptions_creator_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE descriptions
            SET created_by = creator_id, created_at = date_created, last_updated_at = coalesce(date_updated,date_created)
        """
    )

    with op.batch_alter_table('descriptions', schema=None) as batch_op:
        batch_op.drop_column('date_created')
        batch_op.drop_column('creator_id')
        batch_op.drop_column('date_updated')

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_index('ix_documents_date_inserted')
        batch_op.drop_constraint('documents_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE documents
            SET created_by = user_id, created_at = date_inserted, last_updated_at = date_inserted
        """
    )

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_column('date_inserted')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('faces', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_constraint('faces_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE faces
            SET created_by = user_id
        """
    )

    with op.batch_alter_table('faces', schema=None) as batch_op:
        batch_op.drop_column('user_id')

    with op.batch_alter_table('incident_license_plates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    with op.batch_alter_table('incident_links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    with op.batch_alter_table('incident_officers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_constraint('incidents_creator_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('incidents_last_updated_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE incidents
            SET created_by = creator_id, last_updated_by = last_updated_id
        """
    )

    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_column('last_updated_id')
        batch_op.drop_column('creator_id')

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('license_plates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_constraint('links_creator_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE links
            SET created_by = creator_id
        """
    )

    with op.batch_alter_table('links', schema=None) as batch_op:
        batch_op.drop_column('creator_id')

    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_constraint('notes_creator_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE notes
            SET created_by = creator_id, created_at = date_created, last_updated_at = coalesce(date_updated, date_created)
        """
    )

    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.drop_column('date_created')
        batch_op.drop_column('creator_id')
        batch_op.drop_column('date_updated')

    with op.batch_alter_table('officer_incidents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    with op.batch_alter_table('officer_links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    with op.batch_alter_table('officers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_index('ix_posts_created')
        batch_op.drop_constraint('posts_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE posts
            SET created_by = user_id, created_at = created, last_updated_at = created
        """
    )

    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_column('user_id')
        batch_op.drop_column('created')

    with op.batch_alter_table('raw_images', schema=None) as batch_op:
        batch_op.add_column(sa.Column('taken_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_index('ix_raw_images_date_image_inserted')
        batch_op.drop_index('ix_raw_images_date_image_taken')
        batch_op.create_index(batch_op.f('ix_raw_images_taken_at'), ['taken_at'], unique=False)
        batch_op.drop_constraint('raw_images_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE raw_images
            SET created_by = user_id, created_at = coalesce(date_image_inserted, date '1970-01-01'), 
                last_updated_at = coalesce(date_image_inserted, date '1970-01-01'), 
                taken_at = date_image_taken
        """
    )

    with op.batch_alter_table('raw_images', schema=None) as batch_op:
        batch_op.drop_column('date_image_inserted')
        batch_op.drop_column('user_id')
        batch_op.drop_column('date_image_taken')

    with op.batch_alter_table('salaries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('unit_types', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('last_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by', sa.Integer(), nullable=True))
        batch_op.drop_index('ix_unit_types_descrip')
        batch_op.create_index(batch_op.f('ix_unit_types_description'), ['description'], unique=False)
        batch_op.create_foreign_key(None, 'users', ['last_updated_by'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(None, 'users', ['created_by'], ['id'], ondelete='SET NULL')

    op.execute(
        """
            UPDATE unit_types
            SET description = descrip
        """
    )

    with op.batch_alter_table('unit_types', schema=None) as batch_op:
        batch_op.drop_column('descrip')


    op.add_column("users", sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    # add UUID col to users
    op.add_column("users", sa.Column("_uuid",sa.String(36), ))
    bind = op.get_bind()
    session = Session(bind=bind)
    for user in session.query(User).all():
        user._uuid = str(uuid.uuid4())
        session.commit()
    op.create_index(op.f("ix_users__uuid"), "users", ["_uuid"], unique=True)
    op.alter_column("users", "_uuid", nullable=False)




    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users__uuid'))
        batch_op.drop_column('created_at')
        batch_op.drop_column('_uuid')

    with op.batch_alter_table('unit_types', schema=None) as batch_op:
        batch_op.add_column(sa.Column('descrip', sa.VARCHAR(length=120), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_unit_types_description'))
        batch_op.create_index('ix_unit_types_descrip', ['descrip'], unique=False)
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('description')

    with op.batch_alter_table('salaries', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('raw_images', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_image_taken', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('date_image_inserted', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('raw_images_user_id_fkey', 'users', ['user_id'], ['id'])
        batch_op.drop_index(batch_op.f('ix_raw_images_taken_at'))
        batch_op.create_index('ix_raw_images_date_image_taken', ['date_image_taken'], unique=False)
        batch_op.create_index('ix_raw_images_date_image_inserted', ['date_image_inserted'], unique=False)
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('taken_at')

    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('posts_user_id_fkey', 'users', ['user_id'], ['id'])
        batch_op.create_index('ix_posts_created', ['created'], unique=False)
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('officers', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('officer_links', schema=None) as batch_op:
        batch_op.drop_column('created_at')

    with op.batch_alter_table('officer_incidents', schema=None) as batch_op:
        batch_op.drop_column('created_at')

    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_updated', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('creator_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('date_created', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('notes_creator_id_fkey', 'users', ['creator_id'], ['id'], ondelete='SET NULL')
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('creator_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('links_creator_id_fkey', 'users', ['creator_id'], ['id'], ondelete='SET NULL')
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('license_plates', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('creator_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('last_updated_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('incidents_last_updated_id_fkey', 'users', ['last_updated_id'], ['id'])
        batch_op.create_foreign_key('incidents_creator_id_fkey', 'users', ['creator_id'], ['id'])
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('incident_officers', schema=None) as batch_op:
        batch_op.drop_column('created_at')

    with op.batch_alter_table('incident_links', schema=None) as batch_op:
        batch_op.drop_column('created_at')

    with op.batch_alter_table('incident_license_plates', schema=None) as batch_op:
        batch_op.drop_column('created_at')

    with op.batch_alter_table('faces', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('faces_user_id_fkey', 'users', ['user_id'], ['id'])
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('date_inserted', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('documents_user_id_fkey', 'users', ['user_id'], ['id'])
        batch_op.create_index('ix_documents_date_inserted', ['date_inserted'], unique=False)
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('descriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_updated', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('creator_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('date_created', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('descriptions_creator_id_fkey', 'users', ['creator_id'], ['id'], ondelete='SET NULL')
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint('departments_name_state', type_='unique')
        batch_op.create_index('ix_departments_name', ['name'], unique=False)
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('state')

    with op.batch_alter_table('assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('star_date', sa.DATE(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_assignments_start_date'))
        batch_op.create_index('ix_assignments_star_date', ['star_date'], unique=False)
        batch_op.drop_column('last_updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('last_updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('start_date')

    # ### end Alembic commands ###
