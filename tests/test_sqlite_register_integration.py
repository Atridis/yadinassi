"""Owned SQLite v8 admission and cross-port compatibility, not native evidence."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi.catalog_backend import (BackendError, CatalogDraft, CatalogKey,
    CatalogSchema, FieldSchema, TabularRow, TabularSectionRows, TabularSectionSchema)
from yadinassi.configuration_xml import ConfigurationFile, ConfigurationImport
from yadinassi.document_backend import DocumentDraft, DocumentKey, DocumentSchema
from yadinassi.register_backend import InformationRegisterSchema, RegisterDraft, RegisterKey, RegisterScanRequest, RegisterSetDraft
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_documents import DOCUMENT_DDL
from yadinassi.sqlite_registers import REGISTER_DDL
from test_sqlite_catalog_admission_cleanup import AdmissionFaultConnection
from test_sqlite_catalog_create_uncertain import CreateConnection


def configuration(*, catalogs=True, documents=True, registers=True):
    category = CatalogSchema(uuid4(), 'Orders', 8, 32, numbering='decimal_v1')
    section = TabularSectionSchema(uuid4(), 'Lines', (FieldSchema(uuid4(), 'Flag', 'boolean'),))
    document = DocumentSchema(uuid4(), 'Orders', 9, (), (section,), 'decimal_v1')
    register = InformationRegisterSchema(uuid4(), 'Orders',
        (FieldSchema(uuid4(), 'Item', 'string', (32,)),),
        (FieldSchema(uuid4(), 'Amount', 'number', (12, 2, 'Any')),))
    return ConfigurationImport(uuid4(), 'OwnedRegister',
        (category,) if catalogs else (),
        (ConfigurationFile(path='Configuration.xml', content=b'<owned-register/>', kind='xml'),), (), (),
        (document,) if documents else (), information_registers=(register,) if registers else ())


class RegisterStorageIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owned.sqlite'
        self.config = configuration()
        self.backend = SQLiteCatalogBackend.create(self.path, self.config)
        self.addCleanup(self.backend.close)

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(statement, args).fetchall()

    def drafts(self):
        identity = self.backend.database_id
        catalog = CatalogDraft(CatalogKey(identity, self.config.catalogs[0].identity, uuid4()),
                               '', 'Catalog', False, (), auto_number=True)
        section = self.config.documents[0].tabular_sections[0]
        document = DocumentDraft(DocumentKey(identity, self.config.documents[0].identity, uuid4()),
            '', datetime(2026, 11, 10), False, (),
            (TabularSectionRows(section.identity, (TabularRow(uuid4(), (True,)),)),), True)
        register = RegisterDraft(RegisterKey(identity, self.config.information_registers[0].identity, ('item',)),
                                 (Decimal('12.50'),))
        return catalog, document, register

    def test_register_only_database_reopens_without_shadow_catalogs_or_documents(self):
        path = Path(self.temp.name) / 'register-only.sqlite'
        config = configuration(catalogs=False, documents=False)
        backend = SQLiteCatalogBackend.create(path, config)
        backend.close()
        backend = SQLiteCatalogBackend(path)
        try:
            self.assertEqual(backend.storage_version, 8)
            self.assertTrue(backend.capabilities().register_read)
            view = backend.begin_read()
            self.assertEqual(view.catalogs(), ())
            view.close()
            view = backend.begin_document_read()
            self.assertEqual(view.documents(), ())
            view.close()
            view = backend.begin_register_read()
            self.assertEqual(view.registers(), config.information_registers)
            view.close()
            self.assertEqual(backend.export_configuration(), {'Configuration.xml': b'<owned-register/>'})
        finally:
            backend.close()

    def test_older_catalog_and_document_files_are_not_upgraded(self):
        base = configuration(documents=False, registers=False)
        plain = replace(base.catalogs[0], numbering='explicit')
        section = TabularSectionSchema(uuid4(), 'Lines', ())
        variants = ((2, replace(base, catalogs=(plain,))),
                    (3, replace(base, catalogs=(replace(plain, tabular_sections=(section,)),))),
                    (4, base), (7, configuration(registers=False)))
        for version, config in variants:
            with self.subTest(version=version):
                path = Path(self.temp.name) / f'old-{version}.sqlite'
                backend = SQLiteCatalogBackend.create(path, config)
                backend.close()
                before = path.read_bytes()
                backend = SQLiteCatalogBackend(path)
                try:
                    self.assertEqual(backend.storage_version, version)
                    self.assertFalse(backend.capabilities().register_read)
                    self.assertFalse(backend.capabilities().register_write)
                    with self.assertRaisesRegex(BackendError, 'unsupported'):
                        backend.begin_register_read()
                    with self.assertRaisesRegex(BackendError, 'unsupported'):
                        backend.begin_register_write(uuid4())
                finally:
                    backend.close()
                self.assertEqual(path.read_bytes(), before)

    def test_open_missing_path_never_creates_database(self):
        path = Path(self.temp.name) / 'missing.sqlite'
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend(path)
        self.assertFalse(path.exists())

    def test_unknown_or_downgraded_format_is_rejected_without_repair(self):
        self.backend.close()
        for version in (9, 7):
            with self.subTest(version=version):
                self.sql(f'PRAGMA user_version={version}')
                before = self.path.read_bytes()
                with self.assertRaises(BackendError):
                    SQLiteCatalogBackend(self.path)
                self.assertEqual(self.path.read_bytes(), before)
        self.sql('PRAGMA user_version=8')

    def test_v8_preserves_document_ddl_and_uses_distinct_register_tables(self):
        actual = dict(self.sql("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        for ddl in (*DOCUMENT_DDL, *REGISTER_DDL):
            self.assertEqual(actual[ddl.split('(')[0].split()[-1]], ddl)
        self.assertEqual(self.sql('SELECT name FROM catalog_schema'), [('Orders',)])
        self.assertEqual(self.sql('SELECT name FROM document_schema'), [('Orders',)])
        self.assertEqual(self.sql('SELECT name FROM information_register_schema'), [('Orders',)])

    def test_mixed_catalog_document_and_register_persistence_and_receipts(self):
        catalog, document, register = self.drafts()
        operations = [uuid4() for _ in range(3)]
        view = self.backend.begin_write(operations[0])
        view.create(catalog)
        catalog_revision = view.commit()[0]
        view = self.backend.begin_document_write(operations[1])
        view.create(document)
        document_outcome = view.commit()
        view = self.backend.begin_register_write(operations[2])
        view.write(register)
        register_outcome = view.commit()
        self.backend.close()
        self.backend = SQLiteCatalogBackend(self.path)
        self.addCleanup(self.backend.close)
        view = self.backend.begin_read()
        card = view.read_catalog(catalog.key)
        view.close()
        self.assertEqual((card.code, card.revision), ('00000001', catalog_revision))
        view = self.backend.begin_document_read()
        card = view.read_document(document.key)
        view.close()
        self.assertEqual((card.number, card.revision, card.tabular_sections),
                         ('000000001', document_outcome.revision, document.tabular_sections))
        view = self.backend.begin_register_read()
        record = view.read_record(register.key)
        view.close()
        self.assertEqual((record.values, record.revision), (register.values, register_outcome.revision))
        self.assertEqual(self.backend.resolve_document_write(operations[1], document), document_outcome)
        self.assertEqual(self.backend.resolve_register_write(operations[2], register), register_outcome)
        catalog_receipt = json.loads(self.sql('SELECT revisions_json FROM commit_receipt')[0][0])
        self.assertEqual(len(catalog_receipt[0]), 4)
        for table in ('commit_receipt', 'document_commit_receipt', 'information_register_receipt'):
            self.assertEqual(self.sql(f'SELECT COUNT(*) FROM {table}'), [(1,)])

    def test_receipt_operation_ids_cannot_be_reused_through_other_ports(self):
        catalog, document, register = self.drafts()
        operations = [uuid4() for _ in range(3)]
        for begin, draft, method, operation in (
                (self.backend.begin_write, catalog, 'create', operations[0]),
                (self.backend.begin_document_write, document, 'create', operations[1]),
                (self.backend.begin_register_write, register, 'write', operations[2])):
            view = begin(operation)
            getattr(view, method)(draft)
            view.commit()
        for operation in operations:
            for begin in (self.backend.begin_write, self.backend.begin_document_write,
                          self.backend.begin_register_write):
                with self.subTest(operation=operation, port=begin.__name__):
                    with self.assertRaisesRegex(BackendError, 'conflict'):
                        begin(operation)
                    self.assertIsNone(self.backend._active)

    def test_read_only_open_keeps_reads_and_refuses_all_write_ports(self):
        self.backend.close()
        backend = SQLiteCatalogBackend(self.path, read_only=True)
        try:
            capabilities = backend.capabilities()
            self.assertTrue(capabilities.register_read)
            self.assertTrue(capabilities.document_read)
            self.assertFalse(capabilities.register_write)
            self.assertFalse(capabilities.document_create)
            self.assertFalse(capabilities.catalog_create)
            for begin in (backend.begin_read, backend.begin_document_read, backend.begin_register_read):
                begin().close()
            for begin in (backend.begin_write, backend.begin_document_write, backend.begin_register_write):
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    begin(uuid4())
        finally:
            backend.close()

    def test_inactive_v8_exposes_no_active_port(self):
        path = Path(self.temp.name) / 'inactive.sqlite'
        backend = SQLiteCatalogBackend.create(path, self.config, activate=False)
        try:
            capabilities = backend.capabilities()
            self.assertFalse(capabilities.register_read)
            self.assertFalse(capabilities.document_read)
            self.assertFalse(capabilities.catalog_read)
            for begin in (backend.begin_read, backend.begin_document_read, backend.begin_register_read):
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    begin()
        finally:
            backend.close()

    def test_register_metadata_drift_blocks_every_port_without_ddl_change(self):
        schema_version = self.sql('PRAGMA schema_version')
        raw = json.loads(self.sql('SELECT definition FROM information_register_schema')[0][0])
        raw[2] = 'Changed'
        self.sql('UPDATE information_register_schema SET name=?,definition=?',
                 ('Changed', json.dumps(raw, ensure_ascii=False, separators=(',', ':'))))
        self.assertEqual(self.sql('PRAGMA schema_version'), schema_version)
        for begin in (self.backend.begin_read, self.backend.begin_document_read, self.backend.begin_register_read):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                begin()
            self.assertIsNone(self.backend._active)

    def test_document_metadata_drift_blocks_register_port(self):
        schema_version = self.sql('PRAGMA schema_version')
        self.sql('UPDATE document_schema SET name=?', ('Changed',))
        self.assertEqual(self.sql('PRAGMA schema_version'), schema_version)
        with self.assertRaises(BackendError):
            self.backend.begin_register_read()
        self.assertIsNone(self.backend._active)

    def test_register_schema_and_sequence_inventory_are_required(self):
        for table in ('information_register_schema', 'information_register_sequence'):
            path = Path(self.temp.name) / f'{table}.sqlite'
            backend = SQLiteCatalogBackend.create(path, self.config)
            backend.close()
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute(f'DELETE FROM {table}')
            with self.subTest(table=table), self.assertRaises(BackendError):
                SQLiteCatalogBackend(path)

    def test_register_sequence_corruption_fails_transaction_and_reopen(self):
        self.sql('UPDATE information_register_sequence SET next_value=?', ('bad',))
        with self.assertRaises(BackendError):
            self.backend.begin_register_read()
        self.assertIsNone(self.backend._active)
        self.backend.close()
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend(self.path)

    def test_unexpected_ddl_blocks_admission(self):
        self.backend.close()
        self.sql('CREATE TABLE unexpected(value TEXT)')
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            SQLiteCatalogBackend(self.path)

    def test_busy_and_closed_register_views_share_connection_ownership(self):
        view = self.backend.begin_register_read()
        for begin in (self.backend.begin_read, self.backend.begin_document_read, self.backend.begin_register_read):
            with self.assertRaisesRegex(BackendError, 'busy'):
                begin()
        view.close()
        self.assertIsNone(self.backend._active)
        with self.assertRaisesRegex(BackendError, 'closed'):
            view.registers()
        self.backend.close()
        with self.assertRaisesRegex(BackendError, 'closed'):
            self.backend.begin_register_read()

    def test_register_wrapper_failure_closes_owned_transaction(self):
        error = MemoryError('injected')
        with patch('yadinassi.sqlite_catalog.RegisterView', side_effect=error):
            with self.assertRaises(MemoryError) as raised:
                self.backend.begin_register_read()
        self.assertIs(raised.exception, error)
        self.assertIsNone(self.backend._active)
        self.backend.begin_read().close()

    def test_wrapper_interruption_and_failed_close_retain_owner(self):
        error = MemoryError('injected')
        real_connect = sqlite3.connect
        connections = []
        def connect(*args, **kwargs):
            proxy = AdmissionFaultConnection(real_connect(*args, **kwargs),
                                              close_error=sqlite3.OperationalError('close failed'))
            connections.append(proxy)
            return proxy
        try:
            with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=connect), \
                    patch('yadinassi.sqlite_catalog.RegisterView', side_effect=error):
                with self.assertRaises(MemoryError) as raised:
                    self.backend.begin_register_read()
            self.assertIs(raised.exception, error)
            self.assertIsNotNone(self.backend._active)
            self.assertTrue(self.backend._active._closed)
            with self.assertRaisesRegex(BackendError, 'busy'):
                self.backend.begin_read()
        finally:
            for connection in connections:
                connection.disable_faults()
            self.backend.close()

    def test_register_schema_load_fault_releases_pending_connection(self):
        error = MemoryError('injected')
        with patch('yadinassi.sqlite_catalog.load_register_schemas', side_effect=error):
            with self.assertRaises(MemoryError) as raised:
                self.backend.begin_register_read()
        self.assertIs(raised.exception, error)
        self.assertIsNone(self.backend._active)

    def test_uncertain_creation_preserves_complete_v8_file(self):
        path = Path(self.temp.name) / 'uncertain.sqlite'
        real_connect = sqlite3.connect
        connections = []
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            if connections:
                return connection
            proxy = CreateConnection(connection, commit='after')
            connections.append(proxy)
            return proxy
        with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=connect):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(path, self.config)
        self.assertTrue(path.exists())
        backend = SQLiteCatalogBackend(path)
        try:
            self.assertEqual(backend.storage_version, 8)
            self.assertEqual(backend.export_configuration(), {'Configuration.xml': b'<owned-register/>'})
            backend.begin_register_read().close()
        finally:
            backend.close()

    def test_cross_port_identity_or_reference_target_collision_rejected_before_create(self):
        register = self.config.information_registers[0]
        variants = (
            replace(register, identity=self.config.documents[0].identity),
            replace(register, dimensions=(replace(register.dimensions[0], identity=self.config.catalogs[0].identity),)),
            replace(register, dimensions=(FieldSchema(uuid4(), 'Item', 'catalog_ref', (), uuid4()),)),
        )
        for index, schema in enumerate(variants):
            path = Path(self.temp.name) / f'invalid-{index}.sqlite'
            with self.subTest(index=index), self.assertRaises(BackendError):
                SQLiteCatalogBackend.create(path, replace(self.config, information_registers=(schema,)))
            self.assertFalse(path.exists())

    def test_query_view_reuses_one_snapshot_and_keeps_register_continuation(self):
        _, _, draft = self.drafts()
        for item in ('a', 'b', 'c'):
            view = self.backend.begin_register_write(uuid4())
            view.write(replace(draft, key=replace(draft.key, dimensions=(item,))))
            view.commit()
        view = self.backend.begin_query_read()
        try:
            owner = self.backend._active
            self.assertIs(view._view, owner)
            self.assertEqual(view.registers(), self.config.information_registers)
            self.assertEqual(view.register_schema(draft.key.register_id), self.config.information_registers[0])
            self.assertIs(view._register_read_view._view, owner)
            self.assertEqual(view.document_schema(self.config.documents[0].identity), self.config.documents[0])
            self.assertEqual(view.catalog_schema(self.config.catalogs[0].identity), self.config.catalogs[0])
            page = view.scan_register(draft.key.register_id, RegisterScanRequest(page_size=1))
            self.assertEqual(page.rows[0].key.dimensions, ('a',))
            self.assertIsNotNone(page.continuation)
            page = view.scan_register(draft.key.register_id, RegisterScanRequest(1, page.continuation))
            self.assertEqual(page.rows[0].key.dimensions, ('b',))
            page = view.scan_register(draft.key.register_id, RegisterScanRequest(1, page.continuation))
            self.assertEqual(page.rows[0].key.dimensions, ('c',))
            self.assertIsNone(page.continuation)
        finally:
            view.close()
        self.assertIsNone(self.backend._active)
        with self.assertRaisesRegex(BackendError, 'closed'):
            view.registers()

    def test_record_set_receipt_resolves_through_backend_wrapper(self):
        _, _, row = self.drafts()
        register = self.config.information_registers[0]
        draft = RegisterSetDraft(register.identity, ((register.dimensions[0].identity, 'item'),), (row,))
        operation = uuid4()
        view = self.backend.begin_register_write(operation)
        view.write_set(draft)
        outcome = view.commit()
        self.assertEqual(self.backend.resolve_register_set(operation, draft), outcome)
        self.assertIsNone(self.backend._active)
        self.assertIsNone(self.backend.resolve_register_set(uuid4(), draft))
