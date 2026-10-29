"""Copy semantics from genuine run40926194836; safety checks are local policy.

Evidence: tree-copy-pr147-native-audit-v5/RESULT.json, native capture SHA256
 dae222dc6fe669bedadc51cb6e8ffde4e2707559c8d44f9fb7ed8aaab533112c.
Do not require native Rows getter wrapper identity; ownership is the stable key.
"""
from decimal import Decimal as D
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.value_trees import BSLValueTree

FIXTURE = '''
t=New ValueTree;
t.Columns.Add("Payload",,"P",3);
t.Columns.Add("N",New TypeDescription("Number",New NumberQualifiers(6,2)),"N",4);
t.Columns.Add("Text",New TypeDescription("String",,New StringQualifiers(5)),"Text",5);
r=t.Rows.Add(); child=r.Rows.Add(); grand=child.Rows.Add(); other=t.Rows.Add();
r.Payload=1; r.N=1; r.Text="a";
child.Payload=True; child.N=2; child.Text="b";
grand.Payload=Null; grand.N=3; grand.Text="c";
other.Payload=Undefined; other.N=4; other.Text="d";
'''


class CopyNativeSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.vm=Interpreter(); self.vm.execute(FIXTURE)

    def evaluate(self, expression):
        return self.vm.execute(expression)

    def true(self, expression):
        self.assertIs(self.evaluate("("+expression+")"),True,expression)

    def test_both_aliases_empty_and_schema_only(self):
        for alias in ('Copy','Скопировать'):
            self.vm.execute(f'e=New ValueTree; f=e.{alias}();')
            self.true('TypeOf(f)=Type("ValueTree")'); self.true('f<>e')
            self.assertEqual(self.evaluate('f.Rows.Count()'),D(0))
            self.assertEqual(self.evaluate('f.Columns.Count()'),D(0))
            self.vm.execute(f'e.Columns.Add("N",,"number",7); f=e.{alias}();')
            self.true('f.Columns<>e.Columns'); self.true('f.Columns.Get(0)<>e.Columns.Get(0)')
            self.assertEqual(self.evaluate('f.Columns.Get(0).Title'),'number')
            self.assertEqual(self.evaluate('f.Columns.Get(0).Width'),D(7))
            self.assertEqual(self.evaluate('f.Rows.Count()'),D(0))

    def test_hierarchy_order_owner_parent_level_and_scalar_types(self):
        self.vm.execute('c=t.Copy(); cr=c.Rows.Get(0); cc=cr.Rows.Get(0); cg=cc.Rows.Get(0); co=c.Rows.Get(1);')
        for expr in ('c<>t','cr<>r','cc<>child','cg<>grand','co<>other',
                     'cr.Owner()=c','cc.Owner()=c','cg.Owner()=c','co.Owner()=c',
                     'cr.Parent=Undefined','co.Parent=Undefined','cc.Parent=cr','cg.Parent=cc',
                     'c.Rows.Parent=Undefined','cr.Rows.Parent=cr','cc.Rows.Parent=cc',
                     'TypeOf(cr.Payload)=Type("Number")','TypeOf(cc.Payload)=Type("Boolean")',
                     'TypeOf(cg.Payload)=Type("Null")','TypeOf(co.Payload)=Type("Undefined")'):
            self.true(expr)
        for expr, expected in [('c.Rows.Count()',2),('cr.Rows.Count()',1),('cc.Rows.Count()',1),
                               ('cg.Rows.Count()',0),('cr.Level()',0),('cc.Level()',1),('cg.Level()',2),
                               ('cr.N',1),('cc.N',2),('cg.N',3),('co.N',4)]:
            self.assertEqual(self.evaluate(expr),D(expected))
        self.assertEqual([self.evaluate(expr) for expr in ('cr.Text','cc.Text','cg.Text','co.Text')],list('abcd'))

    def test_column_metadata_and_type_qualifiers(self):
        self.vm.execute('c=t.Copy();')
        for i,(name,title,width) in enumerate([('Payload','P',3),('N','N',4),('Text','Text',5)]):
            self.true(f'c.Columns.Get({i})<>t.Columns.Get({i})')
            for field,value in [('Name',name),('Title',title),('Width',D(width))]:
                self.assertEqual(self.evaluate(f'c.Columns.Get({i}).{field}'),value)
        self.assertEqual(self.evaluate('c.Columns.Get(0).ValueType.Types().Count()'),D(0))
        self.true('c.Columns.Get(1).ValueType.Types().Get(0)=Type("Number")')
        self.assertEqual(self.evaluate('c.Columns.Get(1).ValueType.NumberQualifiers.Digits'),D(6))
        self.assertEqual(self.evaluate('c.Columns.Get(1).ValueType.NumberQualifiers.FractionDigits'),D(2))
        self.true('c.Columns.Get(1).ValueType.NumberQualifiers.AllowedSign=AllowedSign.Any')
        self.true('c.Columns.Get(2).ValueType.Types().Get(0)=Type("String")')
        self.assertEqual(self.evaluate('c.Columns.Get(2).ValueType.StringQualifiers.Length'),D(5))
        self.true('c.Columns.Get(2).ValueType.StringQualifiers.AllowedLength=AllowedLength.Variable')

    def test_scalar_slots_are_independent_in_both_directions(self):
        self.vm.execute('c=t.Copy(); c.Rows.Get(0).Payload=5; child.N=6;')
        self.assertEqual(self.evaluate('r.Payload'),D(1))
        self.assertEqual(self.evaluate('c.Rows.Get(0).Payload'),D(5))
        self.assertEqual(self.evaluate('c.Rows.Get(0).Rows.Get(0).N'),D(2))
        self.assertEqual(self.evaluate('child.N'),D(6))

    def test_schema_mutations_independent_in_both_directions(self):
        self.vm.execute('c=t.Copy(); col=c.Columns.Get(0); col.Name="X"; col.Title="Q"; col.Width=6; c.Columns.Add("Y");')
        self.assertEqual(self.evaluate('t.Columns.Count()'),D(3))
        self.assertEqual(self.evaluate('t.Columns.Get(0).Name'),'Payload')
        self.assertEqual(self.evaluate('t.Columns.Get(0).Title'),'P')
        self.assertEqual(self.evaluate('t.Columns.Get(0).Width'),D(3))
        self.vm.execute('t.Columns.Get(0).Name="Y"; t.Columns.Add("X"); t.Columns.Delete(t.Columns.Get(1));')
        self.assertEqual(self.evaluate('c.Columns.Get(1).Name'),'N')
        self.assertEqual(self.evaluate('c.Rows.Get(0).N'),D(1))
        self.vm.execute('c.Columns.Delete(c.Columns.Get(1));')
        self.assertEqual(self.evaluate('t.Columns.Get(1).Name'),'Text')
        self.assertEqual(self.evaluate('r.Y'),D(1))

    def test_row_add_delete_independent_in_both_directions(self):
        self.vm.execute('c=t.Copy(); cr=c.Rows.Get(0); cc=cr.Rows.Get(0); cg=cc.Rows.Get(0); '
                        'added=cr.Rows.Add(); c.Rows.Delete(c.Rows.Get(1));')
        self.assertEqual(self.evaluate('t.Rows.Count()'),D(2))
        self.assertEqual(self.evaluate('r.Rows.Count()'),D(1))
        self.assertEqual(self.evaluate('cr.Rows.Count()'),D(2))
        self.vm.execute('t.Rows.Add(); r.Rows.Delete(child);')
        self.assertEqual(self.evaluate('t.Rows.Count()'),D(3))
        self.assertEqual(self.evaluate('c.Rows.Count()'),D(1))
        self.assertEqual(self.evaluate('cc.N'),D(2))
        self.assertEqual(self.evaluate('cg.N'),D(3))
        self.true('cc.Parent=cr'); self.true('cg.Parent=cc')

    def test_shared_outer_nested_arrays_and_alias_groups(self):
        self.vm.execute('inner=New Array; inner.Add(2); a=New Array; a.Add(1); a.Add(inner); '
                        'inner2=New Array; inner2.Add(2); a2=New Array; a2.Add(1); a2.Add(inner2); '
                        'r.Payload=a; child.Payload=a; grand.Payload=a2; c=t.Copy(); '
                        'cr=c.Rows.Get(0); cc=cr.Rows.Get(0); cg=cc.Rows.Get(0); '
                        'ca=cr.Payload; ci=ca.Get(1);')
        for expr in ('ca=a','ci=inner','cc.Payload=a','cg.Payload=a2','cg.Payload<>ca'):
            self.true(expr)
        self.vm.execute('ca.Set(0,3); ci.Set(0,4);')
        self.assertEqual(self.evaluate('a.Get(0)'),D(3))
        self.assertEqual(self.evaluate('inner.Get(0)'),D(4))
        self.assertEqual(self.evaluate('a2.Get(0)'),D(1))
        self.assertEqual(self.evaluate('inner2.Get(0)'),D(2))
        self.vm.execute('a.Set(0,5); inner.Set(0,6);')
        self.assertEqual(self.evaluate('ca.Get(0)'),D(5))
        self.assertEqual(self.evaluate('ci.Get(0)'),D(6))
        self.true('cc.Payload=ca')

    def test_extra_argument_rejected_without_source_change(self):
        source=self.evaluate('t')
        columns=tuple(source.columns.items); rows=tuple(source.rows.items)
        row_registry=dict(source._all_rows)
        cells={id(row):dict(row.cells) for row in source._all_rows}
        for alias in ('Copy','Скопировать'):
            with self.assertRaises(BSLError):self.vm.execute(f't.{alias}(1);')
            self.assertEqual(tuple(source.columns.items),columns)
            self.assertEqual(tuple(source.rows.items),rows)
            self.assertEqual(source._all_rows,row_registry)
            self.assertEqual({id(row):dict(row.cells) for row in source._all_rows},cells)


class CopyLocalSafetyTests(unittest.TestCase):
    """Local boundedness/no-hook policy, NOT measured native behavior."""
    def fixture(self):
        vm=Interpreter();vm.execute(FIXTURE);return vm.execute('t')

    def test_local_existing_budgets_reject_over_limit_without_mutation(self):
        for name,limit in [('_MAX_ROWS',3),('_MAX_COLUMNS',2),('_MAX_CELLS',11),('_MAX_DEPTH',1)]:
            tree=self.fixture(); rows=tuple(tree.rows.items); registry=dict(tree._all_rows)
            with self.subTest(name=name),patch('yadinassi.value_trees.'+name,limit):
                with self.assertRaises((ValueError,TypeError)):tree.copy()
            self.assertEqual(tuple(tree.rows.items),rows)
            self.assertEqual(tree._all_rows,registry)

    def test_corrupt_graph_is_rejected_not_traversed_forever(self):
        def cycle(t):t.rows.items[0].rows.items.append(t.rows.items[0])
        def duplicate(t):t.rows.items.append(t.rows.items[0])
        def wrong_parent(t):t.rows.items[0].rows.items[0].parent=None
        def deleted(t):t.rows.items[0]._deleted=True
        def missing_registry(t):t._all_rows.clear()
        def duplicate_column(t):t.columns.items.append(t.columns.items[0])
        def missing_cell(t):t.rows.items[0].cells.clear()
        for corrupt in (cycle,duplicate,wrong_parent,deleted,missing_registry,duplicate_column,missing_cell):
            tree=self.fixture();corrupt(tree)
            rows=tuple(tree.rows.items); columns=tuple(tree.columns.items); registry=dict(tree._all_rows)
            with self.subTest(corrupt=corrupt.__name__),self.assertRaises((ValueError,TypeError)):
                tree.copy()
            self.assertEqual(tuple(tree.rows.items),rows)
            self.assertEqual(tuple(tree.columns.items),columns)
            self.assertEqual(tree._all_rows,registry)

    def test_opaque_cell_reference_copy_invokes_no_python_hooks(self):
        class Trap:
            def __eq__(self,*args):raise AssertionError('equality hook')
            def __repr__(self):raise AssertionError('repr hook')
            def __str__(self):raise AssertionError('str hook')
            def __iter__(self):raise AssertionError('iteration hook')
            def __deepcopy__(self,*args):raise AssertionError('deepcopy hook')
            def __reduce_ex__(self,*args):raise AssertionError('pickle hook')
        tree=self.fixture();cell=Trap();column=tree.columns.items[0]
        tree.rows.items[0].cells[column]=cell
        copied=tree.copy()
        self.assertIs(copied.rows.items[0].cells[copied.columns.items[0]],cell)
        self.assertIs(tree.rows.items[0].cells[column],cell)


if __name__=='__main__':unittest.main()
