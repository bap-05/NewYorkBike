"""Rename physical business tables/columns; preserve legacy workers through simple views."""
import json
import re
from pathlib import Path

from alembic import op, context
from sqlalchemy import inspect

revision='0007_vietnamese_names'
down_revision='0006_prediction'
branch_labels=None
depends_on=None
PLAN=json.loads((Path(__file__).resolve().parents[1]/'schema_0007.json').read_text(encoding='utf-8'))


def quoted(name):
    return '`'+name.replace('`','``')+'`'


def translated(expression,mapping):
    return re.sub(r"'(?:''|[^'])*'|\b[a-z_][a-z_0-9]*\b",
        lambda m:m[0] if m[0].startswith("'") else mapping.get(m[0],m[0]),expression)


def upgrade():
    bind=op.get_bind()
    dialect=bind.dialect.name
    offline=op.get_context().as_sql
    for old,definition in PLAN.items():
        new=definition['name']
        tables=set(inspect(bind).get_table_names()) if not offline else {old}
        if old in tables and new in tables:
            raise ValueError('Both physical naming versions exist: '+old)
        if old in tables:
            op.rename_table(old,new)
        elif new not in tables:
            raise ValueError('Missing business table: '+old)
        columns={c['name'] for c in inspect(bind).get_columns(new)} if not offline else set(definition['columns'])
        renames=[]
        for logical,physical in definition['columns'].items():
            if logical in columns and physical not in columns:
                renames.append((logical,physical))
            elif physical not in columns:
                raise ValueError('Missing column in '+new+': '+logical)
        if dialect=='mysql':
            checks={c['name']:c['sqltext'] for c in inspect(bind).get_check_constraints(new)} if not offline else definition['checks']
            restore=checks or definition['checks']
            if renames:
                if checks:
                    op.execute('ALTER TABLE '+quoted(new)+' '+', '.join('DROP CHECK '+quoted(name) for name in checks))
                op.execute('ALTER TABLE '+quoted(new)+' '+', '.join('RENAME COLUMN '+quoted(a)+' TO '+quoted(b) for a,b in renames)+', ALGORITHM=INPLACE')
                missing=restore
            else:
                missing={name:sql for name,sql in definition['checks'].items() if name not in checks}
            if missing:
                op.execute('ALTER TABLE '+quoted(new)+' '+', '.join('ADD CONSTRAINT '+quoted(name)+' CHECK ('+
                    translated(sql,definition['columns'])+')' for name,sql in missing.items()))
        else:
            for a,b in renames:
                op.execute('ALTER TABLE '+quoted(new)+' RENAME COLUMN '+quoted(a)+' TO '+quoted(b))
        select=', '.join(quoted(physical)+' AS '+quoted(logical) for logical,physical in definition['columns'].items())
        if dialect=='mysql':
            op.execute('CREATE OR REPLACE ALGORITHM=MERGE SQL SECURITY INVOKER VIEW '+quoted(old)+' AS SELECT '+select+' FROM '+quoted(new))
        else:
            op.execute('DROP VIEW IF EXISTS '+quoted(old))
            op.execute('CREATE VIEW '+quoted(old)+' AS SELECT '+select+' FROM '+quoted(new))


def downgrade():
    # Names can be rolled back with the same tested translation, preserving constraints and rows.
    for old in reversed(PLAN):
        op.execute('DROP VIEW IF EXISTS '+quoted(old))
    for old,definition in reversed(list(PLAN.items())):
        bind=op.get_bind()
        if bind.dialect.name=='mysql':
            checks=inspect(bind).get_check_constraints(definition['name'])
            if checks:
                op.execute('ALTER TABLE '+quoted(definition['name'])+' '+', '.join('DROP CHECK '+quoted(c['name']) for c in checks))
            op.execute('ALTER TABLE '+quoted(definition['name'])+' '+', '.join(
                'RENAME COLUMN '+quoted(physical)+' TO '+quoted(logical) for logical,physical in definition['columns'].items())+', ALGORITHM=INPLACE')
            if definition['checks']:
                op.execute('ALTER TABLE '+quoted(definition['name'])+' '+', '.join('ADD CONSTRAINT '+quoted(name)+
                    ' CHECK ('+sql+')' for name,sql in definition['checks'].items()))
            op.rename_table(definition['name'],old)
            continue
        for logical,physical in reversed(list(definition['columns'].items())):
            op.execute('ALTER TABLE '+quoted(definition['name'])+' RENAME COLUMN '+quoted(physical)+' TO '+quoted(logical))
        op.rename_table(definition['name'],old)
