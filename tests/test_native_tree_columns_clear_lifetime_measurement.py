"""Execute CL BSL against distinguishable models, not inferred native answers."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.values import HostFunction
from yadinassi.value_trees import BSLValueTreeColumnCollection as Columns, BSLValueTreeRowCollection as Rows
from scripts import native_1c_tree_columns_clear_lifetime_contract as wire

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'integrational_tests/measurements/tree_columns_clear_lifetime.bsl').read_text(encoding='utf-8')
HELPERS = SOURCE[:SOURCE.index('Сообщить("CL-C1:')]


def emit():
    output = []; Interpreter(output.append).execute(SOURCE)
    return ('\n'.join(output) + '\n').encode('ascii')


@contextmanager
def model(mode='forward'):
    method, live, insert, clear = Columns.get_method, Rows._live, Rows.insert, Rows.clear
    def get_method(receiver, name):
        if name.casefold() not in ('clear', 'очистить'): return method(receiver, name)
        if mode == 'missing': raise ValueError('Метод не найден')
        def action():
            if mode == 'noop': return
            tree = receiver.table
            old_rows = list(tree._all_rows)
            for row in old_rows:
                row._deleted = True; row.cells.clear(); row.rows.items.clear()
            tree._all_rows.clear(); tree.rows.items.clear()
            for column in receiver.items: column._deleted = True
            receiver.items.clear()
            if mode in ('forward', 'detached'):
                for row in old_rows:
                    row.rows._probe_held = True
                    if mode == 'forward': row.rows.items = tree.rows.items
        return HostFunction(name, action, returns_value=False)
    def held_live(receiver):
        if not getattr(receiver, '_probe_held', False): live(receiver)
    def held_insert(receiver, index):
        if mode == 'forward' and getattr(receiver, '_probe_held', False): return insert(receiver.tree.rows, index)
        return insert(receiver, index)
    def held_clear(receiver):
        if mode == 'forward' and getattr(receiver, '_probe_held', False): return clear(receiver.tree.rows)
        return clear(receiver)
    with patch.object(Columns, 'get_method', get_method), patch.object(Rows, '_live', held_live), patch.object(Rows, 'insert', held_insert), patch.object(Rows, 'clear', held_clear):
        yield


class LifetimeMeasurementTests(unittest.TestCase):
    def test_current_guard_and_missing_are_unavailable(self):
        raw = emit(); records = wire.validate_output(raw)
        self.assertEqual([r['checkpoints'][1]['status'] for r in records], ['O'] * 6)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)
        with model('missing'): raw = emit()
        self.assertEqual([r['checkpoints'][1]['status'] for r in wire.validate_output(raw)], ['M'] * 6)

    def test_forwarding_and_detached_are_distinct_observations(self):
        with model(): forward = wire.require_available(emit())
        with model('detached'): detached = wire.require_available(emit())
        self.assertNotEqual(forward, detached)
        case = forward[2]['checkpoints']
        self.assertEqual([len(c['snapshot']['nodes']) for c in case], [4, 0, 1, 2, 3])
        for checkpoint in case[2:]:
            self.assertEqual(checkpoint['queries'][14], ('I', None))
            self.assertEqual(checkpoint['queries'][15], ('N', 0))
            self.assertIsNotNone(checkpoint['queries'][7][1])
        self.assertEqual(len(forward[4]['checkpoints'][-1]['snapshot']['nodes']), 0)
        self.assertEqual(len(forward[5]['checkpoints'][-1]['snapshot']['nodes']), 1)
        last = forward[3]['checkpoints'][-1]
        self.assertEqual(last['queries'][12][1], last['snapshot']['nodes'][0].row)

    def test_invalidated_wrappers_and_noop_are_not_normalized(self):
        with model('invalidate'): invalidated = wire.require_available(emit())
        self.assertEqual(invalidated[2]['checkpoints'][2]['status'], 'O')
        with model('noop'): raw = emit()
        # A no-op can exceed the bounded active-row domain during later Add;
        # it must never pass availability, whether it is decoded or rejected.
        with self.assertRaises((wire.AvailabilityError, wire.ObservationError)): wire.require_available(raw)

    def test_repeated_invocation_same_capture(self):
        with model(): self.assertEqual(emit(), emit())

    def test_action_error_is_captured_before_query_helpers(self):
        with model():
            original = Rows.insert
            def fail(receiver, index):
                if getattr(receiver, '_probe_held', False): raise ValueError('Метод не найден private-action')
                return original(receiver, index)
            with patch.object(Rows, 'insert', fail): records = wire.validate_output(emit())
        self.assertEqual(records[2]['checkpoints'][2]['status'], 'M')
        self.assertEqual(records[3]['checkpoints'][3]['status'], 'M')

    def test_unsupported_returned_value_is_observer_failure(self):
        with model():
            original = Rows.insert
            def wrong(receiver, index):
                if getattr(receiver, '_probe_held', False): return Decimal(7)
                return original(receiver, index)
            with patch.object(Rows, 'insert', wrong): raw = emit()
        with self.assertRaises(wire.ObservationError): wire.validate_output(raw)


if __name__ == '__main__': unittest.main()
