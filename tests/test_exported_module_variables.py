"""Measured module exports and local integration with existing import dispatch.

The field lifecycle and reference cases follow native run 39864376445.
Import caching, explicit shadowing and collection composition are Yadinassi
regressions, not additional claims about the native object presentation.
"""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter


MODULE = '''
    Var Private, Value Export, Other Export, Unset Export, Items Export;
    Function Read() Export Return Value; EndFunction
    Procedure Write(Val next) Export Value = next; EndProcedure
    Function LocalShadow() Var Value; Value = 37; Return Value; EndFunction
    Function Hidden() Return Private; EndFunction
    Function PublicIdentity(Val receiver) Export Return receiver = ThisObject; EndFunction
    Function Defaults(Val first = "A", Val second = "B") Export
        Return first + second;
    EndFunction
    Procedure Alias(first, second) Export first = 23; Message(second); EndProcedure
    Function Copy(Val argument) Export argument = 41; Return argument; EndFunction
    Procedure Fail(argument) Export argument = 53; Raise "controlled"; EndProcedure
    Value = 11; Other = 17; Private = 19;
    Items = New Array; Items.Add(1);
'''


class ExportedModuleVariableTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def initialize(self, source=MODULE):
        self.vm.execute(source)

    def test_per_name_bilingual_exports_are_case_insensitive_and_unset_is_undefined(self):
        for declaration in ('Var Private, Value Export, Other Export, Unset Export;',
                            'Перем Private, Value Экспорт, Other Экспорт, Unset Экспорт;'):
            with self.subTest(declaration=declaration):
                vm = Interpreter(self.output.append)
                vm.execute(declaration + 'Private=19; Value=11; Other=17;')
                self.assertEqual(vm.execute('thisobject.vAlUe'), Decimal(11))
                self.assertEqual(vm.execute('ЭТОТОБЪЕКТ.oThEr'), Decimal(17))
                self.assertIsNone(vm.execute('ThisObject.Unset'))
                for code in ('ThisObject.Private', 'ThisObject.Private=59;'):
                    with self.assertRaisesRegex(BSLError, 'Поле объекта не обнаружено.*Private'):
                        vm.execute(code)
                self.assertEqual(vm.execute('Private'), Decimal(19))

    def test_initialization_exposes_identity_but_not_fields_or_exported_methods(self):
        self.initialize('''
            Var Value Export; Value = 11;
            Function Read() Export Return Value; EndFunction
            Message(ThisObject = ЭтотОбъект);
            Try Result = ThisObject.Value; Except Message("static-read-closed"); EndTry;
            Try ThisObject.Value = 31; Except Message("static-write-closed"); EndTry;
            Try Result = ThisObject.Read(); Except Message("static-call-closed"); EndTry;
            Try Execute("Result = ThisObject.Value;"); Except Message("execute-read-closed"); EndTry;
            Try Execute("ThisObject.Value = 31;"); Except Message("execute-write-closed"); EndTry;
            Try Execute("Result = ThisObject.Read();"); Except Message("execute-call-closed"); EndTry;
            Message(Value);
        ''')
        self.assertEqual(self.output, ['Да', 'static-read-closed', 'static-write-closed',
                                      'static-call-closed', 'execute-read-closed',
                                      'execute-write-closed', 'execute-call-closed', '11'])
        self.assertEqual(self.vm.execute('ThisObject.Read()'), Decimal(11))
        self.vm.execute('ThisObject.Value = 31;')
        self.assertEqual(self.vm.execute('ThisObject.Value'), Decimal(31))

    def test_failed_initialization_does_not_publish_but_successful_retry_does(self):
        with self.assertRaises(BSLError):
            self.initialize('Var Value Export; Value = 11; Raise "initialization failed";')
        with self.assertRaisesRegex(BSLError, 'Поле объекта не обнаружено'):
            self.vm.execute('ThisObject.Value')
        self.vm.execute('Value = 12;')
        self.assertEqual(self.vm.execute('ThisObject.Value'), Decimal(12))
        with self.assertRaises(BSLError):
            self.vm.execute('Raise "later failure";')
        self.assertEqual(self.vm.execute('ThisObject.Value'), Decimal(12))

    def test_internal_and_public_writes_share_storage_across_later_executions(self):
        self.initialize()
        self.vm.execute('ThisObject.Value = 31;')
        self.assertEqual(self.vm.execute('Read()'), Decimal(31))
        self.vm.execute('Write(43);')
        self.assertEqual(self.vm.execute('ЭтотОбъект.Value'), Decimal(43))
        self.vm.execute('Execute("ThisObject.Value = 61;");')
        self.assertEqual(self.vm.execute('Value'), Decimal(61))
        self.assertEqual(self.vm.execute('LocalShadow()'), Decimal(37))
        self.assertEqual(self.vm.execute('ThisObject.Read()'), Decimal(61))
        self.assertEqual(self.vm.execute('Private'), Decimal(19))

    def test_self_alias_and_exported_receiver_identity_are_stable(self):
        self.initialize()
        self.vm.execute('public = ThisObject;')
        self.assertTrue(self.vm.execute('(public = ЭтотОбъект)'))
        self.assertTrue(self.vm.execute('ThisObject.PublicIdentity(public)'))
        self.vm.execute('public.Value = 61;')
        self.assertEqual(self.vm.execute('ThisObject.Value'), Decimal(61))
        self.assertEqual(self.vm.execute('public.Read()'), Decimal(61))

    def test_unshadowed_self_names_are_read_only_and_parameter_rebinding_does_not_replace_them(self):
        self.initialize('Procedure Replace(argument) argument = 7; EndProcedure')
        for name in ('ThisObject', 'ЭтотОбъект'):
            for code in (f'{name} = 7;', f'Execute("{name} = 7;");'):
                with self.subTest(code=code), self.assertRaises(BSLError):
                    self.vm.execute(code)
                self.assertTrue(self.vm.execute('(ThisObject = ЭтотОбъект)'))
            self.vm.execute(f'Replace({name});')
            self.assertTrue(self.vm.execute('(ThisObject = ЭтотОбъект)'))

    def test_explicit_self_name_shadows_keep_ordinary_scope_rules(self):
        self.initialize('''
            Function ParameterShadow(Val ThisObject) Return ThisObject; EndFunction
            Function LocalShadow() Var ЭтотОбъект; ЭтотОбъект = 37; Return ЭтотОбъект; EndFunction
        ''')
        self.assertEqual(self.vm.execute('ParameterShadow(23)'), Decimal(23))
        self.assertEqual(self.vm.execute('LocalShadow()'), Decimal(37))
        self.assertTrue(self.vm.execute('(ThisObject = ЭтотОбъект)'))
        for name in ('ThisObject', 'ЭтотОбъект'):
            vm = Interpreter()
            vm.execute(f'Var {name}; {name} = 41;')
            self.assertEqual(vm.execute(name), Decimal(41))

    def test_exported_routine_defaults_and_receiver_evaluation_once(self):
        self.initialize(MODULE + '''
            Var calls; calls = 0;
            Function Receiver() calls = calls + 1; Return ThisObject; EndFunction
        ''')
        self.assertEqual(self.vm.execute('ThisObject.Defaults(, "Z")'), 'AZ')
        self.assertEqual(self.vm.execute('Receiver().Read()'), Decimal(11))
        self.assertEqual(self.vm.execute('calls'), Decimal(1))
        self.vm.execute('Receiver().Value = 31;')
        self.assertEqual(self.vm.execute('calls'), Decimal(2))
        self.assertEqual(self.vm.execute('ThisObject.Value'), Decimal(31))
        # Unknown factories with omitted arguments remain the existing bounded
        # host-call path; do not execute a factory to discover defaults.
        with self.assertRaises(BSLError):
            self.vm.execute('Receiver().Defaults(, "Z")')
        self.assertEqual(self.vm.execute('calls'), Decimal(2))

    def test_exported_properties_are_live_reference_aliases_and_val_snapshots(self):
        self.initialize()
        self.vm.execute('ThisObject.Alias(ThisObject.Value, ЭтотОбъект.Value);')
        self.assertEqual(self.output, ['23'])
        self.assertEqual(self.vm.execute('Value'), Decimal(23))
        self.vm.execute('Value = 11;')
        self.assertEqual(self.vm.execute('ThisObject.Copy(ThisObject.Value)'), Decimal(41))
        self.assertEqual(self.vm.execute('Value'), Decimal(11))
        with self.assertRaises(BSLError):
            self.vm.execute('ThisObject.Fail(ThisObject.Value);')
        self.assertEqual(self.vm.execute('Value'), Decimal(53))
        self.assertIsNone(self.vm.locals)

    def test_reference_receiver_once_forwarding_and_bidirectional_live_updates(self):
        self.initialize(MODULE + '''
            Var calls; calls = 0;
            Function Receiver() calls = calls + 1; Return ThisObject; EndFunction
            Procedure Live(slot)
                slot = 31; Message(ThisObject.Value);
                ThisObject.Value = 43; Message(slot);
            EndProcedure
            Procedure Forward(slot) Execute("Live(slot);"); EndProcedure
        ''')
        self.vm.execute('Forward(Receiver().Value);')
        self.assertEqual(self.output, ['31', '43'])
        self.assertEqual(self.vm.execute('calls'), Decimal(1))
        self.assertEqual(self.vm.execute('Value'), Decimal(43))

    def test_property_output_parameter_writes_exported_slot(self):
        self.initialize()
        self.vm.execute('source = New Structure("Found", 42);')
        self.assertTrue(self.vm.execute('source.Property("Found", ThisObject.Value)'))
        self.assertEqual(self.vm.execute('Value'), Decimal(42))
        self.assertFalse(self.vm.execute('source.Property("Absent", ThisObject.Value)'))
        self.assertIsNone(self.vm.execute('Value'))

    def test_shared_collection_and_nested_slot_references(self):
        self.initialize(MODULE + 'Procedure SetValue(slot) slot = 7; EndProcedure')
        self.vm.execute('alias = ThisObject.Items; alias.Add(2);')
        self.assertEqual(self.vm.execute('Items.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('ThisObject.Items[1]'), Decimal(2))
        self.vm.execute('SetValue(ThisObject.Items[0]);')
        self.assertEqual(self.vm.execute('Items[0]'), Decimal(7))

    def test_known_exported_table_and_list_properties_allow_existing_optional_slots(self):
        self.initialize('''
            Var Table Export, List Export;
            Table = New ValueTable; List = New ValueList;
        ''')
        self.vm.execute('''
            ThisObject.Table.Columns.Add("N", , "Title", 12);
            row = ThisObject.Table.Add(); row.N = 7;
            copy = ЭтотОбъект.Table.Copy(, "N");
            item = ThisObject.List.Add(23, , True);
        ''')
        self.assertEqual(self.vm.execute('ThisObject.Table.Columns[0].Title'), 'Title')
        self.assertEqual(self.vm.execute('copy[0].N'), Decimal(7))
        self.assertEqual(self.vm.execute('ThisObject.List[0].Value'), Decimal(23))
        self.assertTrue(self.vm.execute('ThisObject.List[0].Check'))

    def test_private_unknown_and_python_attributes_remain_closed_for_reads_writes_and_calls(self):
        self.initialize()
        for member in ('Private', 'Missing', 'interpreter', 'variables', 'routines',
                       'path', 'routine', 'exported_variables', 'ready', '__dict__', '__class__'):
            for code in (f'ThisObject.{member}', f'ThisObject.{member} = 99;',
                         f'ThisObject.{member}()'):
                with self.subTest(code=code), self.assertRaises(BSLError):
                    self.vm.execute(code)
        self.assertEqual(self.vm.execute('Private'), Decimal(19))
        self.assertEqual(self.vm.execute('Value'), Decimal(11))

    def test_properties_and_methods_are_separate_and_methods_are_not_values(self):
        self.initialize()
        for code in ('ThisObject.Value()', 'ThisObject.Read', 'ThisObject.Read = 99;',
                     'ThisObject.Hidden()', 'ThisObject["Value"]', 'ThisObject["Value"] = 99;',
                     'Message(ThisObject)', 'ValueToStringInternal(ThisObject)', 'TypeOf(ThisObject)'):
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('ThisObject.Read()'), Decimal(11))


class ImportedExportedVariableTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.write('Side.bsl', MODULE)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
        return path

    def execute(self, source, vm=None):
        return (vm or self.vm).execute(source, str(self.root / 'Main.bsl'))

    def test_import_is_ready_for_caller_and_uses_shared_internal_state(self):
        self.execute('// #Import Side.bsl\nMessage(Side.Value); Side.Value = 31; Message(Side.Read());')
        self.assertEqual(self.output, ['11', '31'])
        self.vm.execute('Side.Write(43);')
        self.assertEqual(self.vm.execute('Side.Value'), Decimal(43))
        self.assertIsNone(self.vm.execute('Side.Unset'))
        self.assertEqual(self.vm.execute('Side.Other'), Decimal(17))
        for code in ('Side.Private', 'Side.Private = 59;', 'Side.Hidden()', 'Side.interpreter',
                     'Side.Value()', 'Side.Read', 'Side.Read = 99;', 'Side', 'alias = Side'):
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_imported_self_alias_return_matches_external_fields(self):
        self.write('Side.bsl', MODULE + 'Function Identity() Export Return ThisObject; EndFunction')
        self.execute('// #Import Side.bsl\npublic = Side.Identity(); public.Value = 31;')
        self.assertEqual(self.vm.execute('Side.Value'), Decimal(31))
        self.assertTrue(self.vm.execute('Side.PublicIdentity(public)'))
        self.assertEqual(self.vm.execute('public.Read()'), Decimal(31))

    def test_imported_fields_bind_live_references_val_and_exception_writes(self):
        self.execute('// #Import Side.bsl\nSide.Alias(Side.Value, Side.Value);')
        self.assertEqual(self.output, ['23'])
        self.assertEqual(self.vm.execute('Side.Value'), Decimal(23))
        self.assertEqual(self.vm.execute('Side.Copy(Side.Value)'), Decimal(41))
        self.assertEqual(self.vm.execute('Side.Value'), Decimal(23))
        with self.assertRaises(BSLError):
            self.vm.execute('Side.Fail(Side.Value);')
        self.assertEqual(self.vm.execute('Side.Value'), Decimal(53))
        self.assertIsNone(self.vm.locals)

    def test_imported_initialization_self_access_is_closed_before_caller_readiness(self):
        self.write('Side.bsl', '''
            Var Value Export; Value = 11;
            Function Read() Export Return Value; EndFunction
            Try Message(ThisObject.Value); Except Message("field-closed"); EndTry;
            Try Execute("Message(ThisObject.Read());"); Except Message("method-closed"); EndTry;
        ''')
        self.execute('// #Import Side.bsl\nMessage(Side.Value); Message(Side.Read());')
        self.assertEqual(self.output, ['field-closed', 'method-closed', '11', '11'])

    def test_diamond_imports_share_one_initialization_and_exported_storage(self):
        self.write('Shared.bsl', '''
            Var Value Export; Value = 11; Message("init");
            Function Read() Export Return Value; EndFunction
        ''')
        for name in ('BranchA', 'BranchB'):
            self.write(name + '.bsl', '''// #Import Shared.bsl
                Procedure Write(Val value) Export Shared.Value = value; EndProcedure
                Function Read() Export Return Shared.Value; EndFunction
            ''')
        self.execute('// #Import BranchA.bsl\n// #Import BranchB.bsl\n// #Import Shared.bsl\n'
                     'BranchA.Write(31); Message(BranchB.Read()); Message(Shared.Value);')
        self.assertEqual(self.output, ['init', '31', '31'])
        self.write('Shared.bsl', '@ invalid changed file')
        self.execute('// #Import Shared.bsl\nShared.Value = 43; Message(BranchA.Read());')
        self.assertEqual(self.output, ['init', '31', '31', '43'])

    def test_root_interpreters_have_independent_exported_module_state(self):
        second = Interpreter(self.output.append)
        for vm in (self.vm, second):
            self.execute('// #Import Side.bsl\n', vm)
        self.vm.execute('Side.Value = 31;')
        self.assertEqual(second.execute('Side.Value'), Decimal(11))
        self.assertEqual(self.vm.execute('Side.Value'), Decimal(31))
        self.assertIsNot(self.vm.execute('ThisObject'), second.execute('ThisObject'))

    def test_directory_exports_and_nested_collections_preserve_namespace_boundary(self):
        self.write('Package/Side.bsl', MODULE)
        self.execute('// #Import Package\nPackage.Side.Value = 31; '
                     'Package.Side.Items.Add(2); Package.Side.Items[0] = 7;')
        self.assertEqual(self.vm.execute('Package.Side.Read()'), Decimal(31))
        self.assertEqual(self.vm.execute('Package.Side.Items.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('Package.Side.Items[0]'), Decimal(7))
        for code in ('Package', 'Package.Side', 'Package.members', 'Package.Side.path',
                     'Package.Side.Private', 'Package.Unknown.Value', 'Package.Side.Items.__dict__'):
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_imported_table_and_list_optional_arguments_use_real_field_storage(self):
        self.write('Package/Collections.bsl', '''
            Var Table Export, List Export;
            Table = New ValueTable; List = New ValueList;
        ''')
        self.execute('// #Import Package\n'
                     'Package.Collections.Table.Columns.Add("N", , "Title"); '
                     'row = Package.Collections.Table.Add(); row.N = 7; '
                     'copy = Package.Collections.Table.Copy(, "N"); '
                     'Package.Collections.List.Add(23, , True);')
        self.assertEqual(self.vm.execute('copy[0].N'), Decimal(7))
        self.assertEqual(self.vm.execute('Package.Collections.List[0].Value'), Decimal(23))
        self.assertTrue(self.vm.execute('Package.Collections.List[0].Check'))


if __name__ == '__main__':
    unittest.main()
