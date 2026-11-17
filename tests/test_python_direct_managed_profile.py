"""Managed compilation symbols are independent of direct runtime-side support."""
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.syntax.parser import parse
import test_python_direct_database as database_fixture

ROOT=Path(__file__).resolve().parents[1]
PROFILE='managed-thick-file'


def client_mask():
    source='&AtClient\nFunction Mask()\nN=0;\n'
    for flag,weight in (('Client',1),('Server',2),('AtClient',4),('AtServer',8),('ThickClientManagedApplication',128)):
        source+=f'#If {flag} Then\nN=N+{weight};\n#EndIf\n'
    return source+'Return N;EndFunction\nR=Mask();'


class DirectManagedProfileTests(unittest.TestCase):
    def test_client_native_mask_in_source_ast_and_prepared_routes(self):
        for profile,expected in (('standalone',5),(PROFILE,135)):
            for route in ('source','ast','prepared'):
                with self.subTest(profile=profile,route=route):
                    vm=Interpreter(compilation_profile=profile)
                    with patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
                        if route=='source':vm.execute(client_mask())
                        elif route=='ast':vm.execute_program(parse(client_mask(),compilation_profile=profile))
                        else:vm.execute_prepared(vm.prepare(client_mask()))
                    self.assertEqual(vm.variables['r'],expected)
                    self.assertEqual(vm.execution_context,'client')

    def test_prepared_profile_cannot_be_rebound(self):
        for source_profile,destination in (('standalone',PROFILE),(PROFILE,'standalone')):
            plan=Interpreter(compilation_profile=source_profile).prepare(client_mask())
            vm=Interpreter(compilation_profile=destination)
            with self.assertRaisesRegex(PythonDirectUnsupported,'contract changed'):vm.execute_prepared(plan)
            self.assertEqual(vm.variables,{})

    def test_unsupported_runtime_sides_still_refuse_before_effects(self):
        for declaration in ('&AtServer\nVar State;',
                            '&AtServerNoContext\nFunction F() Return 1; EndFunction',
                            '&AtClientAtServerNoContext\nFunction F() Return 1; EndFunction'):
            vm=Interpreter(compilation_profile=PROFILE)
            with self.subTest(declaration=declaration),self.assertRaises(PythonDirectUnsupported):
                vm.execute('Effect=1;\n'+declaration)
            self.assertEqual(vm.variables,{})

    def test_invalid_profile_and_restricted_owner_remain_denied(self):
        for attribute,value in (('_compilation_profile','unknown'),('_configuration_runtime',object())):
            vm=Interpreter(compilation_profile=PROFILE);setattr(vm,attribute,value)
            with self.subTest(attribute=attribute),self.assertRaises(PythonDirectUnsupported):vm.execute_program(parse('Effect=1;',compilation_profile=PROFILE))
            self.assertEqual(vm.variables,{})

    def test_server_and_nocontext_entry_are_not_granted_by_profile(self):
        for stack,value in (('_module_context_stack',False),('_context_stack','server')):
            vm=Interpreter(compilation_profile=PROFILE);getattr(vm,stack)[-1]=value
            with self.subTest(stack=stack),self.assertRaises(PythonDirectUnsupported):vm.execute('Effect=1;')
            self.assertEqual(vm.variables,{})

    def test_original_dates_and_numbers_complete_under_managed_profile(self):
        for name,count in (('dates',185),('numbers',427)):
            source=(ROOT/'integrational_tests/tests'/f'{name}.bsl').read_text()
            captures=[]
            for profile in ('standalone',PROFILE):
                output=[];vm=Interpreter(output.append,compilation_profile=profile);vm.execute(source)
                self.assertEqual(len(output),count);captures.append(output)
            self.assertEqual(*captures)

    def test_exact_whole_client_witness_exposes_nocontext_blocker(self):
        vm=Interpreter(compilation_profile=PROFILE)
        with self.assertRaisesRegex(PythonDirectUnsupported,'async/NoContext'):
            vm.execute((ROOT/'scripts/native_1c_bootstrap/client_probe.bsl').read_text())
        self.assertEqual(vm.variables,{})


class DirectManagedDatabaseTests(unittest.TestCase):
    setUp=database_fixture.DirectDatabaseTests.setUp

    def test_managed_profile_keeps_host_selected_sqlite_write_contract(self):
        vm=Interpreter(database_context=self.context,compilation_profile=PROFILE);self.addCleanup(vm.close)
        vm.execute('A=Catalogs.Склады.CreateItem(); A.Description="managed"; A.Write(); R=A.Ref.GetObject().Description;')
        self.assertEqual(vm.variables['r'],'managed')
        with self.assertRaises(BSLRuntimeError):vm.execute('BeginTransaction();')
