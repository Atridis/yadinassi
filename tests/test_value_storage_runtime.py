"""ValueStorage local contract and exact source-bound native comparison slice."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi.runtime import Interpreter
from yadinassi.serialization import value_to_string_internal
from yadinassi.type_values import type_by_name, type_of
from yadinassi.value_storage import BSLValueStorage, Snapshot, SnapshotError, capture
from yadinassi.values import BSLArray, BSLType, NULL
from yadinassi.file_io import BSLBinaryData
from yadinassi.dates import BSLDate
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.value_tables import BSLValueTable
from yadinassi.values import BSLFixedArray
from yadinassi.structures import BSLStructure, BSLFixedStructure
from yadinassi.maps import BSLMap, BSLFixedMap

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "value_storage"


def array(*items):
    result = BSLArray()
    result.items = list(items)
    return result


class ValueStorageRuntimeTests(unittest.TestCase):
    def test_01_type_aliases_and_constructor(self):
        vm = Interpreter()
        vm.execute('A = Новый ХранилищеЗначения(1); B = New ValueStorage(2); '
                   'X = A.Получить(); Y = B.Get();')
        self.assertEqual(vm.variables['x'], Decimal(1))
        self.assertEqual(vm.variables['y'], Decimal(2))
        self.assertIs(type_by_name('ХранилищеЗначения'), BSLType.VALUE_STORAGE)
        self.assertIs(type_by_name('ValueStorage'), BSLType.VALUE_STORAGE)
        self.assertIs(type_of(BSLValueStorage(None)), BSLType.VALUE_STORAGE)

    def test_02_scalar_values_and_type_identity(self):
        for value in (None, NULL, True, False, Decimal('42.25'), '', 'abc'):
            with self.subTest(value=value):
                result = BSLValueStorage(value).get()
                self.assertIs(type(result), type(value))
                self.assertEqual(result, value)

    def test_03_nested_storage(self):
        inner = BSLValueStorage(array('a'))
        outer = BSLValueStorage(inner)
        restored = outer.get()
        self.assertIs(type(restored), BSLValueStorage)
        first = restored.get()
        first.items.append('b')
        self.assertEqual(restored.get().items, ['a'])
        self.assertEqual(inner.get().items, ['a'])

    def test_04_nested_storage_counts_budget(self):
        inner = BSLValueStorage(array(None, None, None))
        with patch('yadinassi.value_storage.MAX_NODES', 4):
            with self.assertRaises(SnapshotError):
                BSLValueStorage(inner)
        with patch('yadinassi.value_storage.MAX_DEPTH', 1):
            with self.assertRaises(SnapshotError):
                BSLValueStorage(inner)

    def test_05_bad_private_snapshot_fails_closed(self):
        holder = BSLValueStorage(Decimal(1))
        holder._snapshot = Snapshot(('storage', ('array', [('undefined',)])))
        with self.assertRaises(SnapshotError):
            holder.get()
        holder._snapshot = object()
        with self.assertRaises(SnapshotError):
            holder.get()
        holder = BSLValueStorage(Decimal(1))
        calls = []
        holder.get = lambda: calls.append('host-callback')
        nested = BSLValueStorage(holder).get()
        self.assertEqual(BSLValueStorage.get(nested), Decimal(1))
        self.assertEqual(calls, [])

    def test_06_binary(self):
        holder = BSLValueStorage(BSLBinaryData.from_bytes(b'\x00\xff\x80'))
        self.assertEqual(holder.get()._data, b'\x00\xff\x80')
        self.assertIsNot(holder.get(), holder.get())

    def test_07_shared_dag_is_charged_per_occurrence(self):
        child = array(None, None)
        root = array(child, child)
        with patch('yadinassi.value_storage.MAX_NODES', 6):
            with self.assertRaises(SnapshotError):
                BSLValueStorage(root)
        with patch('yadinassi.value_storage.MAX_NODES', 7):
            result = BSLValueStorage(root).get()
        self.assertIsNot(result.items[0], result.items[1])

    def test_08_cycles_fail_closed(self):
        source = array()
        source.items.append(source)
        with self.assertRaises(SnapshotError):
            BSLValueStorage(source)
        self.assertIs(source.items[0], source)

    def test_09_unmeasured_forms_fail_closed(self):
        vm = Interpreter()
        for expression in ('New ValueStorage()', 'New ValueStorage(1, "bad")'):
            with self.subTest(expression=expression), self.assertRaises(Exception):
                vm.execute('X = ' + expression + ';')
        vm.execute('X = New ValueStorage(New ValueTable);')
        table = vm.variables['x'].get()
        self.assertIs(type(table), BSLValueTable)
        self.assertEqual((table.columns.items, table.rows, table.indexes.items), ([], [], []))
        with self.assertRaises(SnapshotError):
            BSLValueStorage(1)

    def test_10_codec_rejects_value_and_type(self):
        for value in (BSLValueStorage(None), BSLType.VALUE_STORAGE):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    value_to_string_internal(value)

    def test_11_provenance_and_native27_source_bound_replay(self):
        source = (FIXTURE / 'native27.bsl').read_bytes()
        raw = (FIXTURE / 'native27-linux-8.3.27.1508.out').read_bytes()
        provenance = json.loads((FIXTURE / 'provenance.json').read_text())
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         '0d6c7ddc213df18af0140a4ecff88246bfc293fd4483746f3137f96ca853ca2e')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '99e0452fe2e13973ba80bb057b202d0beb3aa9fd32c95729c0716670c957c7cd')
        self.assertTrue(provenance['native_measurement_accepted'])
        self.assertEqual(provenance['comparison']['acceptance_status'], 'rejected')
        lines = raw.decode('ascii').splitlines()
        self.assertEqual(len(lines), 28)
        # Explicit unsupported local policies, never edits to the raw capture.
        self.assertEqual(lines[17], 'VS-17: [ok|ABCA]')  # One untyped table cell.
        lines[18] = 'VS-18: [setup-error]'      # DataCompression deferred.
        output = []
        vm = Interpreter(output.append)
        vm.execute(source.decode('utf-8'))
        self.assertEqual(output, lines)

    def test_12_methods_arity_and_unmeasured_presentation(self):
        holder = BSLValueStorage(Decimal(1))
        self.assertEqual(holder.get_method('Получить')(), Decimal(1))
        self.assertEqual(holder.get_method('Get')(), Decimal(1))
        with self.assertRaises(TypeError):
            holder.get_method('Get')(Decimal(1))
        with self.assertRaises(ValueError):
            holder.get_method('Missing')
        with self.assertRaises(ValueError):
            str(holder)

    def test_13_bsl_catches_missing_exact_host_fields(self):
        vm = Interpreter()
        for kind in (BSLDate, BSLUUID, BSLBinaryData, BSLArray, BSLFixedArray,
                     BSLStructure, BSLFixedStructure, BSLMap, BSLFixedMap,
                     BSLValueStorage):
            vm.variables['broken'] = object.__new__(kind)
            with self.subTest(kind=kind.__name__):
                vm.execute('Caught = False; Try V = New ValueStorage(Broken); '
                           'Except Caught = True; EndTry;')
                self.assertIs(vm.variables['caught'], True)
        vm.variables['broken'] = object.__new__(BSLValueStorage)
        vm.execute('Caught = False; Try V = Broken.Get(); '
                   'Except Caught = True; EndTry;')
        self.assertIs(vm.variables['caught'], True)
        holder = BSLValueStorage(None)
        holder._snapshot = object.__new__(Snapshot)
        vm.variables['broken'] = holder
        vm.execute('Caught = False; Try V = Broken.Get(); '
                   'Except Caught = True; EndTry;')
        self.assertIs(vm.variables['caught'], True)

    def test_14_hostile_subclass_get_does_not_invoke_property(self):
        calls = []
        class Hostile(BSLValueStorage):
            @property
            def _snapshot(self):
                calls.append('property')
                raise AssertionError('must not invoke a hostile descriptor')
        value = object.__new__(Hostile)
        with self.assertRaises(SnapshotError):
            BSLValueStorage.get(value)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
