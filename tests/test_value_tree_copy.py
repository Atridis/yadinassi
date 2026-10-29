"""Genuine Copy capture parity plus explicitly local corruption/resource policy."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.value_trees import BSLValueTree
from scripts import native_1c_tree_copy_contract as contract
from scripts import native_1c_tree_access_probe as probe
from scripts import native_1c_tree_profiles as profiles

ROOT=Path(__file__).resolve().parents[1]
FULL_SHA='dae222dc6fe669bedadc51cb6e8ffde4e2707559c8d44f9fb7ed8aaab533112c'
MAIN_SHA='2350822aa712702e7f3ac31020a71307421dddcb6b4d5d9ed49c0eabd07c2238'


class CopyNativeCaptureTests(unittest.TestCase):
    def test_actual_unpatched_runtime_matches_exact_source_bound_native_main(self):
        fixture=ROOT/'tests/fixtures/value_tree_copy_linux_8_3_27_1508.out'
        raw=fixture.read_bytes();meta=json.loads(fixture.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(6269,FULL_SHA))
        self.assertEqual((meta['full_size'],meta['full_sha256']),(6269,FULL_SHA))
        self.assertEqual((meta['main_size'],meta['main_sha256']),(6237,MAIN_SHA))
        self.assertEqual(meta['head'],'08982c9751e03d496fa3d4b2e4d45e0900a15cfc')
        self.assertEqual(meta['run_id'],'40926194836')
        self.assertTrue(meta['native_measurement_accepted']);self.assertFalse(meta['source_run_runtime_parity_accepted'])
        spec=profiles.select('tree-copy-v1');source=(ROOT/spec.source).read_text(encoding='utf-8').encode()
        self.assertEqual(meta['source'],spec.source)
        self.assertEqual(hashlib.sha256(source).hexdigest(),meta['source_sha256'])
        self.assertEqual(spec.source_sha256,meta['source_sha256'])
        native_probe,native_main=probe.split_capture(raw)
        self.assertTrue(probe.scalar_controls_valid(native_probe))
        self.assertEqual(hashlib.sha256(native_main).hexdigest(),MAIN_SHA)
        output=[];Interpreter(output.append).execute(source.decode())
        actual=('\n'.join(output)+'\n').encode('ascii')
        actual_probe,actual_main=probe.split_capture(actual)
        self.assertTrue(probe.scalar_controls_valid(actual_probe))
        self.assertEqual(actual_main,native_main)
        self.assertEqual([case['status'] for case in contract.validate_output(actual_main)],['S']*8+['A'])
        # Exercise the real parity gate using independently executed actual bytes;
        # native bytes are never supplied as interpreter output.
        import test_native_tree_profile_budget as budget
        self.assertEqual(budget.full.digest(budget.full.generated_module(source)),meta['server_module_sha256'])
        template=(ROOT/budget.full.CLIENT_SOURCE).read_text(encoding='utf-8').encode()
        self.assertEqual(budget.full.digest(budget.tree.client_module(source,template,profile='tree-copy-v1')),meta['client_module_sha256'])
        self.assertEqual(meta['statuses'],['S']*8+['A'])
        with tempfile.TemporaryDirectory() as tmp,budget.synthetic_inventory_reader():
            root=Path(tmp).resolve(strict=True);path=root/spec.source;path.parent.mkdir(parents=True);path.write_bytes(source)
            result=budget.host.compare_output(root,root,raw,{spec.source:spec.source_sha256},
                runner=lambda *args:(0,actual,b''),profile='tree-copy-v1')
        self.assertEqual(result['status'],'matched');self.assertEqual(result['acceptance_status'],'accepted')
        self.assertEqual(result['native_main_sha256'],MAIN_SHA)
        self.assertEqual(result['interpreter_main_sha256'],MAIN_SHA)


class CopyLocalPolicyTests(unittest.TestCase):
    def fixture(self):
        t=BSLValueTree();t.columns.add('Value');r=t.rows.add();r.set_index('Value',D(1));return t

    def test_existing_unnamed_columns_keep_distinct_slots_and_schema_objects(self):
        t=BSLValueTree();a=t.columns.add();b=t.columns.add();r=t.rows.add()
        r.cells[a]=D(1);r.cells[b]=D(2);c=t.copy()
        self.assertEqual([x.name for x in c.columns.items],['',''])
        self.assertEqual(list(c.rows.items[0]),[D(1),D(2)])
        self.assertTrue(all(old is not new for old,new in zip(t.columns.items,c.columns.items)))
        c.rows.items[0].set_index(D(0),D(9));self.assertEqual(list(r),[D(1),D(2)])

    def test_copy_uses_current_hierarchy_order_not_creation_registry_order(self):
        t=self.fixture();first=t.rows.items[0];second=t.rows.add();child=first.rows.add()
        second.set_index('Value',D(2));child.set_index('Value',D(3))
        doomed=first.rows.add();first.rows.delete(doomed)
        t.rows.move(second,D(-1));c=t.copy()
        self.assertEqual([r.get_index('Value') for r in c.rows.items],[D(2),D(1)])
        cloned_child=c.rows.items[1].rows.items[0]
        self.assertEqual(cloned_child.get_index('Value'),D(3))
        self.assertIs(cloned_child.parent,c.rows.items[1]);self.assertIs(cloned_child.owner(),c)
        self.assertEqual(len(c._all_rows),3)

    def test_width_coefficients_are_bounded_before_integral_conversion(self):
        t=self.fixture();col=t.columns.items[0];col.width=D('1.00000000')
        with mock.patch('yadinassi.value_trees._MAX_NUMBER_DIGITS',8):
            with self.assertRaises(ValueError):t.copy()
        self.assertEqual(col.width,D('1.00000000'))
        col.width=D('1.0000000')
        with mock.patch('yadinassi.value_trees._MAX_NUMBER_DIGITS',8):self.assertEqual(t.copy().columns.items[0].width,col.width)

    def test_text_and_default_budgets_fail_without_mutating_source(self):
        t=self.fixture();rows=tuple(t.rows.items);columns=tuple(t.columns.items)
        with mock.patch('yadinassi.value_trees._MAX_COPY_TEXT',1):
            with self.assertRaises(ValueError):t.copy()
        vm=Interpreter();vm.execute('t=New ValueTree; q=New StringQualifiers(10,AllowedLength.Fixed); t.Columns.Add("S",New TypeDescription("String",,q)); t.Rows.Add();')
        padded=vm.execute('t')
        with mock.patch('yadinassi.value_trees._MAX_DEFAULT_TEXT',9):
            with self.assertRaises(ValueError):padded.copy()
        self.assertEqual(tuple(t.rows.items),rows);self.assertEqual(tuple(t.columns.items),columns)
        self.assertEqual(len(padded.columns.items[0].default),10)

    def test_foreign_cell_key_never_runs_equality_hook(self):
        t=self.fixture();column=t.columns.items[0]
        class Foreign:
            def __hash__(self):return hash(column)
            def __eq__(self,other):raise AssertionError('foreign equality called')
        bad=Foreign();t.rows.items[0].cells={bad:D(1)}
        with self.assertRaises(ValueError):t.copy()
        self.assertIs(next(iter(t.rows.items[0].cells)),bad)

    def test_corrupt_ownership_depth_and_registry_fail_closed(self):
        changes=(lambda t:setattr(t.rows,'parent',t.rows.items[0]),
                 lambda t:setattr(t.columns.items[0],'table',BSLValueTree()),
                 lambda t:setattr(t.rows.items[0].rows,'parent',None),
                 lambda t:setattr(t.rows.items[0],'depth',False),
                 lambda t:t._all_rows.__setitem__(t.rows.items[0],D(1)))
        for change in changes:
            t=self.fixture();change(t)
            with self.subTest(change=change),self.assertRaises(ValueError):t.copy()

    def test_deep_graph_clone_is_iterative_and_limit_is_inclusive(self):
        t=self.fixture();row=t.rows.items[0]
        for _ in range(32):row=row.rows.add()
        with mock.patch('yadinassi.value_trees._MAX_DEPTH',32):
            c=t.copy();node=c.rows.items[0]
            for _ in range(32):node=node.rows.items[0]
            self.assertEqual(node.depth,32);self.assertIs(node.owner(),c)
        with mock.patch('yadinassi.value_trees._MAX_DEPTH',31):
            with self.assertRaises(ValueError):t.copy()
