"""plaque workflow: one plaque per order with its status and every version

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-19 03:00:00

New tables only (plaques, plaque_versions) plus media_assets.sacrifice_id. Plaques saved
before this keep their files and timeline events; they are listed here as versions:
- a well whose plaque was approved becomes "approved_for_contractor" (it then shows in the
  approved plaques section until someone records that it was sent to the contractor);
- other saved plaques become "ready_for_review".
No order gets an automatic draft from this migration: drafts start with new orders.
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

STATES = ('draft', 'ready_for_review', 'awaiting_customer', 'needs_changes', 'customer_approved',
          'approved_for_contractor', 'sent_to_contractor')


def upgrade():
    op.add_column('media_assets', sa.Column('sacrifice_id', sa.Integer(), sa.ForeignKey('sacrifices.id'), nullable=True))
    op.create_index('ix_media_assets_sacrifice_id', 'media_assets', ['sacrifice_id'])
    op.create_table(
        'plaques',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True, unique=True),
        sa.Column('sacrifice_id', sa.Integer(), sa.ForeignKey('sacrifices.id'), nullable=True, unique=True),
        sa.Column('status', sa.Enum(*STATES, name='plaque_status', native_enum=False, length=40), nullable=False),
        sa.Column('missing', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('honoree_gender', sa.String(10)), sa.Column('honoree_state', sa.String(10)),
        sa.Column('anonymous', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('dua_kind', sa.String(20)),
        sa.Column('current_version_id', sa.Integer()), sa.Column('approved_version_id', sa.Integer()),
        sa.Column('sent_to_customer_at', sa.DateTime(timezone=True)),
        sa.Column('customer_decision_at', sa.DateTime(timezone=True)),
        sa.Column('customer_decision_by', sa.String(200)), sa.Column('customer_note', sa.Text()),
        sa.Column('contractor_id', sa.Integer(), sa.ForeignKey('contractors.id')),
        sa.Column('contractor_country', sa.String(80)),
        sa.Column('sent_to_contractor_on', sa.Date()), sa.Column('sent_to_contractor_by', sa.String(200)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(project_id is null) <> (sacrifice_id is null)", name='ck_plaques_one_order'),
    )
    op.create_index('ix_plaques_status', 'plaques', ['status'])
    op.create_index('ix_plaques_updated_at', 'plaques', ['updated_at'])
    op.create_table(
        'plaque_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plaque_id', sa.Integer(), sa.ForeignKey('plaques.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('design', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('media_id', sa.Integer(), sa.ForeignKey('media_assets.id')),
        sa.Column('drive_file_id', sa.String(200)), sa.Column('filename', sa.String(300)),
        sa.Column('source', sa.String(20), nullable=False, server_default='dashboard'),
        sa.Column('event_id', sa.String(40)),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('actor_label', sa.String(200)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('plaque_id', 'version', name='uq_plaque_versions_no'),
    )
    op.create_index('ix_plaque_versions_plaque_id', 'plaque_versions', ['plaque_id'])
    op.create_foreign_key('fk_plaques_current_version', 'plaques', 'plaque_versions', ['current_version_id'], ['id'])
    op.create_foreign_key('fk_plaques_approved_version', 'plaques', 'plaque_versions', ['approved_version_id'], ['id'])
    _carry_over(op.get_bind())


def _carry_over(conn):
    t = sa.text
    # wells: versions are the plaque_saved timeline events
    projects = conn.execute(t("select distinct p.id, p.plaque_status, p.plaque_media_id from projects p "
                              "join project_events e on e.project_id = p.id and e.event_type = 'plaque_saved'")).all()
    for pid, pstatus, approved_media in projects:
        evs = conn.execute(t("select id, payload, actor_user_id, actor_label, created_at from project_events "
                             "where project_id = :p and event_type = 'plaque_saved' order by created_at"), {"p": pid}).all()
        status = 'approved_for_contractor' if pstatus == 'approved' else 'ready_for_review'
        first, last = evs[0], evs[-1]
        plaque_id = conn.execute(t("insert into plaques (kind, project_id, status, missing, anonymous, dua_kind, created_at, updated_at) "
                                   "values ('well', :p, :s, '[]', false, :k, :c, :u) returning id"),
                                 {"p": pid, "s": status, "k": ((last.payload or {}).get('design') or {}).get('dua_kind'),
                                  "c": first.created_at, "u": last.created_at}).scalar()
        cur = appr = None
        for i, e in enumerate(evs, 1):
            pl = e.payload or {}
            vid = conn.execute(t("insert into plaque_versions (plaque_id, version, design, media_id, filename, source, event_id, "
                                 "created_by_id, actor_label, created_at) values (:pl, :v, cast(:d as jsonb), :m, :f, 'import', :ev, :by, :a, :c) returning id"),
                               {"pl": plaque_id, "v": i, "d": json.dumps(pl.get('design') or {}), "m": pl.get('media_id'),
                                "f": pl.get('filename'), "ev": str(e.id), "by": e.actor_user_id, "a": e.actor_label, "c": e.created_at}).scalar()
            cur = vid
            if approved_media and pl.get('media_id') == approved_media:
                appr = vid
        conn.execute(t("update plaques set current_version_id = :c, approved_version_id = :a where id = :id"),
                     {"c": cur, "a": appr, "id": plaque_id})
    # sacrifices: versions were kept in the audit log (file straight in Drive)
    nos = conn.execute(t("select distinct entity_id from audit_log where action = 'plaque.saved' and entity_type = 'sacrifice'")).scalars().all()
    for no in nos:
        sid = conn.execute(t("select id from sacrifices where sacrifice_no = :n"), {"n": int(no)}).scalar()
        if not sid:
            continue
        rows = conn.execute(t("select after, actor_user_id, actor_label, at from audit_log where action = 'plaque.saved' "
                              "and entity_type = 'sacrifice' and entity_id = :n order by at"), {"n": no}).all()
        plaque_id = conn.execute(t("insert into plaques (kind, sacrifice_id, status, missing, anonymous, created_at, updated_at) "
                                   "values ('sacrifice', :s, 'ready_for_review', '[]', false, :c, :u) returning id"),
                                 {"s": sid, "c": rows[0].at, "u": rows[-1].at}).scalar()
        cur = None
        for i, r in enumerate(rows, 1):
            a = r.after or {}
            cur = conn.execute(t("insert into plaque_versions (plaque_id, version, design, drive_file_id, filename, source, "
                                 "created_by_id, actor_label, created_at) values (:pl, :v, cast(:d as jsonb), :df, :f, 'import', :by, :a, :c) returning id"),
                               {"pl": plaque_id, "v": i, "d": json.dumps(a.get('design') or {}), "df": a.get('drive_file_id'),
                                "f": a.get('filename'), "by": r.actor_user_id, "a": r.actor_label, "c": r.at}).scalar()
        conn.execute(t("update plaques set current_version_id = :c where id = :id"), {"c": cur, "id": plaque_id})


def downgrade():
    op.drop_constraint('fk_plaques_current_version', 'plaques', type_='foreignkey')
    op.drop_constraint('fk_plaques_approved_version', 'plaques', type_='foreignkey')
    op.drop_table('plaque_versions')
    op.drop_table('plaques')
    op.drop_index('ix_media_assets_sacrifice_id', 'media_assets')
    op.drop_column('media_assets', 'sacrifice_id')
