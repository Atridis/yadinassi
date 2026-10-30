"""Synthetic models distinguish observations, never native Columns.Move answers."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.value_trees import BSLValueTreeColumnCollection as Columns, BSLValueTreeColumn, BSLValueTreeRow
from yadinassi.values import HostFunction
from scripts import native_1c_tree_columns_move_contract as wire

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'integrational_tests/measurements/tree_columns_move.bsl').read_text(encoding='utf-8')
HELPERS = SOURCE[:SOURCE.index('Сообщить("CM-C1:')]


def emit():
    out = []
    Interpreter(out.append).execute(SOURCE)
    return ('\n'.join(out) + '\n').encode('ascii')


@contextmanager
def model(mode='bounded', returns_value=False):
    original = Columns.get_method
    def get(receiver, name):
        if name.casefold() not in ('move', 'сдвинуть'):
            return original(receiver, name)
        def action(*args):
            if mode == 'noop':
                return None
            if mode == 'partial':
                receiver.items.reverse()
                raise ValueError('private action failure')
            if mode == 'replacement':
                old = receiver.items[0]
                new = BSLValueTreeColumn(receiver.table, old.name, old.value_type, old.title, old.width)
                new.default = old.default
                receiver.items[0] = new
                for row in receiver.table._all_rows:
                    row.cells[new] = row.cells.pop(old)
                return None
            if len(args) != 2:
                raise ValueError('Неверное количество параметров')
            column, offset = args
            if type(column) is Decimal:
                if not 0 <= column < len(receiver.items):
                    raise ValueError('index')
                index = int(column)
            elif type(column) is BSLValueTreeColumn:
                index = next((i for i, c in enumerate(receiver.items) if c is column), None)
                if index is None:
                    raise ValueError('foreign')
            else:
                raise ValueError('selector')
            if type(offset) is not Decimal:
                raise ValueError('offset')
            destination = index + int(offset)
            if mode == 'wrap':
                destination %= len(receiver.items)
            elif not 0 <= destination < len(receiver.items):
                raise ValueError('destination')
            receiver.items.insert(destination, receiver.items.pop(index))
            return Decimal(1) if mode == 'result' else None
        return HostFunction(name, action, returns_value=returns_value)
    with patch.object(Columns, 'get_method', get):
        yield


class ColumnsMoveObserverTests(unittest.TestCase):
    def probe(self, case):
        vm = Interpreter(); vm.execute(HELPERS)
        return wire.validate_payload(vm.execute(f'CMProbe({case})').encode(), case)

    def test_actual_absent_method_is_not_available(self):
        raw = emit()
        decoded = wire.validate_output(raw)
        self.assertEqual(len(decoded), 28)
        self.assertTrue(all(item['status'] == 'M' for item in decoded))
        self.assertLessEqual(len(raw), wire.MAX_ENCODED_BYTES)
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(raw)

    def test_controls_aliases_and_positional_cell_association(self):
        with model():
            en, ru = self.probe(1), self.probe(2)
        self.assertEqual(en, dict(ru, case=1))
        before, after = en['snapshots']
        self.assertNotEqual(before['schema'], after['schema'])
        self.assertEqual(tuple(x[0] for x in after['schema']),
                         tuple(before['schema'][i][0] for i in (0, 2, 1)))
        for old, new in zip(before['nodes'], after['nodes']):
            self.assertEqual(old[:6], new[:6])
            self.assertEqual(new.cells, tuple(old.cells[i] for i in (0, 2, 1)))
        with model('noop'):
            noop = self.probe(1)
        self.assertNotEqual(noop['snapshots'][1], after)

    def test_competing_boundary_models_are_distinguished(self):
        with model():
            bounded = self.probe(6)
        with model('wrap'):
            wrapped = self.probe(6)
        self.assertEqual(bounded['status'], 'O')
        self.assertEqual(wrapped['status'], 'S')
        self.assertNotEqual(bounded['snapshots'][1], wrapped['snapshots'][1])

    def test_partial_failure_and_fresh_fixture_preserved(self):
        with model('partial'):
            first, second = self.probe(1), self.probe(2)
        self.assertEqual(first['status'], 'O')
        self.assertNotEqual(*first['snapshots'])
        self.assertEqual(first['snapshots'][0], second['snapshots'][0])
        self.assertNotIn('private', str(first))

    def test_new_column_identity_is_observed_without_normalization(self):
        with model('replacement'):
            record = self.probe(1)
        before, after = record['snapshots']
        self.assertNotEqual(before['schema'][0][0], after['schema'][0][0])
        self.assertEqual(before['schema'][0][1], after['schema'][0][1])
        self.assertEqual(before['nodes'], after['nodes'])

    def test_postaction_named_and_positional_disagreement_is_observed(self):
        original_method=Columns.get_method
        original_get=BSLValueTreeRow.get
        changed=set()
        def method(receiver,name):
            if name.casefold() not in ('move','сдвинуть'):
                return original_method(receiver,name)
            def action(*args):
                changed.add(id(receiver.table))
            return HostFunction(name,action,returns_value=False)
        def positional(row,index):
            value=original_get(row,index)
            return Decimal(9) if id(row.tree) in changed else value
        with patch.object(Columns,'get_method',method),patch.object(BSLValueTreeRow,'get',positional):
            record=self.probe(1)
        self.assertEqual(record['status'],'S')
        before,after=record['snapshots']
        self.assertEqual(before['schema'],after['schema'])
        for old,new in zip(before['nodes'],after['nodes']):
            self.assertEqual(old.cells,old.named_cells)
            self.assertEqual(old.named_cells,new.named_cells)
            self.assertEqual(new.cells,(('N','9'),)*3)
            self.assertNotEqual(new.cells,new.named_cells)
            self.assertEqual(old[:6],new[:6])

    def test_expression_undefined_is_separate_and_other_result_rejected(self):
        with model(returns_value=True):
            record = self.probe(23)
        self.assertEqual(record['status'], 'E')
        with model('result', returns_value=True):
            with self.assertRaises(wire.ObservationError):
                self.probe(23)

    def test_all_synthetic_cases_and_error_capture_order(self):
        with model():
            raw = emit()
        wire.require_available(raw)
        for exception in ('OriginalErrorDescription', 'OriginalObserverErrorDescription',
                          'OriginalCalibrationErrorDescription', 'PrivateSnapshotDescription'):
            self.assertIn('Исключение\n        ' + ('    ' if exception == 'OriginalErrorDescription' else '') + exception + ' = ОписаниеОшибки();', SOURCE)
        self.assertNotIn('private', raw.decode())

    def test_observer_failure_is_not_an_action_outcome(self):
        with patch.object(Columns, 'get', side_effect=ValueError('private observer failure')):
            with self.assertRaises(wire.ObservationError):
                wire.validate_output(emit())

    def test_source_read_uses_explicit_utf8(self):
        original = Path.read_text
        def windows_read(path, *args, **kwargs):
            if not args and kwargs.get('encoding') is None:
                kwargs['encoding'] = 'cp1252'
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', windows_read):
            namespace = runpy.run_path(str(Path(__file__).resolve()))
        self.assertEqual(namespace['SOURCE'], SOURCE)


if __name__ == '__main__':
    unittest.main()
