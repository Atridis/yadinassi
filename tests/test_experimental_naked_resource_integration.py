import os
import unittest
from unittest.mock import patch
from yadinassi import values
from yadinassi.experimental_naked_boundaries import BoundaryContext

class ResourceIntegrationTests(unittest.TestCase):

    def test_huge_bad_index_diagnostic_does_not_expand_integer(self):
        from decimal import Decimal
        from yadinassi import experimental_naked_collections as module
        with patch.object(module, 'int', side_effect=AssertionError('integer expansion'), create=True):
            with self.assertRaises(IndexError):
                module._checked_array_index([], Decimal('1e1000000'))
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
