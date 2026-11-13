"""Exact16 direct reports: measured subset, not full native observer parity."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_inventory_enums import PROFILE
from yadinassi.configuration_profile_import import create_prepared, prepare_directory
from yadinassi.enum_storage_binding import EnumStorageBinding
from yadinassi.query_enum_reporting import _EnumReportScope, _EnumDescriptor
from yadinassi.values import BSLArray, NULL

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/inventory_enum_relational_behavior'
CAPTURE = ROOT / 'tests/fixtures/native_inventory_enum_relational'


def array(*values):
    result = BSLArray()
    result.items.extend(values)
    return result


class EnumRelationalEvidenceTests(unittest.TestCase):
    def test_fresh_example_combines_posted_and_pending_receipts(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            with closing(create_prepared(Path(temp) / 'stock.sqlite',
                    prepare_directory(SOURCE / 'runtime_source', profile=PROFILE))) as context:
                output=[]
                with closing(Interpreter(database_context=context,output=output.append)) as vm:
                    vm.execute((ROOT/'examples/inventory_enum/seed.bsl').read_text(encoding='utf-8'))
                    vm.execute((ROOT/'examples/inventory_enum/relational_report.bsl').read_text(encoding='utf-8'))
                    self.assertEqual(output,['ER-P','Piece','10'])
                    self.assertIsNone(context.backend._active)

    def test_capture_and_supported_control_manifest_are_not_full_parity(self):
        raw = (CAPTURE / 'inventory-enum-relational.out').read_bytes()
        coverage = json.loads((CAPTURE / 'supported-controls.json').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), coverage['raw_output_sha256'])
        self.assertEqual(coverage['source_commit'], '0b481c58488b84f326fa81f5036b4d3eb5dc137b')
        self.assertFalse(coverage['full_observer_parity'])
        values = json.loads(raw)
        controls = [(g, n, value) for g, row in enumerate(values, 1)
                    for n, value in enumerate(row.split('|'), 1)]
        self.assertEqual(len(controls), 79)
        self.assertEqual(controls, [(c['group'], c['control'], c['native_fragment']) for c in coverage['controls']])
        closed = {(c['group'], c['control']) for c in coverage['controls']
                  if c['classification'] == 'intentional-host-refusal'}
        self.assertEqual(closed, {(6,1),(6,2),(6,3),(6,5),(9,5),(9,6)})
        p = json.loads((CAPTURE / 'provenance.json').read_bytes())
        self.assertTrue(p['native_measurement_accepted']); self.assertFalse(p['runtime_parity_accepted'])
        self.assertEqual(p['interpreter']['source_file_count'], 251)  # Historical acquisition, not current source inventory.
        for key in ('container_cleanup_verified','docker_cli_reap_verified','private_payloads_removed'):
            self.assertIs(p[key], True)
        for path, digest in p['trusted_input_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)
        self.assertIn('tests/fixtures/native_inventory_enum_relational/* -text',
                      (ROOT / '.gitattributes').read_text(encoding='utf-8'))

    def test_public_bsl_replays_supported_controls_and_keeps_closed_divergences(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            with closing(create_prepared(Path(temp) / 'stock.sqlite',
                    prepare_directory(SOURCE / 'runtime_source', profile=PROFILE))) as context:
                with closing(Interpreter(database_context=context, output=lambda text: None)) as vm:
                    observed, diagnostics = [], []
                    vm.register_function('ПодробноеПредставлениеОшибки', lambda info: info.get_member('Description'))
                    vm.register_function('AccumulationEmit', lambda n,v: observed.append((int(n),v)), returns_value=False)
                    vm.register_function('AccumulationDiagnostic', lambda n,s,e: diagnostics.append((int(n),s,e)), returns_value=False)
                    vm.execute((SOURCE / 'observe.bsl').read_text(encoding='utf-8'), 'native-enum-relational-supported-subset')
                    self.assertIsNone(context.backend._active)
        self.assertEqual(diagnostics, [])
        self.assertEqual([n for n,_ in observed], list(range(1,13)))
        by_group = {n: value.split('|') for n,value in observed}
        coverage = json.loads((CAPTURE / 'supported-controls.json').read_bytes())
        self.assertEqual(sum(map(len, by_group.values())), 79)
        for control in coverage['controls']:
            with self.subTest(group=control['group'], control=control['control']):
                actual = by_group[control['group']][control['control']-1]
                if control['classification'] == 'intentional-host-refusal':
                    self.assertEqual(actual, 'execute-refused')
                else:
                    self.assertEqual(actual, control['native_fragment'])


class EnumRelationalGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.context = create_prepared(self.directory / 'stock.sqlite',
            prepare_directory(SOURCE / 'runtime_source', profile=PROFILE))
        self.addCleanup(self.context.close)
        self.vm = Interpreter(database_context=self.context)
        self.addCleanup(self.vm.close)
        self.vm.execute('P=Catalogs.Products.CreateItem();P.Code="P";P.Unit=Enums.Units.Piece;P.Write();'
                        'K=Catalogs.Products.CreateItem();K.Code="K";K.Unit=Enums.Units.Pack;K.Write();'
                        'E=Catalogs.Products.CreateItem();E.Code="E";E.Write();')
        self.piece = self.vm.execute('Enums.Units.Piece')
        self.pack = self.vm.execute('Enums.Units.Pack')
        self.empty = self.vm.execute('Enums.Units.EmptyRef()')
        self.catalogs = self.vm.execute('Catalogs')

    def query(self, text, **parameters):
        q = self.vm.execute('New Query')
        q.set_member('Text', text)
        for name, value in parameters.items():
            q.set_parameter(name, value)
        return q.execute()

    def test_array_null_is_not_nonnull_not_in_poison(self):
        text = 'SELECT Code FROM Catalog.Products WHERE Unit NOT IN (&V) ORDER BY Code'
        self.assertEqual(self.query(text,V=array(NULL))._rows, (('E',),('K',),('P',)))
        self.assertEqual(self.query(text,V=array(NULL,self.piece))._rows, (('E',),('K',)))
        self.assertEqual(self.query(text,V=array(self.empty,NULL))._rows, (('K',),('P',)))

    def test_nullable_operand_distinguishes_original_empty_from_null_only_array(self):
        base = ('SELECT A.Code FROM Catalog.Products AS A LEFT JOIN Catalog.Products AS B '
                'ON A.Ref=B.Ref AND B.Code="absent" WHERE B.Unit ')
        for values, expected_not in ((array(),3),(array(NULL),0),(array(self.piece),0),(array(NULL,self.piece),0)):
            self.assertEqual(self.query(base+'IN (&V)',V=values)._rows, ())
            self.assertEqual(len(self.query(base+'NOT IN (&V)',V=values)._rows), expected_not)

    def test_subquery_null_only_does_not_poison_nonnull_not_in(self):
        sub = ('SELECT B.Unit FROM Catalog.Products AS A LEFT JOIN Catalog.Products AS B '
               'ON A.Ref=B.Ref AND B.Code="absent"')
        self.assertEqual(len(self.query('SELECT Unit FROM Catalog.Products WHERE Unit NOT IN ('+sub+')')._rows),3)
        self.assertEqual(self.query('SELECT Unit FROM Catalog.Products WHERE Unit IN ('+sub+')')._rows,())

    def test_scalar_singleton_and_other_owned_enum_controls(self):
        text = 'SELECT Code FROM Catalog.Products WHERE Unit IN (&One)'
        self.assertEqual(self.query(text,One=self.piece)._rows,(('P',),))
        self.assertEqual(self.query(text,One=self.vm.execute('Enums.States.Draft'))._rows,())
        sub = 'SELECT &State AS Unit FROM Catalog.Products'
        self.assertEqual(self.query('SELECT Unit FROM Catalog.Products WHERE Unit IN ('+sub+')',
                                   State=self.vm.execute('Enums.States.Draft'))._rows,())

    def test_bare_array_and_unmeasured_kinds_remain_refused(self):
        with self.assertRaises(ValueError):
            self.query('SELECT Unit FROM Catalog.Products WHERE Unit IN &V',V=array(self.piece))
        for value in (True,self.vm.execute('Date(2024,1,1)'),self.vm.execute('P.Ref')):
            with self.subTest(kind=type(value)), self.assertRaises(TypeError):
                self.query('SELECT Unit FROM Catalog.Products WHERE Unit IN (&V)',V=array(value))
        for value in ('owned',Decimal(1)):
            with self.assertRaises(TypeError):
                self.query('SELECT Unit FROM Catalog.Products WHERE Unit IN (&V)',V=value)

    def test_null_parameter_is_absence_not_empty_reference(self):
        rows = self.query('SELECT ISNULL(&N,Unit) AS U FROM Catalog.Products ORDER BY Code',N=NULL)._rows
        self.assertIs(rows[0][0],self.empty)
        self.assertIs(rows[1][0],self.pack)
        self.assertIs(rows[2][0],self.piece)

    def test_mixed_output_schemas_refused_before_scan_even_for_empty_arms(self):
        for text in (
            'SELECT CASE WHEN Code="absent" THEN Unit ELSE &State END AS Unit FROM Catalog.Products WHERE Code="absent"',
            'SELECT ISNULL(Unit,&State) AS Unit FROM Catalog.Products WHERE Code="absent"',
            'SELECT Unit FROM Catalog.Products WHERE Code="absent" UNION ALL SELECT &State AS Unit FROM Catalog.Products WHERE Code="absent"'):
            q = self.vm.execute('New Query'); q.set_member('Text',text)
            q.set_parameter('State',self.vm.execute('Enums.States.Draft'))
            from yadinassi.sqlite_catalog import _View
            from yadinassi.query_packages import BSLTempTablesManager
            manager = BSLTempTablesManager()
            q.set_member('TempTablesManager', manager)
            with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('source scan')):
                with self.assertRaises(TypeError):q.execute()
            self.assertEqual(manager._tables, {})
            self.assertIsNone(self.context.backend._active)

    def test_internal_union_derived_and_subquery_share_one_query_view(self):
        text = ('SELECT T.Unit FROM (SELECT Unit FROM Catalog.Products UNION ALL '
                'SELECT Unit FROM Catalog.Products) AS T WHERE T.Unit IN '
                '(SELECT Unit FROM Catalog.Products)')
        original=self.context.backend.begin_query_read
        with patch.object(self.context.backend,'begin_query_read',wraps=original) as opened:
            self.assertEqual(len(self.query(text)._rows),6)
            self.assertEqual(opened.call_count,1)
        self.assertIsNone(self.context.backend._active)

    def test_array_snapshot_once_even_if_mutated_when_read_opens(self):
        values=array(self.piece); original=self.context.backend.begin_query_read
        def open_view():
            values.items[:]=[self.pack]
            return original()
        with patch.object(self.context.backend,'begin_query_read',side_effect=open_view):
            rows=self.query('SELECT Code FROM Catalog.Products WHERE Unit IN (&V)',V=values)._rows
        self.assertEqual(rows,(('P',),))
        self.assertEqual(self.query('SELECT Code FROM Catalog.Products WHERE Unit IN (&V)',V=values)._rows,(('K',),))

    def test_all_nested_foreign_or_forged_enum_members_refused_before_lease(self):
        with closing(Interpreter(database_context=self.context)) as other:
            values=(replace(self.piece),other.execute('Enums.Units.Piece'))
            for value in values:
                with patch.object(self.context.backend,'begin_query_read') as opened:
                    with self.assertRaises(BackendError):
                        self.query('SELECT Unit FROM Catalog.Products WHERE Code="absent"',Unused=array(value))
                    opened.assert_not_called()

    def test_oversized_unused_array_refused_before_member_ownership_loop(self):
        scope=_EnumReportScope(self.catalogs)
        with patch.object(EnumStorageBinding,'owned_key',side_effect=AssertionError('ownership loop')):
            with self.assertRaisesRegex(ValueError,'member limit'):
                scope.snapshot_parameters({'unused':array(*([self.piece]*257))})

    def test_catalog_parameter_callbacks_and_nested_foreign_ownership_checked(self):
        owned=self.vm.execute('P.Ref');touched=[]
        class Hostile:
            def __call__(self,*args):touched.append('call')
            def __eq__(self,other):touched.append('eq');return True
        with closing(Interpreter(database_context=self.context)) as other:
            foreign=other.execute('Catalogs.Products.EmptyRef()')
            for value in (foreign,replace(owned,read_member=Hostile()),replace(owned,get_object=Hostile())):
                with patch.object(self.context.backend,'begin_query_read') as opened:
                    with self.assertRaises(BackendError):
                        self.query('SELECT Unit FROM Catalog.Products',Unused=array(value))
                    opened.assert_not_called()
        self.assertEqual(touched,[])

    def test_namespace_interposition_is_detected_even_for_empty_result(self):
        scope=_EnumReportScope(self.catalogs)
        manager=scope.binding._namespace._managers['units'];old=manager._values
        original=self.context.backend.begin_query_read
        def open_view():
            view=original();manager._values=tuple(list(old));return view
        try:
            with patch.object(self.context.backend,'begin_query_read',side_effect=open_view):
                with self.assertRaises(BackendError):
                    self.query('SELECT Unit FROM Catalog.Products WHERE Code="absent"')
            self.assertIsNone(self.context.backend._active)
        finally:manager._values=old

    def test_descriptor_clones_foreign_scopes_and_hooks_are_not_authority(self):
        scope=_EnumReportScope(self.catalogs);desc=scope.value_descriptor(self.piece)
        foreign=_EnumReportScope(self.catalogs).value_descriptor(self.piece)
        touched=[]
        class Hostile:
            def __getattribute__(self,name):touched.append(name);raise AssertionError(name)
            def __eq__(self,other):touched.append('eq');raise AssertionError('eq')
        for value in (replace(desc),foreign,Hostile()):
            with self.assertRaises(BackendError):scope.require_descriptor(value)
        self.assertEqual(touched,[])
        self.assertIs(scope.require_descriptor(desc),desc)

    def test_open_failure_retires_scope_without_publishing_or_reusing_it(self):
        scope=_EnumReportScope(self.catalogs)
        with patch.object(self.context.backend,'begin_query_read',side_effect=BackendError('integrity')):
            with self.assertRaises(BackendError):scope.execute(object())
        with self.assertRaises(BackendError):scope.value_descriptor(self.piece)

    def test_close_failure_never_returns_result_and_retires_lexical_scope(self):
        from yadinassi import query_parser
        from yadinassi.relational_queries import _Plan
        from yadinassi.sqlite_documents import DocumentView
        from yadinassi.inventory_enum_runtime import _POINT_READ
        scope=_EnumReportScope(self.catalogs)
        plan=_Plan(query_parser.parse_package('SELECT Unit FROM Catalog.Products')[0],
                   self.catalogs,{},enum_scope=scope)
        original=self.context.backend.begin_query_read;opened=[]
        def open_view():
            view=original();opened.append(view);return view
        try:
            with patch.object(self.context.backend,'begin_query_read',side_effect=open_view), \
                 patch.object(DocumentView,'close',side_effect=BackendError('integrity')):
                with self.assertRaises(BackendError):scope.execute(plan)
            self.assertTrue(scope._retired)
            self.assertIsNone(_POINT_READ.get())
            self.assertIsNotNone(self.context.backend._active)
            with self.assertRaises(BackendError):scope.require_current()
        finally:
            for view in opened:view.close()

    def test_reused_membership_charges_before_dedup(self):
        text='SELECT Unit FROM Catalog.Products WHERE Unit IN (&V) OR Unit IN (&V)'
        with patch('yadinassi.queries._MAX_CELLS',3):
            with self.assertRaisesRegex(ValueError,'membership resource'):
                self.query(text,V=array(self.piece,self.piece))

    def test_compound_enum_ordering_and_unbound_inputs_remain_closed(self):
        for text in ('SELECT Unit FROM Catalog.Products UNION SELECT Unit FROM Catalog.Products ORDER BY Unit',
                     'SELECT Unit FROM Catalog.Products WHERE NOT (Unit=&U)',
                     'SELECT Unit FROM &External'):
            with self.subTest(text=text),self.assertRaises((ValueError,TypeError)):
                self.query(text,U=self.piece)

    def test_previous_reference_profile_does_not_gain_null_parameters(self):
        from yadinassi.configuration_accumulation_references import PROFILE as LEGACY
        source=ROOT/'scripts/inventory_reference_behavior/runtime_source'
        with closing(create_prepared(self.directory/'legacy.sqlite',prepare_directory(source,profile=LEGACY))) as context:
            with closing(Interpreter(database_context=context)) as vm:
                with self.assertRaises(TypeError):vm.execute('New Query').set_parameter('N',NULL)
                q=vm.execute('New Query');q.set_member('Text','SELECT Code FROM Catalog.Products WHERE NOT Code="absent"')
                self.assertEqual(q.execute()._rows,())
