"""Input/instrumentation/source contracts only: no native FindRows expected answers."""
from contextlib import ExitStack
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from unittest import mock

from yadinassi import BSLError, Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.values import BSLArray, BSLFixedArray, HostFunction
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRow, BSLValueTreeRowCollection
from scripts.native_historical_replay import without_tree_find_probes, without_tree_findrows_probes, without_value_tree_probes
import test_native_1c_full_stage as fixtures

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '5468d16850a9774251d4ef80ae5e938afdfabef69fe496cb3a6cb579d0564782'
HELPER_SHA = '6bcf3286bb2394fc3e8dd46701a3e8eacb611bc0d825be63989e83a47dd8c74d'
CALLS_SHA = '6b0b93c42cedcb4eb48ad25f5755fa14c4a21e5851018da0a36179fe1a5437a2'
BASE_SHA = 'b12fb063732fa8ea16a6e0e88e56d6da99c5958989c9533a07870aee07b72c27'
HELPER_START = '// Begin bounded ValueTree FindRows helpers (measurement only; no native answers).\n'
HELPER_END = '// End bounded ValueTree FindRows helpers.\n\n'
CALLS_START = '// Begin bounded ValueTree FindRows observations (measurement only; no native answers).\n'
CALLS_END = '// End bounded ValueTree FindRows observations.\n'
INPUTS = (('alias.ru', 'S.Tree.Строки.НайтиСтроки(Filter, Истина)'), ('alias.en', 'S.Tree.Rows.FindRows(Filter, True)'), ('root.false', 'S.Tree.Rows.FindRows(Filter, False)'), ('root.omitted', 'S.Tree.Rows.FindRows(Filter)'), ('child.true', 'S.A.Rows.FindRows(Filter, True)'), ('child.false', 'S.A.Rows.FindRows(Filter, False)'), ('child.omitted', 'S.A.Rows.FindRows(Filter)'), ('leaf', 'S.A11.Rows.FindRows(Filter, True)'), ('no-match', 'S.Tree.Rows.FindRows(New Structure("Key", "absent"), True)'), ('nonmatching-parents', 'S.Tree.Rows.FindRows(Filter, True)', 'descendants'), ('conjunction', 'S.Tree.Rows.FindRows(New Structure("Key,Group", "hit", "x"), True)', 'descendants'), ('conjunction-reversed', 'S.Tree.Rows.FindRows(New Structure("Group,Key", "x", "hit"), True)', 'descendants'), ('column-case', 'S.Tree.Rows.FindRows(New Structure("kEy,gRoUp", "hit", "x"), True)', 'descendants'), ('empty-filter.nonempty', 'S.Tree.Rows.FindRows(New Structure, True)'), ('empty-filter.empty', 'S.A11.Rows.FindRows(New Structure, True)'), ('number-boolean', 'S.Tree.Rows.FindRows(New Structure("Key", 1), True)', 'scalars', 'number-boolean'), ('string-case', 'S.Tree.Rows.FindRows(New Structure("Key", "x"), True)', 'strings'), ('string-space', 'S.Tree.Rows.FindRows(New Structure("Key", "x "), True)', 'strings'), ('undefined-value', 'S.Tree.Rows.FindRows(New Structure("Key", Undefined), True)', 'nullish'), ('null-value', 'S.Tree.Rows.FindRows(New Structure("Key", Null), True)', 'nullish'), ('result-to-source', 'S.Tree.Rows.FindRows(New Structure("Id", 4), True)', 'base', 'result-to-source'), ('source-to-result', 'S.Tree.Rows.FindRows(New Structure("Id", 4), True)', 'base', 'source-to-result'), ('array-delete', 'S.Tree.Rows.FindRows(Filter, True)', 'base', 'array-delete'), ('add-node', 'S.Tree.Rows.FindRows(Filter, True)', 'base', 'add-node'), ('filter-change', 'S.Tree.Rows.FindRows(Filter, True)', 'base', 'filter-change'), ('unknown-column.nonempty', 'S.Tree.Rows.FindRows(New Structure("Missing", 1), True)'), ('unknown-column.empty', 'S.A11.Rows.FindRows(New Structure("Missing", 1), True)'), ('missing-filter', 'S.Tree.Rows.FindRows()'), ('undefined-filter', 'S.Tree.Rows.FindRows(Undefined, True)'), ('number-filter', 'S.Tree.Rows.FindRows(1, True)'), ('fixed-filter', 'S.Tree.Rows.FindRows(New FixedStructure(Filter), True)'), ('undefined-flag', 'S.Tree.Rows.FindRows(Filter, Undefined)'), ('number-flag', 'S.Tree.Rows.FindRows(Filter, 1)'), ('string-flag', 'S.Tree.Rows.FindRows(Filter, "True")'), ('wrong-tree', 'S.Tree.FindRows(Filter, True)'), ('wrong-row', 'S.A.FindRows(Filter, True)'))
LABELS = tuple(row[0] for row in INPUTS)
PRESENT = 'Procedure Показать(Label, Value) Message(Label + ": [" + Value + "]"); EndProcedure;'


def raw_source():
    raw = (ROOT / 'integrational_tests/tests/collections.bsl').read_bytes()
    raw = raw.replace(b'\r\n', b'\n') if os.name == 'nt' else raw
    return without_tree_find_probes(raw.decode('utf-8-sig')).encode('utf-8-sig')


def fragments():
    text = raw_source().decode('utf-8-sig')
    helper = HELPER_START + text.split(HELPER_START)[1].split(HELPER_END)[0] + HELPER_END
    return helper, text[text.index(CALLS_START):]


def quoted(text):
    return '"' + text.replace('"', '""') + '"'


def array(*rows):
    value = BSLArray()
    value.items.extend(rows)
    return value


class TreeSearchInstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.vm.execute(PRESENT + fragments()[0])

    def probe(self, expression, kind='base', change='none'):
        return self.vm.execute('TreeSearchProbe(' + ', '.join(map(quoted, (expression, kind, change))) + ')')

    def witness(self, callback):
        stack = ExitStack()
        for cls in (BSLValueTree, BSLValueTreeRow, BSLValueTreeRowCollection):
            original = cls.get_method
            def method(receiver, name, original=original):
                if name.casefold() in ('findrows', 'найтистроки'):
                    return HostFunction(name, lambda *args: callback(receiver, name, args))
                return original(receiver, name)
            stack.enter_context(mock.patch.object(cls, 'get_method', method))
        return stack

    def test_only_fixed_inputs_and_independent_fresh_setup(self):
        helpers, calls = fragments()
        parse(helpers + calls)
        parsed = []
        for line in calls.splitlines()[1:-1]:
            self.assertTrue(line.startswith('Показать("tree.findrows.'))
            fields = re.findall(r'"((?:[^"]|"")*)"', line)
            fields = tuple(value.replace('""', '"') for value in fields)
            parsed.append((fields[0].removeprefix('tree.findrows.'), *fields[1:]))
        self.assertEqual(tuple(parsed), INPUTS)
        self.assertEqual(len(set(LABELS)), 36)
        self.assertEqual(helpers.count('Result = Вычислить(Expression);'), 1)
        for forbidden in ('ОписаниеОшибки', 'Выполнить(', 'ЗначениеВСтрокуВнутр', 'Найти(', '_all_rows', 'Записать', 'Прочитать', 'Пока '):
            self.assertNotIn(forbidden, helpers + calls)
        self.assertEqual(helpers.count('T = Новый ДеревоЗначений;'), 1)
        self.assertEqual(helpers.count('Добавить();'), 6)
        self.assertEqual(helpers.count('Added = S.A.Rows.Add();'), 1)
        seen = []
        def capture(receiver, alias, args):
            tree = receiver if type(receiver) is BSLValueTree else receiver.tree
            seen.append((tree, receiver, alias, args))
            # Instrumentation stub: always return the known A1 input node,
            # independent of receiver/filter; this is NOT a search implementation.
            return array(tree.rows.items[0].rows.items[0])
        with self.witness(capture):
            self.vm.execute(calls)
        self.assertEqual(len(self.output), 36)
        self.assertEqual(len(seen), 39)  # 36 primary + three explicit second calls.
        trees = []
        for entry in seen:
            if not any(entry[0] is old for old in trees): trees.append(entry[0])
        self.assertEqual(len(trees), 36)
        primaries = [next(entry for entry in seen if entry[0] is tree) for tree in trees]
        self.assertEqual([entry[2] for entry in primaries[:2]], ['НайтиСтроки', 'FindRows'])
        self.assertEqual([entry[3][1:] for entry in primaries[:7]], [(True,), (True,), (False,), (), (True,), (False,), ()])
        self.assertTrue(all(entry[1].parent is None for entry in primaries[:4]))
        self.assertEqual([entry[1].parent.get_member('Id') for entry in primaries[4:8]], [D(1), D(1), D(1), D(6)])
        self.assertEqual(primaries[27][3], ())
        self.assertIsNone(primaries[28][3][0])
        self.assertEqual(primaries[29][3][0], D(1))
        self.assertEqual(type(primaries[30][3][0]).__name__, 'BSLFixedStructure')
        self.assertEqual([entry[3][1] for entry in primaries[31:34]], [None, D(1), 'True'])
        self.assertIs(type(primaries[34][1]), BSLValueTree)
        self.assertIs(type(primaries[35][1]), BSLValueTreeRow)
        self.assertTrue(all(value.isascii() and len(value) < 640 for value in self.output))

    def test_setup_distinguishes_creation_order_from_hierarchy_without_predicting_search(self):
        self.vm.execute('S = TreeSearchFresh("base");')
        s = self.vm.variables['s']
        get = lambda name: s.get_member(name)
        self.assertEqual([get(name).get_member('Id') for name in ('A','B','B1','A1','A2','A11')], list(map(D,range(1,7))))
        self.assertIs(get('A1').parent, get('A'))
        self.assertIs(get('A2').parent, get('A'))
        self.assertIs(get('A11').parent, get('A1'))
        self.assertIs(get('B1').parent, get('B'))
        self.assertEqual(list(get('Tree').rows), [get('A'), get('B')])

    def test_result_observer_preserves_order_type_and_rejects_unbounded_input(self):
        self.vm.execute('S = TreeSearchFresh("base");')
        s = self.vm.variables['s']
        a, b = s.get_member('A'), s.get_member('B')
        for result, expected in ((array(a,b), 'array:2:1,2,'), (array(b,a), 'array:2:2,1,'),
                                 (array(), 'array:0:'), (BSLFixedArray(array(a)), 'fixed-array:1:1,'),
                                 (None, 'undefined'), (D(1), 'number'), (True, 'boolean'), ('x', 'string')):
            self.vm.variables['r'] = result
            self.assertEqual(self.vm.execute('TreeSearchResult(R)'), expected)
        for result in (array(*([a]*8)), array(D(1))):
            self.vm.variables['r'] = result
            with self.assertRaises(BSLError): self.vm.execute('TreeSearchResult(R)')
        for value in ('x'*17, '\n', 'Я', D(8), D('0.5')):
            self.vm.variables['r'] = value
            with self.assertRaises(BSLError): self.vm.execute('TreeSearchCell(R)')

    def test_complete_ascii_observer_bound_includes_state_and_two_results(self):
        self.vm.execute('S = TreeSearchFresh("base");')
        setup = self.vm.variables['s']
        for name in ('A', 'B', 'B1', 'A1', 'A2', 'A11'):
            row = setup.get_member(name)
            for field in ('Id', 'Key', 'Group'):
                row.set_member(field, '~' * 16)
            row.set_member('Mark', 'from-source')
        state = self.vm.execute('TreeSearchState(S)')
        # 7 one-digit local counts, 6 rows x 3 bounded ASCII cells + marks.
        self.assertEqual(len(state), 14 + 6 * (1 + 65 + 1 + 65 + 1 + 65 + 1 + 11))
        self.assertTrue(state.isascii())
        longest_label = max(len('tree.findrows.' + label) for label in LABELS)
        result_bound = len('fixed-array:7:') + 7 * len('7,')
        complete = longest_label + len(': [ok|change=change-error|result=') + result_bound
        complete += len('|second=') + result_bound + len('|state=') + len(state) + len(']\n')
        self.assertLessEqual(complete, 2048)

    def test_setup_action_change_and_observer_failures_are_distinct_and_continue(self):
        with mock.patch.object(BSLValueTreeRowCollection, 'add', side_effect=ValueError('PRIVATE-setup')):
            self.assertEqual(self.probe('S.Tree.Rows.FindRows(Filter)'), 'setup-error')
        def failed(receiver, alias, args):
            receiver.tree.rows.items[0].rows.items[0].set_member('Mark','from-result')
            raise ValueError('PRIVATE-action')
        with self.witness(failed):
            action = self.probe('S.Tree.Rows.FindRows(Filter)')
        self.assertTrue(action.startswith('action-error|state='))
        self.assertIn('from-result', action)
        with self.witness(lambda receiver, alias, args: array(D(1))):
            self.assertEqual(self.probe('S.Tree.Rows.FindRows(Filter)'), 'ok|change=none|observer-error')
        with self.witness(lambda receiver, alias, args: BSLFixedArray(array())):
            change = self.probe('S.Tree.Rows.FindRows(Filter)', change='array-delete')
        self.assertTrue(change.startswith('ok|change=change-error|result=fixed-array:0:'))
        with self.witness(lambda receiver, alias, args: array()):
            self.assertTrue(self.probe('S.Tree.Rows.FindRows(Filter)').startswith('ok|change=none|result=array:0:'))
        self.assertNotIn('PRIVATE', action + change)

    def test_two_way_mutation_array_delete_and_saved_result_are_actual_observations(self):
        def known(receiver, alias, args):
            return array(receiver.tree.rows.items[0].rows.items[0])
        with self.witness(known):
            for change, mark in (('result-to-source','from-result'), ('source-to-result','from-source')):
                value = self.probe('S.Tree.Rows.FindRows(Filter)', change=change)
                self.assertIn('|result-mark='+mark+'|state=', value)
                self.assertIn('/'+mark, value)
            value = self.probe('S.Tree.Rows.FindRows(Filter)', change='array-delete')
            self.assertIn('|result=array:0:|state=2,2,1,1,0,0,0,', value)
            value = self.probe('S.Tree.Rows.FindRows(Filter)', change='add-node')
            self.assertIn('|state=2,3,1,1,0,0,0,', value)
        calls = []
        def snapshots(receiver, alias, args):
            calls.append(tuple(args[0]._items.items()))
            return array(receiver.tree.rows.items[0]) if len(calls)==1 else array()
        with self.witness(snapshots):
            value = self.probe('S.Tree.Rows.FindRows(Filter)', change='filter-change')
        self.assertIn('|result=array:1:1,|second=array:0:|state=', value)
        self.assertEqual(calls[0][0][1][1], 'hit')
        self.assertEqual(calls[1][0][1][1], 'miss')


class TreeSearchSourceContract(unittest.TestCase):
    def setUp(self):
        self.source = raw_source()
        raw = (ROOT / fixtures.suite.CLIENT_SOURCE).read_bytes()
        self.template = raw.replace(b'\r\n',b'\n') if os.name=='nt' else raw

    def test_source_blocks_counts_exact_inverse_and_module_identity(self):
        helpers, calls = fragments()
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), SOURCE_SHA)
        self.assertEqual((len(self.source.splitlines()),len(self.source)), (4241,327655))
        self.assertEqual(hashlib.sha256(helpers.encode()).hexdigest(), HELPER_SHA)
        self.assertEqual(hashlib.sha256(calls.encode()).hexdigest(), CALLS_SHA)
        baseline = without_tree_findrows_probes(self.source.decode('utf-8-sig')).encode('utf-8-sig')
        self.assertEqual((len(baseline.splitlines()), len(baseline)), (4000,312961))
        self.assertEqual(hashlib.sha256(baseline).hexdigest(), BASE_SHA)
        from test_native_async_fixture import historical_tree_find_collections_module
        current=(ROOT / 'integrational_tests/tests/collections.bsl').read_bytes()
        if os.name=='nt': current=current.replace(b'\r\n',b'\n')
        module = historical_tree_find_collections_module(current,self.template)
        self.assertIn(helpers.replace('Функция ', '&НаКлиенте\nФункция ').encode(), module)
        self.assertIn(calls.encode(), module)
        self.assertEqual(fixtures.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT,1023)
        self.assertEqual(hashlib.sha256(module).hexdigest(), '6828717dcc15fbf02e9b4032952b85286dda4b1d6d597e41ffd4a7306f17be31')
        from test_native_async_fixture import historical_tree_findrows_collections_module, historical_tree_collections_module
        self.assertEqual(hashlib.sha256(historical_tree_findrows_collections_module(self.source,self.template)).hexdigest(),
                         '2e764a10a0420e5af4e9a4ededd74ff9f0d4ae18062d5beb85e245f0282dbb91')
        self.assertEqual(hashlib.sha256(historical_tree_collections_module(self.source,self.template)).hexdigest(),
                         'b8d28abf2a28f7ff11958f9f3a31a966e3032484b8f0cf7d316b24ef8fb847e8')
        for changed in (baseline, self.source.replace(b'\n',b'\r\n'), self.source[3:], self.source+b'\n'):
            with self.assertRaises(fixtures.suite.FullError): fixtures.suite.client_collections_module(changed,self.template)
        for changed in (self.source+b'\n', self.source.replace(b'S.A11.Rows.FindRows',b'S.A.Rows.FindRows',1)):
            with self.assertRaises(ValueError): without_tree_findrows_probes(changed.decode('utf-8-sig'))

    def test_block_tamper_cannot_rebase_outer_hash_and_historical_harness_is_exact(self):
        for before,after in ((b'Count > 7',b'Count > 8'), (b'"from-result"',b'"changed"'),
                             (b'B1 = B.',b'B1 = A.'), (b'S.Tree.Rows.FindRows(Filter, True)',b'S.Tree.Rows.FindRows(Filter, False)')):
            raw=(ROOT / 'integrational_tests/tests/collections.bsl').read_bytes()
            current=raw.replace(b'\r\n',b'\n') if os.name=='nt' else raw
            changed=current.replace(before,after,1)
            self.assertNotEqual(changed,current)
            with mock.patch.object(fixtures.suite,'CLIENT_COLLECTIONS_SOURCE_SHA256',hashlib.sha256(changed).hexdigest()):
                with self.assertRaises(fixtures.suite.FullError): fixtures.suite.client_collections_module(changed,self.template)
        from test_native_async_fixture import without_tree_findrows_measurement
        for host,path in ((False,'scripts/native_1c_bootstrap/full_suite.py'),(True,'scripts/native_1c_full_host.py')):
            source=(ROOT/path).read_text(encoding='utf-8')
            restored=without_tree_findrows_measurement(source,host=host)
            self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),json.loads((ROOT/'tests/tree_findrows_source_inverse.json').read_text(encoding='utf-8'))[path]['base_sha256'])
            with self.assertRaises(AssertionError): without_tree_findrows_measurement(source+'\n',host=host)

    def test_inverse_paths_require_explicit_utf8_under_cp1252_default(self):
        original = Path.read_text
        encodings = []
        def windows_default(path, *args, **kwargs):
            if path.name == 'tree_findrows_source_inverse.json':
                encodings.append(kwargs.get('encoding'))
                # Emulate a non-UTF-8 Windows default only for this offline file.
                # Production source bytes/normalization are never patched here.
                kwargs.setdefault('encoding', 'cp1252')
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'read_text', windows_default):
            self.test_block_tamper_cannot_rebase_outer_hash_and_historical_harness_is_exact()
        self.assertGreaterEqual(len(encodings), 4)
        self.assertEqual(set(encodings), {'utf-8'})

    def test_every_new_record_and_id_permutation_are_byte_exact_not_map_exceptions(self):
        import test_native_1c_map_contract as f
        contract=f.contract
        rows=f.records()
        for ordinal,label in enumerate(LABELS,867):
            rows[ordinal-1]=('tree.findrows.'+label,b'ok|array:2:1,2,')
        encoded=f.encode(rows)
        self.assertEqual(contract.compare_collections(encoded,encoded,contract.SOURCE_SHA256)['status'],'equivalent')
        expected={283:'internal.map.typed-keys.payload',286:'internal.map.typed-keys.roundtrip.payload',
                  287:'internal.map.typed-keys-again.payload',290:'internal.map.typed-keys-again.roundtrip.payload',
                  291:'internal.map.reverse-insertion.payload',294:'internal.map.reverse-insertion.roundtrip.payload',
                  303:'internal.array.nested.payload',306:'internal.array.nested.roundtrip.payload'}
        self.assertEqual(contract._ELIGIBLE,expected)
        for ordinal,label in enumerate(LABELS,867):
            self.assertNotIn('tree.findrows.'+label,contract.ELIGIBLE_LABELS)
            changed=f.encode(f.change(rows,ordinal,payload=b'ok|array:2:2,1,'))
            self.assertEqual(contract.compare_collections(encoded,changed,contract.SOURCE_SHA256)['reason'],'ineligible_difference')
        for changed in (f.encode(rows[:-1]), f.encode(rows[:866]), encoded[:-1], f.encode(rows+[('extra',b'ok')])):
            self.assertEqual(contract.compare_collections(encoded,changed,contract.SOURCE_SHA256)['status'],'rejected')
        self.assertEqual(contract.compare_collections(encoded,encoded,BASE_SHA)['reason'],'source_mismatch')


if __name__=='__main__': unittest.main()
