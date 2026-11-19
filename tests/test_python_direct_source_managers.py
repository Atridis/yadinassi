"""Declared manager exports run directly without granting storage or VM access."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch
from test_source_manager_modules import configuration
from test_source_manager_families import FAMILIES
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.errors import BSLError


class DirectSourceManagers(unittest.TestCase):
    @contextmanager
    def no_vm(self):
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('legacy program')), \
             patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):yield

    def app(self,config):
        output=[];app=SourceApplication(config,output=output.append)
        self.addCleanup(app.close);return app,output

    def test_common_module_named_manager_is_not_a_metadata_manager_key(self):
        from test_configuration_source_runtime import source
        from test_source_metadata import xml
        config=source(b'Procedure OnStart() Message(Manager.Answer()); EndProcedure',{
            'CommonModules/Manager.xml':xml('CommonModule','Manager',properties='<ClientManagedApplication>true</ClientManagedApplication><Server>true</Server>'),
            'CommonModules/Manager/Ext/Module.bsl':b'Function Answer() Export Return 42; EndFunction'})
        app,out=self.app(config)
        with self.no_vm():app.start()
        self.assertEqual(out,['42'])

    def test_client_index_denied_before_index_expression(self):
        from yadinassi.configuration.configuration_source import import_source
        config=configuration('Try Catalogs[Name()].Answer(); Except Message("denied"); EndTry;',session=False)
        files={entry.path:entry.content for entry in config.files}
        files['Ext/ManagedApplicationModule.bsl']+=b' Function Name() Message("effect"); Return "Items"; EndFunction'
        app,out=self.app(import_source(files))
        with self.no_vm():app.start()
        self.assertEqual(out,['denied'])

    def test_all_manager_namespaces_export_without_vm_or_storage(self):
        for family,folder,ru in FAMILIES:
            with self.subTest(family=family):
                app,out=self.app(configuration('Message('+folder+'.Items.Answer()); Message('+ru+'["Items"].Answer());',family=family,folder=folder))
                with self.no_vm():app.start()
                self.assertEqual(out,['42','42']);self.assertIsNone(app.constant_store)

    def test_byref_and_default_exports(self):
        for family,folder in (('Catalog','Catalogs'),('Report','Reports'),('Document','Documents'),('InformationRegister','InformationRegisters')):
            with self.subTest(family=family):
                body='Procedure Change(X, Val Amount=3) Export X=X+Amount; EndProcedure'
                app,out=self.app(configuration('X=2; '+folder+'.Items.Change(X); Message(X);',body=body,family=family,folder=folder))
                with self.no_vm():app.start()
                self.assertEqual(out,['5'])

    def test_private_client_and_initializer_denied_without_effects(self):
        configs=(configuration(body='Function Answer() Return 1; EndFunction'),
                 configuration(session=False),
                 configuration(body='Message("initializer"); Function Answer() Export Return 1; EndFunction'))
        for config in configs:
            app,out=self.app(config)
            with self.no_vm(),self.assertRaises(BSLError):app.start()
            self.assertEqual(out,[])

    def test_exports_do_not_enable_storage(self):
        for call,family,folder in (('Catalogs.Items.CreateItem();','Catalog','Catalogs'),
                                  ('Documents.Items.CreateDocument();','Document','Documents'),
                                  ('InformationRegisters.Items.CreateRecordSet();','InformationRegister','InformationRegisters')):
            app,out=self.app(configuration(call,family=family,folder=folder))
            with self.no_vm(),self.assertRaises(BSLError):app.start()
            self.assertEqual(out,[]);self.assertIsNone(app.constant_store)

    def test_delayed_manager_registry_replacement_revokes_bound_call(self):
        import test_python_direct_source_query as fixtures
        app,out=self.app(configuration('',body='Function Answer(Val X=1) Export Return X; EndFunction'))
        with self.no_vm():app.start()
        owner=app._session_owner;owner._context_stack.append('server')
        self.addCleanup(owner._context_stack.pop)
        with fixtures.DirectSourceQueryTests.boundary(self,app,owner) as boundary:
            module=app.manager_module('Catalog','Items',owner)
            bound=boundary.resolve_source_member(module,'Answer',require_value=True,argument_count=1)
            self.assertEqual(bound(9),9)
            child=app._instances.pop(('manager','Catalog','items'))
            self.addCleanup(child.close)
            with self.assertRaisesRegex(BoundaryViolation,'replaced|binding|module'):bound(9)

    def test_wrong_arity_and_procedure_as_value_before_argument_effect(self):
        for statement in ('Catalogs.Items.Answer(ArgumentEffect());', 'X=Catalogs.Items.Action(ArgumentEffect());'):
            app,out=self.app(configuration('',body='Function Answer() Export Return 1; EndFunction Procedure Action(X) Export EndProcedure'))
            with self.no_vm():app.start()
            effects=[];owner=app._session_owner
            owner._context_stack.append('server');self.addCleanup(owner._context_stack.pop)
            owner.register_function('ArgumentEffect',lambda:effects.append('argument'))
            with self.no_vm(),self.assertRaises(BSLError):
                owner.execute('&AtServer\nProcedure Run() '+statement+' EndProcedure Run();')
            self.assertEqual(effects,[])


if __name__=='__main__':unittest.main()
