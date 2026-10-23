"""Side-local module storage; target observations are in the captured fixture."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from yadinassi import Interpreter, BSLError
from yadinassi.parser import parse

class ModuleContextTests(unittest.TestCase):
    def setUp(self):
        self.messages=[]
        self.vm=Interpreter(self.messages.append)

    def test_bilingual_declarations_and_default_client(self):
        self.vm.execute('''&НаКлиенте
Перем C;
&НаСервере
Перем S;
Var DefaultClient;
&AtServer
Function Read() Return S; EndFunction
C=1; DefaultClient=2;
Message(Read()=Undefined); Message(C+DefaultClient);
''')
        self.assertEqual(self.messages,['Да','3'])
        self.assertNotIn('s',self.vm.variables)

    def test_captured_standalone_replay(self):
        p=Path(__file__).resolve().parents[1]/'integrational_tests/directive_probes/module_context_core.bsl'
        self.vm.execute(p.read_text(encoding='utf-8')+'\nRunModuleContextProbe();')
        expected=['{"N",10}','{"N",100}','{"N",111}','{"B",1}','{"N",100}',
                  '{"B",1}','{"N",100}','{"B",1}','{"N",11}']
        self.assertEqual([s.split(': ',1)[1] for s in self.messages],expected)

    def test_initializer_runs_before_formals_and_shares_nested_calls(self):
        self.vm.execute('''&AtServer
Var S;
&AtServer
Function Nested() S=S+1; Return S; EndFunction
&AtServer
Function Read(Val S) Return Nested()+S; EndFunction
#If AtServer Then
S=40;
S=Nested();
#EndIf
Message(Read(10)); Message(Read(10));
''')
        self.assertEqual(self.messages,['52','52'])

    def test_compound_and_else_elsif_selection(self):
        for guard in ('#If AtServer And Not AtClient Then',
                      '#If AtClient Then\n#Else',
                      '#If AtClient Then\n#ElsIf AtServer Then',
                      '#Если НаСервере И Не НаКлиенте Тогда'):
            with self.subTest(guard=guard):
                vm=Interpreter()
                vm.execute('&AtServer\nVar S;\n&AtServer\nFunction Read() Return S; EndFunction\n'+guard+'\nS=42;\n#EndIf')
                self.assertEqual(vm.execute('Read()'),Decimal(42))

    def test_excluded_nested_branch_has_no_effect(self):
        self.vm.execute('''&AtServer
Var S;
&AtServer
Function Read() Return S; EndFunction
#If AtServer Then
S=1;
#If AtClient Then
S=99;
#Else
S=S+1;
#EndIf
#EndIf
Message(Read());
''')
        self.assertEqual(self.messages,['2'])

    def test_unguarded_and_generic_server_root_not_replayed(self):
        self.vm.execute('''&AtServer
Var S;
&AtServer
Function Read() Return S; EndFunction
Message("once");
#If Server Then
this deliberately invalid ! ignored root
#EndIf
#If AtServer Then
S=42;
#EndIf
Message(Read());Message(Read());
''')
        self.assertEqual(self.messages,['once','42','42'])

    def test_initializer_failure_has_fresh_next_activation(self):
        calls=[]
        def fail_once():
            calls.append(1)
            if len(calls)==1: raise ValueError('init failure')
        self.vm.register_function('FailOnce',fail_once)
        self.vm.execute('''&AtServer
Var S;
&AtServer
Function Read() Return S; EndFunction
#If AtServer Then
If S<>Undefined Then Raise "retained state"; EndIf;
S=42; FailOnce();
#EndIf
Try Read(); Except Message("caught"); EndTry;
Message(Read());
''')
        self.assertEqual(self.messages,['caught','42'])
        self.assertEqual(self.vm.execution_context,'client')

    def test_initialization_failure_does_not_copyback(self):
        self.vm.execute('''&AtServer
Var S;
&AtServer
Procedure Change(X) X=99; EndProcedure
#If AtServer Then
Raise "init failure";
#EndIf
X=1; Try Change(X); Except EndTry; Message(X);
''')
        self.assertEqual(self.messages,['1'])

    def test_side_local_names_do_not_leak(self):
        self.vm.execute('''&AtClient
Var C;
&AtServer
Var S;
&AtServer
Function ReadClient() Return C; EndFunction
C=42;
Try ReadClient(); Except Message("server denied"); EndTry;
Try Message(S); Except Message("client denied"); EndTry;
''')
        self.assertEqual(self.messages,['server denied','client denied'])

    def test_imported_module_owner_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source='''&AtServer
Var S;
&AtServer
Function Read() Export S=S+1;Return S;EndFunction
#If AtServer Then
S=40;
#EndIf
'''
            for name in ('A','B'):(root/(name+'.bsl')).write_text(source,encoding='utf-8')
            self.vm.execute('// #Import A.bsl\n// #Import B.bsl\nMessage(A.Read());Message(B.Read());Message(A.Read());',str(root/'Main.bsl'))
        self.assertEqual(self.messages,['41','41','41'])

    def test_server_imports_never_loaded(self):
        for source in ('#If AtServer Then\n// #Import Missing.bsl\n#EndIf',
                       '#If AtClient Then\n#Else\n// #Import Missing.bsl\n#EndIf',
                       '#If Server Then\n// #Import Missing.bsl\n#EndIf'):
            with self.subTest(source=source), mock.patch.object(
                    self.vm, '_load_module', side_effect=AssertionError('must not load')) as load:
                self.vm.execute(source+'\n42')
                load.assert_not_called()
        self.assertFalse(self.vm.imports)
        self.assertFalse(self.vm._module_cache)
        with self.assertRaises(BSLError):
            parse('&AtServer\nFunction Read()\n// #Import Missing.bsl\nEndFunction')

    def test_unsupported_declarations_fail_before_effects(self):
        for source in ('&AtServer\nVar S Export;', '&AtServerNoContext\nVar S;',
                       'Procedure P()\n&AtServer\nVar S;\nEndProcedure',
                       '#If AtServer Then\nVar S;\n#EndIf'):
            with self.subTest(source=source),self.assertRaises(BSLError):
                self.vm.execute('Message("must not run");\n'+source)
        self.assertEqual(self.messages,[])

    def test_nested_annotations_not_promoted(self):
        for annotation in ('','&AtClient\n'):
            with self.subTest(annotation=annotation):
                self.vm.execute('#If Server Then\n'+annotation+'Procedure C()\n&AtServer\nVar Hidden;\nEndProcedure\n#EndIf')
                self.assertNotIn('hidden',self.vm.server_module_names)

    def test_nested_preprocessor_inside_runtime_if_and_loop(self):
        self.vm.execute('''&AtServer
Var S;
&AtServer
Function Read() Return S; EndFunction
#If AtServer Then
S=0;
If True Then
#If AtClient Then
Raise "excluded";
#Else
S=3;
#EndIf
EndIf;
While S<5 Do
#If AtClient Or Not AtServer Then
Raise "excluded";
#ElsIf AtServer And Not AtClient Then
S=S+1;
#EndIf
EndDo;
#EndIf
Message(Read());
''')
        self.assertEqual(self.messages,['5'])

    def test_initializer_error_retains_original_source_position(self):
        source='''&AtServer
Var S;
&AtServer
Function Read() Return S; EndFunction
#If AtServer Then
If True Then
#If AtClient Then
S=999;
#Else
Raise "position";
#EndIf
EndIf;
#EndIf
Read();'''
        with self.assertRaises(BSLError) as caught:self.vm.execute(source,'module-position.bsl')
        self.assertEqual((caught.exception.source,caught.exception.line),('module-position.bsl',10))
