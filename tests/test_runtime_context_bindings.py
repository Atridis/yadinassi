"""VM-local helpers with shared family/context metadata and isolated external roots."""
from pathlib import Path
import unittest

from yadinassi import Interpreter
from yadinassi.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.values import HostFunction
from configuration_runtime_fixture import module_files, SERVER
import test_catalog_queries as catalog_fixtures


BODY = '''
Ref = Catalogs.Categories.FindByCode("01");
If TypeOf(Ref) <> Type("CatalogRef.Categories") Then Raise "type owner"; EndIf;
If ТипЗнч(Ref) <> Тип("СправочникСсылка.Categories") Then Raise "alias owner"; EndIf;
Q = New Query("SELECT Ref FROM Catalog.Categories WHERE Ref=&Target");
Q.SetParameter("Target", Ref); S = Q.Execute().Select(); S.Next();
P = Catalogs.Products.CreateItem();
FillPropertyValues(P, New Structure("Category", S.Ref));
If P.Category <> Ref Then Raise "reference owner"; EndIf;
M = New МенеджерВременныхТаблиц;
Q = New Запрос("SELECT Ref INTO Prepared FROM Catalog.Categories; SELECT Ref FROM Prepared");
Q.TempTablesManager = M; S = Q.Execute().Select(); S.Next();
P.Category = S.Ref; M.Close();
Return P.Category = Ref;
'''


class RuntimeContextBindingTests(unittest.TestCase):
    setUp = catalog_fixtures.CatalogQueryTests.setUp
    tearDown = catalog_fixtures.CatalogQueryTests.tearDown

    def load(self, source=BODY):
        path = Path(self.temp.name) / 'Helper.bsl'
        path.write_text('Function Check() Export\n' + source + '\nEndFunction', encoding='utf-8')
        self.vm.execute('// #Import Helper.bsl\n', str(path.with_name('main.bsl')))
        return self.vm.imports['helper'].interpreter

    def test_imported_query_type_reference_and_temporary_tables_share_child_owner(self):
        child = self.load()
        self.assertTrue(self.vm.execute('Helper.Check()'))
        self.assertIs(child._catalogs._metadata, self.vm._catalogs._metadata)
        self.assertIsNot(child._catalogs, self.vm._catalogs)
        self.assertIs(self.vm.functions['type'].function.__self__, self.vm)

    def test_nested_import_and_cached_module_use_their_own_binding(self):
        self.load()
        bridge = Path(self.temp.name) / 'Bridge.bsl'
        bridge.write_text('// #Import Helper.bsl\nFunction Check() Export Return Helper.Check(); EndFunction', encoding='utf-8')
        self.vm.execute('// #Import Bridge.bsl\n', str(bridge.with_name('main.bsl')))
        child = self.vm.imports['bridge'].interpreter
        self.assertIs(child.imports['helper'], self.vm.imports['helper'])
        for _ in range(2): self.assertTrue(self.vm.execute('Bridge.Check()'))

    def test_server_and_nocontext_query_type_and_reference_assignment(self):
        for directive in ('AtServer', 'AtServerNoContext', 'AtClientAtServerNoContext'):
            with self.subTest(directive=directive):
                self.vm.execute('&' + directive + '\nFunction Check()\n' + BODY + '\nEndFunction')
                self.assertTrue(self.vm.execute('Check()'))
                self.assertEqual(self.vm.execution_context, 'client')

    def test_imported_server_activation_does_not_keep_ancestor_binding(self):
        path = Path(self.temp.name) / 'Gateway.bsl'
        path.write_text('&AtServerNoContext\nFunction Check() Export\n' + BODY + '\nEndFunction', encoding='utf-8')
        self.vm.execute('// #Import Gateway.bsl\n', str(path.with_name('main.bsl')))
        self.assertTrue(self.vm.execute('Gateway.Check()'))

    def test_type_query_and_manager_aliases_share_rebound_wrapper(self):
        child = self.load()
        for vm in (child, child._new_server_activation(module_context=False)):
            for registry, ru, en in ((vm.functions, 'тип', 'type'),
                                     (vm.types, 'запрос', 'query'),
                                     (vm.types, 'менеджервременныхтаблиц', 'temptablesmanager'),
                                     (vm.types, 'сообщениепользователю', 'usermessage')):
                self.assertIs(registry[ru], registry[en])
                self.assertIs(registry[en].function.__self__, vm)
            self.assertIs(vm.user_messages, self.vm.user_messages)
            self.assertNotIn('c', vm.variables)

    def test_host_overrides_and_reference_parameter_contract_are_preserved(self):
        def override(value=None): return value
        function = HostFunction('Type', override, reference_parameters=(0,), returns_value=False)
        self.vm.functions['type'] = function
        self.vm.functions['customalias'] = function
        self.vm.register_type('Query', override, 'MyQuery')
        child = self.load('Return True;')
        for vm in (child, child._new_server_activation(module_context=False)):
            inherited = vm.functions['type']
            self.assertIs(inherited.function, override)
            self.assertIs(vm.functions['customalias'], inherited)
            self.assertEqual(inherited.reference_parameters, (0,))
            self.assertFalse(inherited.returns_value)
            self.assertIs(vm.types['query'], vm.types['myquery'])
            self.assertIs(vm.types['query'].function, override)
            # Overriding one spelling does not overwrite the other spelling.
            self.assertIs(vm.functions['тип'].function.__self__, vm)

    def test_same_database_foreign_snapshot_still_rejected_for_field_and_query(self):
        child = self.load()
        independent = Interpreter(database_context=self.context)
        self.addCleanup(independent.close)
        child.variables['foreign'] = independent.execute('Catalogs.Categories.EmptyRef()')
        for code in ('P=Catalogs.Products.CreateItem();P.Category=Foreign;',
                     'P=Catalogs.Products.CreateItem();FillPropertyValues(P,New Structure("Category",Foreign));',
                     'Q=New Query("SELECT Ref FROM Catalog.Categories WHERE Ref=&R");Q.SetParameter("R",Foreign);Q.Execute();'):
            with self.subTest(code=code), self.assertRaisesRegex(Exception, 'same database|foreign|snapshot'):
                child.execute(code)

    def test_independent_root_temporary_table_manager_rejected_by_child_query(self):
        child = self.load()
        independent = Interpreter(database_context=self.context)
        self.addCleanup(independent.close)
        child.variables['foreign'] = independent.execute('New TempTablesManager')
        with self.assertRaises(Exception):
            child.execute('Q=New Query("SELECT Ref FROM Catalog.Categories");Q.TempTablesManager=Foreign;Q.Execute();')

    def test_same_family_reference_flows_through_assignment_fill_and_query(self):
        child = self.load()
        child.variables['shared'] = self.vm.execute('Catalogs.Categories.EmptyRef()')
        for code in ('P=Catalogs.Products.CreateItem();P.Category=Shared;',
                     'P=Catalogs.Products.CreateItem();FillPropertyValues(P,New Structure("Category",Shared));',
                     'Q=New Query("SELECT Ref FROM Catalog.Categories WHERE Ref=&R");Q.SetParameter("R",Shared);Q.Execute();'):
            with self.subTest(code=code): child.execute(code)

    def test_same_family_temporary_table_manager_can_be_used_by_child(self):
        child = self.load()
        manager = self.vm.execute('New TempTablesManager')
        child.variables['shared'] = manager
        try:
            child.execute('Q=New Query("SELECT Ref INTO Prepared FROM Catalog.Categories; SELECT Ref FROM Prepared");'
                          'Q.TempTablesManager=Shared;R=Q.Execute();')
            self.assertEqual(len(child.variables['r']._rows), 1)
        finally: manager.close()

    def test_common_modules_client_server_and_global_keep_context_owned_helpers(self):
        for flags in ({}, SERVER, {'Global': 'true'}):
            with self.subTest(flags=flags):
                files = module_files([('Tools', 'Function Check() Export\n' + BODY + '\nEndFunction', flags)])
                config = import_configuration(files, module_runtime=MODULE_RUNTIME)
                path = Path(self.temp.name) / ('common-' + str(len(flags)) + '.sqlite')
                with SQLiteDBContext.create(path, config) as context:
                    app = ConfigurationApplication(config, database_context=context)
                    try:
                        app.start()
                        app.interpreter.execute('C=Catalogs.Categories.CreateItem();C.Code="01";C.Write();')
                        call = 'Check()' if flags.get('Global') == 'true' else 'Tools.Check()'
                        self.assertTrue(app.interpreter.execute(call))
                    finally:
                        app.interpreter.close()


if __name__ == '__main__': unittest.main()
