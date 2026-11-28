"""Ordinary ValueStorage shares the bounded codec, not Source authority."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_plain_map import PlainMap
from yadinassi.formats.storage.value_storage import BSLValueStorage, SnapshotError, capture, restore
from yadinassi.streams.data_compression import BSLDeflation


class DirectValueStorageTests(unittest.TestCase):
    def test_native_map_keeps_lookup_semantics_and_fresh_payload(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('M=New Map; A=New Array; A.Add(7); M.Insert(1,"number"); M.Insert(True,A); '
                   'S=New ValueStorage(M); A[0]=9; First=S.Get(); '
                   'A1=First.Get(True); A1[0]=8; Second=S.Get(); A2=Second.Get(True);')
        first, second = vm.variables['first'], vm.variables['second']
        self.assertIs(type(first), PlainMap)
        self.assertIs(type(second), PlainMap)
        self.assertIsNot(first, second)
        self.assertEqual(first.get(Decimal(1)), 'number')
        self.assertEqual(second.get(1), 'number')
        self.assertEqual(vm.execute('A1[0]'), 8)
        self.assertEqual(vm.execute('A2[0]'), 7)
        self.assertEqual(vm.execute('A[0]'), 9)

    def test_capture_budget_cycles_and_no_generic_mapping_admission(self):
        value = PlainMap({1: 2})
        value[True] = 3
        restored = restore(capture(value, _source_direct=True))
        self.assertEqual((restored.get(True), restored.get(1)), (Decimal(3), Decimal(2)))
        with self.assertRaises(SnapshotError):
            BSLValueStorage(value)  # The host constructor contract stays exact.
        with self.assertRaises(SnapshotError):
            capture({1: 2}, _source_direct=True)
        value['cycle'] = value
        with self.assertRaisesRegex(SnapshotError, 'cyclic'):
            capture(value, _source_direct=True)

    def test_constructor_checks_original_factory_after_arguments(self):
        vm = Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        def change():
            vm.types.pop('хранилищезначения')
            return Decimal(1)
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):
            vm.execute('S=New ValueStorage(Change());')
        self.assertNotIn('s',vm.variables)

    def test_compression_class_sealed_before_constructor_effect(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        calls = []
        with patch.object(BSLDeflation,'__init__',lambda *_:calls.append(1)):
            with self.assertRaises(BoundaryViolation):
                vm.execute('S=New ValueStorage("payload",New Deflation());')
        self.assertEqual(calls,[])
