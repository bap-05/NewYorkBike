"""Test MySQL rename/FK/check/view upsert behavior using only uniquely named scratch tables."""
import json
from uuid import uuid4

from sqlalchemy import inspect,text
from shared.config import Settings
from shared.database import make_engine


def main():
    prefix='codex_vn_'+uuid4().hex[:12]
    p,c=prefix+'_p',prefix+'_c'
    engine=make_engine(Settings.load(outbound=False))
    created=[]
    try:
        with engine.connect() as conn:
            try:
                version=conn.scalar(text('SELECT VERSION()'))
                check=prefix+'_status'
                conn.exec_driver_sql(f'CREATE TABLE `{p}` (id INTEGER PRIMARY KEY AUTO_INCREMENT, source VARCHAR(32) UNIQUE NOT NULL, status VARCHAR(16) NOT NULL, CONSTRAINT `{check}` CHECK (status IN (\'success\',\'partial\'))) ENGINE=InnoDB')
                created.append(('TABLE',p))
                conn.exec_driver_sql(f'CREATE TABLE `{c}` (id INTEGER PRIMARY KEY AUTO_INCREMENT, parent_id INTEGER NOT NULL, FOREIGN KEY(parent_id) REFERENCES `{p}`(id)) ENGINE=InnoDB')
                created.append(('TABLE',c))
                conn.exec_driver_sql(f'INSERT INTO `{p}` (source,status) VALUES (\'test-only\',\'success\')')
                conn.exec_driver_sql(f'INSERT INTO `{c}` (parent_id) VALUES (1)')
                conn.commit()
                conn.exec_driver_sql(f'RENAME TABLE `{p}` TO `{p}_vn`, `{c}` TO `{c}_vn`')
                created[:]=[('TABLE',p+'_vn'),('TABLE',c+'_vn')]
                conn.exec_driver_sql(f'ALTER TABLE `{p}_vn` DROP CHECK `{check}`')
                conn.exec_driver_sql(f'ALTER TABLE `{p}_vn` RENAME COLUMN id TO ma, RENAME COLUMN source TO nguon, RENAME COLUMN status TO trang_thai, ALGORITHM=INPLACE')
                conn.exec_driver_sql(f'ALTER TABLE `{p}_vn` ADD CONSTRAINT `{check}` CHECK (trang_thai IN (\'success\',\'partial\'))')
                conn.exec_driver_sql(f'ALTER TABLE `{c}_vn` RENAME COLUMN id TO ma, RENAME COLUMN parent_id TO ma_cha')
                conn.exec_driver_sql(f'CREATE ALGORITHM=MERGE SQL SECURITY INVOKER VIEW `{p}` AS SELECT ma AS id, nguon AS source, trang_thai AS status FROM `{p}_vn`')
                created.append(('VIEW',p))
                conn.exec_driver_sql(f'CREATE ALGORITHM=MERGE SQL SECURITY INVOKER VIEW `{c}` AS SELECT ma AS id, ma_cha AS parent_id FROM `{c}_vn`')
                created.append(('VIEW',c))
                conn.exec_driver_sql(f'INSERT INTO `{p}` (source,status) VALUES (\'test-only\',\'partial\') ON DUPLICATE KEY UPDATE status=VALUES(status)')
                assert conn.scalar(text(f'SELECT status FROM `{p}`'))=='partial'
                conn.exec_driver_sql(f'INSERT INTO `{p}` (source,status) VALUES (\'second-test\',\'success\')')
                new_id=conn.scalar(text('SELECT LAST_INSERT_ID()'))
                conn.exec_driver_sql(f'INSERT INTO `{c}` (parent_id) VALUES ({int(new_id)})')
                conn.commit()
                inspector=inspect(conn)
                assert {col['name'] for col in inspector.get_columns(p)}=={'id','source','status'}
                fks=inspector.get_foreign_keys(c+'_vn')
                assert fks[0]['referred_columns']==['ma']
                print(json.dumps({'mysql_version':version,'foreign_keys_renamed':True,'checks_renamed':True,'legacy_view_upsert':True,'legacy_view_auto_increment':True,'legacy_view_child_insert':True}))
            finally:
                conn.rollback()
                for kind,name in reversed(created):
                    conn.exec_driver_sql(f'DROP {kind} `{name}`')
                conn.commit()
    finally:
        engine.dispose()


if __name__=='__main__':
    main()
