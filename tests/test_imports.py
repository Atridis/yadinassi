"""Sibling-file imports, export boundaries, and cross-module BSL calls."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi import ast
from yadinassi.parser import parse


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.output = []
        self.vm = Interpreter(output=self.output.append)
        self.main = self.directory / 'Основное.bsl'

    def write(self, name, code, encoding='utf-8'):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding=encoding)
        return path

    def execute(self, code, vm=None, path=None):
        path = path or self.main
        path.write_text(code, encoding='utf-8')
        return (vm or self.vm).execute(path.read_text(encoding='utf-8'), str(path))

    def test_russian_directive_and_qualified_exports_are_case_insensitive(self):
        self.write('Побочное.bsl', '''
            Функция Ответ(Знач число = 40) Экспорт Возврат число + 2; КонецФункции
            Процедура Печать(Знач текст) Экспорт Сообщить(текст); КонецПроцедуры
        ''')
        self.execute('  #иМпОрТ Побочное.bsl // комментарий\n'
                     'Сообщить(ПОБОЧНОЕ.оТвЕт()); побочное.ПЕЧАТЬ("готово");')
        self.assertEqual(self.output, ['42', 'готово'])
        with self.assertRaisesRegex(BSLError, 'не определена'):
            self.vm.execute('Ответ()')

    def test_directive_ast_preserves_filename_and_source_position(self):
        source = str(self.main)
        directive = parse('\n  # Импорт Побочное.bsl\n', source)[0]
        self.assertIsInstance(directive, ast.Import)
        self.assertEqual(directive.filename, 'Побочное.bsl')
        self.assertEqual((directive.token.source, directive.token.line, directive.token.column),
                         (source, 2, 3))

    def test_comments_and_strings_do_not_import(self):
        self.execute('// # Импорт Missing.bsl\nMessage("# Импорт Missing.bsl");')
        self.assertEqual(self.output, ['# Импорт Missing.bsl'])

    def test_import_initializes_before_statements_and_only_once(self):
        self.write('Side.bsl', 'Message("module"); Function F() Export Return 42; EndFunction')
        self.execute('Message("main");\n# Импорт Side.bsl\n'
                     '# Импорт Side.bsl\nMessage(Side.F());')
        self.assertEqual(self.output, ['module', 'main', '42'])

    def test_imported_module_uses_own_variables_and_private_routines(self):
        self.write('Side.bsl', '''
            Var counter; counter = 10;
            Function Helper() Return 2; EndFunction
            Function Next() Export counter = counter + Helper(); Return counter; EndFunction
        ''')
        self.execute('''# Импорт Side.bsl
            Var counter; counter = 100;
            Function Helper() Return 999; EndFunction
            Message(Side.Next()); Message(Side.Next()); Message(counter); Message(Helper());
        ''')
        self.assertEqual(self.output, ['12', '14', '100', '999'])
        self.assertNotIn('next', self.vm.routines)

    def test_imported_routine_cannot_read_caller_global_or_local(self):
        self.write('Side.bsl', 'Function Read() Export Return secret; EndFunction')
        self.execute('# Импорт Side.bsl\nVar secret; secret = 42;\n'
                     'Function Caller(Val secret) Return Side.Read(); EndFunction')
        for code in ['Side.Read()', 'Caller(7)']:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'не определена'):
                self.vm.execute(code)
        self.assertIsNone(self.vm.locals)

    def test_private_missing_and_python_members_are_never_exported(self):
        self.write('Side.bsl', '''
            Var value; value = 42;
            Function Private() Return value; EndFunction
            Function Public() Export Return Private(); EndFunction
        ''')
        self.execute('# Импорт Side.bsl\n')
        for member in ['Private', 'value', 'Missing', 'interpreter', 'routine',
                       'variables', 'routines', '__dict__', '__class__', '__str__']:
            with self.subTest(member=member), self.assertRaises(BSLError):
                self.vm.execute(f'Side.{member}()')
            with self.subTest(attribute=member), self.assertRaises(BSLError):
                self.vm.execute(f'Side.{member}')
        self.assertEqual(self.vm.execute('Side.Public()'), Decimal(42))

    def test_namespace_and_export_are_not_first_class_values(self):
        self.write('Side.bsl', 'Function F() Export Return 42; EndFunction')
        self.execute('# Импорт Side.bsl\n')
        for code in ['Side', 'alias = Side', 'Message(Side)', 'Side.F', 'alias = Side.F',
                     'Side[0]', 'Side()', 'Side.Other.F()', 'Side.F.__class__']:
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('((Side).F)()'), Decimal(42))

    def test_exported_procedures_cannot_be_used_as_values(self):
        self.write('Side.bsl', 'Procedure P() Export Message("body"); EndProcedure')
        self.execute('# Импорт Side.bsl\n')
        with self.assertRaisesRegex(BSLError, 'не возвращает значение'):
            self.vm.execute('Message(Side.P())')
        self.assertEqual(self.output, [])
        self.vm.execute('Side.P()')
        self.assertEqual(self.output, ['body'])

    def test_reference_value_defaults_and_skips_cross_module_boundary(self):
        self.write('Side.bsl', '''
            Procedure Change(reference, Val value) Export reference = 7; value = 8; EndProcedure
            Function Increment(x = 10) Export x = x + 1; Return x; EndFunction
            Function Join(Val a = "A", Val b, Val c = "C") Export
                Return String(a) + ":" + String(b) + ":" + String(c);
            EndFunction
        ''')
        self.execute('''# Импорт Side.bsl
            x = 1; y = 2; Side.Change(x, y); Message(x); Message(y);
            Message(Side.Increment()); Message(Side.Increment());
            Message(Side.Increment(x)); Message(x);
            Message(Side.Join(, "B")); Message(Side.Join(,, "Z"));
            Message(Side.Join(Undefined, "B"));
        ''')
        self.assertEqual(self.output, ['7', '2', '11', '11', '8', '8',
                                       'A:B:C', 'A::Z', ':B:C'])
        self.assertIsNone(self.vm.locals)

    def test_reference_aliases_and_value_snapshots_are_bound_in_caller_order(self):
        self.write('Side.bsl', '''
            Procedure Show(Val snapshot, reference, unused) Export
                Message(snapshot); Message(reference); reference = reference + 1;
            EndProcedure
            Procedure Alias(first, second) Export
                first = 20; Message(second); second = second + 1; Message(first);
            EndProcedure
        ''')
        self.execute('''# Импорт Side.bsl
            Var x; x = 1;
            Function Change() x = 9; Return 0; EndFunction
            Side.Show(x, x, Change()); Message(x); Side.Alias(x, x); Message(x);
        ''')
        self.assertEqual(self.output, ['1', '9', '10', '20', '21', '21'])

    def test_arguments_are_evaluated_in_caller_local_frame(self):
        self.write('Side.bsl', '''
            Var x; x = 100;
            Procedure Add(reference, Val value) Export reference = reference + value; EndProcedure
        ''')
        self.execute('''# Импорт Side.bsl
            x = 1;
            Function Caller(Val x) Side.Add(x, x + 1); Return x; EndFunction
            Message(Caller(7)); Message(x);
        ''')
        self.assertEqual(self.output, ['15', '1'])

    def test_forwarded_references_through_multiple_modules(self):
        self.write('Inner.bsl', 'Procedure Add(x) Export x = x + 1; EndProcedure')
        self.write('Outer.bsl', '''# Импорт Inner.bsl
            Procedure Forward(x, Val y) Export Inner.Add(x); Inner.Add(y); Message(y); EndProcedure
        ''')
        self.execute('# Импорт Outer.bsl\nx = 1; y = 4; '
                     'Outer.Forward(x, y); Message(x); Message(y);')
        self.assertEqual(self.output, ['5', '2', '4'])

    def test_complex_reference_restrictions_and_value_mutable_object_semantics(self):
        self.write('Side.bsl', '''
            Procedure Ref(x) Export x = 99; EndProcedure
            Function Value(Val x) Export Return x + 1; EndFunction
            Procedure Mutate(Val a) Export a.Add(7); a = New Array; a.Add(9); EndProcedure
        ''')
        self.execute('# Импорт Side.bsl\nx = 1; a = New Array; a.Add(3);')
        for code in ['Side.Ref((x))', 'Side.Ref(a[0])']:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'по ссылке пока'):
                self.vm.execute(code)
        self.vm.execute('Message(Side.Value((x))); Message(Side.Value(a[0])); '
                        'Side.Mutate(a); Message(a.Count()); Message(a[1]); Message(x);')
        self.assertEqual(self.output, ['2', '4', '2', '7', '1'])

    def test_imported_recursion_restores_module_frames(self):
        self.write('Side.bsl', '''
            Function Sum(Val n, Val total = 0) Export
                If n = 0 Then Return total; EndIf;
                Return Sum(n - 1, total + n);
            EndFunction
        ''')
        self.execute('# Импорт Side.bsl\nMessage(Side.Sum(3)); Message(Side.Sum(2));')
        self.assertEqual(self.output, ['6', '3'])
        self.assertIsNone(self.vm.locals)

    def test_arity_and_procedure_errors_precede_argument_or_body_effects(self):
        self.write('Side.bsl', 'Procedure P(a = 1, b) Export Message("body"); EndProcedure')
        self.execute('# Импорт Side.bsl\n')
        for code in ['Side.P(Message("argument"))', 'Side.P(1, 2, Message("argument"))',
                     'Message(Side.P(Message("argument"), 2))']:
            with self.subTest(code=code), self.assertRaises(BSLError) as caught:
                self.vm.execute(code, 'caller.bsl')
            self.assertEqual(caught.exception.source, 'caller.bsl')
            self.assertEqual(caught.exception.line, 1)
        self.assertEqual(self.output, [])

    def test_argument_errors_point_to_caller(self):
        self.write('Side.bsl', 'Function F(Val x) Export Return x; EndFunction')
        self.execute('# Импорт Side.bsl\n')
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('\nSide.F(1 / 0)', 'caller.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), ('caller.bsl', 2))

    def test_imported_runtime_errors_keep_source_and_reference_writes(self):
        side = self.write('Side.bsl', 'Procedure Fail(x) Export\nx = 7;\nx = 1 / 0;\nEndProcedure\n'
                          'Function Healthy() Export Return 42; EndFunction')
        self.execute('# Импорт Side.bsl\nx = 1;')
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('Side.Fail(x)', 'caller.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), (str(side), 3))
        self.assertEqual(self.vm.variables['x'], Decimal(7))
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.execute('Side.Healthy()'), Decimal(42))

    def test_imported_parse_and_initialization_errors_keep_source(self):
        for code, line in [('Message("unreached");\n@', 2), ('\nMessage(1 / 0);', 2)]:
            with self.subTest(code=code):
                vm = Interpreter(output=self.output.append)
                side = self.write('Side.bsl', code)
                with self.assertRaises(BSLError) as caught:
                    self.execute('# Импорт Side.bsl\n', vm=vm)
                self.assertEqual((caught.exception.source, caught.exception.line), (str(side), line))
        self.assertEqual(self.output, [])

    def test_missing_file_and_directory_errors_point_to_import(self):
        (self.directory / 'Directory.bsl').mkdir()
        for filename in ['Missing.bsl', 'Directory.bsl']:
            with self.subTest(filename=filename), self.assertRaises(BSLError) as caught:
                self.execute(f'\n  # Импорт {filename}\n')
            self.assertEqual((caught.exception.source, caught.exception.line,
                              caught.exception.column), (str(self.main), 2, 3))
            self.assertIn(filename, str(caught.exception))

    def test_cached_module_retains_state_across_execute_calls_and_file_changes(self):
        side = self.write('Side.bsl', '''
            Message("init"); Var count; count = 0;
            Function Next() Export count = count + 1; Return count; EndFunction
        ''')
        self.execute('# Импорт Side.bsl\nMessage(Side.Next());')
        side.write_text('@ invalid new source', encoding='utf-8')
        self.execute('# Импорт Side.bsl\nMessage(Side.Next());')
        self.assertEqual(self.output, ['init', '1', '2'])

    def test_cache_is_shared_by_transitive_and_direct_imports(self):
        self.write('Shared.bsl', '''
            Message("shared"); Var count; count = 0;
            Function Next() Export count = count + 1; Return count; EndFunction
        ''')
        for name in ['Left', 'Right']:
            self.write(f'{name}.bsl', '# Импорт Shared.bsl\n'
                       'Function Next() Export Return Shared.Next(); EndFunction')
        self.execute('# Импорт Left.bsl\n# Импорт Right.bsl\n# Импорт Shared.bsl\n'
                     'Message(Left.Next()); Message(Right.Next()); Message(Shared.Next());')
        self.assertEqual(self.output, ['shared', '1', '2', '3'])

    def test_each_interpreter_gets_independent_module_cache(self):
        self.write('Side.bsl', 'Message("init"); Var n; n = 0; '
                   'Function Next() Export n = n + 1; Return n; EndFunction')
        for vm in [self.vm, Interpreter(output=self.output.append)]:
            self.execute('# Импорт Side.bsl\nMessage(Side.Next());', vm=vm)
        self.assertEqual(self.output, ['init', '1', 'init', '1'])

    def test_failed_load_is_not_cached_and_can_be_retried(self):
        for failure in ['@', 'x = 1 / 0;']:
            with self.subTest(failure=failure):
                vm = Interpreter(output=self.output.append)
                self.write('Side.bsl', failure)
                with self.assertRaises(BSLError):
                    self.execute('# Импорт Side.bsl\n', vm=vm)
                self.write('Side.bsl', 'Function F() Export Return 42; EndFunction')
                self.assertEqual(self.execute('# Импорт Side.bsl\nSide.F()', vm=vm), Decimal(42))
        with self.assertRaises(BSLError):
            self.execute('# Импорт Later.bsl\n')
        self.write('Later.bsl', 'Function F() Export Return 7; EndFunction')
        self.assertEqual(self.execute('# Импорт Later.bsl\nLater.F()'), Decimal(7))

    def test_direct_and_transitive_cycles_have_source_aware_errors(self):
        cases = [
            ('# Импорт Основное.bsl\n', None, self.main, 1),
            ('# Импорт Side.bsl\n', '# Импорт Side.bsl\n', self.directory / 'Side.bsl', 1),
            ('# Импорт Side.bsl\n', '\n# Импорт Основное.bsl\n', self.directory / 'Side.bsl', 2),
        ]
        for main, side, error_source, line in cases:
            with self.subTest(main=main, side=side):
                vm = Interpreter(output=self.output.append)
                if side is not None:
                    self.write('Side.bsl', side)
                with self.assertRaisesRegex(BSLError, 'Циклический импорт') as caught:
                    self.execute(main, vm=vm)
                self.assertEqual((caught.exception.source, caught.exception.line),
                                 (str(error_source), line))
        self.assertEqual(self.output, [])

    def test_cycle_failure_does_not_leave_loading_state(self):
        self.write('Side.bsl', '# Импорт Other.bsl\n')
        other = self.write('Other.bsl', '# Импорт Side.bsl\n')
        with self.assertRaisesRegex(BSLError, 'Циклический импорт'):
            self.execute('# Импорт Side.bsl\n')
        other.write_text('Function F() Export Return 42; EndFunction', encoding='utf-8')
        self.write('Side.bsl', '# Импорт Other.bsl\n'
                   'Function F() Export Return Other.F(); EndFunction')
        self.assertEqual(self.execute('# Импорт Side.bsl\nSide.F()'), Decimal(42))

    def test_execute_program_tracks_main_file_for_cycle_detection(self):
        self.write('Side.bsl', '# Импорт Основное.bsl\n')
        self.write('Основное.bsl', '# Импорт Side.bsl\n')
        program = parse(self.main.read_text(encoding='utf-8'), str(self.main))
        with self.assertRaisesRegex(BSLError, 'Циклический импорт') as caught:
            self.vm.execute_program(program)
        self.assertEqual(caught.exception.source, str(self.directory / 'Side.bsl'))
        self.write('Side.bsl', 'Function F() Export Return 42; EndFunction')
        self.vm.execute_program(program)
        self.assertEqual(self.vm.execute('Side.F()'), Decimal(42))

    def test_nested_missing_import_points_to_its_importing_module(self):
        side = self.write('Side.bsl', '\n# Импорт Missing.bsl\n')
        with self.assertRaises(BSLError) as caught:
            self.execute('# Импорт Side.bsl\n')
        self.assertEqual((caught.exception.source, caught.exception.line), (str(side), 2))
        self.assertIn('Missing.bsl', str(caught.exception))

    def test_case_insensitive_extension_preserves_disk_filename(self):
        self.write('Side.BSL', 'Function F() Export Return 42; EndFunction')
        self.assertEqual(self.execute('# Импорт Side.BSL\nside.f()'), Decimal(42))

    def test_local_namespace_shadowing_preserves_host_omission_rejection(self):
        self.write('Side.bsl', 'Function F(x = 1, y = 2) Export Return x + y; EndFunction')
        self.execute('# Импорт Side.bsl\n'
                     'Procedure P(Val Side) Side.Add(Message("bad"),,1); EndProcedure\n'
                     'a = New Array;')
        with self.assertRaisesRegex(BSLError, 'Пропуск аргументов'):
            self.vm.execute('P(a)')
        self.assertEqual(self.output, [])
        self.assertEqual(self.vm.execute('Side.F(, 3)'), Decimal(4))

    def test_import_free_program_does_not_resolve_diagnostic_source_label(self):
        source = self.directory / 'Label.bsl'
        try:
            source.symlink_to(source.name)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks are not available on this host')
        self.vm.execute('Message(42)', str(source))
        self.assertEqual(self.output, ['42'])

    def test_import_needs_a_real_source_path(self):
        self.write('Side.bsl', 'Message("bad");')
        for source in ['<строка>', '<команда>', '<stdin>', '<консоль>']:
            with self.subTest(source=source), self.assertRaisesRegex(BSLError, 'путь исходного файла'):
                self.vm.execute('# Импорт Side.bsl\n', source)
        self.assertEqual(self.output, [])

    def test_unsupported_directive_forms_fail_before_statement_effects(self):
        directives = ['# Import Side.bsl', '# Импорт "Side.bsl"', '# Импорт Side',
                      '# Импорт Side.txt', '# Импорт Side.part.bsl', '# Импорт ./Side.bsl',
                      '# Импорт ../Side.bsl', '# Импорт folder/Side.bsl',
                      '# Импорт folder\\Side.bsl', '# Импорт /tmp/Side.bsl',
                      '# Импорт C:\\Side.bsl', '# Импорт Side-name.bsl',
                      '# Импорт Function.bsl', '# Импорт Если.bsl',
                      '# Импорт 1Side.bsl', '# Импорт Side.bsl;',
                      '# Импорт Side.bsl Other.bsl', '# Импорт', '# Использовать Side.bsl']
        for directive in directives:
            with self.subTest(directive=directive), self.assertRaises(BSLError):
                self.execute('Message("bad");\n' + directive + '\n')
        self.assertEqual(self.output, [])

    def test_directive_must_begin_line_and_be_at_module_level(self):
        programs = ['Message("bad"); # Импорт Side.bsl\n',
                    'If True Then\n# Импорт Side.bsl\nEndIf;',
                    'While False Do\n# Импорт Side.bsl\nEndDo;',
                    'Procedure P()\n# Импорт Side.bsl\nEndProcedure',
                    'Function F()\n# Импорт Side.bsl\nEndFunction']
        for program in programs:
            with self.subTest(program=program), self.assertRaises(BSLError):
                self.execute('Message("bad");\n' + program)
        self.assertEqual(self.output, [])

    def test_import_names_conflict_with_existing_globals_routines_and_builtins(self):
        self.write('Side.bsl', 'Message("bad");')
        for declaration in ['Side = 1;', 'Var Side;', 'Function Side() Return 1; EndFunction']:
            with self.subTest(declaration=declaration):
                vm = Interpreter(output=self.output.append)
                vm.execute(declaration)
                with self.assertRaisesRegex(BSLError, 'занято|конфликт'):
                    self.execute('# Импорт Side.bsl\n', vm=vm)
        self.write('Message.bsl', 'Message("bad");')
        with self.assertRaisesRegex(BSLError, 'занято|конфликт'):
            self.execute('# Импорт Message.bsl\n')
        self.assertEqual(self.output, [])

    def test_import_declaration_collisions_are_checked_before_initialization(self):
        self.write('Side.bsl', 'Message("bad");')
        for declaration in ['Var SIDE;', 'Function side() Return 1; EndFunction']:
            with self.subTest(declaration=declaration), self.assertRaisesRegex(BSLError, 'конфликт'):
                self.execute('# Импорт Side.bsl\n' + declaration)
        self.assertEqual(self.output, [])

    def test_root_import_is_read_only_but_local_names_can_shadow_it(self):
        self.write('Side.bsl', 'Function F() Export Return 42; EndFunction')
        self.execute('# Импорт Side.bsl\n')
        with self.assertRaisesRegex(BSLError, 'имени импорта'):
            self.vm.execute('Side = 7')
        self.vm.execute('''
            Function Local() Var Side; Side = 7; Return Side; EndFunction
            Function Parameter(Val Side) Return Side; EndFunction
            Message(Local()); Message(Parameter(8)); Message(Side.F());
        ''')
        self.assertEqual(self.output, ['7', '8', '42'])

    def test_root_block_cannot_declare_variable_over_import_namespace(self):
        self.write('Side.bsl', 'Function F() Export Return 42; EndFunction')
        self.execute('# Импорт Side.bsl\n')
        with self.assertRaises(BSLError):
            self.vm.execute('If True Then Var Side; EndIf;')
        self.assertEqual(self.vm.execute('Side.F()'), Decimal(42))
        with self.assertRaises(BSLError):
            self.vm.execute('Message(Side)')

    def test_same_namespace_cannot_rebind_to_another_directory(self):
        self.write('Side.bsl', 'Function F() Export Return 1; EndFunction')
        self.write('other/Side.bsl', 'Function F() Export Return 2; EndFunction')
        self.execute('# Импорт Side.bsl\n')
        with self.assertRaisesRegex(BSLError, 'другим модулем'):
            self.execute('# Импорт Side.bsl\n', path=self.directory / 'other/Main.bsl')
        self.assertEqual(self.vm.execute('Side.F()'), Decimal(1))

    def test_imported_utf8_bom_and_explicit_encoding(self):
        self.write('Side.bsl', 'Function F() Export Return "Привет"; EndFunction', 'utf-8-sig')
        self.assertEqual(self.execute('# Импорт Side.bsl\nSide.F()'), 'Привет')
        self.write('Legacy.bsl', 'Функция Ответ() Экспорт Возврат "Привет"; КонецФункции', 'cp1251')
        vm = Interpreter(output=self.output.append, encoding='cp1251')
        self.assertEqual(self.execute('# Импорт Legacy.bsl\nLegacy.Ответ()', vm=vm), 'Привет')

    def test_imported_decode_error_is_source_aware(self):
        self.write('Side.bsl', 'Сообщить("Привет")', 'cp1251')
        with self.assertRaises(BSLError) as caught:
            self.execute('\n# Импорт Side.bsl\n')
        self.assertEqual((caught.exception.source, caught.exception.line), (str(self.main), 2))
        self.assertIn('Side.bsl', str(caught.exception))

    def test_registered_host_functions_are_available_to_imported_module(self):
        self.vm.register_function('Double', lambda value: value * 2)
        self.write('Side.bsl', 'Function F() Export Return Double(21); EndFunction')
        self.assertEqual(self.execute('# Импорт Side.bsl\nSide.F()'), Decimal(42))


if __name__ == '__main__':
    unittest.main()
