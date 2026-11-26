import unittest
from unittest.mock import patch
from yadinassi.types import values

class ResourceIntegrationTests(unittest.TestCase):

    def test_huge_bad_index_diagnostic_does_not_expand_integer(self):
        from decimal import Decimal
        from yadinassi.types import array_index as module
        from yadinassi import BSLError, Interpreter
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.variables['huge'] = Decimal('1e1000000')
        with patch.object(module, 'int', side_effect=AssertionError('integer expansion'), create=True):
            with self.assertRaisesRegex(BSLError, 'Индекс массива вне границ'):
                vm.execute('A=New Array(1); R=A[Huge];')

    def test_trusted_local_constructor_does_not_adopt_artificial_cap(self):
        from yadinassi import Interpreter
        vm = Interpreter();self.addCleanup(vm.close)
        with patch.object(values, '_MAX_ARRAY_CONSTRUCTION', 4):
            vm.execute('a=New Array(5);')
        self.assertEqual(vm.variables['a'], [None]*5)

    def test_trusted_local_insert_does_not_adopt_artificial_growth_cap(self):
        from yadinassi import Interpreter
        vm = Interpreter();self.addCleanup(vm.close)
        with patch.object(values, '_MAX_INSERT_GROWTH', 4):
            vm.execute('b=New Array; b.Insert(5,9);')
        self.assertEqual(vm.variables['b'], [None]*5+[9])
