"""Clear local safety policies; native lifetimes are pinned in separate fixtures."""
from decimal import Decimal as D
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, target_context
from yadinassi.value_trees import BSLValueTree, BSLValueTreeColumnCollection as Columns, BSLValueTreeRowCollection as Rows


class Poison:
    __hash__ = object.__hash__
    def __eq__(self, other): raise AssertionError('equality hook')
    def __bool__(self): raise AssertionError('bool hook')
    def __str__(self): raise AssertionError('str hook')
    def __iter__(self): raise AssertionError('iteration hook')
    def __int__(self): raise AssertionError('int hook')


class ClearPolicyTests(unittest.TestCase):
    def setUp(self):
        scope=target_context(LINUX_8_3_27_1508);scope.__enter__();self.addCleanup(scope.__exit__,None,None,None)

    def fixture(self):
        tree=BSLValueTree();column=tree.columns.add('Key');root=tree.rows.add();child=root.rows.add();deep=child.rows.add();sibling=tree.rows.add()
        return tree,column,(root,child,deep,sibling)

    def test_reset_rows_columns_and_measured_wrapper_operations(self):
        tree,column,rows=self.fixture();held=[r.rows for r in rows]
        tree.columns.clear()
        self.assertEqual(tree.rows.count(),D(0));self.assertEqual(tree.columns.items,[])
        for name,value in [('Name',''),('Имя',''),('Title',''),('Заголовок',''),('Width',D(0)),('Ширина',D(0))]:self.assertEqual(column.get_member(name),value)
        with self.assertRaises(ValueError):column.get_member('ValueType')
        with self.assertRaises(ValueError):column.set_member('Name','Reused')
        for row in rows:
            for action in (row.owner,row.level,lambda:row.get_member('Rows'),lambda:row.get_member('Parent'),lambda:row.set_member('Key',D(4))):
                with self.assertRaises(ValueError):action()
        for collection,parent in zip(held,rows):self.assertIs(collection.get_member('Parent'),parent)
        a=held[2].add();b=held[3].insert(D(0))
        for collection in held:
            self.assertEqual(collection.count(),D(2));self.assertIs(collection.get(D(0)),b)
        for row in (a,b):
            self.assertIs(row.collection,tree.rows);self.assertIs(row.owner(),tree);self.assertIsNone(row.parent);self.assertEqual(row.level(),D(0))
        held[1].clear();self.assertEqual(tree.rows.count(),D(0))

    def test_repeated_generations_and_ordinary_deletion_are_distinct(self):
        tree,column,rows=self.fixture();old=rows[2].rows;tree.columns.clear()
        tree.columns.add('Key');fresh=old.add();fresh_held=fresh.rows;fresh_child=fresh_held.add();fresh_child_held=fresh_child.rows
        tree.columns.clear()
        for held in (old,fresh_held,fresh_child_held):self.assertEqual(held.count(),D(0))
        rebuilt=fresh_child_held.add();self.assertIs(old.get(D(0)),rebuilt)
        ordinary=rebuilt.rows;tree.rows.delete(rebuilt)
        with self.assertRaises(ValueError):ordinary.add()
        self.assertEqual(old.count(),D(0));old.add();tree.rows.clear();self.assertEqual(old.count(),D(0))
        tree,column,rows=self.fixture();held=rows[0].rows;tree.rows.clear()
        for action in (held.count,held.add,held.clear,lambda:held.get_member('Parent')):
            with self.assertRaises(ValueError):action()

    def test_only_measured_detached_collection_methods_are_enabled(self):
        tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear()
        for action in (lambda:list(held),lambda:held.total('Key'),lambda:held.find(D(1)),lambda:held.move(D(0),D(1))):
            with self.assertRaises(ValueError):action()

    def test_no_cell_value_hooks(self):
        tree,column,rows=self.fixture()
        for row in rows:row.cells[column]=Poison()
        tree.columns.clear();self.assertFalse(tree._all_rows)

    def test_preflight_rejects_cycles_aliases_owner_registry_and_cells_without_mutation(self):
        mutations=(lambda t,c,r:r[1].rows.items.append(r[0]),lambda t,c,r:t.rows.items.append(r[0]),
            lambda t,c,r:setattr(r[0],'tree',BSLValueTree()),lambda t,c,r:setattr(r[0],'depth',True),
            lambda t,c,r:setattr(r[0].rows,'parent',r[1]),lambda t,c,r:t._all_rows.pop(r[1]),
            lambda t,c,r:t._all_rows.__setitem__(r[0],D(1)),lambda t,c,r:r[0].cells.clear(),
            lambda t,c,r:r[0].cells.__setitem__(Poison(),D(1)),lambda t,c,r:setattr(t.rows,'items',()),
            lambda t,c,r:setattr(c,'_deleted',Poison()),lambda t,c,r:setattr(t.columns,'items',[c,c]))
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                tree,column,rows=self.fixture();mutate(tree,column,rows)
                with self.assertRaises(ValueError):tree.columns.clear()
                self.assertFalse(rows[0]._deleted);self.assertEqual(column.name,'Key')

    def test_forward_marker_and_root_owner_guards(self):
        for mutate in (lambda t,h:setattr(h,'_columns_clear_forward',Poison()),lambda t,h:setattr(h.parent,'tree',BSLValueTree()),
                       lambda t,h:setattr(t.rows,'parent',h.parent),lambda t,h:setattr(t.rows,'items',()),
                       lambda t,h:setattr(t,'_all_rows',[])):
            tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear();mutate(tree,held)
            with self.assertRaises(ValueError):held.add()

    def test_forward_operations_reject_foreign_schema_and_root_rows(self):
        class Foreign:
            def __getattribute__(self,name):raise AssertionError('foreign attribute hook')
        for action in ('count','get','add','insert','clear'):
            tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear()
            tree.columns.items.append(Foreign())
            call=lambda:getattr(held,action)(D(0)) if action in ('get','insert') else getattr(held,action)()
            with self.subTest(action=action),self.assertRaises(ValueError):call()
        tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear()
        other=BSLValueTree();foreign=other.rows.add();tree.rows.items.append(foreign)
        with self.assertRaises(ValueError):held.get(D(0))
        with self.assertRaises(ValueError):held.add()

    def test_forward_creation_rejects_poisoned_descriptors_qualifiers_and_defaults(self):
        from yadinassi.type_descriptions import BSLTypeDescription
        for mutate in (lambda c:setattr(c,'value_type',Poison()),
                       lambda c:object.__setattr__(c.value_type,'types',Poison()),
                       lambda c:object.__setattr__(c.value_type,'types',(Poison(),)),
                       lambda c:object.__setattr__(c.value_type,'string_qualifiers',Poison()),
                       lambda c:object.__setattr__(c.value_type.string_qualifiers,'length',Poison()),
                       lambda c:object.__setattr__(c.value_type.number_qualifiers,'digits',D('1e1000000')),
                       lambda c:object.__setattr__(c.value_type,'adjust_value',lambda:(_ for _ in ()).throw(AssertionError('method hook'))),
                       lambda c:setattr(c,'default',Poison()),
                       lambda c:setattr(c,'default','x'*1_000_001)):
            for operation in ('add','insert'):
                tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear();column=tree.columns.add('Key');mutate(column)
                with self.subTest(operation=operation,mutate=mutate),self.assertRaises(ValueError):
                    held.add() if operation=='add' else held.insert(D(0))
                self.assertEqual(tree.rows.count(),D(0))
        for name in ('Number','String','Boolean','Date'):
            tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear()
            tree.columns.add('Key',BSLTypeDescription(name));held.add();held.insert(D(0))
            self.assertEqual(tree.rows.count(),D(2))

    def test_forwarding_never_calls_injected_receiver_callbacks(self):
        for receiver,name in (('tree','_clear_graph'),('tree','_budget'),('root','count'),
                              ('root','get'),('root','add'),('root','insert'),('root','clear'),
                              ('root','_live'),('root','_remove_subtrees'),
                              ('held','_clear_target'),('held','_clear_defaults')):
            tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear();calls=[]
            target={'tree':tree,'root':tree.rows,'held':held}[receiver]
            setattr(target,name,lambda *args:calls.append('hook'))
            for action,args in ((Rows.count,()),(Rows.get,(D(0),)),(Rows.add,()),(Rows.insert,(D(0),)),(Rows.clear,())):
                with self.subTest(receiver=receiver,name=name,action=action),self.assertRaises(ValueError):action(held,*args)
            self.assertEqual(calls,[])
        tree,column,rows=self.fixture();tree._clear_graph=lambda:(_ for _ in ()).throw(AssertionError('hook'))
        with self.assertRaises(ValueError):tree.columns.clear()

    def test_forward_clear_prevalidates_corrupt_active_graph(self):
        tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear();root=held.add();root.rows.items.append(root)
        with self.assertRaises(ValueError):held.clear()
        self.assertFalse(root._deleted)

    def test_row_column_cell_and_work_budgets(self):
        for name,limit in (('_MAX_ROWS',3),('_MAX_COLUMNS',0),('_MAX_CELLS',3),('_MAX_SEARCH_WORK',2)):
            tree,column,rows=self.fixture()
            with patch('yadinassi.value_trees.'+name,limit),self.assertRaises(ValueError):tree.columns.clear()
            self.assertFalse(rows[0]._deleted)
        tree,column,rows=self.fixture();held=rows[1].rows;tree.columns.clear()
        with patch('yadinassi.value_trees._MAX_ROWS',0),self.assertRaises(ValueError):held.add()

    def test_depth_boundary_and_iterative_work(self):
        tree=BSLValueTree();tree.columns.add('Key');row=tree.rows.add()
        for _ in range(256):row=row.rows.add()
        held=row.rows;tree.columns.clear();self.assertEqual(held.add().depth,0)
        tree,column,rows=self.fixture()
        with patch('yadinassi.value_trees._MAX_DEPTH',1),self.assertRaises(ValueError):tree.columns.clear()

    def test_linux_target_not_host_os_procedure_arity_and_expression(self):
        tree,column,rows=self.fixture()
        with target_context(WINDOWS_8_3_27_2342),self.assertRaises(ValueError):tree.columns.clear()
        with self.assertRaises(TypeError):tree.columns.clear(D(1))
        for alias in ('Clear','Очистить'):self.assertFalse(tree.columns.get_method(alias).returns_value)
        vm=Interpreter(native_target=LINUX_8_3_27_1508);vm.execute('T=Новый ДеревоЗначений;T.Columns.Add("Key");T.Rows.Add();')
        with self.assertRaises(BSLRuntimeError):vm.execute('Result=T.Columns.Clear();')
        self.assertEqual(len(vm.variables['t'].columns.items),1)
        with patch('os.name','nt'):tree.columns.clear()
        with target_context(WINDOWS_8_3_27_2342),self.assertRaises(ValueError):rows[0].rows.add()


if __name__=='__main__':unittest.main()
