"""Synthetic distinguishing models and observer faults, NOT native Sort answers."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.value_trees import BSLValueTreeRowCollection as Rows
from yadinassi.values import HostFunction
from scripts import native_1c_tree_sort_contract as wire

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'integrational_tests/measurements/tree_sort.bsl').read_text()
HELPERS = SOURCE[:SOURCE.index('Сообщить("TS-C1:')]


def emit():
    out = []
    Interpreter(out.append).execute(SOURCE)
    return ('\n'.join(out) + '\n').encode('ascii')


@contextmanager
def model(mode='recursive', returns_value=False):
    original = Rows.get_method
    def get(receiver, name):
        if name.casefold() not in ('sort', 'сортировать'):
            return original(receiver, name)
        if mode == 'missing':
            raise ValueError('Метод не найден: ' + name)
        def action(*args):
            if mode == 'noop':
                return None
            if mode == 'replace_rows':
                saved = [tuple(row.get_member(field) for field in ('Key','Secondary','Tag')) for row in receiver.items]
                receiver.clear()
                for cells in saved:
                    row = receiver.add()
                    for field,value in zip(('Key','Secondary','Tag'),cells):
                        row.set_member(field,value)
                return None
            if mode == 'partial':
                receiver.items.reverse()
                raise ValueError('synthetic action failure must stay private')
            if not args or len(args) > 3 or type(args[0]) is not str:
                raise ValueError('Неверное количество параметров')
            if len(args) > 1 and type(args[1]) is not bool:
                raise ValueError('Неверные параметры')
            if len(args) > 2 and args[2] is not None:
                raise ValueError('Неверные параметры')
            if not args[0] or 'Missing' in args[0]:
                raise ValueError('synthetic selector failure')
            fields = []
            for item in args[0].split(','):
                words = item.split()
                fields.append((words[0], len(words) > 1 and words[1].casefold() in ('desc', 'убыв')))
            def sort(rows):
                # Deliberately separate plausible models; no native claim.
                for field, descending in reversed(fields):
                    rows.items.sort(key=lambda r: r.get_member(field), reverse=descending)
                if mode == 'unstable':
                    groups = []
                    for row in rows.items:
                        key = tuple(row.get_member(field) for field, _ in fields)
                        if not groups or groups[-1][0] != key:
                            groups.append((key, []))
                        groups[-1][1].append(row)
                    rows.items[:] = [r for _, group in groups for r in reversed(group)]
                if mode != 'flat' and len(args) > 1 and args[1]:
                    for row in rows.items:
                        sort(row.rows)
            sort(receiver)
        return HostFunction(name, action, returns_value=returns_value)
    with patch.object(Rows, 'get_method', get):
        yield


class SortObserverTests(unittest.TestCase):
    def probe(self, case):
        vm = Interpreter(); vm.execute(HELPERS)
        return wire.validate_payload(vm.execute(f'TSProbe({case})').encode(), case)

    def test_calibration_and_missing_method_do_not_claim_availability(self):
        with model('missing'):
            raw = emit()
        decoded = wire.validate_output(raw)
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertTrue(all(r['status'] == 'M' for r in decoded))
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(raw)
        self.assertNotIn(b'synthetic', raw)

    def test_positive_controls_distinguish_noop_and_sort_and_match_aliases(self):
        with model('noop'):
            noop = self.probe(1)
        with model():
            en = self.probe(1); ru = self.probe(2)
        self.assertEqual(noop['snapshots'][0], noop['snapshots'][1])
        self.assertNotEqual(noop['snapshots'][1], en['snapshots'][1])
        self.assertEqual(en['snapshots'], ru['snapshots'])

    def test_models_distinguish_recursion_and_child_receiver(self):
        for case in (3, 4):
            with model('recursive'):
                recursive = self.probe(case)
            with model('flat'):
                flat = self.probe(case)
            self.assertNotEqual(recursive['snapshots'][1], flat['snapshots'][1])
        with model('recursive'):
            default = self.probe(5)
            recursive = self.probe(4)
        self.assertNotEqual(default['snapshots'][1], recursive['snapshots'][1])

    def test_stable_unstable_ties_are_observed_not_assumed(self):
        for case in (8, 9):
            with model('recursive'):
                stable = self.probe(case)
            with model('unstable'):
                unstable = self.probe(case)
            self.assertNotEqual(stable['snapshots'][1], unstable['snapshots'][1])
            self.assertEqual(len(stable['snapshots'][1]['nodes']), 18)

    def test_posterror_partial_state_and_fresh_fixtures(self):
        with model('partial'):
            first = self.probe(1); second = self.probe(2)
        self.assertEqual(first['status'], 'O')
        self.assertNotEqual(first['snapshots'][0], first['snapshots'][1])
        self.assertEqual(first['snapshots'][0], second['snapshots'][0])

    def test_multikey_en_ru_match_and_differ_from_single_key(self):
        with model():
            en = self.probe(6); ru = self.probe(7); single = self.probe(3)
        self.assertEqual(en['snapshots'], ru['snapshots'])
        self.assertNotEqual(en['snapshots'][1], single['snapshots'][1])

    def test_complete_synthetic_run_records_expression_and_argument_cases(self):
        with model():
            raw = emit(); decoded = wire.validate_output(raw)
        wire.require_available(raw)
        self.assertEqual(decoded[9]['snapshots'][0]['nodes'], ())
        self.assertEqual(decoded[18]['status'], 'S')
        self.assertNotEqual(decoded[19]['status'], 'S')
        self.assertNotEqual(decoded[20]['status'], 'S')
        with model(returns_value=True):
            expression = self.probe(21)
        self.assertEqual(expression['status'], 'S')

    def test_snapshot_captures_all_cells_and_real_identity(self):
        vm = Interpreter(); vm.execute(HELPERS)
        vm.execute('T=TSFixture(1); Registry=Новый Массив; Before=TSSnapshot(T,Registry); T.Rows.Get(0).Key=9; T.Rows.Get(0).Secondary=8; T.Rows.Get(0).Tag="r"; After=TSSnapshot(T,Registry);')
        decoded = wire.validate_payload(('S/'+vm.variables['before']+'/'+vm.variables['after']).encode(),1)
        before, after = decoded['snapshots']
        self.assertEqual(before['nodes'][0].row, after['nodes'][0].row)
        self.assertNotEqual(before['nodes'][0].cells, after['nodes'][0].cells)
        self.assertEqual(after['nodes'][0].cells, (('N','9'),('N','8'),('S','r')))

    def test_new_postaction_row_identities_remain_observations(self):
        # Synthetic replacement is not a prediction about real Rows.Sort.
        # Equal cells must not erase distinct newly allocated row identities.
        with model('replace_rows'):
            result = self.probe(8)
        before,after = result['snapshots']
        self.assertEqual(result['status'],'S')
        self.assertEqual([row.cells for row in before['nodes']], [row.cells for row in after['nodes']])
        self.assertTrue(set(row.row for row in before['nodes']).isdisjoint(row.row for row in after['nodes']))
        self.assertEqual([row.row for row in after['nodes']], list(range(23,41)))
        self.assertEqual([row.children_owner for row in after['nodes']], list(range(23,41)))
        self.assertEqual(len(result['identities']),41)

    def test_observer_fault_not_reclassified_as_action_error(self):
        original = Rows.get_method
        def get(receiver, name):
            if name.casefold() in ('sort','сортировать'):
                def corrupt(*args):
                    receiver.items[0].cells[receiver.tree.columns.items[0]] = Decimal(100)
                return HostFunction(name, corrupt, returns_value=False)
            return original(receiver,name)
        vm = Interpreter(); vm.execute(HELPERS)
        with patch.object(Rows,'get_method',get):
            payload = vm.execute('TSProbe(1)').encode()
        self.assertEqual(payload,b'XO')
        with self.assertRaises(wire.ObservationError):
            wire.validate_payload(payload,1)

    def test_schema_and_row_metadata_changes_are_observed(self):
        vm = Interpreter(); vm.execute(HELPERS)
        vm.execute('T=TSFixture(1); Registry=Новый Массив; Before=TSSnapshot(T,Registry);')
        tree = vm.variables['t']; row = tree.rows.items[0]
        tree.columns.items[0].title = 'Q'
        tree.columns.items[0].width = Decimal(9)
        row.depth = 3
        # Preserve the old identity in the registry while replacing one real row.
        import copy
        replacement = copy.copy(tree.rows.items[1].rows.items[1])
        replacement.rows = Rows(tree, replacement)
        tree.rows.items[1].rows.items[1] = replacement
        vm.execute('After=TSSnapshot(T,Registry);')
        decoded = wire.validate_payload(('O/'+vm.variables['before']+'/'+vm.variables['after']).encode(),1)
        before, after = decoded['snapshots']
        self.assertNotEqual(before['schema'], after['schema'])
        self.assertEqual(after['nodes'][0].level, 3)
        self.assertNotEqual(before['nodes'][7].row, after['nodes'][7].row)
        self.assertEqual(before['nodes'][0].children_owner, after['nodes'][0].children_owner)

    def test_rowcollection_wrappers_never_enter_identity_registry(self):
        # Only Rows iteration, Count and Parent are observed: identity is its owner.
        vm = Interpreter(); vm.execute(HELPERS)
        vm.execute('T=TSFixture(1); Registry=Новый Массив; Snapshot=TSSnapshot(T,Registry);')
        identities = vm.variables['registry'].items
        self.assertFalse(any(isinstance(value, Rows) for value in identities))
        self.assertEqual(len(identities), 13)  # tree, columns, three columns, eight rows

    def test_source_keeps_original_action_error_and_excludes_comparator_type(self):
        self.assertIn('OriginalErrorDescription = ОписаниеОшибки();\n            Status = TSError(OriginalErrorDescription);', SOURCE)
        self.assertNotIn('Новый СравнениеЗначений',SOURCE)
        self.assertNotIn('New CompareValues',SOURCE)
        self.assertNotIn('TSId(R.Rows',SOURCE)
        self.assertNotIn('TSId(T.Rows',SOURCE)


if __name__ == '__main__':
    unittest.main()
