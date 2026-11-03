from contextlib import closing
"""Migration tests use authored temporary v1 databases, never user data."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from uuid import UUID, uuid4

from yadinassi.catalog_backend import BackendError, CatalogSchema, FieldSchema, CatalogKey
from yadinassi.sqlite_catalog import _APPLICATION_ID, _json, _schema_data, SQLiteCatalogBackend
from yadinassi.sqlite_catalog_layout import load_layout, decode_columns, quote_identifier
from yadinassi.sqlite_catalog_migration import _V1_DDL, prepare_v1, migrate_v1, resolve_migration
import yadinassi.sqlite_catalog_migration as migration


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'fixture.sqlite'
        self.database_id, self.config_id, self.a, self.b = [uuid4() for _ in range(4)]
        self.ra, self.rb, self.empty, self.op = uuid4(), uuid4(), uuid4(), uuid4()
        fields = (FieldSchema(uuid4(), 'Text', 'string', (32,)),
                  FieldSchema(uuid4(), 'Amount', 'number', (12, 2, 'Any')),
                  FieldSchema(uuid4(), 'Active', 'boolean'),
                  FieldSchema(uuid4(), 'Date', 'datetime', ('DateTime',)),
                  FieldSchema(uuid4(), 'Link', 'catalog_ref', (), self.b))
        self.sa = CatalogSchema(self.a, 'A', 8, 64, fields)
        self.sb = CatalogSchema(self.b, 'B', 8, 64, (FieldSchema(uuid4(), 'Link', 'catalog_ref', (), self.a),))
        self.va = [['s', 'текст'], ['n', '123.40'], ['b', True], ['d', '00010101000000'], ['r', str(self.b), str(self.rb)]]
        self.vb = [['r', str(self.a), str(self.ra)]]
        self.ve = [['r', str(self.a), str(UUID(int=0))]]
        self.receipt = (str(self.op), 'a'*64, _json([[str(self.a), str(self.ra), '7']]))
        with closing(sqlite3.connect(self.path)) as db, db:
            for ddl in _V1_DDL: db.execute(ddl)
            db.execute('PRAGMA application_id=%d' % _APPLICATION_ID)
            db.execute('PRAGMA user_version=1')
            db.execute('INSERT INTO database_info VALUES(1,?,3,?,?,1,?)', (str(self.database_id), str(self.config_id), 'Example', '[]'))
            content = b'<fixture/>'
            db.execute('INSERT INTO configuration_file VALUES(?,?,?,?)', ('Configuration.xml', 'xml', content, hashlib.sha256(content).hexdigest()))
            for s in (self.sa, self.sb):
                db.execute('INSERT INTO catalog_schema VALUES(?,?,?)', (str(s.identity), s.name, _json(_schema_data(s))))
            for cat, rid, revision, code, value in ((self.a,self.ra,7,'1',self.va), (self.b,self.rb,4,'2',self.vb), (self.b,self.empty,1,'3',self.ve)):
                db.execute('INSERT INTO catalog_record VALUES(?,?,?,?,?,?,?)', (str(cat), str(rid), revision, code, 'Описание', 0, _json(value)))
            db.execute('INSERT INTO commit_receipt VALUES(?,?,?)', self.receipt)
        self.plan = prepare_v1(self.path, maintenance=True)

    def tearDown(self): self.tmp.cleanup()

    def execute(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db, db: db.execute(sql, args)

    def assert_v1(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM catalog_record').fetchone()[0], 3)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='catalog_storage_map'").fetchone())
            self.assertEqual(db.execute('SELECT * FROM commit_receipt').fetchone(), self.receipt)

    def test_roundtrip_and_preserved_receipt(self):
        migrate_v1(self.path, self.plan, maintenance=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='catalog_record'").fetchone())
            layout = load_layout(db, (self.sa, self.sb))
            row = db.execute(f'SELECT * FROM {quote_identifier(layout.table_name(self.a))} WHERE record_id=?', (str(self.ra),)).fetchone()
            self.assertEqual(row[:5], (str(self.ra),7,'1','Описание',0))
            self.assertEqual(decode_columns(row[5:], self.sa), self.va)
            self.assertEqual(db.execute('SELECT * FROM commit_receipt').fetchone(), self.receipt)
            self.assertEqual(db.execute('SELECT database_uuid,generation FROM database_info').fetchone(), (str(self.database_id),3))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_backend_reopen_and_old_receipt_resolves_exact_intent(self):
        from yadinassi.catalog_backend import CatalogDraft, CatalogKey, Revision
        from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _decode
        values = tuple(_decode(v, f, self.database_id) for v, f in zip(self.va, self.sa.fields))
        draft = CatalogDraft(CatalogKey(self.database_id,self.a,self.ra), '1', 'Описание', False, values)
        expected = Revision(self.database_id,3,self.a,self.ra,'6')
        intent = [[str(self.a),str(self.ra),'1','Описание',False,_json(self.va),7]]
        digest = hashlib.sha256(_json(intent).encode('utf-8')).hexdigest()
        self.receipt = (str(self.op),digest,_json([[str(self.a),str(self.ra),'7']]))
        self.execute('UPDATE commit_receipt SET request_hash=?, revisions_json=? WHERE operation_id=?', self.receipt[1:] + (self.receipt[0],))
        self.plan = prepare_v1(self.path, maintenance=True)
        old = SQLiteCatalogBackend(self.path)
        self.assertEqual(old.storage_version, 1)
        old.close()
        migrate_v1(self.path, self.plan, maintenance=True)
        backend = SQLiteCatalogBackend(self.path)
        try:
            self.assertEqual(backend.resolve_write(self.op,draft,expected).token,'7')
            view = backend.begin_read(); card = view.read_catalog(draft.key); view.close()
            self.assertEqual(card.values,values)
            self.assertEqual(card.revision.token,'7')
            tx = backend.begin_write(uuid4()); tx.update(draft, card.revision)
            self.assertEqual(tx.commit()[0].token,'8')
        finally: backend.close()

    def test_stale_new_backend_rejects_migrated_file(self):
        from yadinassi.sqlite_catalog import SQLiteCatalogBackend
        idle = SQLiteCatalogBackend(self.path)
        try:
            migrate_v1(self.path, self.plan, maintenance=True)
            with self.assertRaisesRegex(BackendError, 'schema_changed'): idle.begin_read()
        finally: idle.close()

    def test_non_ascii_v1_json_remains_readable_after_migration(self):
        from yadinassi.catalog_backend import CatalogKey
        from yadinassi.sqlite_catalog import SQLiteCatalogBackend
        fields = tuple(FieldSchema(uuid4(), 'Text%d' % i, 'string', (65536,)) for i in range(4))
        schema = CatalogSchema(self.a, 'A', 8, 64, fields)
        text = '猫' * 50000
        encoded = [['s', text] for _ in fields]
        raw = json.dumps(encoded, ensure_ascii=False, separators=(',', ':'))
        self.execute('UPDATE catalog_schema SET definition=? WHERE identity=?', (_json(_schema_data(schema)),str(self.a)))
        self.execute('UPDATE catalog_record SET values_json=? WHERE catalog_id=?', (raw,str(self.a)))
        self.plan = prepare_v1(self.path, maintenance=True)
        migrate_v1(self.path, self.plan, maintenance=True)
        backend = SQLiteCatalogBackend(self.path)
        try:
            view = backend.begin_read()
            try: self.assertEqual(view.read_catalog(CatalogKey(self.database_id,self.a,self.ra)).values,(text,)*4)
            finally: view.close()
        finally: backend.close()

    def test_cycles_and_empty_reference(self):
        migrate_v1(self.path, self.plan, maintenance=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            layout = load_layout(db, (self.sa, self.sb))
            f = quote_identifier(layout.field_name(self.b, self.sb.fields[0].identity))
            table = quote_identifier(layout.table_name(self.b))
            self.assertEqual(db.execute(f'SELECT {f} FROM {table} WHERE record_id=?',(str(self.rb),)).fetchone()[0],str(self.ra))
            self.assertIsNone(db.execute(f'SELECT {f} FROM {table} WHERE record_id=?',(str(self.empty),)).fetchone()[0])
            sql = db.execute("SELECT sql FROM sqlite_master WHERE name=?",(layout.table_name(self.b),)).fetchone()[0]
            self.assertIn('DEFERRABLE INITIALLY DEFERRED', sql)

    def test_maintenance_required(self):
        with self.assertRaisesRegex(BackendError, 'invalid_input'): migrate_v1(self.path, self.plan)
        self.assert_v1()

    def test_utf16_v1_is_rejected_without_modification(self):
        path = Path(self.tmp.name) / 'utf16.sqlite'
        tables = ('database_info', 'configuration_file', 'catalog_schema', 'catalog_record', 'commit_receipt')
        with closing(sqlite3.connect(self.path)) as source, source, closing(sqlite3.connect(path)) as db, db:
            db.execute("PRAGMA encoding='UTF-16le'")
            for ddl in _V1_DDL: db.execute(ddl)
            db.execute('PRAGMA application_id=%d' % _APPLICATION_ID)
            db.execute('PRAGMA user_version=1')
            for table in tables:
                for row in source.execute(f'SELECT * FROM {table}'):
                    db.execute(f'INSERT INTO {table} VALUES(' + ','.join('?' for _ in row) + ')', row)
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            prepare_v1(path, maintenance=True)
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            migrate_v1(path, self.plan, maintenance=True)
        with closing(sqlite3.connect(path)) as db, db:
            self.assertEqual(db.execute('PRAGMA encoding').fetchone()[0], 'UTF-16le')
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM catalog_record').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT * FROM commit_receipt').fetchone(), self.receipt)

    def test_unknown_version_rejected(self):
        self.execute('PRAGMA user_version=3')
        with self.assertRaisesRegex(BackendError, 'unsupported'): migrate_v1(self.path, self.plan, maintenance=True)
        with closing(sqlite3.connect(self.path)) as db, db: self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)

    def test_unknown_schema_rejected(self):
        self.execute('CREATE TABLE unexpected(value TEXT)')
        with self.assertRaisesRegex(BackendError, 'unsupported'): migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()

    def test_v1_explicit_index_works_in_backend_but_migration_rejects_it(self):
        self.execute('CREATE INDEX user_index ON catalog_record(code)')
        backend = SQLiteCatalogBackend(self.path)
        try:
            view = backend.begin_read()
            try:
                card = view.read_catalog(CatalogKey(self.database_id, self.a, self.ra))
                self.assertEqual(card.revision.token, '7')
            finally: view.close()
        finally: backend.close()
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='user_index'").fetchone())

    def test_malformed_values_roll_back(self):
        self.execute('UPDATE catalog_record SET values_json=? WHERE record_id=?', ('[]', str(self.ra)))
        self.plan = prepare_v1(self.path, maintenance=True)
        with self.assertRaisesRegex(BackendError, 'integrity'): migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()

    def test_dangling_reference_rolls_back(self):
        values = list(self.va); values[-1] = ['r', str(self.b), str(uuid4())]
        self.execute('UPDATE catalog_record SET values_json=? WHERE record_id=?', (_json(values), str(self.ra)))
        self.plan = prepare_v1(self.path, maintenance=True)
        with self.assertRaises(BackendError): migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()

    def test_corrupted_target_before_verification_rolls_back(self):
        original = migration._copy_records
        def corrupt(db, database_id, schemas, layout):
            original(db, database_id, schemas, layout)
            table = quote_identifier(layout.table_name(self.a))
            db.execute(f"UPDATE {table} SET description='corrupted' WHERE record_id=?", (str(self.ra),))
        with mock.patch.object(migration, '_copy_records', side_effect=corrupt):
            with self.assertRaisesRegex(BackendError, 'integrity'):
                migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()

    def test_legacy_non_ascii_json_above_one_mib_bytes(self):
        fields = tuple(FieldSchema(uuid4(), 'Field' + str(i), 'string', (65536,)) for i in range(5))
        schema = CatalogSchema(self.a, 'A', 8, 64, fields)
        values = [['s', '😀' * 60000] for _ in fields]
        raw = json.dumps(values, ensure_ascii=False, separators=(',', ':'))
        self.assertLess(len(raw), 1024 * 1024)
        self.assertGreater(len(raw.encode('utf-8')), 1024 * 1024)
        self.execute('UPDATE catalog_schema SET definition=? WHERE identity=?', (_json(_schema_data(schema)), str(self.a)))
        self.execute('UPDATE catalog_record SET values_json=? WHERE record_id=?', (raw, str(self.ra)))
        plan = prepare_v1(self.path, maintenance=True)
        backend = SQLiteCatalogBackend(self.path)
        try:
            view = backend.begin_read()
            try: self.assertEqual(view.read_catalog(CatalogKey(self.database_id, self.a, self.ra)).values, tuple(v[1] for v in values))
            finally: view.close()
        finally: backend.close()
        migrate_v1(self.path, plan, maintenance=True)
        backend = SQLiteCatalogBackend(self.path)
        try:
            view = backend.begin_read()
            try: self.assertEqual(view.read_catalog(CatalogKey(self.database_id, self.a, self.ra)).values, tuple(v[1] for v in values))
            finally: view.close()
        finally: backend.close()
        self.assertEqual(resolve_migration(self.path, plan, maintenance=True), 'committed')

    def test_sqlite_like_name_with_cascade_is_rejected(self):
        self.execute('CREATE TABLE sqliteXhidden(catalog_id TEXT, record_id TEXT, FOREIGN KEY(catalog_id,record_id) REFERENCES catalog_record(catalog_id,record_id) ON DELETE CASCADE)')
        self.execute('INSERT INTO sqliteXhidden VALUES(?,?)', (str(self.a), str(self.ra)))
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sqliteXhidden').fetchone()[0], 1)

    def test_configuration_digest_failure_rolls_back(self):
        self.execute("UPDATE configuration_file SET sha256='bad'")
        with self.assertRaisesRegex(BackendError, 'integrity'): migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()

    def test_active_reader_blocks_exclusive_migration(self):
        db = sqlite3.connect(self.path, isolation_level=None)
        try:
            db.execute('BEGIN'); db.execute('SELECT * FROM catalog_record').fetchone()
            with self.assertRaisesRegex(BackendError, 'busy'): migrate_v1(self.path, self.plan, maintenance=True)
        finally: db.execute('ROLLBACK'); db.close()
        self.assert_v1()

    def test_commit_failure_before_commit_is_uncertain(self):
        real_connect = sqlite3.connect
        class Connection:
            def __init__(self, connection): self.connection = connection
            def __getattr__(self, name): return getattr(self.connection, name)
            def execute(self, sql, *args):
                if sql == 'COMMIT': raise sqlite3.OperationalError('injected')
                return self.connection.execute(sql, *args)
        with mock.patch('yadinassi.sqlite_catalog_migration.sqlite3.connect', side_effect=lambda *a, **kw: Connection(real_connect(*a, **kw))):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'): migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()
        self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'not_committed')
        self.execute("UPDATE catalog_record SET description='changed' WHERE record_id=?", (str(self.ra),))
        self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'uncertain')

    def test_commit_failure_after_commit_is_uncertain(self):
        real_connect = sqlite3.connect
        class Connection:
            def __init__(self, connection): self.connection = connection
            def __getattr__(self, name): return getattr(self.connection, name)
            def execute(self, sql, *args):
                result = self.connection.execute(sql, *args)
                if sql == 'COMMIT': raise sqlite3.OperationalError('injected')
                return result
        with mock.patch('yadinassi.sqlite_catalog_migration.sqlite3.connect', side_effect=lambda *a, **kw: Connection(real_connect(*a, **kw))):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'): migrate_v1(self.path, self.plan, maintenance=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT * FROM commit_receipt').fetchone(), self.receipt)
        self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'committed')
        self.execute("UPDATE migration_marker SET source_hash=?", ('b'*64,))
        self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'uncertain')

    def test_process_crash_before_commit_preserves_v1(self):
        tables = ('database_info', 'configuration_file', 'catalog_schema', 'catalog_record', 'commit_receipt')
        with closing(sqlite3.connect(self.path)) as db, db:
            before = {table: db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall() for table in tables}
        script = """
import os, sys
from uuid import UUID
import yadinassi.sqlite_catalog_migration as migration
plan = migration.MigrationPlan(UUID(sys.argv[2]), UUID(sys.argv[3]), sys.argv[4], sys.argv[5])
def crash(*args): os._exit(71)
migration._verify_records = crash
migration.migrate_v1(sys.argv[1], plan, maintenance=True)
"""
        result = subprocess.run([sys.executable, '-c', script, str(self.path), str(self.plan.migration_id),
                                 str(self.plan.database_uuid), self.plan.source_hash, self.plan.layout_hash],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 71, result.stderr.decode('utf-8', errors='replace'))
        # A read-only resolver may be unable to recover a hot journal. It must
        # not report the migration committed without its transaction marker.
        self.assertIn(resolve_migration(self.path, self.plan, maintenance=True), ('uncertain', 'not_committed'))
        # This writable recovery is explicitly limited to the temporary fixture
        # and occurs while the test has exclusive maintenance control.
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            after = {table: db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall() for table in tables}
        self.assertEqual(after, before)
        self.assert_v1()
        self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'not_committed')

    def test_non_sqlite_exception_after_real_commit_is_uncertain(self):
        real_connect = sqlite3.connect
        class Connection:
            def __init__(self, connection): self.connection = connection
            def __getattr__(self, name): return getattr(self.connection, name)
            def execute(self, sql, *args):
                result = self.connection.execute(sql, *args)
                if sql == 'COMMIT': raise RuntimeError('injected after commit')
                return result
        with mock.patch('yadinassi.sqlite_catalog_migration.sqlite3.connect', side_effect=lambda *a, **kw: Connection(real_connect(*a, **kw))):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                migrate_v1(self.path, self.plan, maintenance=True)
        self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'committed')

    def test_close_failure_before_commit_is_uncertain(self):
        real_connect = sqlite3.connect
        class Connection:
            def __init__(self, connection): self.connection = connection
            def __getattr__(self, name): return getattr(self.connection, name)
            def close(self):
                self.connection.close()
                raise sqlite3.OperationalError('injected close failure')
        with mock.patch('yadinassi.sqlite_catalog_migration.sqlite3.connect', side_effect=lambda *a, **kw: Connection(real_connect(*a, **kw))):
            with mock.patch.object(migration, '_copy_records', side_effect=BackendError('integrity')):
                with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                    migrate_v1(self.path, self.plan, maintenance=True)
        self.assert_v1()
        self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'not_committed')

    def test_close_failure_after_real_commit_is_uncertain(self):
        real_connect = sqlite3.connect
        class Connection:
            def __init__(self, connection): self.connection = connection
            def __getattr__(self, name): return getattr(self.connection, name)
            def close(self):
                self.connection.close()
                raise sqlite3.OperationalError('injected close failure')
        with mock.patch('yadinassi.sqlite_catalog_migration.sqlite3.connect', side_effect=lambda *a, **kw: Connection(real_connect(*a, **kw))):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                migrate_v1(self.path, self.plan, maintenance=True)
        self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'committed')

    def test_resolver_close_failure_is_uncertain(self):
        migrate_v1(self.path, self.plan, maintenance=True)
        real_connect = sqlite3.connect
        class Connection:
            def __init__(self, connection): self.connection = connection
            def __getattr__(self, name): return getattr(self.connection, name)
            def close(self):
                self.connection.close()
                raise sqlite3.OperationalError('injected close failure')
        with mock.patch('yadinassi.sqlite_catalog_migration.sqlite3.connect', side_effect=lambda *a, **kw: Connection(real_connect(*a, **kw))):
            self.assertEqual(resolve_migration(self.path, self.plan, maintenance=True), 'uncertain')


if __name__ == '__main__': unittest.main()
