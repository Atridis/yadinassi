"""Header-only format16 admission never grants a usable movement port."""
from contextlib import closing, ExitStack
from unittest.mock import patch
import unittest
from uuid import UUID, uuid4

import test_sqlite_transaction_source as fixture
from yadinassi import sqlite_accumulation_movements as movements
from yadinassi import sqlite_inventory_enum_profile as profile
from yadinassi import sqlite_catalog as storage
from yadinassi.catalog_backend import BackendError
from yadinassi.document_backend import DocumentKey


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
        from yadinassi.accumulation_movements import AccumulationReplacement
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
                    self.backend._prepared_source.clear()
                    with patch.object(movements, method, side_effect=BackendError('integrity')):
                        with self.assertRaises(BackendError):
                            self.backend.begin_write(uuid4()) if writer else self.backend.begin_read()
                    self.assertIsNone(self.backend._active)
                    self.assertIsNone(self.backend._prepared_source._entry)
                    with closing(self.backend.begin_read()): pass
