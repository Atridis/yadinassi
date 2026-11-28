import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_scalar_semantics import truth, typed_find, presentation, concatenate, UnsupportedScalarSemantics
from yadinassi.execution.codegen.direct_collections import _TypedMap
from yadinassi.execution.codegen.direct_structure import _DirectStructure

class ScalarSemanticsTests(unittest.TestCase):

    def test_truth_exact_numeric_and_boolean(self):
        for value, expected in [(True, True), (False, False), (0, False), (1, True), (Decimal(0), False), (Decimal(-2), True)]:
            self.assertIs(truth(value), expected)
        for value in [1.0, '', [], {}, None]:
            with self.assertRaises(TypeError):
                truth(value)

    def test_typed_find_number_boolean_and_missing(self):
        self.assertEqual(typed_find([True, Decimal(1)], Decimal(1)), Decimal(1))
        self.assertIs(type(typed_find([True, Decimal(1)], Decimal(1))), Decimal)
        self.assertIsNone(typed_find([], Decimal(1)))
        self.assertEqual(typed_find([True, Decimal(1)], True), Decimal(0))

    def test_typed_find_collections_identity_not_contents(self):
        for value, other in [([], []), ({}, {}), (_TypedMap(), _TypedMap()), (_DirectStructure(), _DirectStructure())]:
            self.assertIsNone(typed_find([value], other))
            self.assertEqual(typed_find([value], value), Decimal(0))

    def test_bsl_order_keeps_case_and_equality_separate(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Lower="a"; Upper="A"; R=(Lower<Upper); E=(Lower=Upper);')
        self.assertIs(vm.variables['r'], True)
        self.assertIs(vm.variables['e'], False)

    def test_order_number_boolean_coercion_survives_direct_translation(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=True; N=1; X=(T<=N); Y=(N<False);')
        self.assertIs(vm.variables['x'], True)
        self.assertIs(vm.variables['y'], False)

    def test_surrogate_pair_join(self):
        self.assertEqual(concatenate('\ud83d', '\ude00'), '😀')

    def test_host_hooks_never_called(self):
        events = []

        class Host:

            def __str__(self):
                events.append('str')
                return 'host'

            def __eq__(self, other):
                events.append('eq')
                return True

            def __bool__(self):
                events.append('bool')
                return True
        value = Host()
        with self.assertRaises(UnsupportedScalarSemantics):
            presentation(value)
        with self.assertRaises(UnsupportedScalarSemantics):
            typed_find([value], value)
        with self.assertRaises(TypeError):
            truth(value)
        self.assertIsNone(typed_find([value], Decimal(1)))
        self.assertEqual(events, [])

    def test_hostile_metaclass_does_not_run_during_scalar_admission(self):
        events = []

        class Meta(type):

            def __eq__(cls, other):
                events.append('meta')
                return True

        class Host(metaclass=Meta):

            def __str__(self):
                events.append('str')
                return 'unsafe'

            def __eq__(self, other):
                events.append('eq')
                return True
        value = Host()
        with self.assertRaises(UnsupportedScalarSemantics):
            presentation(value)
        with self.assertRaises(UnsupportedScalarSemantics):
            typed_find([], value)
        self.assertEqual(events, [])

    def test_presentations_have_fixed_expected_text(self):
        for value, expected in [([], 'Массив'), ({}, 'Структура'), (_TypedMap(), 'Соответствие'), (_DirectStructure(), 'Структура'), (True, 'Да'), (False, 'Нет'), (Decimal('1234.50'), '1\xa0234,5'), (None, '')]:
            with self.subTest(value=type(value).__name__):
                self.assertEqual(concatenate('x', value), 'x' + expected)
