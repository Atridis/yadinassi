"""Measured typed virtual predicates; old profiles retain their previous grants."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi import query_parser as syntax
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_inventory_enums import PROFILE
from yadinassi.configuration_profile_import import prepare_directory, create_prepared
from yadinassi.values import BSLArray, BSLFixedArray, NULL

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'scripts/inventory_typed_filter_behavior'
CAPTURE=ROOT/'tests/fixtures/native_inventory_typed_filter'
REG='AccumulationRegister.Stock.'


def array(*values):
    result=BSLArray();result.items.extend(values);return result


class TypedVirtualNativeReplayTests(unittest.TestCase):
    def test_capture_source_cleanup_and_exact_bytes(self):
        for name,digest in (
                ('observations12.out','12beeb7fac4ddf8dc33f0364ebcba159ff88869d13e852b18bea4ede24d2b6a9'),
                ('provenance.json','2d440a789efecc7f01048592adcfac4b971728350c7cad2ba58049b0e3cde5b3')):
            self.assertEqual(hashlib.sha256((CAPTURE/name).read_bytes()).hexdigest(),digest)
        p=json.loads((CAPTURE/'provenance.json').read_bytes());stage=p['native_report']['stage3']
        self.assertEqual(p['repository'],dict(commit='31505d622377c899b6dbbb46520383df66a5f6db',
            tree='e18012018b88db01deb282dcde58f1c9f591af75',github_run_id='43105381775',github_run_attempt='1'))
        self.assertEqual(p['interpreter']['source_file_count'],251) # Historical acquisition inventory.
        self.assertTrue(p['native_measurement_accepted']);self.assertFalse(p['runtime_parity_accepted'])
        for key in ('container_cleanup_verified','private_payloads_removed','docker_cli_reap_verified'):
            self.assertIs(p[key],True)
        for key in ('completed','config_verified','process_exited','witness_verified','quiet'):
            self.assertIs(stage[key],True)
        self.assertEqual(stage['record_count'],12);self.assertEqual(stage['case_diagnostics'],[])
        for path,digest in p['trusted_input_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
        self.assertIn('tests/fixtures/native_inventory_typed_filter/* -text',
            (ROOT/'.gitattributes').read_text(encoding='utf-8'))

    def test_all_twelve_native_groups_replay_through_public_bsl(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            with closing(create_prepared(Path(temp)/'stock.sqlite',prepare_directory(SOURCE/'runtime_source',profile=PROFILE))) as context:
                with closing(Interpreter(database_context=context,output=lambda text:None)) as vm:
                    observed=[];diagnostics=[]
                    vm.register_function('ПодробноеПредставлениеОшибки',lambda info:info.get_member('Description'))
                    vm.register_function('AccumulationEmit',lambda n,v:observed.append((int(n),v)),returns_value=False)
                    vm.register_function('AccumulationDiagnostic',lambda n,s,e:diagnostics.append((int(n),s,e)),returns_value=False)
                    vm.execute((SOURCE/'observe.bsl').read_text(encoding='utf-8'),'native-typed12-replay')
        self.assertEqual(diagnostics,[])
        self.assertEqual([n for n,_ in observed],list(range(1,13)))
        self.assertEqual([v for _,v in observed],json.loads((CAPTURE/'observations12.out').read_bytes()))


class TypedVirtualGrammarTests(unittest.TestCase):
    def parse(self,condition):
        return syntax.parse_package('SELECT QuantityBalance FROM '+REG+'Balance(&At,'+condition+')')[0]

    def test_dedicated_array_node_does_not_enable_package_membership(self):
        q=self.parse('Product IN (&Products) AND (Unit В (&Units))')
        self.assertEqual(sum(type(n) is syntax.VirtualMembership for n in syntax.walk_nodes(q)),2)
        self.assertFalse(syntax.extended_filters(q))
        self.assertEqual(sum(type(n) is syntax.Parameter for n in syntax.walk_nodes(q)),3)

    def test_only_parenthesized_single_parameter_form_is_admitted(self):
        for condition in ('Unit IN &Units','Unit IN (&A,&B)','Unit IN ("Piece")',
                'Unit IN (SELECT Unit FROM Catalog.Products)','Unit NOT IN (&Units)',
                'Unit IN (&Units) OR Unit=&U','R.Unit IN (&Units)'):
            with self.subTest(condition=condition),self.assertRaises(ValueError):self.parse(condition)

    def test_in_uses_existing_comparison_and_depth_budgets(self):
        for condition in (' AND '.join(['Unit IN (&Units)']*129),'('*18+'Unit IN (&Units)'+')'*18):
            with self.assertRaises(ValueError):self.parse(condition)


class TypedVirtualRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'stock.sqlite'
        self.context=create_prepared(self.path,prepare_directory(SOURCE/'runtime_source',profile=PROFILE))
        self.addCleanup(self.context.close)
        self.vm=Interpreter(database_context=self.context,output=lambda text:None);self.addCleanup(self.vm.close)
        functions=(SOURCE/'observe.bsl').read_text(encoding='utf-8').split('Function ObserveCase')[0]
        self.vm.execute(functions+'P=Item("P"); W=Warehouse("W"); U=Enums.Units.Piece; U2=Enums.Units.Pack;'
            'LotDate=Date(2024,2,1);'
            'First=Move("A",P,W,U,Date(2024,2,2),5,"lot",1.25,True,LotDate);'
            'Second=Move("B",P,W,U2,Date(2024,2,3),7,"LOT ",2.5,False,LotDate);')
        self.p,self.w,self.u,self.u2=[self.vm.execute(n) for n in ('P','W','U','U2')]
        self.at=self.vm.execute('Date(2024,3,31,23,59,59)')

    def query(self,text,**parameters):
        q=self.vm.execute('New Query');q.set_member('Text',text)
        for k,v in dict(At=self.at,Product=self.p,Warehouse=self.w,U=self.u,**parameters).items():q.set_parameter(k,v)
        return q

    def report(self,condition,**parameters):
        return self.query('SELECT QuantityBalance FROM '+REG+'Balance(&At,'+condition+')',**parameters).execute()._rows

    def test_four_scalars_and_measured_nonmatch(self):
        for condition,value,expected in (
                ('Batch','lot',12),('Batch','LOT ',12),('Grade',Decimal('1.25'),5),
                ('Reserved',True,5),('LotDate',self.vm.execute('LotDate'),12),
                ('Grade','1.25',0),('Grade',Decimal('1.251'),0),('Batch','x'*40,0)):
            with self.subTest(field=condition,value=value):
                self.assertEqual(self.report(condition+'=&V',V=value),((Decimal(expected),),))

    def test_only_measured_wrong_kind_is_nonmatch(self):
        for condition,value in (('Grade',True),('Reserved',Decimal(1)),('Unit','Piece'),('Batch',Decimal(1))):
            with self.subTest(field=condition),self.assertRaises(TypeError):self.report(condition+'=&V',V=value)

    def test_scalar_arrays_and_duplicates(self):
        self.assertEqual(self.report('Grade IN (&V)',V=array(Decimal('1.25'),Decimal('1.25'))),((Decimal(5),),))
        self.assertEqual(self.report('Reserved IN (&V)',V=array(True,False)),((Decimal(12),),))
        self.assertEqual(self.report('LotDate IN (&V)',V=array(self.vm.execute('LotDate'))),((Decimal(12),),))

    def test_enum_array_fixed_array_and_owned_wrong_enum(self):
        wrong=self.vm.execute('Enums.States.Draft')
        for values,expected in ((array(wrong),0),(array(wrong,self.u),5),
                (array(self.u,self.u2),12),(BSLFixedArray(array(self.u)),5)):
            with self.subTest(expected=expected):self.assertEqual(self.report('Unit IN (&V)',V=values),((Decimal(expected),),))
        self.assertEqual(self.report('Unit=&V',V=wrong),((Decimal(0),),))

    def test_empty_null_and_typed_empty_are_distinct(self):
        for values,expected in ((array(),0),(array(NULL),0),(array(NULL,self.u),5),
                (array(self.vm.execute('Enums.Units.EmptyRef()')),0)):
            self.assertEqual(self.report('Unit IN (&V)',V=values),((Decimal(expected),),))

    def test_duplicate_members_count_before_dedup(self):
        self.assertEqual(self.report('Unit IN (&V)',V=array(*([self.u]*256))),((Decimal(5),),))
        with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('no query lease')):
            with self.assertRaisesRegex(ValueError,'member limit'):self.report('Unit IN (&V)',V=array(*([self.u]*257)))

    def test_list_snapshot_is_once_per_execute_and_shared_by_sources(self):
        from yadinassi import relational_queries
        values=array(self.u)
        q=self.query('SELECT A.QuantityBalance AS X,B.QuantityBalance AS Y FROM '+REG+
            'Balance(&At,Unit IN (&V)) AS A INNER JOIN '+REG+
            'Balance(&At,Unit IN (&V)) AS B ON A.Unit=B.Unit',V=values)
        original=relational_queries.snapshot_parameters
        with patch.object(relational_queries,'snapshot_parameters',wraps=original) as frozen:
            self.assertEqual(q.execute()._rows,((Decimal(5),Decimal(5)),))
            values.items.append(self.u2)
            self.assertEqual(sorted(q.execute()._rows),[(Decimal(5),Decimal(5)),(Decimal(7),Decimal(7))])
        self.assertEqual(frozen.call_count,2)

    def test_array_mutation_after_binding_does_not_change_current_execution(self):
        values=array(self.u);q=self.query('SELECT QuantityBalance FROM '+REG+'Balance(&At,Unit IN (&V))',V=values)
        original=self.context.backend.begin_query_read
        def open_view():
            values.items.append(self.u2);return original()
        with patch.object(self.context.backend,'begin_query_read',side_effect=open_view):
            self.assertEqual(q.execute()._rows,((Decimal(5),),))
        self.assertEqual(q.execute()._rows,((Decimal(12),),))

    def test_foreign_and_fabricated_nested_enum_rejected_before_query_lease(self):
        with closing(Interpreter(database_context=self.context)) as other:
            foreign=other.execute('Enums.Units.Piece')
            for value in (foreign,replace(self.u),replace(self.u,metadata=object())):
                with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('no query lease')):
                    with self.assertRaises((BackendError,ValueError,TypeError)):
                        self.report('Unit IN (&Empty) AND Unit IN (&V)',Empty=array(),V=array(value))

    def test_nested_catalog_issuer_and_target_guards(self):
        touched=[]
        class Hook:
            def __call__(self,*a):touched.append('call')
            def __eq__(self,other):touched.append('eq');return True
            def __hash__(self):touched.append('hash');return 1
        with patch('yadinassi.accumulation_queries.load', side_effect=AssertionError('no source scan')):
            with self.assertRaises((TypeError,ValueError,BackendError)): self.report('Product IN (&V)',V=array(self.w))
        self.assertIsNone(self.context.backend._active)
        for value in (replace(self.p,read_member=Hook()),replace(self.p,metadata=object())):
            with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('no query lease')):
                with self.assertRaises((TypeError,ValueError,BackendError)):self.report('Product IN (&V)',V=array(value))
        self.assertEqual(touched,[])

    def test_no_arbitrary_iterables_nested_arrays_or_managers(self):
        for value in ([self.u],(self.u,),array(array(self.u)),array(self.vm.execute('Enums.Units'))):
            with self.assertRaises((TypeError,ValueError)):self.report('Unit IN (&V)',V=value)

    def test_all_terms_bound_and_limits_remain_closed(self):
        with patch('yadinassi.accumulation_queries.load',side_effect=AssertionError('no source scan')):
            with self.assertRaises(ValueError):self.report('Unit IN (&Empty) AND Missing=&U',Empty=array())
            self.assertIsNone(self.context.backend._active)
        with patch.object(self.context.backend,'begin_query_read',side_effect=AssertionError('no query lease')):
            with self.assertRaises(ValueError):self.report(' AND '.join(['Unit=&U']*17))

    def test_query_scalar_bounds_not_storage_qualifier_adjustment(self):
        for value in ('x'*4097,Decimal('NaN'),Decimal('1e99')):
            with self.assertRaises(ValueError):self.report('Grade IN (&V)',V=array(value))

    def test_unselected_rows_and_fields_charge_before_filter(self):
        with patch.object(syntax,'MAX_ROWS',1):
            with self.assertRaisesRegex(ValueError,'input row limit'):self.report('Unit=&U')
        with patch('yadinassi.queries._MAX_CELLS',20):
            with self.assertRaisesRegex(ValueError,'input resource limit'):self.report('Unit=&U')

    def test_unselected_raw_edit_is_detected_after_warm_read(self):
        self.report('Unit=&U');key=self.vm.execute('Second')._key
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE accumulation_movement SET values_json=? WHERE record_id=?',('[]',str(key.record_id)))
        with self.assertRaises((BackendError,ValueError)):self.report('Unit=&U')

    def test_bare_membership_refused_and_typed_package_composes(self):
        with self.assertRaises(ValueError):
            self.query('SELECT Unit FROM Catalog.Products WHERE Unit IN &V',V=array(self.u)).execute()
        text = 'SELECT QuantityBalance FROM '+REG+'Balance(&At,Unit IN (&V));SELECT Unit FROM Catalog.Products'
        self.assertEqual(self.query(text,V=array(self.u)).execute()._rows,
                         self.query('SELECT Unit FROM Catalog.Products').execute()._rows)

    def test_legacy_profiles_do_not_gain_virtual_in(self):
        from yadinassi.configuration_accumulation_references import PROFILE as LEGACY
        path=Path(self.temp.name)/'legacy.sqlite'
        with closing(create_prepared(path,prepare_directory(ROOT/'scripts/inventory_reference_behavior/runtime_source',profile=LEGACY))) as context:
            with closing(Interpreter(database_context=context)) as vm:
                q=vm.execute('New Query');q.set_member('Text','SELECT QuantityBalance FROM '+REG+'Balance(&At,Product IN (&V))')
                q.set_parameter('At',self.at);q.set_parameter('V',array(vm.execute('Catalogs.Products.EmptyRef()')))
                with patch.object(context.backend,'begin_query_read',side_effect=AssertionError('no query lease')):
                    with self.assertRaises(ValueError):q.execute()

    def test_reused_array_charges_each_term_before_dedup(self):
        values=array('lot','lot')
        with patch('yadinassi.queries._MAX_RESULT_TEXT',10):
            with self.assertRaisesRegex(ValueError,'binding resource limit'):
                self.report('Batch IN (&V) AND Batch IN (&V)',V=values)
        with patch('yadinassi.queries._MAX_CELLS',3):
            with self.assertRaisesRegex(ValueError,'binding resource limit'):
                self.report('Batch IN (&V) AND Batch IN (&V)',V=values)

    def test_binding_budget_is_shared_across_joined_sources(self):
        text='SELECT A.QuantityBalance AS X,B.QuantityBalance AS Y FROM '+REG+'Balance(&At,Batch IN (&V)) AS A INNER JOIN '+REG+'Balance(&At,Batch IN (&V)) AS B ON A.Unit=B.Unit'
        with patch('yadinassi.queries._MAX_RESULT_TEXT',10):
            with self.assertRaisesRegex(ValueError,'binding resource limit'):
                self.query(text,V=array('lot','lot')).execute()

    def test_empty_scan_revalidates_issuer_after_binding_inside_view(self):
        self.vm.execute('First.Write(DocumentWriteMode.UndoPosting);Second.Write(DocumentWriteMode.UndoPosting);')
        from yadinassi.inventory_enum_runtime import query_binding
        binding=query_binding(self.vm.execute('Catalogs'))
        manager=binding._namespace._managers['units'];old=manager._values
        original=self.context.backend.begin_query_read
        def open_view():
            view=original();manager._values=tuple(list(old));return view
        try:
            with patch.object(self.context.backend,'begin_query_read',side_effect=open_view):
                with self.assertRaises(BackendError):self.report('Unit IN (&V)',V=array(self.u))
            self.assertIsNone(self.context.backend._active)
        finally:manager._values=old
