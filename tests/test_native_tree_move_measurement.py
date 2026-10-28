"""Observer fault injection only; synthetic actions are not native Move answers."""
from contextlib import contextmanager
import hashlib
from decimal import Decimal as D
from pathlib import Path
import unittest
from unittest import mock

from yadinassi import Interpreter, BSLError
from yadinassi.value_trees import BSLValueTreeRowCollection as Rows, BSLValueTreeColumnCollection as Columns
from yadinassi.values import HostFunction
from scripts import native_1c_tree_move_contract as contract

ROOT = Path(__file__).resolve().parents[1]


def helpers():
    # Universal newlines only for these synthetic observer tests, never capture validation.
    text = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
    if hashlib.sha256(text.encode('utf-8-sig')).hexdigest() != 'a0212150d3d5d2a7252971aa8ba509d439ced04e85b5a157ff1148bf3eff4574':
        raise AssertionError('synthetic Move observer source binding changed')
    result = []
    for kind in ('LoadColumn', 'Move'):
        start = '// Begin bounded ValueTree ' + kind + ' helpers'
        end = '// End bounded ValueTree ' + kind + ' helpers.'
        result.append(text[text.index(start):text.index(end) + len(end)])
    return '\n'.join(result)


class MoveObserverTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.vm.execute(helpers())

    def state(self, mode=5):
        self.vm.execute(f'S = TreeMoveFresh({mode});')
        return self.vm.variables['s']

    def observe(self):
        return self.vm.execute('TreeMoveState(S)')

    def probe(self, case):
        return self.vm.execute(f'TreeMoveProbe({case})')

    @contextmanager
    def witness(self, callback, returns_value=True):
        original = Rows.get_method
        def method(receiver, name):
            if name.casefold() in ('move', 'сдвинуть'):
                return HostFunction(name, lambda *args: callback(receiver, args), returns_value=returns_value)
            return original(receiver, name)
        with mock.patch.object(Rows, 'get_method', method):
            yield

    def test_missing_method_is_valid_measurement_not_semantic_answer(self):
        # Preserve the original missing-method control after runtime support.
        with self.witness(lambda receiver, args: (_ for _ in ()).throw(ValueError('synthetic missing method'))):
            payload = self.vm.execute('TreeMoveObservations()').encode()
        decoded = contract.validate_payload(payload)
        self.assertEqual(len(payload), 193)
        self.assertTrue(all(outcome == b'0' for _, outcome, _ in decoded))

    def test_fresh_modes_and_retained_order_are_observed(self):
        with mock.patch.object(Rows, 'clear', side_effect=AssertionError('must not clear')):
            for mode, expected in ((0, '-----'), (1, 'A----'), (5, 'ABCDE')):
                self.state(mode)
                self.assertEqual(self.observe(), expected)
        s = self.state()
        s.get_member('Tree').rows.items.reverse()
        s.get_member('Nodes').items[0].rows.items.reverse()
        self.assertEqual(self.observe(), 'CBAED')

    def test_schema_topology_identity_and_scalar_corruption_reject(self):
        mutations = [
            lambda s: s.get_member('Tree').columns.add('Extra'),
            lambda s: setattr(s.get_member('Columns').items[0], 'name', 'ID'),
            lambda s: setattr(s.get_member('Columns').items[0], 'title', 'other'),
            lambda s: setattr(s.get_member('Columns').items[0], 'width', D(1)),
            lambda s: s.get_member('Tree').rows.add(),
            lambda s: s.get_member('Nodes').items[1].rows.add(),
            lambda s: s.get_member('Tree').rows.items.__setitem__(1, s.get_member('Nodes').items[0]),
            lambda s: setattr(s.get_member('Nodes').items[3], 'parent', None),
            lambda s: setattr(s.get_member('Nodes').items[0], 'tree', s.get_member('Nodes').items[0]),
            lambda s: s.get_member('Nodes').items[0].set_member('Id', True),
            lambda s: s.get_member('Nodes').items[0].set_member('Id', '1'),
            lambda s: s.get_member('Nodes').items[0].set_member('Id', D(2)),
            lambda s: setattr(s.get_member('Nodes').items[0], '_deleted', True),
            lambda s: setattr(s.get_member('Tree'), 'columns', Columns(s.get_member('Tree'))),
            lambda s: s.get_member('Views').items.__setitem__(0, Rows(s.get_member('Tree'))),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                s = self.state(); mutate(s)
                with self.assertRaises(BSLError):
                    self.observe()

    def test_action_success_and_error_remain_distinct(self):
        def error(receiver, args):
            raise ValueError('synthetic action error')
        for expected, callback in (('1', lambda r, a: None), ('0', error)):
            with self.witness(callback, returns_value=False):
                for case in range(1, 32):
                    self.assertTrue(self.probe(case).startswith(expected), case)

    def test_action_corruption_is_not_ordinary_action_error(self):
        for callback in (lambda r, a: r.add(), lambda r, a: r.items[0].set_member('Id', True)):
            with self.witness(callback, returns_value=False):
                self.assertEqual(self.probe(1), '!')
        def corrupt_then_raise(receiver, args):
            receiver.add()
            raise ValueError('synthetic action error after corruption')
        with self.witness(corrupt_then_raise):
            self.assertEqual(self.probe(1), '!')

    def test_foreign_mutation_is_rejected(self):
        def corrupt_foreign(receiver, args):
            args[0].set_member('Id', True)
        with self.witness(corrupt_foreign, returns_value=False):
            self.assertEqual(self.probe(30), '!')

    def test_expression_value_is_fail_closed(self):
        for value, expected in ((None, '2ABCDE'), (True, '!ABCDE')):
            with self.witness(lambda r, a: value):
                self.assertEqual(self.probe(32), expected)

    def test_partial_order_change_before_error_is_preserved(self):
        def mutate_then_error(receiver, args):
            receiver.items.reverse()
            raise ValueError('synthetic action error after order change')
        with self.witness(mutate_then_error):
            self.assertEqual(self.probe(1), '0CBADE')


if __name__ == '__main__':
    unittest.main()
