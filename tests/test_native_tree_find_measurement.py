"""Fixed inputs and independent instrumentation, never native expected answers."""
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
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRow, BSLValueTreeRowCollection
from yadinassi.values import BSLArray, HostFunction
from scripts.native_historical_replay import without_tree_find_probes
import test_native_1c_full_stage as fixtures
from test_native_tree_findrows_measurement import fragments as old_fragments, PRESENT

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'd94101cf391fa84668b7f94bb9295655d62d3ff6baa084de17a48b62966a0901'
BASE_SHA = '5468d16850a9774251d4ef80ae5e938afdfabef69fe496cb3a6cb579d0564782'
HELPER_SHA = 'a43a652d9327fe026a3b61f7063c35eac014ee0fe385f37605396198354ba679'
CALLS_SHA = 'f289a6a06ed23a2bf1af90800255473491a73e433bf7f21a10a98180d60457be'
HELPER_START = '// Begin bounded ValueTree Find helpers (measurement only; no native answers).\n'
HELPER_END = '// End bounded ValueTree Find helpers.\n\n'
CALLS_START = '// Begin bounded ValueTree Find observations (measurement only; no native answers).\n'
CALLS_END = '// End bounded ValueTree Find observations.\n'


def raw_source():
    raw = (ROOT / 'integrational_tests/tests/collections.bsl').read_bytes()
    return raw.replace(b'\r\n', b'\n') if os.name == 'nt' else raw


def fragments():
    text = raw_source().decode('utf-8-sig')
    return (HELPER_START + text.split(HELPER_START)[1].split(HELPER_END)[0] + HELPER_END,
            text[text.index(CALLS_START):])


def quoted(text):
    return '"' + text.replace('"', '""') + '"'


class FindInstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.vm.execute(PRESENT + old_fragments()[0] + fragments()[0])

    def probe(self, expression, kind='base', change='none'):
        return self.vm.execute('TreeFindProbe(' + ', '.join(map(quoted, (expression, kind, change))) + ')')

    def witness(self, callback):
        stack = ExitStack()
        for cls in (BSLValueTree, BSLValueTreeRow, BSLValueTreeRowCollection):
            original = cls.get_method
            def method(receiver, name, original=original):
                if name.casefold() in ('find', 'найти'):
                    return HostFunction(name, lambda *args: callback(receiver, name, args))
                return original(receiver, name)
            stack.enter_context(mock.patch.object(cls, 'get_method', method))
        return stack

    def test_fixed_inputs_fresh_setup_exact_argument_routing(self):
        helper, calls = fragments()
        parse(helper + calls)
        parsed = []
        for line in calls.splitlines()[1:-1]:
            self.assertTrue(line.startswith('Показать("tree.find.'))
            fields = tuple(x.replace('""', '"') for x in re.findall(r'"((?:[^"]|"")*)"', line))
            parsed.append((fields[0].removeprefix('tree.find.'), *fields[1:]))
        self.assertEqual(tuple(parsed), INPUTS)
        self.assertEqual(len({row[0] for row in INPUTS}), 42)
        self.assertEqual(helper.count('Result = Вычислить(Expression);'), 1)
        for forbidden in ('ОписаниеОшибки', 'Выполнить(', 'ЗначениеВСтрокуВнутр', '_all_rows', 'Записать', 'Прочитать', 'Пока '):
            self.assertNotIn(forbidden, helper + calls)
        seen = []
        def capture(receiver, alias, args):
            tree = receiver if type(receiver) is BSLValueTree else receiver.tree
            seen.append((tree, receiver, alias, args))
            # Stub always returns known A1 independently of query/columns/flags.
            return tree.rows.items[0].rows.items[0] if tree.rows.items else None
        with self.witness(capture):
            self.vm.execute(calls)
        self.assertEqual(len(seen), 42)
        self.assertEqual(len({id(row[0]) for row in seen}), 42)
        self.assertEqual([row[2] for row in seen[:2]], ['Найти', 'Find'])
        self.assertEqual([row[3] for row in seen[:4]], [('hit','Key',True), ('hit','Key',True), ('hit','Key',False), ('hit','Key')])
        self.assertEqual([row[1].parent.get_member('Id') for row in seen[4:8]], [D(1),D(1),D(1),D(6)])
        self.assertEqual(seen[13][3], ('x',))
        self.assertEqual(seen[15][3], ('x',None,True))
        self.assertEqual(seen[33][3], ())
        self.assertEqual(seen[34][3], ('hit','Key',None))
        self.assertIs(type(seen[37][1]), BSLValueTree)
        self.assertIs(type(seen[38][1]), BSLValueTreeRow)
        self.assertEqual(len(self.output),42)
        self.assertTrue(all(x.isascii() and len(x)<2048 for x in self.output))
        self.assertFalse(any('setup-error' in x or 'observer-error' in x for x in self.output))

    def test_row_observer_records_identity_parent_level_and_mark(self):
        self.vm.execute('S = TreeSearchFresh("base");')
        s = self.vm.variables['s']
        self.vm.variables['r'] = s.get_member('A11')
        self.assertEqual(self.vm.execute('TreeFindResult(R,S)'), 'row:6:parent=n4:level=n2:owner=b1:mark=base')
        other = BSLValueTree(); other.columns.add('Id'); other.columns.add('Mark')
        foreign = other.rows.add(); foreign.set_member('Id',D(1)); foreign.set_member('Mark','base')
        self.vm.variables['r'] = foreign
        self.assertEqual(self.vm.execute('TreeFindResult(R,S)'), 'row:1:parent=undefined:level=n0:owner=b0:mark=base')
        for result, expected in ((None,'undefined'),(D(1),'number'),(True,'boolean'),('x','string'),(BSLArray(),'array:0:')):
            self.vm.variables['r'] = result
            self.assertEqual(self.vm.execute('TreeFindResult(R,S)'),expected)
        for value in (D(0),D(7),D('1.5'),'1'):
            s.get_member('A').set_member('Id',value)
            self.vm.variables['r'] = s.get_member('A')
            with self.assertRaises(BSLError): self.vm.execute('TreeFindResult(R,S)')

    def test_setup_action_change_and_observer_failures_remain_distinct(self):
        with mock.patch.object(BSLValueTreeRowCollection,'add',side_effect=ValueError('PRIVATE-setup')):
            self.assertEqual(self.probe('S.Tree.Rows.Find("hit")'),'setup-error')
        def failure(receiver, alias, args):
            receiver.tree.rows.items[0].set_member('Mark','from-result')
            raise ValueError('PRIVATE-action')
        with self.witness(failure):
            result=self.probe('S.Tree.Rows.Find("hit")')
        self.assertTrue(result.startswith('action-error|state='))
        self.assertIn('from-result',result)
        self.assertNotIn('PRIVATE',result)
        with self.witness(lambda *args: None):
            result=self.probe('S.Tree.Rows.Find(4,"Id",True)',change='result-to-source')
        self.assertTrue(result.startswith('ok|change=change-error|result=undefined|state='))
        def invalid(receiver, alias, args):
            r=receiver.tree.rows.items[0]; r.set_member('Id',D(7)); return r
        with self.witness(invalid):
            self.assertEqual(self.probe('S.Tree.Rows.Find("hit")'),'ok|change=none|observer-error')

    def test_two_way_live_reference_mutation_is_observed_without_search_algorithm(self):
        with self.witness(lambda receiver, alias, args: receiver.tree.rows.items[0].rows.items[0]):
            for change,mark in (('result-to-source','from-result'),('source-to-result','from-source')):
                result=self.probe('S.Tree.Rows.Find(4,"Id",True)',change=change)
                self.assertIn('|result=row:4:parent=n1:level=n1:owner=b1:mark='+mark+'|state=',result)
                self.assertEqual(result.count(mark),2)

    def test_complete_record_bound_includes_worst_source_cells(self):
        self.vm.execute('S = TreeSearchFresh("base");')
        s=self.vm.variables['s']
        for name in ('A','B','B1','A1','A2','A11'):
            row=s.get_member(name)
            for field in ('Id','Key','Group'): row.set_member(field,'~'*16)
            row.set_member('Mark','from-source')
        state=self.vm.execute('TreeSearchState(S)')
        self.assertEqual(len(state),14+6*(1+65+1+65+1+65+1+11))
        longest=max(len('tree.find.'+r[0]) for r in INPUTS)
        # Non-row array result has <=7 IDs; the row form includes bounded parent,
        # level, owner, mark. Reserve the larger form and all status delimiters.
        result_bound=128
        complete=longest+len(': [ok|change=change-error|result=')+result_bound+len('|state=')+len(state)+len(']\n')
        self.assertLessEqual(complete,2048)


class FindSourceContractTests(unittest.TestCase):
    def test_exact_new_and_old_source_and_live_module(self):
        source=raw_source(); helper,calls=fragments()
        self.assertEqual(hashlib.sha256(source).hexdigest(),SOURCE_SHA)
        self.assertEqual(len(source.splitlines()),4358)
        self.assertEqual(hashlib.sha256(helper.encode()).hexdigest(),HELPER_SHA)
        self.assertEqual(hashlib.sha256(calls.encode()).hexdigest(),CALLS_SHA)
        old=without_tree_find_probes(source.decode('utf-8-sig')).encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(old).hexdigest(),BASE_SHA)
        self.assertEqual((len(old),len(old.splitlines())),(327655,4241))
        template=(ROOT/fixtures.suite.CLIENT_SOURCE).read_bytes()
        if os.name=='nt':template=template.replace(b'\r\n',b'\n')
        module=fixtures.suite.client_collections_module(source,template)
        self.assertEqual(fixtures.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT,944)
        self.assertIn(calls.encode(),module)
        for changed in (old,source+b'\n',source[3:],source.replace(b'\n',b'\r\n')):
            with self.assertRaises(fixtures.suite.FullError):fixtures.suite.client_collections_module(changed,template)
        for before,after in ((b'ParentId = "undefined"',b'ParentId = "changed"'),(b'Id > 6',b'Id > 7'),(b'S.A.Rows.Find(""hit"", ""Key"", True)',b'S.B.Rows.Find(""hit"", ""Key"", True)')):
            changed=source.replace(before,after,1);self.assertNotEqual(changed,source)
            with mock.patch.object(fixtures.suite,'CLIENT_COLLECTIONS_SOURCE_SHA256',hashlib.sha256(changed).hexdigest()):
                with self.assertRaises(fixtures.suite.FullError):fixtures.suite.client_collections_module(changed,template)
            with self.assertRaises(ValueError):without_tree_find_probes(changed.decode('utf-8-sig'))

    def test_every_new_record_is_byte_exact_and_never_map_exception(self):
        import test_native_1c_map_contract as f
        rows=f.records()
        for ordinal,row in enumerate(INPUTS,903):rows[ordinal-1]=('tree.find.'+row[0],b'row:4')
        encoded=f.encode(rows)
        self.assertEqual(f.contract.compare_collections(encoded,encoded,SOURCE_SHA)['status'],'equivalent')
        for ordinal,row in enumerate(INPUTS,903):
            self.assertNotIn('tree.find.'+row[0],f.contract.ELIGIBLE_LABELS)
            changed=f.encode(f.change(rows,ordinal,payload=b'row:5'))
            self.assertEqual(f.contract.compare_collections(encoded,changed,SOURCE_SHA)['reason'],'ineligible_difference')
        for changed in (f.encode(rows[:902]),f.encode(rows[:-1]),encoded[:-1]):
            self.assertEqual(f.contract.compare_collections(encoded,changed,SOURCE_SHA)['status'],'rejected')


INPUTS = (('alias.ru', 'S.Tree.Строки.Найти("hit", "Key", Истина)'), ('alias.en', 'S.Tree.Rows.Find("hit", "Key", True)'), ('root.false', 'S.Tree.Rows.Find("hit", "Key", False)'), ('root.omitted', 'S.Tree.Rows.Find("hit", "Key")'), ('child.true', 'S.A.Rows.Find("hit", "Key", True)'), ('child.false', 'S.A.Rows.Find("hit", "Key", False)'), ('child.omitted', 'S.A.Rows.Find("hit", "Key")'), ('leaf', 'S.A11.Rows.Find("hit", "Key", True)'), ('no-match', 'S.Tree.Rows.Find("absent", "Key", True)'), ('descendants.true', 'S.Tree.Rows.Find("hit", "Key", True)', 'descendants'), ('descendants.false', 'S.Tree.Rows.Find("hit", "Key", False)', 'descendants'), ('descendants.omitted', 'S.Tree.Rows.Find("hit", "Key")', 'descendants'), ('child-descendants', 'S.A.Rows.Find("hit", "Key", True)', 'descendants'), ('columns.omitted', 'S.Tree.Rows.Find("x")'), ('columns.empty', 'S.Tree.Rows.Find("x", "", True)'), ('columns.undefined', 'S.Tree.Rows.Find("x", Undefined, True)'), ('columns.case', 'S.Tree.Rows.Find("hit", "kEy", True)'), ('columns.order', 'S.Tree.Rows.Find("hit", "Key,Group", True)', 'cross-columns'), ('columns.reversed', 'S.Tree.Rows.Find("hit", "Group,Key", True)', 'cross-columns'), ('columns.spaces', 'S.Tree.Rows.Find("hit", " Key , Group ", True)', 'cross-columns'), ('columns.duplicate', 'S.Tree.Rows.Find("hit", "Key,Key", True)'), ('columns.unknown', 'S.Tree.Rows.Find("hit", "Missing", True)'), ('columns.unknown-empty', 'S.A11.Rows.Find("hit", "Missing", True)'), ('columns.known-unknown', 'S.Tree.Rows.Find("hit", "Key,Missing", True)'), ('columns.number', 'S.Tree.Rows.Find("hit", 1, True)'), ('value.number', 'S.Tree.Rows.Find(1, "Key", True)', 'scalars'), ('value.boolean', 'S.Tree.Rows.Find(True, "Key", True)', 'scalars'), ('value.string-case', 'S.Tree.Rows.Find("X", "Key", True)', 'strings'), ('value.string-space', 'S.Tree.Rows.Find("x ", "Key", True)', 'strings'), ('value.undefined', 'S.Tree.Rows.Find(Undefined, "Key", True)', 'nullish'), ('value.null', 'S.Tree.Rows.Find(Null, "Key", True)', 'nullish'), ('result-to-source', 'S.Tree.Rows.Find(4, "Id", True)', 'base', 'result-to-source'), ('source-to-result', 'S.Tree.Rows.Find(4, "Id", True)', 'base', 'source-to-result'), ('missing-value', 'S.Tree.Rows.Find()'), ('flag.undefined', 'S.Tree.Rows.Find("hit", "Key", Undefined)'), ('flag.number', 'S.Tree.Rows.Find("hit", "Key", 1)'), ('flag.string', 'S.Tree.Rows.Find("hit", "Key", "True")'), ('wrong-tree', 'S.Tree.Find("hit", "Key", True)'), ('wrong-row', 'S.A.Find("hit", "Key", True)'), ('empty-tree', 'S.Tree.Rows.Find("hit", "Key", True)', 'empty'), ('no-columns', 'S.Tree.Rows.Find("hit")', 'no-columns'), ('empty-token', 'S.Tree.Rows.Find("hit", "Key,,Group", True)'))

if __name__ == '__main__': unittest.main()
