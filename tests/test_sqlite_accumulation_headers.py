"""Header-only format16 admission never grants a usable movement port."""
from contextlib import closing, ExitStack
from unittest.mock import patch
import unittest
from uuid import UUID, uuid4

import test_sqlite_transaction_source as fixture
from yadinassi.db.sqlite import sqlite_accumulation_movements as movements
from yadinassi.db.sqlite import sqlite_inventory_enum_profile as profile
from yadinassi.db.sqlite import sqlite_catalog as storage
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.document.document_backend import DocumentKey


class AccumulationHeaderTests(unittest.TestCase):
    setUp = fixture.TransactionSourceTests.setUp
    mutate = fixture.TransactionSourceTests.mutate

    def port(self, connection):
        return movements.AccumulationMovementPort(connection, self.backend.database_id, 1,
            self.backend.accumulation_configuration.registers, active_only=True,
            reference_catalogs=self.backend._schemas, enum_domain=self.backend._enum_domain)

    def test_header_admission_returns_none_and_never_operates_on_rows(self):
        with closing(self.backend.begin_read()) as view, ExitStack() as stack:
            for method in ('read', 'scan', 'describe', 'replace', 'resolve', '_references', '_encoded'):
                stack.enter_context(patch.object(movements.AccumulationMovementPort, method,
                    side_effect=AssertionError('row/reference operation '+method)))
            stack.enter_context(patch.object(storage, 'load_layout', side_effect=AssertionError('redundant layout')))
            real_require = movements.AccumulationMovementPort._require
            seen = []
            def require(port, register, recorder):
                self.assertIs(type(port), movements.AccumulationMovementPort)
                self.assertFalse(hasattr(port, '_reference_layout'))
                seen.append(register)
                return real_require(port, register, recorder)
            with patch.object(movements.AccumulationMovementPort, '_require', require):
                result = movements._admit_headers(view._connection, self.backend.database_id,
                    self.backend.accumulation_configuration.registers,
                    reference_catalogs=self.backend._schemas, enum_domain=self.backend._enum_domain)
            self.assertIsNone(result)
            self.assertEqual(seen, [s.identity for s in self.backend.accumulation_configuration.registers])

    def test_public_constructor_always_loads_and_rejects_bad_layout(self):
        with closing(self.backend.begin_write(uuid4())) as view:
            with patch.object(storage, 'load_layout', wraps=storage.load_layout) as load:
                port = self.port(view._connection)
                self.assertIsNotNone(port._reference_layout)
                self.assertEqual(load.call_count, 1)
            view._connection.execute("UPDATE catalog_storage_map SET physical_name='broken' WHERE rowid=(SELECT rowid FROM catalog_storage_map LIMIT 1)")
            with self.assertRaises(BackendError): self.port(view._connection)

    def test_validate_rows_still_constructs_full_port(self):
        with closing(self.backend.begin_read()) as view:
            with patch.object(movements, '_admit_headers', side_effect=AssertionError('header-only branch')), \
                 patch.object(storage, 'load_layout', wraps=storage.load_layout) as load:
                profile.admit(view._connection, self.backend.database_id,
                    self.backend._schemas, self.backend._document_schemas, validate_rows=True)
                self.assertEqual(load.call_count, 2)  # Fresh source + complete port.

    def test_actual_read_still_checks_references(self):
        with closing(self.backend.begin_read()) as view:
            port = self.port(view._connection)
            schema = self.backend.accumulation_configuration.registers[0]
            recorder = DocumentKey(self.backend.database_id, schema.recorder_documents[0], UUID(int=1))
            with patch.object(movements.AccumulationMovementPort, '_references', side_effect=BackendError('integrity')) as refs:
                with self.assertRaises(BackendError): port.read(schema.identity, recorder)
                self.assertEqual(refs.call_count, 1)

    def test_actual_write_still_checks_references_before_mutation(self):
        from yadinassi.db.registers.accumulation_movements import AccumulationReplacement
        with closing(self.backend.begin_write(uuid4())) as view:
            port = self.port(view._connection)
            schema = self.backend.accumulation_configuration.registers[0]
            recorder = DocumentKey(self.backend.database_id, schema.recorder_documents[0], UUID(int=1))
            request = AccumulationReplacement(schema.identity, recorder, (), '0' * 64)
            before = view._connection.total_changes
            with patch.object(movements.AccumulationMovementPort, '_references', side_effect=BackendError('not_found')) as refs:
                with self.assertRaises(BackendError): port.replace(uuid4(), request)
                refs.assert_called_once_with((), writing=True)
            self.assertEqual(view._connection.total_changes, before)

    def test_live_initializer_and_require_failures_cleanup_and_repair(self):
        for method in ('schema_data', 'validate_replacement'):
            for writer in (False, True):
                with self.subTest(method=method, writer=writer):
                    # PreparedSource is an importer cache, not the retained
                    # readonly epoch admission. Force this fault path cold.
                    self.backend._close_idle_read_handle()
                    self.backend._prepared_source.clear()
                    with patch.object(movements, method, side_effect=BackendError('integrity')) as injected:
                        with self.assertRaises(BackendError):
                            # Close an unexpected successful view as well, so a
                            # missed fault cannot turn the next case into busy.
                            with closing(self.backend.begin_write(uuid4()) if writer else self.backend.begin_read()):
                                pass
                        injected.assert_called_once()
                    self.assertIsNone(self.backend._active)
                    self.assertIsNone(self.backend._prepared_source._entry)
                    with closing(self.backend.begin_read()): pass

    def test_warm_header_admission_does_not_reenter_initializer(self):
        with closing(self.backend.begin_read()): pass
        handle = self.backend._read_handle
        self.assertIsNotNone(handle.admission)
        # Clearing only parsed source must not masquerade as a changed DB epoch.
        self.backend._prepared_source.clear()
        with patch.object(movements, 'validate_replacement', side_effect=BackendError('integrity')) as injected:
            with closing(self.backend.begin_read()) as view:
                self.assertTrue(view.catalogs())
            injected.assert_not_called()
            self.assertIsNone(self.backend._active)
            self.assertIs(self.backend._read_handle, handle)
            # A writer cannot borrow that warm proof, even when it fails.
            with self.assertRaises(BackendError):
                with closing(self.backend.begin_write(uuid4())): pass
            injected.assert_called_once()
        self.assertIsNone(self.backend._active)
        self.assertIsNone(handle.admission)
        self.assertIsNone(self.backend._prepared_source._entry)
        with closing(self.backend.begin_read()): pass
