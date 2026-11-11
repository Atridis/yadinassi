"""Exact host resource sums, without native direction or query assumptions."""
from dataclasses import replace
from decimal import Decimal, Inexact, ROUND_UP, localcontext
from enum import Enum
import unittest
from uuid import uuid4

from yadinassi.accumulation_movements import (
    AccumulationDirection, AccumulationRegisterSchema, MAX_FIELDS,
    MAX_MOVEMENT_ROWS, _sum_resource_vectors,
)
from yadinassi.catalog_backend import BackendError, FieldSchema


def _schema(*qualifiers):
    return AccumulationRegisterSchema(uuid4(), 'Stock', (uuid4(),), (), tuple(
        FieldSchema(uuid4(), f'Resource{index}', 'number', qualifier)
        for index, qualifier in enumerate(qualifiers)))


class AccumulationResourceArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.schema = _schema((38, 0, 'Any'), (38, 2, 'Any'))

    def reject(self, schema, vectors, weights):
        with self.assertRaises(BackendError) as caught:
            _sum_resource_vectors(schema, vectors, weights)
        self.assertEqual(caught.exception.code, 'invalid_input')

    def test_weighted_vectors_keep_resource_scales_and_duplicate_occurrences(self):
        vectors = ((Decimal('1E+2'), Decimal('-1.2300')),
                   (Decimal('1E+2'), Decimal('-1.2300')),
                   (Decimal('-3'), Decimal('2.50')))
        weights = (1, 1, -1)
        before = tuple(tuple(value.as_tuple() for value in row) for row in vectors)
        result = _sum_resource_vectors(self.schema, vectors, weights)
        self.assertEqual(result, (Decimal('203'), Decimal('-4.96')))
        self.assertEqual(tuple(value.as_tuple().exponent for value in result), (0, -2))
        self.assertIs(type(result), tuple)
        self.assertTrue(all(type(value) is Decimal for value in result))
        self.assertEqual(tuple(tuple(value.as_tuple() for value in row) for row in vectors), before)
        self.assertEqual(weights, (1, 1, -1))
        with self.assertRaises(TypeError):
            result[0] = Decimal(0)

    def test_full_row_budget_is_exact_for_precision38_and_heterogeneous_scales(self):
        scales = (0, 19, 38)
        schema = _schema(*((38, scale, 'Any') for scale in scales))
        vector = tuple(Decimal((0, (9,) * 38, -scale)) for scale in scales)
        result = _sum_resource_vectors(schema, (vector,) * MAX_MOVEMENT_ROWS,
                                       (1,) * MAX_MOVEMENT_ROWS)
        # 10000 occurrences require 42 coefficient digits, not Decimal's 28.
        self.assertEqual(MAX_MOVEMENT_ROWS, 10000)
        expected = tuple(Decimal((0, (9,) * 38 + (0,) * 4, -scale)) for scale in scales)
        self.assertEqual(tuple(value.as_tuple() for value in result),
                         tuple(value.as_tuple() for value in expected))

    def test_exact_cancellation_survives_wide_intermediates_and_order_changes(self):
        schema = _schema((38, 2, 'Any'))
        large = Decimal((0, (9,) * 38, -2))
        vectors = ((large,), (large,), (Decimal('0.01'),), (large,), (large,))
        weights = (1, 1, 1, -1, -1)
        for rows, signs in ((vectors, weights), (vectors[::-1], weights[::-1])):
            with self.subTest(reversed=rows is not vectors):
                result = _sum_resource_vectors(schema, rows, signs)
                self.assertEqual(result[0].as_tuple(), Decimal('0.01').as_tuple())
        self.assertEqual(_sum_resource_vectors(schema, ((large,), (large,)), (1, -1)),
                         (Decimal('0.00'),))

    def test_empty_and_signed_zero_inputs_produce_positive_zeros_at_declared_scales(self):
        for vectors, weights in (((), ()),
                (((Decimal('-0E+999999999'), Decimal('-0E-999999999')),), (-1,))):
            with self.subTest(vectors=vectors):
                result = _sum_resource_vectors(self.schema, vectors, weights)
                self.assertEqual(tuple(value.as_tuple() for value in result),
                                 (Decimal('0').as_tuple(), Decimal('0.00').as_tuple()))

    def test_nonnegative_qualifier_limits_inputs_not_weighted_results(self):
        schema = _schema((3, 1, 'Nonnegative'))
        self.assertEqual(_sum_resource_vectors(schema, ((Decimal('99.9'),),) * 2, (-1, -1)),
                         (Decimal('-199.8'),))
        self.reject(schema, ((Decimal('-0.1'),),), (-1,))

    def test_hostile_decimal_context_and_existing_flags_are_unchanged(self):
        schema = _schema((38, 38, 'Any'), (38, 0, 'Any'))
        vectors = ((Decimal((0, (9,) * 38, -38)), Decimal((0, (9,) * 38, 0))),) * 2
        expected = (Decimal('1.' + '9' * 37 + '8'), Decimal('1' + '9' * 37 + '8'))
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_UP
            context.Emin = context.Emax = 0
            context.clamp = 1
            for signal in context.traps:
                context.traps[signal] = True
            context.clear_flags()
            context.flags[Inexact] = True
            before = context.copy()
            self.assertEqual(_sum_resource_vectors(schema, vectors, (1, 1)), expected)
            self.reject(schema, ((Decimal('1E-999999999'), Decimal(1)),), (1,))
            for attribute in ('prec', 'rounding', 'Emin', 'Emax', 'clamp', 'flags', 'traps'):
                self.assertEqual(getattr(context, attribute), getattr(before, attribute))

    def test_container_types_and_matching_vector_dimensions_are_strict(self):
        class TupleSubclass(tuple):
            pass
        class Unreadable:
            def __iter__(self):
                raise AssertionError('must refuse without reading')
        row = (Decimal(1), Decimal('1.00'))
        for vectors, weights in (([row], (1,)), (TupleSubclass((row,)), (1,)),
                (Unreadable(), (1,)), ((row,), [1]), ((row,), TupleSubclass((1,))),
                ((row,), Unreadable()), ((list(row),), (1,)),
                ((TupleSubclass(row),), (1,)), (((Decimal(1),),), (1,)),
                ((row + (Decimal(1),),), (1,)), ((row,), ()), ((), (1,))):
            with self.subTest(vectors=vectors, weights=weights):
                self.reject(self.schema, vectors, weights)

    def test_weights_are_exact_plus_or_minus_one_not_boolean_or_direction(self):
        class IntSubclass(int):
            pass
        class Other(Enum):
            PLUS = 1
        for weight in (0, 2, -2, True, False, Decimal(1), 1.0, '1', None,
                       IntSubclass(1), Other.PLUS, *AccumulationDirection):
            with self.subTest(weight=weight):
                self.reject(self.schema, ((Decimal(1), Decimal(1)),), (weight,))

    def test_resources_refuse_scalar_coercion_decimal_subclasses_and_nonfinite(self):
        class DecimalSubclass(Decimal):
            pass
        for value in (1, True, 1.0, '1', None, DecimalSubclass('1'), Decimal('NaN'),
                      Decimal('sNaN'), Decimal('Infinity'), Decimal('-Infinity')):
            with self.subTest(value=repr(value)):
                self.reject(self.schema, ((value, Decimal(1)),), (1,))

    def test_input_rounding_clamping_and_extreme_nonzero_exponents_are_refused(self):
        schema = _schema((3, 2, 'Any'))
        for value in ('1.001', '-1.001', '10', '-10', '1E+999999999', '1E-999999999'):
            with self.subTest(value=value):
                self.reject(schema, ((Decimal(value),),), (1,))

    def test_schema_is_validated_even_for_empty_vectors(self):
        resource = self.schema.resources[0]
        for schema in (None, replace(self.schema, resources=()),
                replace(self.schema, resources=[resource]),
                replace(self.schema, resources=(object(),)),
                replace(self.schema, resources=(replace(resource, qualifiers=(39, 0, 'Any')),)),
                replace(self.schema, resources=(replace(resource, qualifiers=(38, True, 'Any')),)),
                replace(self.schema, resources=(resource, resource))):
            with self.subTest(schema=schema):
                self.reject(schema, (), ())
        for resource in (replace(resource, kind='string', qualifiers=(10,)),
                         replace(resource, target_catalog_id=uuid4())):
            with self.subTest(resource=resource), self.assertRaises(BackendError) as caught:
                _sum_resource_vectors(replace(self.schema, resources=(resource,)), (), ())
            self.assertEqual(caught.exception.code, 'unsupported')

    def test_row_field_and_decimal_budgets_refuse_without_mutating_inputs(self):
        row = (Decimal(1), Decimal(1))
        self.reject(self.schema, (row,) * (MAX_MOVEMENT_ROWS + 1), (1,) * (MAX_MOVEMENT_ROWS + 1))
        schema = _schema(*((38, 0, 'Any'),) * MAX_FIELDS)
        self.assertEqual(_sum_resource_vectors(schema, (), ()), (Decimal(0),) * MAX_FIELDS)
        self.reject(_schema(*((38, 0, 'Any'),) * (MAX_FIELDS + 1)), (), ())
        # Numerically valid, but its oversized stored coefficient must not be
        # silently reduced before the existing Decimal allocation budget check.
        oversized = Decimal('1.' + '0' * 10000)
        vectors, weights = (row, (oversized, Decimal(1))), (1, 1)
        before = oversized.as_tuple()
        self.reject(self.schema, vectors, weights)
        self.assertEqual(oversized.as_tuple(), before)
        self.assertIs(vectors[0], row)
        self.assertIs(vectors[1][0], oversized)
        self.assertEqual(weights, (1, 1))
