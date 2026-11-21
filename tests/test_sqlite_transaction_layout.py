"""Reuse only maps freshly admitted inside the same format16 transaction."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_sqlite_transaction_source as fixture
from yadinassi.db.sqlite import sqlite_catalog as storage
from yadinassi.db.sqlite import sqlite_inventory_enum_profile as profile
from yadinassi.db.sqlite import sqlite_main_demo_profile as main_profile
from yadinassi.db.catalog.catalog_backend import BackendError


class TransactionLayoutTests(unittest.TestCase):
    setUp = fixture.TransactionSourceTests.setUp
    mutate = fixture.TransactionSourceTests.mutate

    def test_cold_writer_and_invalidated_reads_load_maps_once_warm_reuses_admission(self):
        # Source admission checks the layout; header-only admission performs
        # no reference operations and must not reload the same registry.
        for phase, writer, expected in (('cold', False, 1), ('warm', False, 0),
                                         ('writer', True, 1), ('after_writer', False, 1)):
            with self.subTest(phase=phase):
                trace = []
                # The warm path never enters read_source: observe its retained
                # connection directly rather than silently collecting no trace.
                if self.backend._read_handle is not None:
                    self.backend._read_handle.connection.set_trace_callback(trace.append)
                original = profile.read_source
                def observed(connection, **kwargs):
                    self.assertTrue(connection.in_transaction)
                    connection.set_trace_callback(trace.append)
                    return original(connection, **kwargs)
                with patch.object(profile, 'read_source', side_effect=observed) as source:
                    view = self.backend.begin_write(uuid4()) if writer else self.backend.begin_read()
                    with closing(view):
                        connection = view._connection
                    connection.set_trace_callback(None) if not writer else None
                self.assertEqual(source.call_count, expected)
                self.assertEqual(trace.count('SELECT catalog_id,physical_name FROM catalog_storage_map'), expected)
                self.assertEqual(trace.count('SELECT catalog_id,section_id,physical_name FROM catalog_section_storage_map'), expected)
                if expected == 0:
                    self.assertIn('BEGIN', trace)
                    self.assertIn('PRAGMA main.data_version', trace)
                self.assertIn('ROLLBACK', trace)
                self.assertIsNone(self.backend._active)

    def test_default_triple_and_optional_maps_match_fresh_loads(self):
        with closing(self.backend.begin_read()) as view:
            connection = view._connection
            self.assertEqual(len(profile.read_source(connection)), 3)
            source, maps = profile.read_source(connection, _with_layout=True)
            self.assertEqual(source, profile.read_source(connection))
            catalogs, sections = maps
            fresh = storage.load_layout(connection, source[0].catalogs)
            fresh_sections = storage.load_section_layout(connection, source[0].catalogs, fresh)
            self.assertEqual((catalogs._tables, catalogs._fields), (fresh._tables, fresh._fields))
            self.assertEqual((sections._tables, sections._fields), (fresh_sections._tables, fresh_sections._fields))

    def test_registry_dml_between_transactions_is_fresh_and_recoverable(self):
        for table in ('catalog_storage_map', 'catalog_field_storage_map',
                      'catalog_section_storage_map', 'catalog_section_field_storage_map'):
            with self.subTest(table=table):
                with closing(self.backend.begin_read()): pass
                with closing(sqlite3.connect(self.path)) as db:
                    before_version = db.execute('PRAGMA schema_version').fetchone()
                    rowid, name = db.execute('SELECT rowid,physical_name FROM '+table+' LIMIT 1').fetchone()
                self.mutate('UPDATE '+table+' SET physical_name=? WHERE rowid=?', ('wrong_layout_name',rowid))
                with closing(sqlite3.connect(self.path)) as db:
                    self.assertEqual(db.execute('PRAGMA schema_version').fetchone(), before_version)
                for writer in (False, True):
                    with self.assertRaises(BackendError):
                        self.backend.begin_write(uuid4()) if writer else self.backend.begin_read()
                    self.assertIsNone(self.backend._active)
                self.mutate('UPDATE '+table+' SET physical_name=? WHERE rowid=?', (name,rowid))
                with closing(self.backend.begin_read()) as view:
                    self.assertTrue(view.catalogs())

    def test_all_open_snapshot_equalities_remain_required(self):
        for layout in (self.backend._layout, self.backend._section_layout):
            for field in ('_tables', '_fields'):
                with self.subTest(layout=type(layout).__name__, field=field):
                    original = getattr(layout, field)
                    changed = dict(original)
                    key = next(iter(changed)); changed[key] = 'forged_snapshot_name'
                    with patch.object(layout, field, changed):
                        with self.assertRaisesRegex(BackendError, 'schema_changed'):
                            self.backend.begin_read()
                    self.assertIsNone(self.backend._active)
        with closing(self.backend.begin_read()): pass

    def test_exact_schema_tuple_is_required_before_map_reuse(self):
        with patch.object(self.backend, '_schemas', tuple(reversed(self.backend._schemas))):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                self.backend.begin_read()
        with closing(self.backend.begin_read()): pass

    def test_layout_failure_rolls_back_without_cache_grant(self):
        original = main_profile.validate_main_demo_ddl
        def corrupt_after_validation(connection, config, domain):
            original(connection, config, domain)
            raise BackendError('integrity')
        with patch.object(main_profile, 'validate_main_demo_ddl', side_effect=corrupt_after_validation):
            with self.assertRaises(BackendError): self.backend.begin_write(uuid4())
        self.assertIsNone(self.backend._active)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name='unit_of_work_receipt'").fetchone())
        with closing(self.backend.begin_write(uuid4())): pass
        with closing(self.backend.begin_read()): pass

    def test_peer_registry_commit_cannot_interleave_with_reused_snapshot(self):
        original = profile.read_source
        def read_then_change(connection, **kwargs):
            result = original(connection, **kwargs)
            with closing(sqlite3.connect(self.path, timeout=0)) as peer:
                peer.execute("UPDATE catalog_section_storage_map SET physical_name='catalog_section_wrong' WHERE rowid=(SELECT rowid FROM catalog_section_storage_map LIMIT 1)")
                with self.assertRaises(sqlite3.OperationalError): peer.commit()
                peer.rollback()
            return result
        with patch.object(profile, 'read_source', side_effect=read_then_change):
            with closing(self.backend.begin_read()) as view:
                self.assertTrue(view.catalogs())
        self.mutate("UPDATE catalog_section_storage_map SET physical_name='catalog_section_wrong' WHERE rowid=(SELECT rowid FROM catalog_section_storage_map LIMIT 1)")
        with self.assertRaises(BackendError): self.backend.begin_read()
        with self.assertRaises(BackendError): self.backend.begin_write(uuid4())
        self.assertIsNone(self.backend._active)


class Format16ProfileLayoutTests(unittest.TestCase):
    def test_all_three_profiles_keep_read_write_and_failure_cleanup(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from test_configuration_inventory_enums import source as core_source
        from inventory_enum_application_fixture import source as ui_source
        from test_main_demo_configuration import source as main_source
        from yadinassi.configuration.configuration_inventory_enums import import_inventory_enum_configuration, PROFILE as CORE
        from yadinassi.configuration.configuration_inventory_enum_application import import_inventory_application, PROFILE as UI
        from yadinassi.configuration.configuration_main_demo import import_main_demo_configuration, PROFILE as MAIN
        configs = (
            (storage.SQLiteCatalogBackend.create_inventory_enum, import_inventory_enum_configuration(core_source(), inventory_runtime=CORE), profile, '_validate_ddl'),
            (storage.SQLiteCatalogBackend.create_inventory_enum_application, import_inventory_application(ui_source(), inventory_runtime=UI), profile, '_validate_ddl'),
            (storage.SQLiteCatalogBackend.create_main_demo, import_main_demo_configuration(main_source(), profile=MAIN), main_profile, 'validate_main_demo_ddl'),
        )
        for create, config, module, method in configs:
            with self.subTest(profile=config.profile), TemporaryDirectory() as folder:
                backend = create(Path(folder)/'owned.sqlite', config)
                try:
                    for writer in (False, True):
                        with patch.object(storage, 'load_layout', wraps=storage.load_layout) as load, \
                             patch.object(storage, 'load_section_layout', wraps=storage.load_section_layout) as sections:
                            view = backend.begin_write(uuid4()) if writer else backend.begin_read()
                            with closing(view): self.assertTrue(view.catalogs())
                            self.assertEqual(load.call_count, 1)
                            self.assertEqual(sections.call_count, 1)
                    with patch.object(module, method, side_effect=BackendError('integrity')):
                        for writer in (False, True):
                            with self.assertRaises(BackendError):
                                backend.begin_write(uuid4()) if writer else backend.begin_read()
                            self.assertIsNone(backend._active)
                    from yadinassi.db.sqlite.sqlite_accumulation_movements import AccumulationMovementPort
                    for writer in (False, True):
                        backend._prepared_source.clear()
                        with patch.object(AccumulationMovementPort, '_require', side_effect=BackendError('integrity')):
                            with self.assertRaises(BackendError):
                                backend.begin_write(uuid4()) if writer else backend.begin_read()
                        self.assertIsNone(backend._active)
                        self.assertIsNone(backend._prepared_source._entry)
                    with closing(backend.begin_read()): pass
                    with closing(backend.begin_write(uuid4())): pass
                finally: backend.close()
