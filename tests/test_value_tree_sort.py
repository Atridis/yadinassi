"""Local bounded Sort safety policies; native answers have a separate fixture."""
from decimal import Decimal as D, Inexact, Rounded, localcontext
import unittest
from unittest import mock
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, target_context
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRow
from yadinassi.values import NULL


class Poison:
    def __str__(self): raise AssertionError('conversion hook')
    def __repr__(self): raise AssertionError('representation hook')
    def __bool__(self): raise AssertionError('boolean hook')
    def __int__(self): raise AssertionError('integer hook')
    def __eq__(self,other): raise AssertionError('equality hook')
    def __lt__(self,other): raise AssertionError('ordering hook')


class SortLocalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.scope=target_context(LINUX_8_3_27_1508);self.scope.__enter__()
        self.addCleanup(self.scope.__exit__,None,None,None)

    def fixture(self,values=(3,1,2)):
        tree=BSLValueTree();tree.columns.add('Key');tree.columns.add('Second')
        for index,value in enumerate(values):
            row=tree.rows.add();row.cells[tree.columns.items[0]]=D(value)
            row.cells[tree.columns.items[1]]=D(index)
        return tree

    def order(self,rows):
        return [row.get_index('Key') for row in rows.items]

    def state(self,tree):
        # Identity-only snapshots remain safe with adversarial cell objects.
        return (tuple(id(c) for c in tree.columns.items),tuple(id(r) for r in tree._all_rows),
                tuple((id(r),id(r.collection),id(r.parent),r.depth,id(r._deleted),
                       tuple(id(c) for c in r.rows.items),
                       tuple((id(k),id(v)) for k,v in r.cells.items())) for r in tree._all_rows if type(r) is BSLValueTreeRow),
                tuple(id(r) for r in tree.rows.items))

    def fail_unchanged(self,tree,*args):
        before=self.state(tree)
        with self.assertRaises((TypeError,ValueError)):
            tree.rows.sort(*args)
        self.assertEqual(self.state(tree),before)

    def test_default_false_and_child_receiver_recursion_preserve_siblings(self):
        tree=self.fixture();first,second,third=tree.rows.items
        for parent in (first,second):
            for value in (3,1,2):
                row=parent.rows.add();row.set_index('Key',D(value));row.set_index('Second',D(0))
        tree.rows.sort('Key')
        self.assertEqual(self.order(tree.rows),[D(1),D(2),D(3)])
        self.assertEqual(self.order(first.rows),[D(3),D(1),D(2)])
        sibling_order=tuple(second.rows.items)
        first.rows.sort('Key',True)
        self.assertEqual(self.order(first.rows),[D(1),D(2),D(3)])
        self.assertEqual(tuple(second.rows.items),sibling_order)
        self.assertIs(first.parent,None)
        for child in first.rows.items:
            self.assertIs(child.parent,first);self.assertIs(child.collection,first.rows)
            self.assertIs(child.owner(),tree);self.assertEqual(child.depth,1)

    def test_recursive_sorts_descendants_without_replacing_any_schema_or_rows(self):
        tree=self.fixture();parents=tuple(tree.rows.items)
        for parent in parents:
            for value in (2,1):
                child=parent.rows.add();child.set_index('Key',D(value));child.set_index('Second',D(0))
                for subvalue in (2,1):
                    grandchild=child.rows.add();grandchild.set_index('Key',D(subvalue));grandchild.set_index('Second',D(0))
        columns=tuple(tree.columns.items);registry=tuple(tree._all_rows)
        cells={id(r):tuple((id(k),id(v)) for k,v in r.cells.items()) for r in registry}
        tree.rows.sort('Key DESC',True)
        self.assertEqual(tuple(tree.columns.items),columns)
        self.assertEqual(tuple(tree._all_rows),registry)
        for row in registry:
            self.assertEqual(tuple((id(k),id(v)) for k,v in row.cells.items()),cells[id(row)])
            self.assertEqual(self.order(row.rows),sorted(self.order(row.rows),reverse=True))
            self.assertIs(row.owner(),tree)

    def test_supported_direction_aliases_casefold_and_multikey(self):
        for direction,expected in (('asc',[1,2,3]),('возр',[1,2,3]),('DeSc',[3,2,1]),('УБЫВ',[3,2,1])):
            tree=self.fixture();tree.rows.sort(' key '+direction+' ')
            self.assertEqual(self.order(tree.rows),list(map(D,expected)))
        tree=self.fixture((2,1,2,1));tree.rows.sort('Key Asc, Second Desc')
        self.assertEqual([(r.get_index('Key'),r.get_index('Second')) for r in tree.rows.items],
                         [(D(1),D(3)),(D(1),D(1)),(D(2),D(2)),(D(2),D(0))])

    def test_invalid_selectors_in_both_positions_fail_before_mutation(self):
        for selector in ('','Missing','Missing,Key','Key,Missing','Key Sideways',
                         'Key Asc Extra','Key ASCENDING','Key DESCENDING'):
            self.fail_unchanged(self.fixture(),selector,True)
        for selector in (None,NULL,True,D(1),Poison()):
            self.fail_unchanged(self.fixture(),selector)

    def test_unsupported_recursion_and_comparator_never_coerce_host_values(self):
        for recursive in (None,NULL,D(0),D(1),'true',Poison()):
            self.fail_unchanged(self.fixture(),'Key',recursive)
        for comparator in (True,D(1),'',Poison()):
            self.fail_unchanged(self.fixture(),'Key',False,comparator)
        tree=self.fixture();tree.rows.sort('Key',False,None)
        self.assertEqual(self.order(tree.rows),[D(1),D(2),D(3)])

    def test_unmeasured_scalar_domains_and_nonfinite_numbers_fail_closed(self):
        for value in ('a',True,None,NULL,Poison(),D('NaN'),D('sNaN'),D('Infinity'),D('-Infinity')):
            tree=self.fixture();tree.rows.items[1].cells[tree.columns.items[0]]=value
            self.fail_unchanged(tree,'Key')

    def test_target_scope_rejects_unmeasured_windows_and_restores_linux(self):
        tree=self.fixture()
        with target_context(WINDOWS_8_3_27_2342): self.fail_unchanged(tree,'Key')
        tree.rows.sort('Key');self.assertEqual(self.order(tree.rows),[D(1),D(2),D(3)])

    def test_aliases_are_procedures_and_invalid_arity_has_no_side_effect(self):
        for alias in ('Sort','Сортировать'):
            tree=self.fixture();method=tree.rows.get_method(alias)
            self.assertFalse(method.returns_value)
            before=self.state(tree)
            for args in ((),('Key',False,None,None)):
                with self.assertRaises((TypeError,ValueError)): method(*args)
                self.assertEqual(self.state(tree),before)
            self.assertIsNone(method('Key'))
            self.assertEqual(self.order(tree.rows),[D(1),D(2),D(3)])
        vm=Interpreter(native_target=LINUX_8_3_27_1508)
        vm.execute('T=New ValueTree; T.Columns.Add("Key"); R=T.Rows.Add(); R.Key=2; R=T.Rows.Add(); R.Key=1;')
        before=self.state(vm.variables['t'])
        with self.assertRaises(Exception): vm.execute('Result=T.Rows.Sort("Key");')
        self.assertEqual(self.state(vm.variables['t']),before)


    def test_local_resource_limits_reject_before_any_row_reordering(self):
        from yadinassi import value_tree_sort as sort
        cases=(('_MAX_SORT_ROWS',2,'Key'),('_MAX_SORT_COLUMNS',1,'Key'),
               ('_MAX_SORT_CELLS',2,'Key'),('_MAX_SORT_TEXT',2,'Key'),
               ('_MAX_SORT_TOKENS',1,'Key,Second'),('_MAX_SORT_WORK',1,'Key'))
        for name,limit,selector in cases:
            with self.subTest(limit=name),mock.patch.object(sort,name,limit):
                self.fail_unchanged(self.fixture(),selector,True)
        tree=self.fixture();parent=tree.rows.items[0]
        for _ in range(3):
            parent=parent.rows.add();parent.set_index('Key',D(1));parent.set_index('Second',D(0))
        with mock.patch('yadinassi.value_trees._MAX_DEPTH',2):
            self.fail_unchanged(tree,'Key',True)

    def test_finite_decimal_coefficients_and_exponents_have_explicit_local_bounds(self):
        from yadinassi import value_tree_sort as sort
        for value,constant in ((D('123456789'),'_MAX_SORT_NUMBER_DIGITS'),
                               (D('1e9'),'_MAX_SORT_NUMBER_EXPONENT'),
                               (D('1e-9'),'_MAX_SORT_NUMBER_EXPONENT')):
            tree=self.fixture();tree.rows.items[1].cells[tree.columns.items[0]]=value
            with mock.patch.object(sort,constant,8):self.fail_unchanged(tree,'Key')
        tree=self.fixture();tree.rows.items[0].cells[tree.columns.items[0]]=D('12345678')
        with mock.patch.object(sort,'_MAX_SORT_NUMBER_DIGITS',8),localcontext() as context:
            context.prec=2;context.traps[Inexact]=True;context.traps[Rounded]=True
            tree.rows.sort('Key')
        self.assertEqual(self.order(tree.rows),[D(1),D(2),D('12345678')])

    def test_late_invalid_child_key_cannot_partially_sort_earlier_collections(self):
        tree=self.fixture();parents=tuple(tree.rows.items)
        for parent in parents:
            for value in (3,1,2):
                child=parent.rows.add();child.set_index('Key',D(value));child.set_index('Second',D(0))
        parents[-1].rows.items[-1].cells[tree.columns.items[0]]=Poison()
        self.fail_unchanged(tree,'Key',True)

    def test_foreign_cell_keys_cannot_invoke_equality_and_corrupt_graph_is_rejected(self):
        tree=self.fixture();column=tree.columns.items[0]
        class Foreign:
            def __hash__(self):return hash(column)
            def __eq__(self,other):raise AssertionError('foreign equality hook')
        tree.rows.items[0].cells={Foreign():D(1)}
        self.fail_unchanged(tree,'Key')
        changes=(lambda t:setattr(t.rows.items[0],'depth',False),
                 lambda t:setattr(t.rows.items[0],'tree',BSLValueTree()),
                 lambda t:setattr(t.rows.items[0],'collection',t.rows.items[1].rows),
                 lambda t:setattr(t.rows.items[0].rows,'parent',None),
                 lambda t:t._all_rows.pop(t.rows.items[0]))
        for change in changes:
            tree=self.fixture();change(tree);self.fail_unchanged(tree,'Key',True)


    def test_corrupt_registry_and_deleted_flags_do_not_run_host_hooks(self):
        tree=self.fixture();row=tree.rows.items[0]
        class Foreign:
            def __hash__(self):return hash(row)
            def __eq__(self,other):raise AssertionError('registry equality hook')
        tree._all_rows={Foreign():None}
        self.fail_unchanged(tree,'Key')
        for change in (lambda t:setattr(t.rows.items[0],'_deleted',Poison()),
                       lambda t:setattr(t.columns.items[0],'_deleted',Poison())):
            tree=self.fixture();change(tree)
            # The snapshot records the flag object's identity, never its truth.
            before=tuple(id(r) for r in tree.rows.items)
            with self.assertRaises((TypeError,ValueError)):tree.rows.sort('Key')
            self.assertEqual(tuple(id(r) for r in tree.rows.items),before)


    def test_failure_after_private_permutations_never_commits_partial_tree(self):
        from yadinassi import value_tree_sort as sort
        tree=self.fixture();parent=tree.rows.items[0]
        for value in (3,1,2):
            child=parent.rows.add();child.set_index('Key',D(value));child.set_index('Second',D(0))
        calls=[];original=sort.introsort
        def interrupted(rows,less):
            original(rows,less);calls.append(1)
            if len(calls)==2:raise ValueError('synthetic bounded-work interruption')
        with mock.patch.object(sort,'introsort',side_effect=interrupted):
            self.fail_unchanged(tree,'Key',True)
        self.assertEqual(len(calls),2)


    def test_scalar_subclasses_and_metaclass_equality_are_not_admitted(self):
        class HostMeta(type):
            def __eq__(self,other):raise AssertionError('metaclass equality hook')
            __hash__=type.__hash__
        class Host(metaclass=HostMeta):pass
        class Number(D):
            def is_finite(self):raise AssertionError('numeric subclass hook')
        class Text(str):
            def split(self,*args):raise AssertionError('selector subclass hook')
        for value in (Host(),Number(1)):
            tree=self.fixture();tree.rows.items[0].cells[tree.columns.items[0]]=value
            self.fail_unchanged(tree,'Key')
        self.fail_unchanged(self.fixture(),Text('Key'))


    def test_larger_deterministic_numeric_inputs_obey_local_order_and_identity_properties(self):
        # Algorithm properties only, not additional native tie-order evidence.
        for size in (0,1,16,17,64,257):
            patterns=(list(range(size)),list(reversed(range(size))),
                      [index%5 for index in range(size)],
                      [min(index,size-index) for index in range(size)])
            for values in patterns:
                for selector in ('Key','Key Desc','Key Asc, Second Desc'):
                    with self.subTest(size=size,selector=selector,pattern=values[:8]):
                        tree=self.fixture(values)
                        columns=tuple(tree.columns.items);rows=tuple(tree.rows.items)
                        metadata={id(row):(row.parent,row.collection,row.depth,
                                           tuple((id(k),id(v)) for k,v in row.cells.items())) for row in rows}
                        tree.rows.sort(selector)
                        self.assertEqual({id(row) for row in tree.rows.items},{id(row) for row in rows})
                        self.assertEqual(tuple(tree.columns.items),columns)
                        self.assertEqual(tuple(tree._all_rows),rows)
                        observed=[(row.get_index('Key'),row.get_index('Second')) for row in tree.rows.items]
                        if selector=='Key Asc, Second Desc':
                            self.assertEqual([(a,-b) for a,b in observed],sorted((D(value),-D(index)) for index,value in enumerate(values)))
                        else:
                            self.assertEqual([a for a,b in observed],sorted(map(D,values),reverse=selector=='Key Desc'))
                        for row in rows:
                            self.assertEqual((row.parent,row.collection,row.depth,
                                              tuple((id(k),id(v)) for k,v in row.cells.items())),metadata[id(row)])


if __name__=='__main__':unittest.main()
