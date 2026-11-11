"""Strict host accumulation intents, not native accumulation observations."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from enum import Enum
import unittest
from uuid import UUID, uuid4

from yadinassi.accumulation_movements import (
    AccumulationDirection, AccumulationMovementRow, AccumulationRegisterKind,
    AccumulationRegisterSchema, AccumulationReplacement, mutation_identity,
    validate_replacement, validate_schema,
)
from yadinassi.catalog_backend import BackendError, FieldSchema
from yadinassi.document_backend import DocumentKey
from yadinassi.document_movements import RecorderReplacement, mutation_identity as recorder_identity


class AccumulationIntentTests(unittest.TestCase):
    def setUp(self):
        self.db, self.doc, self.reg = uuid4(), uuid4(), uuid4()
        self.schema = AccumulationRegisterSchema(
            self.reg, 'Stock', (self.doc,),
            (FieldSchema(uuid4(), 'Item', 'string', (8,)),),
            (FieldSchema(uuid4(), 'Quantity', 'number', (10, 2, 'Any')),),
            (FieldSchema(uuid4(), 'Verified', 'boolean'),
             FieldSchema(uuid4(), 'CheckedAt', 'datetime', ('DateTime',))))
        self.row = AccumulationMovementRow(1, datetime(2026, 1, 2, 3, 4, 5), True,
            AccumulationDirection.RECEIPT, ('A',), (Decimal('7.25'),),
            (False, datetime(2026, 1, 1)))
        self.request = AccumulationReplacement(self.reg, DocumentKey(self.db, self.doc, uuid4()),
                                               (self.row,), '0' * 64)

    def check(self, request=None, schema=None):
        return validate_replacement(self.schema if schema is None else schema,
                                    self.request if request is None else request, self.db)

    def reject_row(self, row):
        with self.assertRaises(BackendError):
            self.check(replace(self.request, rows=(row,)))

    def test_valid_partition_retains_exact_typed_payload(self):
        self.assertIs(self.check(), self.request)

    def test_direction_is_exact_enum_not_scalar_or_foreign_enum(self):
        class Other(Enum):
            RECEIPT = 'receipt'
        for value in (True, False, 1, 0, -1, 'receipt', 'expense', Decimal(1), Other.RECEIPT, None):
            with self.subTest(value=value):
                self.reject_row(replace(self.row, direction=value))

    def test_both_directions_accept_negative_zero_and_positive_resources_without_arithmetic(self):
        for direction in AccumulationDirection:
            for value in (Decimal('-7.25'), Decimal('-0.00'), Decimal('7.25')):
                with self.subTest(direction=direction, value=value):
                    row = replace(self.row, direction=direction, resources=(value,))
                    self.assertIs(self.check(replace(self.request, rows=(row,))).rows[0], row)

    def test_register_kind_is_exact_balance_enum(self):
        self.assertIs(self.schema.kind, AccumulationRegisterKind.BALANCE)
        for kind in ('balance', 'Balance', True, 0, None, AccumulationDirection.RECEIPT):
            with self.subTest(kind=kind), self.assertRaises(BackendError):
                self.check(schema=replace(self.schema, kind=kind))

    def test_period_requires_exact_naive_second_datetime(self):
        class DateSubclass(datetime):
            pass
        for value in ('20260102030405', self.row.period.date(), DateSubclass(2026, 1, 1),
                      self.row.period.replace(tzinfo=timezone.utc), self.row.period.replace(microsecond=1)):
            with self.subTest(value=value):
                self.reject_row(replace(self.row, period=value))

    def test_active_requires_exact_boolean_and_lines_require_contiguous_integers(self):
        self.reject_row(replace(self.row, active=1))
        for line in (True, Decimal(1), 0, 2, -1):
            with self.subTest(line=line):
                self.reject_row(replace(self.row, line_number=line))
        with self.assertRaises(BackendError):
            self.check(replace(self.request, rows=(self.row, self.row)))

    def test_duplicate_payloads_are_distinct_occurrences(self):
        rows = (self.row, replace(self.row, line_number=2))
        self.assertEqual(self.check(replace(self.request, rows=rows)).rows, rows)

    def test_dimension_resource_and_attribute_groups_are_exact_tuples(self):
        for field in ('dimensions', 'resources', 'attributes'):
            for value in (list(getattr(self.row, field)), (), None):
                with self.subTest(field=field, value=value):
                    self.reject_row(replace(self.row, **{field: value}))

    def test_scalar_values_are_not_coerced(self):
        for value in (7, 7.25, True, '7.25', None):
            with self.subTest(value=value):
                self.reject_row(replace(self.row, resources=(value,)))
        self.reject_row(replace(self.row, dimensions=(1,)))
        self.reject_row(replace(self.row, attributes=(0, self.row.attributes[1])))

    def test_number_qualifiers_reject_rounding_clamping_and_nonfinite_values(self):
        for value in (Decimal('1.001'), Decimal('100000000'), Decimal('NaN'),
                      Decimal('sNaN'), Decimal('Infinity'), Decimal('-Infinity'),
                      Decimal('1E+999999999'), Decimal('1E-999999999')):
            with self.subTest(value=str(value)):
                self.reject_row(replace(self.row, resources=(value,)))

    def test_nonnegative_qualifier_rejects_negative_instead_of_converting(self):
        resource = replace(self.schema.resources[0], qualifiers=(10, 2, 'Nonnegative'))
        with self.assertRaises(BackendError):
            self.check(replace(self.request, rows=(replace(self.row, resources=(Decimal('-1'),)),)),
                       replace(self.schema, resources=(resource,)))

    def test_string_qualifier_rejects_truncation_and_malformed_unicode(self):
        for value in ('123456789', '\U0001f600' * 5, '\ud800', 'A\udfff'):
            with self.subTest(value=repr(value)):
                self.reject_row(replace(self.row, dimensions=(value,)))

    def test_attribute_date_is_strict_too(self):
        for value in (self.row.period.replace(microsecond=1), self.row.period.replace(tzinfo=timezone.utc)):
            with self.subTest(value=value):
                self.reject_row(replace(self.row, attributes=(False, value)))

    def test_ambient_decimal_context_cannot_change_valid_intent(self):
        with localcontext() as context:
            context.prec = 1
            context.Emin, context.Emax = -1, 1
            for signal in context.traps:
                context.traps[signal] = True
            self.assertIs(self.check(), self.request)

    def test_empty_replacement_still_requires_snapshot_and_valid_schema(self):
        empty = replace(self.request, rows=())
        self.assertIs(self.check(empty), empty)
        for snapshot in (None, '', '0' * 63, 'A' * 64, 'g' * 64):
            with self.subTest(snapshot=snapshot), self.assertRaises(BackendError):
                self.check(replace(empty, expected_snapshot=snapshot))
        with self.assertRaises(BackendError):
            self.check(empty, replace(self.schema, resources=()))

    def test_schema_qualifiers_are_validated_before_any_rows(self):
        for qualifiers in ((), (0, 0, 'Any'), (39, 0, 'Any'), (10, 11, 'Any'),
                           (True, 0, 'Any'), (10, False, 'Any'), (10, 2, 'other'), [10, 2, 'Any']):
            with self.subTest(qualifiers=qualifiers), self.assertRaises(BackendError):
                self.check(replace(self.request, rows=()), replace(self.schema,
                    resources=(replace(self.schema.resources[0], qualifiers=qualifiers),)))

    def test_resources_must_be_numeric_and_references_are_unsupported(self):
        with self.assertRaises(BackendError):
            validate_schema(replace(self.schema, resources=(FieldSchema(uuid4(), 'Note', 'string', (8,)),)))
        with self.assertRaises(BackendError):
            validate_schema(replace(self.schema, dimensions=(
                FieldSchema(uuid4(), 'ItemRef', 'catalog_ref', (), uuid4()),)))

    def test_schema_identity_and_names_are_unique_across_all_groups(self):
        for attribute in (replace(self.schema.attributes[0], identity=self.schema.resources[0].identity),
                          replace(self.schema.attributes[0], name='qUaNtItY'),
                          replace(self.schema.attributes[0], name='Period'),
                          replace(self.schema.attributes[0], identity=self.reg)):
            with self.subTest(attribute=attribute), self.assertRaises(BackendError):
                validate_schema(replace(self.schema, attributes=(attribute,)))

    def test_schema_and_recorder_shapes_are_bounded_exact_types(self):
        for changes in ({'name': ''}, {'name': '\ud800'}, {'name': 'A' * 129},
                        {'recorder_documents': ()}, {'recorder_documents': (self.doc, self.doc)},
                        {'recorder_documents': [self.doc]}, {'dimensions': []},
                        {'identity': UUID(int=0)}, {'resources': (object(),)}):
            with self.subTest(changes=changes), self.assertRaises(BackendError):
                validate_schema(replace(self.schema, **changes))

    def test_zero_dimensions_are_a_host_storage_shape_not_a_query_claim(self):
        schema = replace(self.schema, dimensions=())
        request = replace(self.request, rows=(replace(self.row, dimensions=()),))
        self.assertIs(self.check(request, schema), request)

    def test_wrong_database_register_or_recorder_cannot_write(self):
        for request in (replace(self.request, register_id=uuid4()),
                        replace(self.request, recorder=replace(self.request.recorder, database_id=uuid4())),
                        replace(self.request, recorder=replace(self.request.recorder, document_id=uuid4())),
                        replace(self.request, recorder=replace(self.request.recorder, record_id=UUID(int=0)))):
            with self.subTest(request=request), self.assertRaises(BackendError):
                self.check(request)

    def test_row_and_field_budgets_are_checked(self):
        from unittest.mock import patch
        with patch('yadinassi.accumulation_movements.MAX_MOVEMENT_ROWS', 0), self.assertRaises(BackendError):
            self.check()
        with patch('yadinassi.accumulation_movements.MAX_FIELDS', 1), self.assertRaises(BackendError):
            validate_schema(self.schema)

    def test_mutation_domain_is_separate_and_recorder_scoped(self):
        other = replace(self.request, recorder=replace(self.request.recorder, record_id=uuid4()))
        ir = RecorderReplacement(self.reg, self.request.recorder, (), '0' * 64)
        self.assertNotEqual(mutation_identity(self.request), mutation_identity(other))
        self.assertNotEqual(mutation_identity(self.request), recorder_identity(ir))
        self.assertEqual(mutation_identity(self.request)[0], 'accumulation_movement')
