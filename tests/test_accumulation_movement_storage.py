"""Borrowed-connection occurrence storage; no native profile is activated."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, localcontext
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi.accumulation_movements import (
    AccumulationDirection, AccumulationMovementRow, AccumulationRegisterSchema,
    AccumulationReplacement,
)
from yadinassi.catalog_backend import BackendError, FieldSchema
from yadinassi.document_backend import DocumentKey
from yadinassi.sqlite_accumulation_movements import (
    ACCUMULATION_DDL, AccumulationMovementPort, _hash, _json, schema_data,
)


class AccumulationStorageTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(self.c.close)
        self.c.execute('PRAGMA foreign_keys=ON')
        self.c.execute('CREATE TABLE document_schema(identity TEXT PRIMARY KEY)')
        self.c.execute('CREATE TABLE document_record(document_id TEXT,record_id TEXT,PRIMARY KEY(document_id,record_id))')
        self.db, self.doc, self.reg = uuid4(), uuid4(), uuid4()
        self.schema = AccumulationRegisterSchema(self.reg, 'Stock', (self.doc,),
            (FieldSchema(uuid4(), 'Item', 'string', (8,)),),
            (FieldSchema(uuid4(), 'Quantity', 'number', (10, 2, 'Any')),),
            (FieldSchema(uuid4(), 'Verified', 'boolean'),))
        for ddl in ACCUMULATION_DDL:
            self.c.execute(ddl)
        self.c.execute('INSERT INTO document_schema VALUES(?)', (str(self.doc),))
        self.c.execute('INSERT INTO accumulation_register_schema VALUES(?,?)',
                       (str(self.reg), _json(schema_data(self.schema))))
        self.c.execute('INSERT INTO accumulation_register_document VALUES(?,?)', (str(self.reg), str(self.doc)))
        self.key = DocumentKey(self.db, self.doc, uuid4())
        self.c.execute('INSERT INTO document_record VALUES(?,?)', (str(self.doc), str(self.key.record_id)))
        self.c.execute('BEGIN')
        self.port = AccumulationMovementPort(self.c, self.db, 1, (self.schema,))
        self.row = AccumulationMovementRow(1, datetime(2026, 1, 2, 3, 4, 5), True,
            AccumulationDirection.RECEIPT, ('A',), (Decimal('7.25'),), (False,))

    def request(self, key=None, rows=None):
        key = self.key if key is None else key
        return AccumulationReplacement(self.reg, key, (self.row,) if rows is None else rows,
                                       self.port.read(self.reg, key).snapshot)

    def other_key(self):
        key = replace(self.key, record_id=uuid4())
        self.c.execute('INSERT INTO document_record VALUES(?,?)', (str(self.doc), str(key.record_id)))
        return key

    def test_round_trip_keeps_period_direction_active_and_all_groups(self):
        rows = (self.row, replace(self.row, line_number=2, active=False,
                                direction=AccumulationDirection.EXPENSE, resources=(Decimal('-0.00'),)))
        request = self.request(rows=rows)
        outcome = self.port.replace(uuid4(), request)
        actual = self.port.read(self.reg, self.key)
        self.assertEqual(actual.rows, rows)
        self.assertIs(type(actual.rows[0].direction), AccumulationDirection)
        self.assertEqual(actual.rows[1].resources[0].as_tuple(), Decimal('-0.00').as_tuple())
        self.assertEqual(actual.snapshot, outcome.snapshot)
        self.assertEqual(outcome.row_count, 2)

    def test_identical_dimensions_periods_payloads_are_occurrences_not_unique_keys(self):
        rows = (self.row, replace(self.row, line_number=2))
        self.port.replace(uuid4(), self.request(rows=rows))
        other = self.other_key()
        self.port.replace(uuid4(), self.request(other, rows))
        self.assertEqual(self.port.read(self.reg, self.key).rows, rows)
        self.assertEqual(self.port.read(self.reg, other).rows, rows)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM accumulation_movement').fetchone(), (4,))

    def test_immutable_receipt_survives_later_partition_replacement(self):
        request, operation = self.request(), uuid4()
        outcome = self.port.replace(operation, request)
        self.port.replace(uuid4(), self.request(rows=()))
        self.assertEqual(self.port.resolve(operation, request), outcome)
        self.assertEqual(self.port.resolve(operation, request), outcome)
        self.assertEqual(self.port.read(self.reg, self.key).rows, ())

    def test_receipt_resolution_does_not_read_current_corrupt_movements(self):
        request, operation = self.request(), uuid4()
        outcome = self.port.replace(operation, request)
        self.c.execute("UPDATE accumulation_movement SET values_json='[]'")
        self.assertEqual(self.port.resolve(operation, request), outcome)
        with self.assertRaises(BackendError):
            self.port.read(self.reg, self.key)

    def test_empty_partition_revision_prevents_aba(self):
        original = self.request(rows=())
        self.port.replace(uuid4(), original)
        self.port.replace(uuid4(), self.request(rows=()))
        self.assertEqual(self.port.read(self.reg, self.key).revision, 2)
        with self.assertRaises(BackendError):
            self.port.replace(uuid4(), original)

    def test_stale_snapshot_cannot_replace_and_emits_no_receipt(self):
        request = self.request()
        self.port.replace(uuid4(), request)
        operation = uuid4()
        with self.assertRaises(BackendError) as caught:
            self.port.replace(operation, request)
        self.assertEqual(caught.exception.code, 'conflict')
        self.assertIsNone(self.port.resolve(operation, request))

    def test_duplicate_operation_never_replays_a_replacement(self):
        request, operation = self.request(), uuid4()
        outcome = self.port.replace(operation, request)
        with self.assertRaises(BackendError):
            self.port.replace(operation, self.request(rows=()))
        self.assertEqual(self.port.read(self.reg, self.key).snapshot, outcome.snapshot)
        self.assertEqual(self.port.resolve(operation, request), outcome)

    def test_outer_rollback_removes_rows_partition_and_receipt(self):
        request, operation = self.request(), uuid4()
        self.port.replace(operation, request)
        self.assertTrue(self.c.in_transaction)
        self.c.execute('ROLLBACK')
        self.c.execute('BEGIN')
        self.assertEqual(self.port.read(self.reg, self.key).revision, 0)
        self.assertIsNone(self.port.resolve(operation, request))

    def test_missing_recorder_fk_rolls_back_only_new_partition(self):
        original = self.port.replace(uuid4(), self.request())
        missing = replace(self.key, record_id=uuid4())
        request, operation = self.request(missing), uuid4()
        with self.assertRaises(sqlite3.IntegrityError):
            self.port.replace(operation, request)
        self.assertTrue(self.c.in_transaction)
        self.assertEqual(self.port.read(self.reg, self.key).snapshot, original.snapshot)
        self.assertEqual(self.port.read(self.reg, missing).revision, 0)
        self.assertIsNone(self.port.resolve(operation, request))

    def test_requires_caller_transaction_and_never_creates_one(self):
        request = self.request()
        self.c.execute('ROLLBACK')
        for action in (lambda: self.port.read(self.reg, self.key),
                       lambda: self.port.scan(self.reg), lambda: self.port.describe(request),
                       lambda: self.port.replace(uuid4(), request), lambda: self.port.resolve(uuid4(), request)):
            with self.subTest(action=action), self.assertRaises(BackendError) as caught:
                action()
            self.assertEqual(caught.exception.code, 'closed')
            self.assertFalse(self.c.in_transaction)

    def test_construction_does_not_install_ddl_or_start_transaction(self):
        connection = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(connection.close)
        connection.execute('PRAGMA foreign_keys=ON')
        AccumulationMovementPort(connection, self.db, 1, (self.schema,))
        self.assertEqual(connection.execute('SELECT name FROM sqlite_master').fetchall(), [])
        self.assertFalse(connection.in_transaction)

    def test_foreign_keys_and_exact_constructor_inputs_are_required(self):
        connection = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(connection.close)
        with self.assertRaises(BackendError):
            AccumulationMovementPort(connection, self.db, 1, (self.schema,))
        for generation in (True, 0, -1, 2**63):
            with self.subTest(generation=generation), self.assertRaises(BackendError):
                AccumulationMovementPort(self.c, self.db, generation, (self.schema,))
        with self.assertRaises(BackendError):
            AccumulationMovementPort(self.c, self.db, 1, (self.schema, self.schema))

    def test_database_and_generation_are_snapshot_domains(self):
        snapshot = self.port.read(self.reg, self.key).snapshot
        changed_generation = AccumulationMovementPort(self.c, self.db, 2, (self.schema,))
        self.assertNotEqual(changed_generation.read(self.reg, self.key).snapshot, snapshot)
        other_db = uuid4()
        changed_database = AccumulationMovementPort(self.c, other_db, 1, (self.schema,))
        self.assertNotEqual(changed_database.read(self.reg, replace(self.key, database_id=other_db)).snapshot, snapshot)

    def test_describe_binds_period_active_direction_and_groups(self):
        request = self.request()
        digest = self.port.describe(request)[0]
        for row in (replace(self.row, period=datetime(2026, 1, 3)), replace(self.row, active=False),
                    replace(self.row, direction=AccumulationDirection.EXPENSE),
                    replace(self.row, dimensions=('B',)), replace(self.row, resources=(Decimal('8'),)),
                    replace(self.row, attributes=(True,))):
            with self.subTest(row=row):
                self.assertNotEqual(self.port.describe(replace(request, rows=(row,)))[0], digest)

    def test_scan_is_bounded_raw_occurrences_including_empty_partitions(self):
        other = self.other_key()
        self.port.replace(uuid4(), self.request())
        self.port.replace(uuid4(), self.request(other, ()))
        result = dict(self.port.scan(self.reg))
        self.assertEqual(result[self.key].rows, (self.row,))
        self.assertEqual(result[other].rows, ())
        self.assertEqual(result[other].revision, 1)

    def test_wrong_schema_definition_or_recorder_binding_is_integrity_error(self):
        self.c.execute("UPDATE accumulation_register_schema SET definition='[]'")
        with self.assertRaises(BackendError):
            self.port.read(self.reg, self.key)
        self.c.execute('UPDATE accumulation_register_schema SET definition=?', (_json(schema_data(self.schema)),))
        self.c.execute('DELETE FROM accumulation_register_document')
        with self.assertRaises(BackendError):
            self.port.read(self.reg, self.key)

    def test_corrupt_scalar_shape_tags_or_noncanonical_json_is_rejected(self):
        self.port.replace(uuid4(), self.request())
        for raw in ('[]', '[[["s","A"]],[["n","7.250"]],[["b",false]]]',
                    '[[["s","A"]],[["n",7.25]],[["b",false]]]',
                    '[[["s","A"]],[["n","NaN"]],[["b",false]]]',
                    '[[["s","A"]],[["n","7.25"]],[["b",0]]]',
                    ' [[["s","A"]],[["n","7.25"]],[["b",false]]]'):
            with self.subTest(raw=raw):
                self.c.execute('UPDATE accumulation_movement SET values_json=?', (raw,))
                with self.assertRaises(BackendError) as caught:
                    self.port.read(self.reg, self.key)
                self.assertEqual(caught.exception.code, 'integrity')

    def test_corrupt_period_direction_active_or_line_is_rejected(self):
        request = self.request()
        self.port.replace(uuid4(), request)
        self.c.execute('PRAGMA ignore_check_constraints=ON')
        for column, corrupt, original in (('period', '20260230000000', '20260102030405'),
                                          ('direction', 'Receipt', 'receipt'),
                                          ('active', 2, 1), ('line_number', 2, 1)):
            with self.subTest(column=column):
                self.c.execute('UPDATE accumulation_movement SET ' + column + '=?', (corrupt,))
                with self.assertRaises(BackendError):
                    self.port.read(self.reg, self.key)
                self.c.execute('UPDATE accumulation_movement SET ' + column + '=?', (original,))

    def test_orphaned_recorder_is_not_hidden_on_read_or_scan(self):
        self.port.replace(uuid4(), self.request())
        self.c.execute('PRAGMA defer_foreign_keys=ON')
        self.c.execute('DELETE FROM document_record')
        with self.assertRaises(BackendError):
            self.port.read(self.reg, self.key)
        with self.assertRaises(BackendError):
            self.port.scan(self.reg)

    def test_row_and_partition_payload_budgets_apply_before_writes(self):
        request = self.request()
        for constant in ('MAX_ROW_BYTES', 'MAX_BYTES'):
            with self.subTest(constant=constant), patch('yadinassi.sqlite_accumulation_movements.' + constant, 1):
                with self.assertRaises(BackendError):
                    self.port.replace(uuid4(), request)
        self.assertEqual(self.port.read(self.reg, self.key).revision, 0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM accumulation_movement_receipt').fetchone(), (0,))

    def test_database_row_budget_rolls_back_rows_revision_and_receipt(self):
        original = self.port.replace(uuid4(), self.request())
        request, operation = self.request(rows=(self.row, replace(self.row, line_number=2))), uuid4()
        with patch('yadinassi.sqlite_accumulation_movements.MAX_DATABASE_ROWS', 1), self.assertRaises(BackendError):
            self.port.replace(operation, request)
        self.assertEqual(self.port.read(self.reg, self.key).snapshot, original.snapshot)
        self.assertIsNone(self.port.resolve(operation, request))

    def test_database_byte_budget_failure_keeps_previous_state(self):
        request, operation = self.request(), uuid4()
        with patch('yadinassi.sqlite_accumulation_movements.MAX_DATABASE_BYTES', 1), self.assertRaises(BackendError):
            self.port.replace(operation, request)
        self.assertEqual(self.port.read(self.reg, self.key).revision, 0)
        self.assertIsNone(self.port.resolve(operation, request))

    def test_partition_budget_includes_empty_partitions(self):
        self.port.replace(uuid4(), self.request(rows=()))
        other = self.other_key()
        request, operation = self.request(other, ()), uuid4()
        with patch('yadinassi.sqlite_accumulation_movements.MAX_DATABASE_PARTITIONS', 1), self.assertRaises(BackendError):
            self.port.replace(operation, request)
        self.assertEqual(self.port.read(self.reg, other).revision, 0)
        self.assertIsNone(self.port.resolve(operation, request))

    def test_receipt_budget_does_not_prune_or_mutate_old_receipts(self):
        request, operation = self.request(), uuid4()
        original = self.port.replace(operation, request)
        with patch('yadinassi.sqlite_accumulation_movements.MAX_DATABASE_RECEIPTS', 1), self.assertRaises(BackendError):
            self.port.replace(uuid4(), self.request(rows=()))
        self.assertEqual(self.port.resolve(operation, request), original)
        self.assertEqual(self.port.read(self.reg, self.key).snapshot, original.snapshot)

    def test_read_and_scan_enforce_payload_budgets(self):
        self.port.replace(uuid4(), self.request())
        with patch('yadinassi.sqlite_accumulation_movements.MAX_ROW_BYTES', 1), self.assertRaises(BackendError):
            self.port.read(self.reg, self.key)
        with patch('yadinassi.sqlite_accumulation_movements.MAX_DATABASE_ROWS', 0), self.assertRaises(BackendError):
            self.port.scan(self.reg)

    def test_missing_receipt_is_none_and_different_request_cannot_resolve(self):
        request, operation = self.request(), uuid4()
        self.assertIsNone(self.port.resolve(operation, request))
        self.port.replace(operation, request)
        changed = replace(request, rows=(replace(self.row, direction=AccumulationDirection.EXPENSE),))
        with self.assertRaises(BackendError):
            self.port.resolve(operation, changed)
        with self.assertRaises(BackendError):
            self.port.resolve(operation, self.request())

    def test_corrupt_receipt_shapes_are_rejected(self):
        request, operation = self.request(), uuid4()
        self.port.replace(operation, request)
        for raw in ('[]', 'null', 'x' * 4097, '[NaN]', '["accumulation_outcome_v1",NaN,0,0,0,0,0]', '{'):
            with self.subTest(raw=raw[:20]):
                self.c.execute('UPDATE accumulation_movement_receipt SET outcome_json=?', (raw,))
                with self.assertRaises(BackendError) as caught:
                    self.port.resolve(operation, request)
                self.assertEqual(caught.exception.code, 'integrity')

    def test_rebound_receipt_still_requires_the_original_snapshot_outcome(self):
        request, operation = self.request(), uuid4()
        self.port.replace(operation, request)
        raw = self.c.execute('SELECT outcome_json FROM accumulation_movement_receipt').fetchone()[0]
        data = json.loads(raw)
        data[5] = '0' * 64
        raw = _json(data)
        digest = self.port.describe(request)[0]
        self.c.execute('UPDATE accumulation_movement_receipt SET request_hash=?,outcome_json=?',
                       (_hash([digest, raw]), raw))
        with self.assertRaises(BackendError) as caught:
            self.port.resolve(operation, request)
        self.assertEqual(caught.exception.code, 'integrity')

    def test_decimal_round_trip_ignores_host_precision_and_traps(self):
        request = self.request()
        with localcontext() as context:
            context.prec = 1
            context.Emin, context.Emax = -1, 1
            for signal in context.traps:
                context.traps[signal] = True
            self.port.replace(uuid4(), request)
            self.assertEqual(self.port.read(self.reg, self.key).rows, request.rows)

    def test_accumulation_tables_do_not_touch_recorder_ir_storage(self):
        self.c.execute('CREATE TABLE recorder_movement(marker TEXT)')
        self.c.execute("INSERT INTO recorder_movement VALUES('unchanged')")
        self.port.replace(uuid4(), self.request())
        self.assertEqual(self.c.execute('SELECT * FROM recorder_movement').fetchall(), [('unchanged',)])
        columns = {row[1] for row in self.c.execute('PRAGMA table_info(accumulation_movement)')}
        self.assertNotIn('dimension_key', columns)
