"""Generic migrated catalogs: metadata reuse is not row or writer authority."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_query_count_pushdown as fixtures
from yadinassi import Interpreter
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_migration_plan import prepare, apply
from yadinassi.db.catalog.catalog_backend import BackendError

class GenericAdmissionEpochTests(unittest.TestCase):
    tearDown = fixtures.CountPushdownTests.tearDown
    query = fixtures.CountPushdownTests.query
    table = fixtures.CountPushdownTests.table

    def setUp(self):
        fixtures.CountPushdownTests.setUp(self)
        path = self.context.path
        self.vm.close(); self.context.close()
        apply(path, prepare(path, maintenance=True), maintenance=True)
        self.context = SQLiteDBContext(path)
        self.vm = Interpreter(database_context=self.context, output=self.output.append)
        self.backend = self.context.backend
        self.assertEqual(self.backend.format_version, 11)
        self.assertTrue(self.backend._read_admission_cache_allowed())

    def sql(self, statement, args=()):
        from yadinassi.db.sqlite.sqlite_catalog import register_query_collations
        with closing(sqlite3.connect(self.context.path)) as db:
            register_query_collations(db)
            result = db.execute(statement, args).fetchall(); db.commit()
            return result

    def warm(self):
        self.assertEqual(self.query()._rows, ((Decimal(3),),))
        self.assertIsNotNone(self.backend._read_handle.admission)

    def test_warm_query_has_no_schema_select_or_full_admission(self):
        self.warm(); statements=[]
        self.backend._read_handle.connection.set_trace_callback(statements.append)
        with patch.object(self.backend, '_validate_transaction_admission', side_effect=AssertionError('cold')):
            self.assertEqual(self.query()._rows, ((Decimal(3),),))
        self.assertFalse(any('FROM catalog_schema' in sql for sql in statements), statements)
        self.assertEqual(sum('SELECT COUNT(*) FROM' in sql for sql in statements), 1)

    def test_foreign_hidden_scalar_corruption_not_hidden(self):
        self.warm(); table=self.table()
        # A noncooperating SQLite writer can bypass CHECK constraints. COUNT
        # must still validate the unprojected revision after the epoch changes.
        from yadinassi.db.sqlite.sqlite_catalog import register_query_collations
        with closing(sqlite3.connect(self.context.path)) as db:
            register_query_collations(db)
            db.execute('PRAGMA ignore_check_constraints=ON')
            db.execute('UPDATE '+table+" SET revision=0 WHERE code='1'"); db.commit()
        with self.assertRaises(BackendError): self.query()
        self.assertIsNone(self.backend._read_handle.admission)

    def test_foreign_schema_cookie_reset_cannot_hide_ddl(self):
        self.warm()
        with closing(sqlite3.connect(self.context.path)) as db:
            version=db.execute('PRAGMA schema_version').fetchone()[0]
            db.execute('CREATE TABLE injected(x)');db.execute('PRAGMA schema_version='+str(version));db.commit()
        with self.assertRaisesRegex(BackendError,'schema_changed'): self.query()

    def test_foreign_layout_change_invalidates(self):
        self.warm()
        self.sql("UPDATE catalog_storage_map SET physical_name='injected' WHERE catalog_id=(SELECT catalog_id FROM catalog_storage_map LIMIT 1)")
        with self.assertRaises(BackendError): self.query()

    def test_nested_schema_mutation_is_not_shared_descriptor(self):
        self.warm(); schema=self.backend._schemas[0]; old=schema.name
        try:
            object.__setattr__(schema,'name','injected')
            with self.assertRaisesRegex(BackendError,'schema_changed'): self.query()
        finally: object.__setattr__(schema,'name',old)

    def test_live_view_schema_drift_fails_before_lookup(self):
        self.warm()
        with closing(self.backend.begin_read()) as view:
            schema=self.backend._schemas[0];old=schema.name
            try:
                object.__setattr__(schema,'name','injected')
                with self.assertRaisesRegex(BackendError,'schema_changed'): view.catalog_schema(schema.identity)
            finally: object.__setattr__(schema,'name',old)

    def test_own_rollback_invalidates_metadata_and_rows(self):
        self.warm();handle=self.backend._read_handle
        with closing(self.backend.begin_write(uuid4())):
            self.assertIsNone(handle.admission);self.assertEqual(handle.proofs,{})
        self.assertEqual(self.query()._rows,((Decimal(3),),))

    def test_valid_external_change_is_fresh(self):
        self.warm();self.sql('DELETE FROM '+self.table()+" WHERE code='1'")
        self.assertEqual(self.query()._rows,((Decimal(2),),))

    def test_generic_source_profiles_remain_outside_scope(self):
        old=self.backend.activation_issues
        try:
            self.backend.activation_issues=('unrecognised-profile',)
            self.assertFalse(self.backend._read_admission_cache_allowed())
        finally:self.backend.activation_issues=old

    def test_foreign_activation_flag_change_is_not_hidden(self):
        self.warm(); self.sql('UPDATE database_info SET activated=0')
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.query()


class GenericSectionAndSequenceEpochTests(unittest.TestCase):
    def backend_variant(self, version, migrated):
        from contextlib import contextmanager
        from dataclasses import replace
        from pathlib import Path
        import tempfile
        from test_catalog_atomic_numbering import numbered_configuration
        from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
        @contextmanager
        def opened():
            with tempfile.TemporaryDirectory() as directory:
                config = numbered_configuration()
                if version != 4:
                    config = replace(config, catalogs=tuple(replace(schema,
                        numbering='explicit',
                        tabular_sections=() if version == 2 else schema.tabular_sections)
                        for schema in config.catalogs))
                path = Path(directory)/'owned.sqlite'
                backend = SQLiteCatalogBackend.create(path, config)
                if migrated:
                    backend.close()
                    apply(path, prepare(path, maintenance=True), maintenance=True)
                    backend = SQLiteCatalogBackend(path)
                try:
                    self.assertEqual(backend.storage_version, version)
                    self.assertEqual(backend.format_version, 11 if migrated else version)
                    yield backend, path
                finally: backend.close()
        return opened()

    def warm(self, backend):
        for _ in range(2):
            with closing(backend.begin_read()) as view:
                view.catalog_schema(backend._schemas[0].identity)
        self.assertIsNotNone(backend._read_handle.admission)

    def test_all_named_generic_variants_reuse_successful_admission(self):
        for version in (2, 3, 4):
            for migrated in (False, True):
                with self.subTest(version=version, migrated=migrated), self.backend_variant(version, migrated) as (backend, path):
                    self.warm(backend)
                    with patch.object(backend, '_validate_transaction_admission', side_effect=AssertionError('cold')):
                        with closing(backend.begin_read()) as view:
                            self.assertEqual(view.catalog_schema(backend._schemas[0].identity), backend._schemas[0])

    def test_foreign_section_layout_change_after_warm_epoch(self):
        for version in (3, 4):
            for migrated in (False, True):
                with self.subTest(version=version, migrated=migrated), self.backend_variant(version, migrated) as (backend, path):
                    self.warm(backend)
                    with closing(sqlite3.connect(path)) as db:
                        db.execute("UPDATE catalog_section_storage_map SET physical_name='injected'"); db.commit()
                    with self.assertRaises(BackendError): backend.begin_read()

    def test_foreign_section_payload_corruption_after_warm_read(self):
        from yadinassi.db.catalog.catalog_backend import CatalogDraft, CatalogKey, TabularRow, TabularSectionRows
        from yadinassi.db.sqlite.sqlite_catalog import register_query_collations
        from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier
        for version in (3, 4):
            for migrated in (False, True):
                with self.subTest(version=version, migrated=migrated), self.backend_variant(version, migrated) as (backend, path):
                    schema = next(s for s in backend._schemas if s.tabular_sections)
                    section = schema.tabular_sections[0]
                    key = CatalogKey(backend.database_id, schema.identity, uuid4())
                    draft = CatalogDraft(key, '01', 'item', False, (),
                        (TabularSectionRows(section.identity, (TabularRow(uuid4(), ('valid',)),)),))
                    with closing(backend.begin_write(uuid4())) as writer:
                        writer.create(draft); writer.commit()
                    for _ in range(2):
                        with closing(backend.begin_read()) as view: view.read_catalog(key)
                    self.assertIsNotNone(backend._read_handle.admission)
                    table = quote_identifier(backend._section_layout.table_name(schema.identity, section.identity))
                    column = quote_identifier(backend._section_layout.field_name(schema.identity, section.identity, section.fields[0].identity))
                    with closing(sqlite3.connect(path)) as db:
                        register_query_collations(db)
                        db.execute('UPDATE '+table+' SET '+column+'=?', (b'not-text',)); db.commit()
                    with closing(backend.begin_read()) as view:
                        with self.assertRaises(BackendError): view.read_catalog(key)

    def test_foreign_sequence_corruption_after_warm_epoch(self):
        for migrated in (False, True):
            with self.subTest(migrated=migrated), self.backend_variant(4, migrated) as (backend, path):
                self.warm(backend)
                with closing(sqlite3.connect(path)) as db:
                    db.execute('PRAGMA ignore_check_constraints=ON')
                    db.execute('UPDATE catalog_sequence SET next_value=0'); db.commit()
                with self.assertRaises(BackendError): backend.begin_read()

    def test_valid_sequence_change_revalidated_after_warm_epoch(self):
        for migrated in (False, True):
            with self.subTest(migrated=migrated), self.backend_variant(4, migrated) as (backend, path):
                self.warm(backend)
                with closing(sqlite3.connect(path)) as db:
                    db.execute('UPDATE catalog_sequence SET next_value=next_value+1'); db.commit()
                with patch.object(backend, '_check_sequences', wraps=backend._check_sequences) as check:
                    with closing(backend.begin_read()): pass
                    self.assertEqual(check.call_count, 1)
