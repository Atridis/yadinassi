"""Actual BSL against distinguishable synthetic lifetimes; no native answers."""
from contextlib import contextmanager
from decimal import Decimal as D
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, runtime
from yadinassi.value_trees import (BSLValueTree, BSLValueTreeColumn as Column,
    BSLValueTreeColumnCollection as Columns, BSLValueTreeRow as Row,
    BSLValueTreeRowCollection as Rows)
from yadinassi.values import BSLArray, HostFunction
from scripts import native_1c_tree_columns_clear_contract as wire

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'integrational_tests/measurements/tree_columns_clear.bsl').read_text(encoding='utf-8')
HELPERS = SOURCE[:SOURCE.index('Сообщить("CC-C1:')]


def emit():
    output = []
    Interpreter(output.append).execute(SOURCE)
    return ('\n'.join(output) + '\n').encode('ascii')


def probe(case=1):
    vm = Interpreter(); vm.execute(HELPERS)
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
    def test_current_guard_and_explicit_missing_method_are_not_availability(self):
        records = wire.validate_output(emit())
        self.assertEqual([r['status'] for r in records[:2]], ['O', 'O'])
        with self.assertRaises(wire.AvailabilityError): wire.require_available(emit())
        with model('missing'):
            raw = emit(); records = wire.validate_output(raw)
        self.assertEqual({r['status'] for r in records}, {'M'})
        with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)

    def test_detach_invalidate_columns_only_and_noop_are_distinct_observations(self):
        seen = {}
        for mode in ('detach', 'invalidate', 'columns_only', 'noop'):
            with model(mode):
                raw = probe(); seen[mode] = wire.validate_payload(raw, 1)
            self.assertEqual(seen[mode]['status'], 'S')
        self.assertEqual(len({str(v['snapshots'][1]) for v in seen.values()}), 4)
        self.assertEqual(len(seen['columns_only']['snapshots'][1]['nodes']), 3)
        self.assertEqual(len(seen['detach']['snapshots'][1]['nodes']), 0)
        query = wire.QUERY_NAMES.index('root.owner')
        self.assertNotEqual(seen['detach']['snapshots'][1]['queries'][query],
                            seen['invalidate']['snapshots'][1]['queries'][query])

    def test_complete_capture_repeated_invocations_and_initial_followup_phases(self):
        with model():
            first = emit(); second = emit(); records = wire.require_available(first)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), wire.MAX_ENCODED_BYTES)
        self.assertEqual(records[6]['status'], 'A')
        self.assertEqual((records[8]['status'], records[8]['follow_status'], records[8]['phase']), ('S', 'O', 1))
        self.assertEqual((records[11]['status'], records[11]['follow_status'], records[11]['phase']), ('S', 'S', 5))
        self.assertEqual(records[7]['expression'], 'U_')
        with model('noop'):
            repeated = wire.validate_payload(probe(12), 12)
        self.assertEqual((repeated['status'], repeated['follow_status'], repeated['phase']), ('S', 'O', 1))

    def test_expression_results_and_procedure_rejection_are_not_assumed(self):
        for result, token in ((None, 'U_'), (D(-1), 'Na'), (D(9), 'N9'), (True, 'B1'), ('a', 'Sa')):
            with model(result=result): value = wire.validate_payload(probe(8), 8)
            self.assertEqual((value['status'], value['expression']), ('S', token))
        with model(returns_value=False): value = wire.validate_payload(probe(8), 8)
        self.assertEqual(value['status'], 'O')
        self.assertEqual(value['snapshots'][0], value['snapshots'][1])

    def test_original_action_error_survives_later_query_errors_and_partial_mutation(self):
        with model('partial'):
            raw = probe(); value = wire.validate_payload(raw, 1)
        self.assertEqual(value['status'], 'M')
        self.assertNotEqual(value['snapshots'][0], value['snapshots'][1])
        self.assertNotIn(b'private-original-action', raw)

    def test_new_valid_column_and_row_identities_are_observed_not_normalized(self):
        with model('replace'): value = wire.validate_payload(probe(), 1)
        before, after = value['snapshots']
        self.assertEqual(value['status'], 'S')
        self.assertTrue({c[0] for c in before['schema']}.isdisjoint(c[0] for c in after['schema']))
        self.assertTrue({r.row for r in before['nodes']}.isdisjoint(r.row for r in after['nodes']))
        self.assertEqual([r.cells for r in before['nodes']], [r.cells for r in after['nodes']])

    def test_postaction_named_positional_discrepancy_is_not_observer_failure(self):
        original = Row.get; changed = [False]; original_method = Columns.get_method
        def method(receiver, name):
            if name.casefold() not in ('clear', 'очистить'): return original_method(receiver, name)
            return HostFunction(name, lambda: changed.__setitem__(0, True))
        def positional(row, index): return D(9) if changed[0] else original(row, index)
        with patch.object(Columns, 'get_method', method), patch.object(Row, 'get', positional):
            value = wire.validate_payload(probe(), 1)
        before, after = value['snapshots']
        self.assertEqual(before['nodes'][0].cells, before['nodes'][0].named_cells)
        self.assertNotEqual(after['nodes'][0].cells, after['nodes'][0].named_cells)
        self.assertEqual(value['status'], 'S')

    def test_collection_wrapper_inequality_does_not_change_capture(self):
        original = runtime.equal
        def unequal(a, b):
            if type(a) in (Columns, Rows) or type(b) in (Columns, Rows): return False
            return original(a, b)
        with model():
            expected = emit()
            with patch.object(runtime, 'equal', unequal): actual = emit()
        self.assertEqual(actual, expected)

    def test_deleted_identity_comparison_failure_is_independent_query_outcome(self):
        poisoned = []; original = runtime.equal
        def clear(receiver):
            poisoned.extend(receiver.table._all_rows); poisoned.extend(receiver.items)
            receiver.items.clear(); receiver.table.rows.items.clear()
        def equal(a, b):
            if any(a is value or b is value for value in poisoned):
                raise ValueError('private deleted equality')
            return original(a, b)
        with patch.object(Columns, 'clear', clear), patch.object(runtime, 'equal', equal):
            raw = probe(); value = wire.validate_payload(raw, 1)
        queries = value['snapshots'][1]['queries']
        self.assertEqual(value['status'], 'S')
        self.assertEqual(queries[wire.QUERY_NAMES.index('root.id')], ('E', None))
        self.assertEqual(queries[wire.QUERY_NAMES.index('root.owner')], ('I', 0))
        self.assertNotIn(b'private deleted equality', raw)

    def test_reported_owner_parent_and_level_are_not_forced_to_active_position(self):
        changed = [False]; other = BSLValueTree(); foreign_parent = other.rows.add()
        old_owner, old_level, old_member = Row.owner, Row.level, Row.get_member
        def clear(receiver): changed[0] = True
        def owner(row): return other if changed[0] else old_owner(row)
        def level(row): return D(-1) if changed[0] else old_level(row)
        def member(row, name):
            if changed[0] and name.casefold() in ('parent', 'родитель'): return foreign_parent
            return old_member(row, name)
        with patch.object(Columns, 'clear', clear), patch.object(Row, 'owner', owner), \
                patch.object(Row, 'level', level), patch.object(Row, 'get_member', member):
            value = wire.validate_payload(probe(), 1)
        before, after = value['snapshots']
        self.assertEqual(value['status'], 'S')
        self.assertNotEqual(after['nodes'][0].owner, after['tree'])
        self.assertNotIn(after['nodes'][0].parent, {row.row for row in after['nodes']})
        self.assertEqual(after['nodes'][0].level, -1)
        self.assertNotEqual(before['nodes'][0], after['nodes'][0])
        changed[0] = False
        with patch.object(Columns, 'clear', clear), patch.object(Row, 'owner',
                lambda row: None if changed[0] else old_owner(row)):
            undefined = wire.validate_payload(probe(), 1)['snapshots'][1]
        self.assertIsNone(undefined['nodes'][0].owner)
        self.assertEqual(undefined['queries'][wire.QUERY_NAMES.index('root.owner')], ('I', None))

    def test_unsupported_scalar_or_identity_type_is_observer_failure_not_query_error(self):
        for result in (D(100), 'private-secret', BSLArray()):
            with model(result=result): raw = probe(8)
            self.assertEqual(raw, b'XO')
            with self.assertRaises(wire.ObservationError): wire.validate_payload(raw, 8)
        changed = [False]; original_owner = Row.owner
        def clear(receiver): changed[0] = True
        def owner(row): return BSLArray() if changed[0] else original_owner(row)
        with patch.object(Columns, 'clear', clear), patch.object(Row, 'owner', owner): raw = probe()
        self.assertEqual(raw, b'XO')


if __name__ == '__main__': unittest.main()
