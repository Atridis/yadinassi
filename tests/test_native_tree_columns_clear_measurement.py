"""Actual BSL against distinguishable synthetic lifetimes; no native answers."""
from contextlib import contextmanager
from decimal import Decimal as D
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.collections.value_trees import (BSLValueTree, BSLValueTreeColumn as Column,
    BSLValueTreeColumnCollection as Columns, BSLValueTreeRow as Row,
    BSLValueTreeRowCollection as Rows)
from yadinassi.types.values import BSLArray, HostFunction
from scripts import native_1c_tree_columns_clear_contract as wire

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'integrational_tests/measurements/tree_columns_clear.bsl').read_text(encoding='utf-8')
HELPERS = SOURCE[:SOURCE.index('Сообщить("CC-C1:')]


def emit(*, backend=None):
    output = []
    Interpreter(output.append, execution_backend=backend).execute(SOURCE)
    return ('\n'.join(output) + '\n').encode('ascii')


def probe(case=1, *, backend=None):
    vm = Interpreter(execution_backend=backend); vm.execute(HELPERS)
    return vm.execute(f'CCProbe({case})').encode('ascii')


@contextmanager
def model(mode='detach', *, returns_value=True, result=None):
    original = Columns.get_method
    def method(receiver, name):
        if name.casefold() not in ('clear', 'очистить'):
            return original(receiver, name)
        if mode == 'missing': raise ValueError('Метод не найден: clear')
        def action(*arguments):
            if arguments: raise TypeError('Неверное количество параметров')
            tree = receiver.table
            if mode == 'noop': return result
            if mode == 'partial':
                receiver.items.pop()
                raise ValueError('Метод не найден: private-original-action')
            if mode == 'replace':
                old_columns = list(receiver.items); old_rows = list(tree.rows.items)
                new_columns = [Column(tree, c.name, c.value_type, c.title, c.width) for c in old_columns]
                for old, new in zip(old_columns, new_columns): new.default = old.default
                # Keep retained synthetic rows readable through the replacement
                # schema; do not leak a Python KeyError as a fake native result.
                for old_row in tree._all_rows:
                    old_row.cells.update({new_c: old_row.cells[old_c] for old_c, new_c in zip(old_columns, new_columns)})
                receiver.items[:] = new_columns; tree.rows.items.clear(); tree._all_rows.clear()
                def clone(rows, collection):
                    for old in rows:
                        new = collection.add()
                        new.cells = {new_c: old.cells[old_c] for old_c, new_c in zip(old_columns, new_columns)}
                        clone(old.rows.items, new.rows)
                clone(old_rows, tree.rows)
                return result
            if mode == 'invalidate':
                tree.rows.clear()
                for column in receiver.items: column._deleted = True
            receiver.items.clear()
            if mode != 'columns_only': tree.rows.items.clear()
            return result
        return HostFunction(name, action, returns_value=returns_value)
    with patch.object(Columns, 'get_method', method): yield


class ClearObserverTests(unittest.TestCase):
    def test_current_direct_capture_is_not_native_availability(self):
        records=wire.validate_output(emit())
        self.assertEqual([r['status'] for r in records[:2]],['O','O'])
        with self.assertRaises(wire.AvailabilityError):wire.require_available(emit())

    def test_retired_synthetic_class_hooks_fail_before_action(self):
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
        with model('noop'):
            with self.assertRaisesRegex(BoundaryViolation,'ValueTree class hooks changed'):
                probe()

    def test_repeated_actual_capture_is_deterministic(self):
        self.assertEqual(emit(),emit())
