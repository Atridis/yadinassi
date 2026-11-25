"""Host-selected catalog bridge; original writer validation is not bypassed."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from sqlite_test_templates import copy_main_demo

class DirectDatabaseTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        path=Path(folder.name)/'db.sqlite'
        copy_main_demo(path)
        self.context=SQLiteDBContext(path)
        self.addCleanup(self.context.close)
        self.vm=DirectDatabaseTests.interpreter(self)

    def interpreter(self, **options):
        vm=Interpreter(database_context=self.context, **options)
        self.addCleanup(vm.close)
        return vm

    def test_objects_fields_sections_and_no_argument_add(self):
        self.vm.execute('A=Catalogs.Номенклатура.CreateItem(); A.Description=" Item "; Row=A.Склады.Add(); N=A.Склады.Count();')
        self.assertEqual(self.vm.variables['a'].get_member('Description'),' Item ')
        self.assertEqual(self.vm.variables['n'],1)

    def test_plain_catalog_write_readback_uses_existing_writer(self):
        self.vm.execute('A=Catalogs.Склады.CreateItem(); A.Description="Warehouse"; A.Write(); B=A.Ref.GetObject();')
        self.assertEqual(self.vm.variables['b'].get_member('Description'),'Warehouse')
        self.assertFalse(self.vm.variables['b'].is_new())

    def test_foreign_receiver_and_backend_attributes_deny(self):
        self.vm.execute('A=Catalogs.Склады.CreateItem();')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.variables['foreign']=self.vm.variables['a']
        with self.assertRaises(BoundaryViolation):other.execute('foreign.Description="bad";')
        with self.assertRaises(Exception):self.vm.execute('secret=A._manager;')

    def test_catalog_object_ref_can_be_forwarded_but_not_rebound(self):
        vm=self.vm
        vm.execute('''A=Catalogs.Склады.CreateItem(); A.Description="Warehouse"; A.Write();
Function InspectRef(R) Return R.IsEmpty(); EndFunction
Procedure ReplaceRef(R) R=Undefined; EndProcedure''')
        for member in ('Ref','Ссылка'):
            with self.subTest(member=member):
                self.assertIs(vm.execute(f'InspectRef(A.{member})'),False)
                with self.assertRaisesRegex(BSLRuntimeError,'Свойство недоступно для записи'):
                    vm.execute(f'ReplaceRef(A.{member});')
        self.assertIs(vm.execute('A.Ref.IsEmpty()'),False)
        other=self.interpreter()
        other.variables['foreign']=vm.variables['a']
        with self.assertRaisesRegex(BoundaryViolation,'foreign database receiver'):
            other.execute('Function InspectRef(R) Return R.IsEmpty(); EndFunction\n'
                          'InspectRef(Foreign.Ref)')

    def test_denied_transaction_caller_is_rejected_before_effect_and_flag_restored(self):
        self.vm._transaction_activation_allowed=False
        with patch('yadinassi.db.database_transactions.begin',side_effect=AssertionError('effect')) as begin:
            with self.assertRaises(Exception):self.vm.execute('BeginTransaction();')
            begin.assert_not_called()
        self.assertFalse(self.vm._transaction_activation_allowed)

    def test_query_selection_on_real_sqlite_without_vm_dispatch(self):
        self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Номенклатура"); S=Q.Execute().Select(); Found=S.Next(); N=S.N;')
        self.assertTrue(self.vm.variables['found'])
        self.assertEqual(self.vm.variables['n'],0)
        self.vm.execute('Again=S.Next(); Last=S.N;')
        self.assertFalse(self.vm.variables['again'])
        self.assertEqual(self.vm.variables['last'],0)

    def test_query_select_and_named_next_keep_ordinary_sql_and_return_values(self):
        vm=self.vm
        source='Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); S=Q.Execute().Select(); B=S.Next(); R=S.N;'
        from yadinassi.execution.direct.python_direct_database import CatalogBoundary
        from yadinassi.syntax.parser import parse
        from decimal import Decimal
        generic=CatalogBoundary.resolve_member
        visits=[]
        def observe(context,value,name):
            visits.append(name.casefold())
            return generic(context,value,name)
        for route in ('default','prepared'):
            program=parse(source)
            run=(lambda:vm.execute_program(program)) if route=='default' else (
                lambda plan=vm.prepare_program(program):vm.execute_prepared(plan))
            with patch.object(CatalogBoundary,'resolve_member',observe):
                run()
            self.assertEqual(vm.variables['r'],Decimal(0))
            self.assertIs(vm.variables['b'],True)
        self.assertFalse(set(visits) & {'execute','select','next'})

    def test_routine_local_query_methods_use_detached_origin_after_alias_rebind(self):
        from yadinassi.execution.direct.python_direct_database import CatalogBoundary
        from yadinassi.syntax.parser import parse
        source=('Function Work() Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); '
                'Results=Q.Execute(); Alias=Results; Results=0; S=Alias.Select(); S.Next(); '
                'Return S.N; EndFunction\nWork()')
        plan=self.vm.prepare_program(parse(source))
        generated=plan._plan.generated_source
        self.assertIn('.select()',generated)
        self.assertIn('.next()',generated)
        self.assertNotIn('_known_detached_after_publication',generated)
        with patch.object(CatalogBoundary,'resolve_member',side_effect=AssertionError('generic query method')):
            self.assertEqual(self.vm.execute(source),0)
            self.assertEqual(self.vm.execute_prepared(plan),0)

    def test_routine_query_conditions_match_direct_return_and_short_circuit(self):
        from yadinassi.execution.direct.python_direct_database import CatalogBoundary
        from yadinassi.syntax.parser import parse
        prefix=('Function Work() Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); '
                'S=Q.Execute().Select(); ')
        for body,calls in (
                ('Return S.Next();',1),
                ('If (S.Next()) Then Return True; EndIf; Return False;',1),
                # Only the reachable Next needs the direct cursor protocol.
                # The one-row COUNT result below detects a spurious dead call.
                ('If False And S.Next() Then Return False; '
                 'ElsIf Not (S.Next() = False) Then Return True; EndIf; Return False;',1),
                ('Return ?(True,S, S).Next();',1),
        ):
            with self.subTest(body=body):
                source=prefix+body+' EndFunction\nWork()'
                plan=self.vm.prepare_program(parse(source))
                self.assertEqual(plan._plan.generated_source.count('.next()'),calls)
                with patch.object(CatalogBoundary,'resolve_member',side_effect=AssertionError('generic query method')):
                    self.assertIs(self.vm.execute(source),True)
                    self.assertEqual([self.vm.execute_prepared(plan) for _ in range(10)],[True]*10)

    def test_routine_query_conditional_join_only_keeps_proven_fallthrough(self):
        from yadinassi.execution.direct.python_direct_database import CatalogBoundary
        from yadinassi.syntax.parser import parse
        prefix=('Procedure Touch() EndProcedure\n'
                'Function Work() Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); '
                'S=Q.Execute().Select(); ')
        original=CatalogBoundary.resolve_member
        for body,direct,generic in (
                ('If S.Next() Then A=S; Else A=S; EndIf; Return A.Next();',2,[]),
                ('If Not S.Next() Then Return False; Else A=S; EndIf; Return A.Next();',2,[]),
                ('If Not S.Next() Then Return S.N; EndIf; Return S.Next();',2,[]),
                ('If S.Next() Then A=S; Else A=0; EndIf; Return A.Next();',1,['next']),
                ('If S.Next() Then Touch(); EndIf; Return S.Next();',1,['next']),
        ):
            with self.subTest(body=body):
                source=prefix+body+' EndFunction\nWork()'
                plan=self.vm.prepare_program(parse(source))
                self.assertEqual(plan._plan.generated_source.count('.next()'),direct)
                seen=[]
                def observe(context,value,name):
                    seen.append(name.casefold())
                    return original(context,value,name)
                with patch.object(CatalogBoundary,'resolve_member',observe):
                    self.assertIs(self.vm.execute_prepared(plan),False)
                self.assertEqual(seen,generic)

    def test_routine_query_condition_preserves_rebound_method_and_extension_dispatch(self):
        from yadinassi.db.query.queries import BSLQueryResultSelection
        from yadinassi.syntax.parser import parse
        from yadinassi.types.values import HostFunction
        source=('Function Work() Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); '
                'S=Q.Execute().Select(); If S.Next() Then Return True; EndIf; Return False; EndFunction\nWork()')
        original=BSLQueryResultSelection.get_method
        seen=[]
        def changed(value,name):
            if name.casefold()=='next':
                seen.append(name)
                return HostFunction(name,lambda:False)
            return original(value,name)
        for vm in (self.vm,self.interpreter(allow_extensions=True)):
            with self.subTest(extensions=vm is not self.vm):
                plan=vm.prepare_program(parse(source))
                with patch.object(BSLQueryResultSelection,'get_method',changed):
                    self.assertIs(vm.execute_prepared(plan),False)
                self.assertIs(vm.execute_prepared(plan),True)
        self.assertEqual(seen,['Next','Next'])

    def test_module_query_branch_and_routine_transaction_keep_the_active_view(self):
        from yadinassi.execution.direct.python_direct_database import CatalogBoundary
        from yadinassi.syntax.parser import parse
        text='SELECT Code FROM Catalog.Склады WHERE Code = ""17""'
        routine=('Function Work() Q=New Query("'+text+'"); S=Q.Execute().Select(); '
                 'If S.Next() Then Return True; EndIf; Return False; EndFunction\n')
        transaction=('BeginTransaction(); Item=Catalogs.Склады.CreateItem(); Item.Code="17"; '
                     'Item.Description="Only in transaction"; Item.Write(); '
                     'Staged=Work(); RollbackTransaction(); Outside=Work();')
        module=('Q=New Query("'+text+'"); S=Q.Execute().Select(); '
                'If S.Next() Then Found=True; Else Found=False; EndIf;')
        with patch.object(CatalogBoundary,'resolve_member',autospec=True,side_effect=CatalogBoundary.resolve_member) as generic:
            self.vm.execute(routine+transaction)
            self.assertIs(self.vm.variables['staged'],True)
            self.assertIs(self.vm.variables['outside'],False)
            plan=self.vm.prepare_program(parse(module))
            self.assertEqual(plan._plan.generated_source.count('.next()'),1)
            self.vm.execute_prepared(plan)
            self.assertIs(self.vm.variables['found'],False)
        self.assertNotIn('next',[call.args[2].casefold() for call in generic.call_args_list])

    def test_second_routine_origin_does_not_relicense_an_earlier_result_alias(self):
        from yadinassi.execution.direct.python_direct_database import CatalogBoundary
        source=('Function Work() Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); '
                'R=Q.Execute(); Other=Q.Execute(); S=R.Select(); S.Next(); '
                'Return S.N; EndFunction\nWork()')
        original=CatalogBoundary.resolve_member
        seen=[]
        def observe(context,value,name):
            seen.append(name.casefold())
            return original(context,value,name)
        with patch.object(CatalogBoundary,'resolve_member',observe):
            self.assertEqual(self.vm.execute(source),0)
        self.assertEqual(seen,['execute','select','next'])

    def test_prepared_query_uses_rebound_method_protocol_via_original_fallback(self):
        from yadinassi.db.query.queries import BSLQueryResultSelection
        from yadinassi.syntax.parser import parse
        from yadinassi.types.values import HostFunction
        vm=self.vm
        plan=vm.prepare_program(parse('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады"); B=Q.Execute().Select().Next();'))
        original=BSLQueryResultSelection.get_method
        calls=[]
        def changed(value,name):
            if name.casefold()=='next':
                calls.append(name)
                return HostFunction(name,lambda:False)
            return original(value,name)
        with patch.object(BSLQueryResultSelection,'get_method',changed):
            vm.execute_prepared(plan)
        self.assertEqual(calls,['Next'])
        self.assertIs(vm.variables['b'],False)
        vm.execute_prepared(plan)
        self.assertIs(vm.variables['b'],True)

    def test_foreign_query_and_query_private_fields_rejected(self):
        self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Номенклатура");')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.variables['foreign']=self.vm.variables['q']
        with self.assertRaises(BoundaryViolation):other.execute('foreign.Execute();')
        with self.assertRaises(Exception):self.vm.execute('secret=Q._catalogs;')

    def test_document_and_enum_buffer_protocol_without_persistence(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument(); D.Number="draft"; L=D.Lines.Add(); L.Unit=Enums.Units.Piece; L.Quantity=3; Mode=DocumentWriteMode.Posting; N=D.Lines.Count();')
        self.assertEqual(self.vm.variables['d'].get_member('Number'),'draft')
        self.assertEqual(self.vm.variables['l'].get_member('Quantity'),3)
        self.assertEqual(self.vm.variables['n'],1)
        from yadinassi.db.document.document_posting_values import DocumentWriteMode
        self.assertIs(self.vm.variables['mode'],DocumentWriteMode.POSTING)
        self.assertTrue(self.vm.variables['d'].is_new())

    def test_foreign_document_receiver_denied(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument();')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.variables['foreign']=self.vm.variables['d']
        with self.assertRaises(BoundaryViolation):other.execute('foreign.Number="bad";')
        self.assertEqual(self.vm.variables['d'].get_member('Number'),'')

    def test_document_selection_denies_foreign_owner_and_subclasses(self):
        from yadinassi.db.document.documents import BSLDocumentSelection
        self.vm.execute('S=Документы.Receipt.Выбрать();'
                        'Before=S.Номер; Missing=S.ПолучитьОбъект(); Ended=S.Следующий();')
        self.assertIsNone(self.vm.variables['before'])
        self.assertIsNone(self.vm.variables['missing'])
        self.assertFalse(self.vm.variables['ended'])
        selection=self.vm.variables['s']
        other=self.interpreter()
        other.variables['s']=selection
        for source in ('S.Next();','X=S.Number;','X=S.GetObject();'):
            with self.subTest(source=source),self.assertRaises(BoundaryViolation):
                other.execute(source)
        class Derived(BSLDocumentSelection): pass
        self.vm.variables['s']=Derived(selection._manager,())
        with self.assertRaises(BoundaryViolation):
            self.vm.execute('S.Следующий();')

    def test_document_additional_properties_output_reference(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument(); D.AdditionalProperties.Insert("Mode",2); Mode=0; Found=D.AdditionalProperties.Property("Mode",Mode);')
        self.assertTrue(self.vm.variables['found'])
        self.assertEqual(self.vm.variables['mode'],2)

    def test_prepared_namespace_profile_rejects_transfer_before_effects(self):
        plain=Interpreter();self.addCleanup(plain.close)
        plain_plan=plain.prepare('Touched=1; Catalogs=1;')
        with self.assertRaisesRegex(Exception, 'contract changed'):
            self.vm.execute_prepared(plain_plan)
        self.assertNotIn('touched',self.vm.variables)
        self.assertNotIn('catalogs',self.vm.variables)
        db_plan=self.vm.prepare('Touched=1; N=Catalogs.Склады.Count();')
        with self.assertRaisesRegex(Exception, 'contract changed'):
            plain.execute_prepared(db_plan)
        self.assertNotIn('touched',plain.variables)

    def test_prepared_database_profile_rebinds_to_current_vm(self):
        plan=self.vm.prepare('A=Catalogs.Склады.CreateItem(); A.Description="fresh";')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.execute_prepared(plan)
        self.assertNotIn('a',self.vm.variables)
        self.assertEqual(other.variables['a'].get_member('Description'),'fresh')
        other.execute('A.Description="current";')
        self.assertEqual(other.variables['a'].get_member('Description'),'current')

    def test_catalog_selection_aliases_fields_restart_and_get_object(self):
        self.vm.execute('A=Catalogs.Склады.CreateItem(); A.Description="Warehouse"; A.Write(); '
                        'S=Catalogs.Склады.Select(); Before=S.Description; Missing=S.GetObject(); '
                        'Found=S.Следующий(); Name=S.Наименование; R=S.Ссылка; O=S.ПолучитьОбъект(); '
                        'Done=S.Next(); Last=S.Description; Restart=S.Next();')
        values=self.vm.variables
        self.assertIsNone(values['before']);self.assertIsNone(values['missing'])
        self.assertTrue(values['found']);self.assertFalse(values['done']);self.assertTrue(values['restart'])
        self.assertEqual(values['name'],'Warehouse');self.assertEqual(values['last'],'Warehouse')
        self.assertEqual(values['o'].get_member('Ref'),values['r'])

    def test_empty_catalog_selection_and_readonly_private_surface(self):
        self.vm.execute('S=Catalogs.Склады.Select(); Found=S.Next(); Again=S.Следующий();')
        self.assertFalse(self.vm.variables['found']);self.assertFalse(self.vm.variables['again'])
        with self.assertRaisesRegex(BoundaryViolation,'iterator not connected'):
            self.vm.execute('For Each X In S Do EndDo;')
        for source in ('X=S._manager;','X=S._rows;','S.Description="bad";'):
            with self.subTest(source=source),self.assertRaises(Exception):self.vm.execute(source)

    def test_foreign_and_subclass_catalog_selection_rejected(self):
        from yadinassi.db.catalog.catalogs import BSLCatalogSelection
        self.vm.execute('S=Catalogs.Склады.Select();')
        selection=self.vm.variables['s']
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.variables['s']=selection
        for source in ('S.Next();','X=S.Description;','X=S.GetObject();'):
            with self.subTest(source=source),self.assertRaises(BoundaryViolation):other.execute(source)
        class Derived(BSLCatalogSelection):pass
        self.vm.variables['s']=Derived(selection._manager,())
        with self.assertRaises(BoundaryViolation):self.vm.execute('S.Next();')

    def test_bound_selection_rechecks_owner_after_argument_effect(self):
        self.vm=self.interpreter(allow_extensions=True)
        self.vm.execute('S=Catalogs.Склады.Select();')
        selection=self.vm.variables['s'];original=selection._manager
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.execute('S=Catalogs.Склады.Select();')
        def change():selection._manager=other.variables['s']._manager
        self.vm.register_function('Change',change)
        try:
            with patch.object(selection,'next',side_effect=AssertionError('cursor effect')) as advance:
                with self.assertRaises(BoundaryViolation):self.vm.execute('S.Next(Change());')
                advance.assert_not_called()
        finally:selection._manager=original

    def test_selection_rejects_closed_family_at_service_boundary(self):
        self.vm=self.interpreter(allow_extensions=True)
        self.vm.execute('S=Catalogs.Склады.Select();')
        selection=self.vm.variables['s']
        self.vm.register_function('CloseOwner',self.vm.close)
        with patch.object(selection,'next',side_effect=AssertionError('cursor effect')) as advance:
            with self.assertRaises(BoundaryViolation):self.vm.execute('CloseOwner(); S.Next();')
            advance.assert_not_called()

    def test_catalog_metadata_aliases_identity_and_public_lookup(self):
        self.vm.execute('M=Metadata.Catalogs.Склады; R=Catalogs.Склады.EmptyRef(); '
                        'Same=M=R.Metadata(); Alias=M=Метаданные.Справочники.Склады; '
                        'Name=M.Имя; Full=M.FullName(); '
                        'Found=Metadata.Catalogs.Find("Склады")=M; '
                        'Indexed=Metadata.Catalogs["Склады"]=M; '
                        'ByName=Metadata.FindByFullName("Catalog.Склады")=M; '
                        'ByType=Metadata.FindByType(TypeOf(R))=M;')
        for name in ('same','alias','found','indexed','byname','bytype'):
            self.assertTrue(self.vm.variables[name],name)
        self.assertEqual(self.vm.variables['name'],'Склады')
        self.assertEqual(self.vm.variables['full'],'Справочник.Склады')

    def test_metadata_foreign_roots_collections_and_items_rejected(self):
        self.vm.execute('Root=Metadata; Collection=Metadata.Catalogs; Item=Collection.Склады;')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        for name,expression in (('root','foreign.Catalogs'),('collection','foreign.Count()'),('item','foreign.Name')):
            other.variables['foreign']=self.vm.variables[name]
            with self.subTest(name=name),self.assertRaises(BoundaryViolation):other.execute('X='+expression+';')

    def test_metadata_private_readonly_and_admitted_family_boundaries(self):
        from yadinassi.types.errors import BSLRuntimeError
        for source in ('Metadata=1;', 'Metadata.Catalogs=1;', 'Metadata.Catalogs.Склады.Name="bad";',
                       'Metadata.Catalogs["Склады"]=1;', 'X=Metadata._catalogs;', 'X=Metadata.Catalogs._context;',
                       'X=Metadata.Catalogs.Склады._root;'):
            with self.subTest(source=source),self.assertRaises(BSLRuntimeError):self.vm.execute(source)
        self.vm.execute('Names=New Array;For Each X In Metadata.Catalogs Do Names.Add(X.Name);EndDo;')
        self.assertEqual(list(self.vm.variables['names']),['ВидыНоменклатуры','Склады','Номенклатура'])
        self.assertEqual(self.vm.execute('Metadata.Documents.Count();'),2)

    def test_metadata_subclasses_rejected(self):
        from yadinassi.configuration.metadata import BSLMetadata,BSLCatalogMetadataCollection,BSLCatalogMetadata
        for base in (BSLMetadata,BSLCatalogMetadataCollection,BSLCatalogMetadata):
            class Derived(base):pass
            self.vm.variables['foreign']=object.__new__(Derived)
            with self.subTest(base=base),self.assertRaises(BoundaryViolation):self.vm.execute('X=foreign.Name;')

    def test_bound_metadata_method_rechecks_current_owner(self):
        self.vm=self.interpreter(allow_extensions=True)
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        original=self.vm._metadata
        def change():
            self.vm._metadata=other._metadata
            return 'Catalog.Склады'
        self.vm.register_function('Change',change)
        try:
            with patch.object(original,'find_by_full_name',side_effect=AssertionError('lookup effect')) as lookup:
                with self.assertRaises(BoundaryViolation):self.vm.execute('X=Metadata.FindByFullName(Change());')
                lookup.assert_not_called()
        finally:self.vm._metadata=original

    def test_prepared_metadata_binds_current_runtime(self):
        plan=self.vm.prepare('M=Metadata.Catalogs.Склады;')
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.execute_prepared(plan)
        self.assertIs(other.variables['m']._root,other._metadata)
        self.assertNotIn('m',self.vm.variables)
        plain=Interpreter();self.addCleanup(plain.close)
        with self.assertRaisesRegex(Exception,'contract changed'):plain.execute_prepared(plan)

    def test_metadata_context_change_denied_before_lookup(self):
        self.vm=self.interpreter(allow_extensions=True)
        original=self.vm._metadata;context=self.vm._database_context
        def change():
            self.vm._database_context=None
            return 'Catalog.Склады'
        self.vm.register_function('Change',change)
        try:
            with patch.object(original,'find_by_full_name',side_effect=AssertionError('lookup effect')) as lookup:
                with self.assertRaises(BoundaryViolation):self.vm.execute('X=Metadata.FindByFullName(Change());')
                lookup.assert_not_called()
        finally:self.vm._database_context=context
