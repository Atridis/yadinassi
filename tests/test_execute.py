"""Execute native core and explicit local safety/generalization boundaries."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.parser import parse_fragment


class ExecuteTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()

    def test_aliases_and_existing_binding(self):
        for name in ('Выполнить', 'Execute', 'вЫпОлНиТь', 'eXeCuTe'):
            self.vm.execute(f'x = 5; {name}("x = x + 3;");')
            self.assertEqual(self.vm.execute('x'), Decimal(8))

    def test_new_names_disappear_after_success_and_error(self):
        for code in ('fresh = 37; saved = fresh;',
                     'fresh = 37; saved = fresh; Raise "stop";'):
            self.vm.execute('saved = 0;')
            self.vm.variables['code'] = code
            self.vm.execute('Try Execute(code); Except caught = True; EndTry;')
            self.assertEqual(self.vm.execute('saved'), Decimal(37))
            for text in ('fresh', 'Eval("fresh")', 'Execute("saved = fresh;");'):
                with self.assertRaises(BSLError):
                    self.vm.execute(text)
            self.assertIsNone(self.vm.locals)

    def test_nested_scope_is_live_but_new_names_do_not_escape(self):
        self.vm.execute('saved = 1; Execute("fresh = 7; Execute(""fresh = 8; nested = 9; saved = fresh;"");");')
        self.assertEqual(self.vm.execute('saved'), Decimal(8))
        for name in ('fresh', 'nested'):
            self.assertNotIn(name, self.vm.variables)

    def test_routine_local_module_and_reference_value_parameters(self):
        self.vm.execute('Var moduleValue; moduleValue = 23; '
                        'Procedure Touch(ref, Val copy) local = 7; '
                        'Execute("ref = ref + 2; copy = copy + 3; moduleValue = moduleValue + 4; local = 8;"); '
                        'ref = ref + local; EndProcedure; '
                        'a = 10; b = 20; Touch(a, b);')
        self.assertEqual(self.vm.execute('a'), Decimal(20))
        self.assertEqual(self.vm.execute('b'), Decimal(20))
        self.assertEqual(self.vm.execute('moduleValue'), Decimal(27))
        self.assertNotIn('local', self.vm.variables)

    def test_collection_mutations_and_existing_serialization(self):
        self.vm.execute('items = New Array(); target = New Structure("Имя", "old"); '
                        'Execute("items.Add(""Я😀""); target.Имя = items[0];"); '
                        'copy = ValueFromStringInternal(ValueToStringInternal(target)); '
                        'Execute("target.Имя = copy.Имя;");')
        self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')
        self.assertEqual(self.vm.execute('copy.Имя'), 'Я😀')
        self.assertEqual(self.vm.execute('items.Count()'), Decimal(1))

    def test_empty_undefined_and_exact_type_validation(self):
        for text in ('', ' ', '// comment'):
            self.vm.variables['code'] = text
            self.vm.execute('Execute(code);')
        self.vm.execute('Execute(Undefined);')
        for text in ('12', 'True', 'New Array()', 'New Structure()'):
            with self.assertRaises(BSLError):
                self.vm.execute(f'Execute({text});')
        class Hostile(str):
            def __str__(self):
                raise AssertionError('host conversion')
        self.vm.variables['code'] = Hostile('')
        with self.assertRaises(BSLError):
            self.vm.execute('Execute(code);')

    def test_whole_fragment_parsed_before_effects(self):
        for code in ('saved = 9; saved = ;', 'saved = 9; @',
                     'saved = 9; If True Then',
                     'saved = 9; Goto ~missing;'):
            self.vm.variables['code'] = code
            self.vm.execute('saved = 5; Try Execute(code); Except caught = True; EndTry;')
            self.assertTrue(self.vm.execute('caught'))
            self.assertEqual(self.vm.execute('saved'), Decimal(5))

    def test_runtime_error_retains_effects_and_recovers(self):
        self.vm.execute('saved = 5; Try Execute("saved = 9; saved = 1/0;"); '
                        'Except caught = True; EndTry; Execute("saved = saved + 1;");')
        self.assertTrue(self.vm.execute('caught'))
        self.assertEqual(self.vm.execute('saved'), Decimal(10))

    def test_declarations_and_directives_are_rejected_before_effects(self):
        for code in ('Var fresh; saved = 9;',
                     'Function f() Return 1; EndFunction saved = 9;',
                     'Procedure p() EndProcedure saved = 9;',
                     'If False Then Var fresh; EndIf; saved = 9;',
                     'saved = 9;\n// #Import hidden.bsl',
                     '#If Client Then\nsaved = 9;\n#EndIf',
                     '#Region Name\nsaved = 9;\n#EndRegion',
                     '&AtClient\nProcedure P() EndProcedure'):
            self.vm.variables['code'] = code
            self.vm.execute('saved = 5;')
            with self.assertRaises(BSLError):
                self.vm.execute('Execute(code);')
            self.assertEqual(self.vm.execute('saved'), Decimal(5))
            self.assertEqual(self.vm.imports, {})
            self.assertEqual(self.vm.routines, {})

    def test_no_python_execution_or_reflection(self):
        for code in ('import os', '__import__("os");',
                     'open("/tmp/unrequested-file", "w");',
                     'saved.__class__;'):
            self.vm.variables['code'] = code
            self.vm.execute('saved = 5;')
            with self.assertRaises(BSLError):
                self.vm.execute('Execute(code);')

    def test_outer_control_flow_does_not_cross_fragment(self):
        for code in ('Return;', 'Return 77;', 'Break;', 'Continue;',
                     'Goto ~outside;', 'Raise;'):
            self.vm.variables['code'] = code
            self.vm.execute('saved = 0; For i = 1 To 2 Do '
                            'Try Execute(code); Except saved = saved + 1; EndTry; '
                            'EndDo; ~outside: saved = saved + 10;')
            self.assertEqual(self.vm.execute('saved'), Decimal(12))

    def test_inner_loops_handlers_and_labels_use_existing_rules(self):
        self.vm.execute('saved = 0; Execute("For i = 1 To 4 Do '
                        'If i = 2 Then Continue; EndIf; '
                        'If i = 4 Then Break; EndIf; saved = saved + i; EndDo; '
                        'Try Raise ""inner""; Except saved = saved + 10; EndTry; '
                        'Goto ~done; saved = 99; ~done: saved = saved + 1;");')
        self.assertEqual(self.vm.execute('saved'), Decimal(15))

    def test_outer_error_not_rethrown_but_inner_rethrow_works(self):
        self.vm.execute('Try Raise "origin"; Except Try Execute("Raise;"); '
                        'Except same = Find(ErrorDescription(), "origin") > 0; EndTry; EndTry;')
        self.assertFalse(self.vm.execute('same'))
        self.vm.execute('Try Execute("Try Raise ""inner""; Except Raise; EndTry;"); '
                        'Except same = Find(ErrorDescription(), "inner") > 0; EndTry;')
        self.assertTrue(self.vm.execute('same'))

    def test_statement_only_arity_and_argument_once(self):
        self.vm.execute('Var count; count = 0; Function Code() count = count + 1; '
                        'Return "saved = 9;"; EndFunction; saved = 5; Execute(Code());')
        self.assertEqual(self.vm.execute('count'), Decimal(1))
        self.assertEqual(self.vm.execute('saved'), Decimal(9))
        for code in ('Execute();', 'Execute("", "");', 'Execute(,);',
                     'saved = Execute(Code());', 'Message(Execute(Code()));',
                     'Function Execute() EndFunction'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('count'), Decimal(1))

    def test_source_and_depth_limits_reset_after_failures(self):
        self.vm.variables['code'] = ' ' * 65536
        self.vm.execute('Execute(code);')
        self.vm.variables['code'] += ' '
        with self.assertRaisesRegex(BSLError, 'предел текста'):
            self.vm.execute('Execute(code);')
        self.vm.variables['code'] = 'Execute(code);'
        with self.assertRaisesRegex(BSLError, 'предел вложенности'):
            self.vm.execute('Execute(code);')
        self.assertEqual(self.vm._execute_depth[0], 0)
        self.assertIsNone(self.vm.locals)
        self.vm.execute('saved = 5; Execute("saved = 9;");')
        self.assertEqual(self.vm.execute('saved'), Decimal(9))

    def test_dynamic_error_source_location(self):
        self.vm.variables['code'] = 'saved = 9;\nsaved = 1/0;'
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('Execute(code);', 'outer.bsl')
        self.assertEqual(caught.exception.source, '<Выполнить>')
        self.assertEqual(caught.exception.line, 2)

    def test_imported_routine_has_own_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'helper.bsl').write_text('Var moduleValue; moduleValue = 3; '
                'Function Run(Val value) Export Execute("value = value + moduleValue;"); Return value; EndFunction;', encoding='utf-8')
            source = root/'main.bsl'
            self.vm.execute('// #Import helper.bsl\nresult = helper.Run(4);', str(source))
            self.assertEqual(self.vm.execute('result'), Decimal(7))
            self.assertEqual(self.vm._execute_depth[0], 0)
            self.assertNotIn('modulevalue', self.vm.variables)


class ExecuteMemberCompatibilityTests(unittest.TestCase):
    def test_existing_execute_named_structure_members_remain_accessible(self):
        vm = Interpreter()
        vm.execute('s = New Structure("Execute,Выполнить", 1, 2); '
                   's.Execute = s.Выполнить + 3; '
                   'Execute("s.Выполнить = s.Execute + 1;");')
        self.assertEqual(vm.execute('s.Execute'), Decimal(5))
        self.assertEqual(vm.execute('s.Выполнить'), Decimal(6))
