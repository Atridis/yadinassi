"""Bounded input instrumentation, not native UnloadColumn expected answers."""
from contextlib import ExitStack
from decimal import Decimal as D
import hashlib
import os
from pathlib import Path
import re
import unittest
from unittest import mock
from yadinassi import BSLError, Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRowCollection
from yadinassi.values import BSLArray, HostFunction
from test_native_tree_findrows_measurement import PRESENT

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '5a9a57fc6ef11e895191d9796bda5387c5bda25510dfa4e42591cadfade273b4'
BASE_SHA = '9de2d85c0b8409b83ccf62e4824ef7a8186518d0bdffc92b53bd98b1f98da0b3'
HELPER_SHA = '816ce1f9f4d175662f374966dc9901acd8f85090fe2672334fd39f3a8b8e88cc'
CALLS_SHA = '61814cf35c1d16af5d512db9383e79beea68ddbc0ea83c7fb8fd7075683f917d'
HELPER_START = '// Begin bounded ValueTree UnloadColumn helpers (measurement only; no native answers).\n'
HELPER_END = '// End bounded ValueTree UnloadColumn helpers.\n\n'
CALLS_START = '// Begin bounded ValueTree UnloadColumn observations (measurement only; no native answers).\n'
CALLS_END = '// End bounded ValueTree UnloadColumn observations.\n'


def raw_source():
    data = (ROOT/'integrational_tests/tests/collections.bsl').read_bytes()
    data = data.replace(b'\r\n', b'\n') if os.name == 'nt' else data
    from scripts.native_historical_replay import without_tree_load_probes
    return without_tree_load_probes(data.decode('utf-8-sig')).encode('utf-8-sig')


def block(text, start, end):
    return start + text.split(start)[1].split(end)[0] + end


def fragments():
    text = raw_source().decode('utf-8-sig')
    return block(text, HELPER_START, HELPER_END), block(text, CALLS_START, CALLS_END)


def array(values):
    result = BSLArray()
    result.items = list(values)
    return result


def quoted(text): return '"' + text.replace('"', '""') + '"'


class UnloadInstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        text = raw_source().decode('utf-8-sig')
        old = block(text, '// Begin bounded ValueTree FindRows helpers (measurement only; no native answers).\n', '// End bounded ValueTree FindRows helpers.\n\n')
        self.vm.execute(PRESENT + old + fragments()[0])

    def probe(self, expression, kind='base', change='none'):
        return self.vm.execute('TreeUnloadProbe('+', '.join(map(quoted,(expression,kind,change)))+')')

    def witness(self, callback):
        stack = ExitStack()
        for cls in (BSLValueTree, BSLValueTreeRowCollection):
            original = cls.get_method
            def method(receiver, name, original=original):
                if name.casefold() in ('unloadcolumn','выгрузитьколонку'):
                    return HostFunction(name, lambda *args: callback(receiver,name,args))
                return original(receiver,name)
            stack.enter_context(mock.patch.object(cls,'get_method',method))
        return stack

    def test_exact_inputs_and_independent_argument_routing(self):
        helper,calls=fragments();parse(helper+calls);parsed=[]
        for line in calls.splitlines()[1:-1]:
            self.assertTrue(line.startswith('Показать("tree.unload.'))
            fields=tuple(x.replace('""','"') for x in re.findall(r'"((?:[^"]|"")*)"',line))
            parsed.append((fields[0].removeprefix('tree.unload.'),*fields[1:]))
        self.assertEqual(tuple(parsed),INPUTS);self.assertEqual(len({x[0] for x in INPUTS}),30)
        self.assertEqual(helper.count('Result = Вычислить(Expression);'),1)
        for forbidden in ('ОписаниеОшибки','Выполнить(','ЗначениеВСтрокуВнутр','_all_rows','Записать','Прочитать','Пока '): self.assertNotIn(forbidden,helper+calls)
        seen=[]
        def capture(receiver,alias,args):
            seen.append((receiver,alias,args));return array([D(1),D(2)])
        with self.witness(capture): self.vm.execute(calls)
        self.assertEqual(len(seen),30);self.assertEqual(len({id(x[0]) for x in seen}),30)
        self.assertEqual([x[2] for x in seen[:2]],[('Id',),('Id',)])
        self.assertEqual([x[2] for x in seen[27:]], [(D('1.5'),), (D('1.9'),), (D('-0.5'),)])
        self.assertEqual(seen[2][0].parent.get_member('Id'),D(1));self.assertEqual(seen[3][0].parent.get_member('Id'),D(6))
        self.assertEqual([x[2] for x in seen[7:12]],[(D(0),),(D(1),),(D('0.5'),),(D(-1),),(D(4),)])
        self.assertIs(seen[12][2][0].table,seen[12][0].tree);self.assertIsNot(seen[13][2][0].table,seen[13][0].tree)
        self.assertEqual([x[2] for x in seen[16:20]],[(None,),(True,),(),('Id',True)])
        self.assertIs(type(seen[20][0]),BSLValueTree);self.assertEqual(len(self.output),30)
        self.assertTrue(all(x.isascii() and len(x)<2048 for x in self.output))
        self.assertFalse(any('setup-error' in x or 'action-error' in x or 'observer-error' in x for x in self.output))

    def test_array_mutation_and_source_membership_are_distinct(self):
        with self.witness(lambda *args: array([D(1),D(2)])):
            deleted=self.probe('S.Tree.Rows.UnloadColumn("Id")',change='array-delete')
            added=self.probe('S.Tree.Rows.UnloadColumn("Id")',change='source-add')
        self.assertIn('|result=array:1:n2,|state=2,',deleted);self.assertIn('|result=array:2:n1,n2,|state=3,',added)
        self.assertNotIn('change-error',deleted+added)

    def test_two_way_mutable_cell_identity_without_unload_algorithm(self):
        def cell(receiver,alias,args):return array([receiver.tree.rows.items[0].get_member('Key')])
        with self.witness(cell):
            for change,marker in (('result-to-source','from-result'),('source-to-result','from-source')):
                result=self.probe('S.Tree.Rows.UnloadColumn("Key")','mutable',change)
                self.assertIn('|result=array:1:structure-mark:'+marker+',|state=',result)
                self.assertEqual(result.count('structure-mark:'+marker),2);self.assertNotIn('error',result)

    def test_failure_stages_and_private_errors_remain_distinct(self):
        with mock.patch.object(BSLValueTreeRowCollection,'add',side_effect=ValueError('PRIVATE-setup')):
            self.assertEqual(self.probe('S.Tree.Rows.UnloadColumn("Id")'),'setup-error')
        def fail(receiver,alias,args):
            receiver.tree.rows.items[0].set_member('Mark','from-result');raise ValueError('PRIVATE-action')
        with self.witness(fail):result=self.probe('S.Tree.Rows.UnloadColumn("Id")')
        self.assertTrue(result.startswith('action-error|state='));self.assertIn('from-result',result);self.assertNotIn('PRIVATE',result)
        with self.witness(lambda *args:None):result=self.probe('S.Tree.Rows.UnloadColumn("Id")',change='array-delete')
        self.assertTrue(result.startswith('ok|change=change-error|result=undefined|state='))
        with self.witness(lambda *args:array([BSLArray()])):
            self.assertEqual(self.probe('S.Tree.Rows.UnloadColumn("Id")'),'ok|change=none|observer-error')

    def test_scalar_and_one_field_structure_observer_fail_closed(self):
        for source in ('New Structure("Mark,Extra","base",1)','New Structure("Other","base")','New Structure("Mark","PRIVATE")','New Structure("Mark",1)','New Array','8','-1','0.5','"é"'):
            with self.assertRaises(BSLError):self.vm.execute('TreeUnloadCell('+source+')')
        self.assertEqual(self.vm.execute('TreeUnloadCell(New Structure("Mark","base"))'),'structure-mark:base')
        self.assertEqual(self.vm.execute('TreeUnloadResult(New FixedArray(New Array))'),'fixed-array:0:')
        self.assertEqual(self.vm.execute('TreeUnloadResult(1)'),'number')
        self.vm.variables['r']=array([D(1)]*8)
        with self.assertRaises(BSLError):self.vm.execute('TreeUnloadResult(R)')

    def test_complete_record_bound(self):
        self.vm.execute('S = TreeSearchFresh("base");');s=self.vm.variables['s']
        for name in ('A','B','B1','A1','A2','A11'):
            row=s.get_member(name)
            for field in ('Id','Key','Group'):row.set_member(field,'~'*16)
            row.set_member('Mark','from-source')
        state=self.vm.execute('TreeUnloadState(S)');self.vm.variables['r']=array(['~'*16]*7)
        result=self.vm.execute('TreeUnloadResult(R)')
        self.assertEqual(len(state),14+6*(1+65+1+65+1+65+1+11))
        self.assertLessEqual(len('structure-mark:from-source'),65)
        bound=max(len('tree.unload.'+x[0]) for x in INPUTS)+len(': [ok|change=change-error|result=')+len(result)+len('|state=')+len(state)+len(']\n')
        self.assertLessEqual(bound,2048)


class UnloadSourceContractTests(unittest.TestCase):
    def test_exact_new_blocks_preserve_every_previous_byte(self):
        source=raw_source();helper,calls=fragments()
        self.assertEqual(hashlib.sha256(source).hexdigest(),SOURCE_SHA);self.assertEqual(len(source.splitlines()),4504)
        self.assertEqual(hashlib.sha256(helper.encode()).hexdigest(),HELPER_SHA);self.assertEqual(hashlib.sha256(calls.encode()).hexdigest(),CALLS_SHA)
        text=source.decode('utf-8-sig');self.assertTrue(text.endswith('\n'+calls))
        restored=text.replace(helper,'',1)[:-len('\n'+calls)].encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(restored).hexdigest(),BASE_SHA);self.assertEqual(len(restored.splitlines()),4360)


    def test_supplement_restores_exact_original27_source(self):
        from scripts.native_historical_replay import without_tree_unload_supplement, TREE_UNLOAD_SUPPLEMENT
        source = raw_source().decode('utf-8-sig')
        restored = without_tree_unload_supplement(source)
        self.assertEqual(hashlib.sha256(restored.encode('utf-8-sig')).hexdigest(),
                         'bae7fc1e006a68f9fba17800e5332d68bbcb028996e7f9b29d45ecf4b4759ada')
        self.assertEqual(len(restored.splitlines()), 4501)
        self.assertEqual(source.replace(TREE_UNLOAD_SUPPLEMENT, '', 1), restored)
        self.assertEqual(len(TREE_UNLOAD_SUPPLEMENT.splitlines()), 3)
        for changed in (source+'\n', source.replace('UnloadColumn(1.9)', 'UnloadColumn(1.8)'),
                        source.replace('\n', '\r\n'), restored):
            with self.assertRaises(ValueError): without_tree_unload_supplement(changed)

    def test_live_adapter_and_inverse_reject_probe_drift(self):
        import test_native_1c_full_stage as fixtures
        from scripts.native_historical_replay import without_tree_unload_probes
        source = raw_source()
        template = (ROOT / fixtures.suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt': template = template.replace(b'\r\n', b'\n')
        from test_native_async_fixture import historical_tree_load_collections_module
        current = (ROOT/'integrational_tests/tests/collections.bsl').read_bytes()
        if os.name == 'nt': current = current.replace(b'\r\n', b'\n')
        module = historical_tree_load_collections_module(current, template)
        self.assertEqual(fixtures.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT, 1023)
        self.assertEqual(hashlib.sha256(module).hexdigest(), 'a7bfc4e3361bdb1bfde5794b211f3fd1c0594f5c81b4f5e3dafecac4c3049786')
        restored = without_tree_unload_probes(source.decode('utf-8-sig')).encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(restored).hexdigest(), BASE_SHA)
        for changed in (restored, source+b'\n', source[3:], source.replace(b'\n', b'\r\n')):
            with self.assertRaises(fixtures.suite.FullError): fixtures.suite.client_collections_module(changed, template)
        for old,new in ((b'Value.Count() <> 1', b'Value.Count() <> 2'),
                        (b'S.Tree.Rows.UnloadColumn(0.5)', b'S.Tree.Rows.UnloadColumn(1.5)')):
            changed = source.replace(old,new,1)
            self.assertNotEqual(changed,source)
            with mock.patch.object(fixtures.suite,'CLIENT_COLLECTIONS_SOURCE_SHA256',hashlib.sha256(changed).hexdigest()):
                with self.assertRaises(fixtures.suite.FullError): fixtures.suite.client_collections_module(changed,template)
            with self.assertRaises(ValueError): without_tree_unload_probes(changed.decode('utf-8-sig'))

    def test_each_new_record_is_strict_and_never_a_map_exception(self):
        import test_native_1c_map_contract as f
        rows = f.records()
        for ordinal,row in enumerate(INPUTS,947): rows[ordinal-1] = ('tree.unload.'+row[0], b'array:2:n1,n2,')
        encoded = f.encode(rows)
        self.assertEqual(f.contract.compare_collections(encoded,encoded,f.SOURCE)['status'],'equivalent')
        for ordinal,row in enumerate(INPUTS,947):
            self.assertNotIn('tree.unload.'+row[0],f.contract.ELIGIBLE_LABELS)
            changed=f.encode(f.change(rows,ordinal,payload=b'array:2:n2,n1,'))
            self.assertEqual(f.contract.compare_collections(encoded,changed,f.SOURCE)['reason'],'ineligible_difference')
        for changed in (f.encode(rows[:946]), f.encode(rows[:-1]), encoded[:-1]):
            self.assertEqual(f.contract.compare_collections(encoded,changed,f.SOURCE)['status'],'rejected')

INPUTS = (('alias.ru', 'S.Tree.Строки.ВыгрузитьКолонку("Id")'), ('alias.en', 'S.Tree.Rows.UnloadColumn("Id")'), ('child', 'S.A.Rows.UnloadColumn("Id")'), ('leaf', 'S.A11.Rows.UnloadColumn("Id")'), ('empty', 'S.Tree.Rows.UnloadColumn("Id")', 'empty'), ('no-columns', 'S.Tree.Rows.UnloadColumn("Id")', 'no-columns'), ('selector.case', 'S.Tree.Rows.UnloadColumn("iD")'), ('selector.index-zero', 'S.Tree.Rows.UnloadColumn(0)'), ('selector.index-one', 'S.Tree.Rows.UnloadColumn(1)'), ('selector.fraction', 'S.Tree.Rows.UnloadColumn(0.5)'), ('selector.negative', 'S.Tree.Rows.UnloadColumn(-1)'), ('selector.out-of-range', 'S.Tree.Rows.UnloadColumn(4)'), ('selector.own-column', 'S.Tree.Rows.UnloadColumn(S.Tree.Columns.Get(1))'), ('selector.foreign-column', 'S.Tree.Rows.UnloadColumn(Foreign.Columns.Get(0))'), ('selector.unknown', 'S.Tree.Rows.UnloadColumn("Missing")'), ('selector.unknown-empty', 'S.A11.Rows.UnloadColumn("Missing")'), ('selector.undefined', 'S.Tree.Rows.UnloadColumn(Undefined)'), ('selector.boolean', 'S.Tree.Rows.UnloadColumn(True)'), ('missing-argument', 'S.Tree.Rows.UnloadColumn()'), ('extra-argument', 'S.Tree.Rows.UnloadColumn("Id", True)'), ('wrong-tree', 'S.Tree.UnloadColumn("Id")'), ('values.scalars', 'S.Tree.Rows.UnloadColumn("Key")', 'scalars'), ('values.nullish', 'S.Tree.Rows.UnloadColumn("Key")', 'nullish'), ('array-delete', 'S.Tree.Rows.UnloadColumn("Id")', 'base', 'array-delete'), ('source-add', 'S.Tree.Rows.UnloadColumn("Id")', 'base', 'source-add'), ('mutable.result-to-source', 'S.Tree.Rows.UnloadColumn("Key")', 'mutable', 'result-to-source'), ('mutable.source-to-result', 'S.Tree.Rows.UnloadColumn("Key")', 'mutable', 'source-to-result'))
INPUTS += (('selector.fraction-one-half', 'S.Tree.Rows.UnloadColumn(1.5)'), ('selector.fraction-one-nine', 'S.Tree.Rows.UnloadColumn(1.9)'), ('selector.fraction-negative-half', 'S.Tree.Rows.UnloadColumn(-0.5)'))
if __name__=='__main__':unittest.main()
