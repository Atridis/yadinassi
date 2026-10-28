"""Current-source observation invariants; synthetic actions are not native semantics."""
from pathlib import Path
import unittest
from unittest import mock
from decimal import Decimal as D
from contextlib import ExitStack
ROOT=Path(__file__).resolve().parents[1]
from yadinassi import Interpreter,BSLError
from yadinassi.values import BSLObject
from yadinassi.value_trees import BSLValueTree,BSLValueTreeRow,BSLValueTreeRowCollection,BSLValueTreeColumnCollection
START='// Begin bounded ValueTree LoadColumn helpers (measurement only; no native answers).\n';END='// End bounded ValueTree LoadColumn helpers.\n\n'
def helper():
 s=(ROOT/'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig');return START+s.split(START,1)[1].split(END,1)[0]+END

def clone(rows, shared=False):
 view=BSLValueTreeRowCollection(rows.tree, rows.parent);view.items=rows.items if shared else list(rows.items);return view

class RowsConsistencyTests(unittest.TestCase):
 def setUp(self):
  self.vm=Interpreter(lambda x:None);self.vm.execute(helper())
 def setup(self,case=1):
  self.vm.execute(f'S=TreeLoadFresh({case}); Source=TreeLoadPair(6,7); Original=Source; Refs=New Array;');return self.vm.variables['s']
 def snapshot(self):return self.vm.execute('TreeLoadSnapshot(S,Source,Original,Refs)')
 def views(self,s):return s.get_member('RowCollections').items+[s.get_member('ForeignRowCollection')]
 def install_saved_clones(self,s):
  a=s.get_member('RowCollections');a.items=[clone(x) for x in a.items];s.set_member('ForeignRowCollection',clone(s.get_member('ForeignRowCollection')))
 def test_calibration_passes_distinct_fresh_wrappers_with_shared_rows(self):
  with ExitStack() as stack:
   for cls in (BSLValueTree,BSLValueTreeRow):
    old=cls.get_member
    def get(obj,name,old=old):
     value=old(obj,name);return clone(value,True) if name.casefold() in ('rows','строки') else value
    stack.enter_context(mock.patch.object(cls,'get_member',get))
   self.assertEqual(self.vm.execute('TreeLoadCalibrate()'),'-')
   for case in range(1,46):
    result=self.vm.execute(f'TreeLoadProbe({case})');self.assertNotIn('?',result);self.assertNotIn('!',result)
 def test_snapshot_accepts_equal_content_copies_without_claiming_identity(self):
  for case in (1,5,6,19,41):
   s=self.setup(case);before=self.snapshot();self.install_saved_clones(s)
   self.assertEqual(self.snapshot(),before)
   with ExitStack() as stack:
    for cls in (BSLValueTree,BSLValueTreeRow):
     old=cls.get_member
     def get(obj,name,old=old):
      value=old(obj,name);return clone(value) if name.casefold() in ('rows','строки') else value
     stack.enter_context(mock.patch.object(cls,'get_member',get))
    self.assertEqual(self.snapshot(),before)
 def test_empty_foreign_tree_root_views_are_observationally_indistinguishable(self):
  # An empty root collection exposes no Owner; current type/count/Parent
  # predicates cannot prove which tree backs it or future mutation aliasing.
  for case in (5,6,19):
   s=self.setup(case);before=self.snapshot();unrelated=BSLValueTree()
   self.assertIsNot(unrelated,s.get_member('Tree'))
   self.assertIsNot(unrelated,s.get_member('Foreign'))
   s.get_member('RowCollections').items[0]=unrelated.rows
   s.set_member('ForeignRowCollection',unrelated.rows)
   self.assertEqual(self.snapshot(),before)
  # Also exercise replacing the fresh empty root views, not only retained ones.
  s=self.setup(5);before=self.snapshot();unrelated=BSLValueTree()
  s.get_member('Tree').rows=unrelated.rows
  s.get_member('Foreign').rows=unrelated.rows
  self.assertEqual(self.snapshot(),before)

 def test_each_of_eight_retained_views_checked_independently(self):
  for index in range(8):
   for mutation in ('membership','parent'):
    with self.subTest(index=index,mutation=mutation):
     s=self.setup();self.install_saved_clones(s);view=self.views(s)[index]
     if mutation=='membership':view.items.append(s.get_member('Nodes').items[0])
     else:view.parent=s.get_member('Nodes').items[1] if view.parent is not s.get_member('Nodes').items[1] else None
     with self.assertRaises(BSLError):self.snapshot()
 def test_each_of_eight_fresh_views_checked_independently(self):
  for index in range(8):
   with self.subTest(index=index):
    s=self.setup();nodes=s.get_member('Nodes').items
    owner=s.get_member('Tree') if index==0 else s.get_member('Foreign') if index==7 else nodes[index-1]
    view=clone(owner.rows);view.items.append(nodes[0]);owner.rows=view
    with self.assertRaises(BSLError):self.snapshot()
 def test_reorder_and_equal_cell_replacement_rows_rejected(self):
  for saved in (True,False):
   for mutation in ('reorder','replacement'):
    s=self.setup();self.install_saved_clones(s);view=s.get_member('RowCollections').items[0] if saved else s.get_member('Tree').rows
    if mutation=='reorder':view.items.reverse()
    else:
     original=view.items[0];other=BSLValueTreeRow(original.collection);other.cells=dict(original.cells);view.items[0]=other
    with self.assertRaises(BSLError):self.snapshot()
 def test_cell_changes_are_observed_and_unknown_values_rejected(self):
  s=self.setup();before=self.snapshot();s.get_member('Nodes').items[0].set_member('Id',D(7));self.assertNotEqual(self.snapshot(),before)
  s.get_member('Nodes').items[0].set_member('Id',D(8))
  with self.assertRaises(BSLError):self.snapshot()
 def test_row_owner_parent_and_columns_guards_unchanged(self):
  for mutate in (
   lambda s:setattr(s.get_member('Nodes').items[3],'parent',s.get_member('Nodes').items[1]),
   lambda s:setattr(s.get_member('Nodes').items[0],'tree',s.get_member('Foreign')),
   lambda s:setattr(s.get_member('Tree').columns.items[0],'title','changed'),
   lambda s:setattr(s.get_member('Tree'),'columns',BSLValueTreeColumnCollection(s.get_member('Tree')))):
   s=self.setup();mutate(s)
   with self.assertRaises(BSLError):self.snapshot()
 def test_snapshot_does_not_mutate_fixture_views_or_cells(self):
  s=self.setup();self.install_saved_clones(s)
  def fingerprint():
   nodes=s.get_member('Nodes').items
   return (tuple((id(v),id(v.parent),tuple(map(id,v.items))) for v in self.views(s)),
    tuple((id(n),id(n.parent),id(n.tree),tuple((id(c),str(v)) for c,v in n.cells.items())) for n in nodes))
  before=fingerprint();self.snapshot();self.snapshot();self.assertEqual(fingerprint(),before)
 def test_wrong_type_duck_view_rejected_without_rejecting_real_clones(self):
  class DuckRows(BSLObject):
   def __init__(self, wrapped):self.wrapped=wrapped
   def get_member(self,name):return self.wrapped.get_member(name)
   def get_method(self,name):return self.wrapped.get_method(name)
  s=self.setup();view=s.get_member('RowCollections').items[0]
  s.get_member('RowCollections').items[0]=DuckRows(view)
  with self.assertRaises(BSLError):self.snapshot()
  # Without the explicit type guard the same duck view would satisfy the
  # count/Parent/Get predicates. The rejection is not a missing-method accident.
  guard='    Если ТипЗнч(Rows) <> Тип("КоллекцияСтрокДереваЗначений") Тогда ВызватьИсключение "tree-load-rows-type"; КонецЕсли;\n'
  original=self.vm;self.vm=Interpreter(lambda x:None);self.vm.execute(helper().replace(guard,''))
  s=self.setup();s.get_member('RowCollections').items[0]=DuckRows(s.get_member('RowCollections').items[0])
  self.assertEqual(len(self.snapshot()),59);self.vm=original
 def test_old_identity_only_failures_not_deleted_wholesale(self):
  text=helper()
  for exact in (
   'Если T.Columns <> Cols Тогда ВызватьИсключение "tree-load-columns-alias"; КонецЕсли;',
   'Если Cols = Other.Columns Тогда ВызватьИсключение "tree-load-columns-distinct"; КонецЕсли;',
   'Если R <> T.Rows.Get(0) Тогда ВызватьИсключение "tree-load-row-alias"; КонецЕсли;',
   'Если R = OtherRow Тогда ВызватьИсключение "tree-load-row-distinct"; КонецЕсли;',
   'Если R.Owner() <> S.Tree Или R.Parent <> Parent Тогда ВызватьИсключение "tree-load-row-links"; КонецЕсли;'):
   self.assertIn(exact,text)


# Reuse synthetic-action assertions against CURRENT fragments, not their
# historical source() peel. Do not inherit historical identity-only assertions.
import importlib.util
_spec = importlib.util.spec_from_file_location(
    '_historical_load_assertions', ROOT / 'tests/test_native_tree_load_measurement.py')
_historical = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_historical)


def current_fragments():
    text = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
    start = _historical.CALL_START
    end = _historical.CALL_END
    return helper(), start + text.split(start, 1)[1].split(end, 1)[0] + end


class CurrentActionObserverTests(unittest.TestCase):
    def setUp(self):
        self.fragments_patch = mock.patch.object(_historical, 'fragments', current_fragments)
        self.fragments_patch.start()
        self.addCleanup(self.fragments_patch.stop)
        _historical.LoadObserverTests.setUp(self)

    probe = _historical.LoadObserverTests.probe
    witness = _historical.LoadObserverTests.witness

    def test_current_all45_route_and_strict_decoder(self):
        from scripts import native_1c_tree_load_contract as contract
        calls = current_fragments()[1]
        self.assertNotIn('Diagnostic', calls)
        self.assertEqual(calls.count('TreeLoadProbe('), 45)
        self.vm.execute(calls)
        records = [None] * 976
        for case, message in enumerate(self.output, 1):
            label = f'TL{case:02d}'
            framed = (message + '\n').encode('ascii')
            records.append((label, framed, framed[len(label) + 3:-2]))
        self.assertEqual(contract.validate_records(records),
                         {'records': 45, 'message_units': 3525})


# Exact named coverage: all call signatures; statement vs expression; partial
# action failures; both alias mutation directions; source membership mutation;
# mutation failure vs skipped mutation. No native behavior is assumed.
for _name in (
    'test_all45_argument_routes_and_no_implicit_expression_calls',
    'test_statement_procedure_succeeds_but_expression_rejects_before_call',
    'test_action_exception_preserves_partial_tree_and_source_mutations',
    'test_two_way_aliases_and_independent_equal_structures_are_distinguished',
    'test_source_membership_changes_do_not_replace_snapshot_with_a_summary',
    'test_mutation_error_and_skipped_mutation_remain_distinct',
):
    setattr(CurrentActionObserverTests, _name, getattr(_historical.LoadObserverTests, _name))

if __name__ == "__main__":
    unittest.main()
