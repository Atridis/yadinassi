"""Labels, bounded outward jumps, and routine/module control-flow isolation.

Entering another block is an interpreter implementation gap. These tests do not
claim that native BSL prohibits inward or sibling-branch jumps.
"""

from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi import ast
from yadinassi.errors import BSLRuntimeError, IncompleteInput
from yadinassi.lexer import Lexer
from yadinassi.parser import parse


ROOT = Path(__file__).resolve().parents[1]
UNSUPPORTED_BLOCK = 'Переход внутрь другого блока пока не поддерживается'


class GotoTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_bilingual_mixed_case_keywords_and_labels(self):
        self.vm.execute('''
            пЕрЕйТи ~пРоДолЖеНиЕ;
            Сообщить("bad");
            ~Продолжение:
            Сообщить("русский");
            gOtO ~fInIsH;
            Message("bad");
            ~Finish:
            Message("english");
        ''')
        self.assertEqual(self.output, ['русский', 'english'])

    def test_labels_are_no_ops_without_variable_bindings(self):
        self.assertIsNone(self.vm.execute('~Unused: ~Another:;'))
        self.assertEqual(self.vm.variables, {})
        self.vm.execute('~Message: Message("done");')
        self.assertEqual(self.output, ['done'])
        with self.assertRaisesRegex(BSLError, 'не определена'):
            self.vm.execute('Unused')

    def test_forward_jump_skips_expressions_and_runtime_failures(self):
        self.vm.execute('''
            Message("before");
            Goto ~Done;
            Message("bad");
            Raise "unreachable";
            missing();
            x = 1 / 0;
            ~Done:
            Message("after");
        ''')
        self.assertEqual(self.output, ['before', 'after'])
        self.assertNotIn('x', self.vm.variables)

    def test_backward_jump_revisits_statements_with_current_state(self):
        self.vm.execute('''
            n = 0;
            ~Again:
            n = n + 1;
            Message(n);
            If n < 3 Then Goto ~Again; EndIf;
            Message("done");
        ''')
        self.assertEqual(self.output, ['1', '2', '3', 'done'])

    def test_many_backward_jumps_do_not_consume_python_call_stack(self):
        self.vm.execute('''
            n = 0;
            ~Again:
            n = n + 1;
            If n < 2000 Then Goto ~Again; EndIf;
            Message(n = 2000);
        ''')
        self.assertEqual(self.output, ['Да'])

    def test_multiple_labels_and_labels_at_end_of_each_scope(self):
        self.vm.execute('''
            Procedure P()
                Goto ~Last;
                Message("bad");
                ~Earlier: ~Last:
            EndProcedure
            Function F()
                Goto ~End;
                Return 99;
                ~End:
            EndFunction
            P(); Message(F() = Undefined);
            Goto ~Final;
            Message("bad");
            ~First: ~Middle:; ~Final:
        ''')
        self.assertEqual(self.output, ['Да'])

    def test_label_at_end_of_branch_and_loop_body(self):
        self.vm.execute('''
            If True Then Goto ~BranchEnd; Message("bad"); ~BranchEnd: EndIf;
            For i = 1 To 2 Do Goto ~IterationEnd; Message("bad"); ~IterationEnd: EndDo;
            Message(i);
        ''')
        self.assertEqual(self.output, ['3'])

    def test_label_identifier_namespace_is_separate_from_values_and_routines(self):
        self.vm.execute('''
            Var Done;
            Function Done() Return 42; EndFunction
            Done = 7;
            Goto ~Done;
            Done = 99;
            ~Done:
            Message(Done); Message(Done());
        ''')
        self.assertEqual(self.output, ['7', '42'])

    def test_same_label_name_in_module_and_distinct_routines(self):
        self.vm.execute('''
            Procedure P()
                Goto ~Done; Message("bad"); ~Done: Message("P");
            EndProcedure
            Function F()
                Goto ~Done; Return 0; ~Done: Return 42;
            EndFunction
            Goto ~Done; Message("bad");
            ~Done: P(); Message(F());
        ''')
        self.assertEqual(self.output, ['P', '42'])

    def test_recursive_routine_jumps_keep_invocation_local_frames(self):
        self.vm.execute('''
            Function Sum(Val n)
                result = n;
                Goto ~Recurse;
                Return -1;
                ~Recurse:
                If n > 0 Then result = result + Sum(n - 1); EndIf;
                Goto ~Done;
                result = -2;
                ~Done:
                Return result;
            EndFunction
            Message(Sum(4)); Message(Sum(2));
        ''')
        self.assertEqual(self.output, ['10', '3'])
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.variables, {})

    def test_jump_after_routine_call_cannot_resolve_in_callee(self):
        self.vm.execute('''
            Procedure P()
                ~Done: Message("callee");
            EndProcedure
            P(); Goto ~Done;
            Message("bad");
            ~Done: Message("caller");
        ''')
        self.assertEqual(self.output, ['callee', 'caller'])

    def test_jump_from_nested_if_to_ancestor_branch(self):
        self.vm.execute('''
            If True Then
                If True Then
                    If True Then Goto ~Outer; EndIf;
                    Message("bad");
                EndIf;
                Message("bad");
                ~Outer: Message("branch");
            EndIf;
            Message("module");
        ''')
        self.assertEqual(self.output, ['branch', 'module'])

    def test_same_list_jump_in_else_and_elsif(self):
        self.vm.execute('''
            If False Then Message("bad");
            ElsIf True Then
                Goto ~Selected; Message("bad"); ~Selected: Message("elsif");
            Else Message("bad"); EndIf;
            If False Then Message("bad");
            Else Goto ~Alternative; Message("bad"); ~Alternative: Message("else"); EndIf;
        ''')
        self.assertEqual(self.output, ['elsif', 'else'])

    def test_loop_local_backward_jump_does_not_increment_for_counter(self):
        self.vm.execute('''
            For i = 1 To 2 Do
                j = 0;
                ~Again:
                j = j + 1;
                Message("" + i + j);
                If j < 2 Then Goto ~Again; EndIf;
            EndDo;
            Message(i);
        ''')
        self.assertEqual(self.output, ['11', '12', '21', '22', '3'])

    def test_loop_local_jump_preserves_continue_and_break(self):
        self.vm.execute('''
            For i = 1 To 5 Do
                Goto ~Check;
                Message("bad");
                ~Check:
                If i = 2 Then Continue; EndIf;
                If i = 4 Then Break; EndIf;
                Message(i);
            EndDo;
            Message("end " + i);
        ''')
        self.assertEqual(self.output, ['1', '3', 'end 4'])

    def test_while_jump_to_body_end_rechecks_condition(self):
        self.vm.execute('''
            i = 0;
            While i < 3 Do
                i = i + 1;
                If i = 2 Then Goto ~Next; EndIf;
                Message(i);
                ~Next:
            EndDo;
            Message("end " + i);
        ''')
        self.assertEqual(self.output, ['1', '3', 'end 3'])

    def test_foreach_jump_to_body_end_advances_iterator_once(self):
        self.vm.execute('''
            values = New Array; values.Add(2); values.Add(4); values.Add(6);
            For Each value In values Do
                If value = 4 Then Goto ~Next; EndIf;
                Message(value);
                ~Next:
            EndDo;
            Message(value);
        ''')
        self.assertEqual(self.output, ['2', '6', '6'])

    def test_outward_jump_exits_all_loop_kinds_without_final_increment(self):
        cases = [
            ('For i = 1 To 3 Do', 'EndDo;', 'i'),
            ('i = 1; While i < 3 Do', 'EndDo;', 'i'),
            ('values = New Array; values.Add(1); values.Add(2); '
             'For Each i In values Do', 'EndDo;', 'i'),
        ]
        for opening, closing, variable in cases:
            with self.subTest(opening=opening):
                output = []
                vm = Interpreter(output=output.append)
                vm.execute(opening + ' Goto ~Done; Message("bad"); ' + closing +
                           ' Message("bad"); ~Done: Message(' + variable + ');')
                self.assertEqual(output, ['1'])

    def test_jump_exits_nested_loops_into_outer_loop_body(self):
        self.vm.execute('''
            For outer = 1 To 2 Do
                For inner = 1 To 3 Do
                    While True Do Goto ~NextOuter; EndDo;
                    Message("bad");
                EndDo;
                Message("bad");
                ~NextOuter:
                Message("" + outer + inner);
                Continue;
            EndDo;
            Message("done");
        ''')
        self.assertEqual(self.output, ['11', '21', 'done'])

    def test_jump_out_of_all_nested_loops_and_try_body_is_not_caught(self):
        self.vm.execute('''
            Try
                For i = 1 To 3 Do
                    While True Do
                        Try Goto ~Done; Except Message("bad inner handler"); EndTry;
                    EndDo;
                EndDo;
            Except Message("bad outer handler"); EndTry;
            Message("bad");
            ~Done: Message("done"); Message(ErrorDescription() = "");
        ''')
        self.assertEqual(self.output, ['done', 'Да'])

    def test_same_try_body_jump_does_not_run_handler(self):
        self.vm.execute('''
            Try
                Goto ~Safe;
                Raise "bad";
                ~Safe: Message("safe");
            Except Message("bad handler"); EndTry;
        ''')
        self.assertEqual(self.output, ['safe'])

    def test_same_handler_jump_preserves_description_and_bare_rethrow(self):
        error = BSLRuntimeError('original', 'original.bsl', 5, 9)

        def fail():
            raise error

        self.vm.register_function('Fail', fail)
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('''
                Try Fail();
                Except
                    saved = ErrorDescription();
                    Goto ~Rethrow;
                    Message("bad");
                    ~Rethrow:
                    Message(ErrorDescription() = saved);
                    Raise;
                EndTry;
            ''')
        self.assertIs(caught.exception, error)
        self.assertEqual(self.output, ['Да'])
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_jump_out_of_handler_unwinds_error_context(self):
        self.vm.execute('''
            Try Raise "caught";
            Except
                Message(ErrorDescription());
                Goto ~Done;
                Message("bad");
            EndTry;
            Message("bad");
            ~Done: Message(ErrorDescription() = "");
        ''', 'handler.bsl')
        self.assertTrue(self.output[0].endswith(': caught'))
        self.assertEqual(self.output[1:], ['Да'])
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_jump_out_of_try_body_retains_existing_outer_handler_error(self):
        error = BSLRuntimeError('outer', 'original.bsl', 7, 3)

        def fail():
            raise error

        self.vm.register_function('Fail', fail)
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('''
                Try Fail();
                Except
                    saved = ErrorDescription();
                    Try
                        While True Do Goto ~Rethrow; EndDo;
                    Except Message("bad"); EndTry;
                    ~Rethrow:
                    Message(ErrorDescription() = saved);
                    Raise;
                EndTry;
            ''')
        self.assertIs(caught.exception, error)
        self.assertEqual(self.output, ['Да'])
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_jump_out_of_nested_handler_does_not_revive_stale_outer_error(self):
        self.vm.execute('''
            Try Raise "outer";
            Except
                Try Raise "inner";
                Except Goto ~AfterInner; EndTry;
                Message("bad");
                ~AfterInner: Message(ErrorDescription() = "");
            EndTry;
            Message(ErrorDescription() = "");
        ''')
        self.assertEqual(self.output, ['Да', 'Да'])

    def test_jump_unwinds_multiple_handlers_then_allows_new_handler(self):
        self.vm.execute('''
            Try Raise "outer";
            Except
                Try Raise "inner";
                Except Goto ~Done; EndTry;
            EndTry;
            ~Done:
            Message(ErrorDescription() = "");
            Try Raise "fresh"; Except Message(ErrorDescription()); EndTry;
            Message(ErrorDescription() = "");
        ''')
        self.assertEqual(self.output[0], 'Да')
        self.assertTrue(self.output[1].endswith(': fresh'))
        self.assertEqual(self.output[2], 'Да')

    def test_routine_jump_out_of_handler_restores_callers_context_and_locals(self):
        self.vm.execute('''
            Function F()
                localOnly = 42;
                Try Raise "inner"; Except Goto ~Done; EndTry;
                ~Done: Return localOnly;
            EndFunction
            Try Raise "outer";
            Except Message(F()); Message(ErrorDescription() = ""); EndTry;
            Message(ErrorDescription() = "");
        ''')
        self.assertEqual(self.output, ['42', 'Да', 'Да'])
        self.assertIsNone(self.vm.locals)
        self.assertNotIn('localonly', self.vm.variables)

    def test_routine_jump_without_new_handler_preserves_callers_outer_error(self):
        self.vm.execute('''
            Function Describe()
                Try Goto ~Done; Except Message("bad"); EndTry;
                ~Done: Return ErrorDescription();
            EndFunction
            Try Raise "outer";
            Except
                saved = ErrorDescription();
                Message(Describe() = saved);
                Message(ErrorDescription() = saved);
            EndTry;
            Message(ErrorDescription() = "");
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да'])
        self.assertIsNone(self.vm.locals)

    def test_regions_do_not_create_label_scopes_or_jump_barriers(self):
        self.vm.execute('''
            #Region Before
            Goto ~Done;
            #EndRegion
            Message("bad");
            #Область После
            #Region Nested
            ~Done:
            Message("done");
            #EndRegion
            #КонецОбласти
        ''')
        self.assertEqual(self.output, ['done'])

    def test_preprocessor_ignores_inactive_labels_and_invalid_jumps(self):
        self.vm.execute('''
            #If Server Then
            ~Done: ~done:
            Goto ~Missing;
            ~123: invalid @
            #Else
            Goto ~Done;
            #EndIf
            Message("bad");
            ~Done: Message("done");
        ''')
        self.assertEqual(self.output, ['done'])

    def test_comments_and_strings_never_define_or_execute_labels(self):
        self.vm.execute('''
            // ~Done: Goto ~Missing;
            Message("Goto ~Missing; ~Done:");
            Goto ~Done;
            Message("bad");
            ~Done: Message("done");
        ''')
        self.assertEqual(self.output, ['Goto ~Missing; ~Done:', 'done'])

    def test_module_labels_do_not_persist_across_execute_calls(self):
        self.vm.execute('~Done: Message("first");', 'first.bsl')
        with self.assertRaisesRegex(BSLError, 'Метка не определена') as caught:
            self.vm.execute('Goto ~Done;', 'second.bsl')
        self.assertEqual(caught.exception.source, 'second.bsl')
        self.vm.execute('Goto ~Done; Message("bad"); ~Done: Message("second");')
        self.assertEqual(self.output, ['first', 'second'])

    def test_persisted_routines_keep_their_own_labels_between_execute_calls(self):
        self.vm.execute('''
            Function F()
                Goto ~Done; Return 0; ~Done: Return 42;
            EndFunction
        ''', 'definition.bsl')
        self.assertEqual(self.vm.execute('F()', 'caller.bsl'), Decimal(42))
        with self.assertRaisesRegex(BSLError, 'Метка не определена'):
            self.vm.execute('Goto ~Done;', 'caller.bsl')
        self.vm.execute('Function F() Goto ~Other; Return 0; ~Other: Return 7; EndFunction')
        self.assertEqual(self.vm.execute('F()'), Decimal(7))
        self.assertIsNone(self.vm.locals)


class GotoValidationTests(unittest.TestCase):
    def assert_rejected_before_effects(self, code, pattern=None):
        output = []
        vm = Interpreter(output=output.append)
        with self.assertRaises(BSLError) as caught:
            vm.execute('Message("bad");\n' + code, 'invalid.bsl')
        self.assertNotIsInstance(caught.exception, BSLRuntimeError)
        if pattern is not None:
            self.assertRegex(caught.exception.message, pattern)
        self.assertEqual(output, [])
        return caught.exception

    def test_ast_and_lexer_preserve_names_aliases_and_source_positions(self):
        code = '\ufeff  ~Ёж_2:\r\n  пЕрЕйТи ~ёЖ_2;'
        tokens = Lexer(code, 'labels.bsl').tokens()
        self.assertEqual([token.kind for token in tokens],
                         ['~', 'IDENT', ':', 'GOTO', '~', 'IDENT', ';', 'EOF'])
        label, jump = parse(code, 'labels.bsl')
        self.assertIsInstance(label, ast.Label)
        self.assertIsInstance(jump, ast.Goto)
        self.assertEqual((label.name, jump.name), ('Ёж_2', 'ёЖ_2'))
        self.assertEqual((label.token.source, label.token.line, label.token.column),
                         ('labels.bsl', 1, 3))
        self.assertEqual((jump.token.source, jump.token.line, jump.token.column),
                         ('labels.bsl', 2, 3))

    def test_unicode_underscore_and_alphanumeric_identifiers(self):
        for name in ['_', '_Again2', 'Метка42', 'Ёж', '中文']:
            with self.subTest(name=name):
                vm = Interpreter()
                self.assertEqual(vm.execute(f'Goto ~{name}; 1 / 0; ~{name}: 42'), Decimal(42))

    def test_duplicate_labels_are_case_insensitive_and_source_aware(self):
        with self.assertRaisesRegex(BSLError, 'Повторное объявление метки') as caught:
            parse('~Ёж:\n  ~ёЖ:', 'duplicate.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line,
                          caught.exception.column), ('duplicate.bsl', 2, 3))

    def test_duplicates_are_rejected_across_every_nested_statement_list(self):
        cases = [
            '~Same: ~sAME:',
            '~Same: If False Then ~same: EndIf;',
            'If True Then ~Same: Else ~same: EndIf;',
            'If True Then ~Same: ElsIf False Then ~same: EndIf;',
            '~Same: While False Do ~same: EndDo;',
            '~Same: For i = 2 To 1 Do ~same: EndDo;',
            '~Same: For Each i In New Array Do ~same: EndDo;',
            'Try ~Same: Except ~same: EndTry;',
            'If False Then While False Do ~Same: EndDo; EndIf; ~same:',
            'Function F() ~Same: Return 1; ~same: EndFunction',
            '#Region A\n~Same:\n#EndRegion\n#Region B\n~same:\n#EndRegion',
        ]
        for code in cases:
            with self.subTest(code=code):
                self.assert_rejected_before_effects(code, 'Повторное объявление метки')

    def test_undefined_jumps_are_rejected_even_in_unreachable_blocks(self):
        cases = [
            'Goto ~Missing;',
            'If False Then Goto ~Missing; EndIf;',
            'If True Then Else Goto ~Missing; EndIf;',
            'If True Then ElsIf False Then Goto ~Missing; EndIf;',
            'While False Do Goto ~Missing; EndDo;',
            'For i = 2 To 1 Do Goto ~Missing; EndDo;',
            'For Each i In New Array Do Goto ~Missing; EndDo;',
            'Try Goto ~Missing; Except Message("bad"); EndTry;',
            'Try Except Goto ~Missing; EndTry;',
            'Procedure NeverCalled() Goto ~Missing; EndProcedure',
            'Function F() Return 1; Goto ~Missing; EndFunction',
            'Goto ~Done; Goto ~Missing; ~Done:',
        ]
        for code in cases:
            with self.subTest(code=code):
                self.assert_rejected_before_effects(code, 'Метка не определена')

    def test_missing_target_reports_jump_location_and_is_not_incomplete_input(self):
        with self.assertRaisesRegex(BSLError, 'Метка не определена: Missing') as caught:
            parse('\n  Goto ~Missing;', 'missing.bsl')
        self.assertNotIsInstance(caught.exception, IncompleteInput)
        self.assertEqual((caught.exception.source, caught.exception.line,
                          caught.exception.column), ('missing.bsl', 2, 3))

    def test_labels_cannot_resolve_across_module_or_routine_boundaries(self):
        cases = [
            '~Outside: Procedure P() Goto ~Outside; EndProcedure',
            'Procedure P() ~Inside: EndProcedure Goto ~Inside;',
            'Procedure P() ~Inside: EndProcedure Procedure Q() Goto ~Inside; EndProcedure',
            'Function F() Goto ~Outside; Return 1; EndFunction ~Outside:',
        ]
        for code in cases:
            with self.subTest(code=code):
                self.assert_rejected_before_effects(code, 'Метка не определена')

    def test_inward_jumps_are_explicit_implementation_gaps_before_effects(self):
        cases = [
            'Goto ~Inside; If True Then ~Inside: EndIf;',
            'Goto ~Inside; If False Then Else ~Inside: EndIf;',
            'Goto ~Inside; If False Then ElsIf True Then ~Inside: EndIf;',
            'Goto ~Inside; While False Do ~Inside: EndDo;',
            'Goto ~Inside; For i = 1 To 1 Do ~Inside: EndDo;',
            'Goto ~Inside; For Each i In New Array Do ~Inside: EndDo;',
            'Goto ~Inside; Try ~Inside: Except EndTry;',
            'Goto ~Inside; Try Except ~Inside: EndTry;',
            'Function F() Goto ~Inside; If True Then ~Inside: EndIf; EndFunction',
        ]
        for code in cases:
            with self.subTest(code=code):
                self.assert_rejected_before_effects(code, UNSUPPORTED_BLOCK)

    def test_sibling_block_jumps_are_explicit_implementation_gaps(self):
        cases = [
            'If True Then Goto ~Sibling; Else ~Sibling: EndIf;',
            'If False Then ~Sibling: Else Goto ~Sibling; EndIf;',
            'If True Then Goto ~Sibling; ElsIf False Then ~Sibling: EndIf;',
            'If False Then Goto ~Sibling; EndIf; If False Then ~Sibling: EndIf;',
            'While False Do Goto ~Sibling; EndDo; While False Do ~Sibling: EndDo;',
            'Try Goto ~Sibling; Except ~Sibling: EndTry;',
            'Try ~Sibling: Except Goto ~Sibling; EndTry;',
            'If True Then While False Do Goto ~Sibling; EndDo; '
            'While False Do ~Sibling: EndDo; EndIf;',
        ]
        for code in cases:
            with self.subTest(code=code):
                self.assert_rejected_before_effects(code, UNSUPPORTED_BLOCK)

    def test_unsupported_jump_is_diagnosed_at_jump_not_target(self):
        with self.assertRaisesRegex(BSLError, UNSUPPORTED_BLOCK) as caught:
            parse('If False Then\n  ~Inside:\nEndIf;\n    Goto ~Inside;', 'inward.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line,
                          caught.exception.column), ('inward.bsl', 4, 5))

    def test_inactive_target_does_not_satisfy_active_jump(self):
        self.assert_rejected_before_effects(
            'Goto ~Missing;\n#If Server Then\n~Missing:\n#EndIf', 'Метка не определена')

    def test_comments_and_strings_do_not_satisfy_undefined_targets(self):
        for code in ['// ~Missing:\nGoto ~Missing;',
                     'Message("~Missing:"); Goto ~Missing;']:
            with self.subTest(code=code):
                self.assert_rejected_before_effects(code, 'Метка не определена')

    def test_malformed_label_and_jump_syntax_fail_before_effects(self):
        cases = [
            '~123:', '~"Name":', '~Name.Other:', '~Name-Other:', '~Name():',
            '~Name = 1;', '~:;', '~~Name:', '~If:', '~Goto:', '~Перейти:',
            'Name:', 'Goto Name;', 'Goto ~123;', 'Goto ~"Name";', 'Goto ~;',
            'Goto ~~Name;', 'Goto ~Name.Other;', 'Goto ~Name();', 'Goto ~If;',
            'Goto ~Name:; ~Name:', 'x = ~Name; ~Name:',
        ]
        for code in cases:
            with self.subTest(code=code):
                self.assert_rejected_before_effects(code)

    def test_labels_do_not_remove_previous_statement_separator_requirement(self):
        for code in ['x = 1 ~Done:', 'Goto ~Done ~Done:',
                     'If True Then x = 1 ~Done: EndIf;',
                     'Procedure P() x = 1 ~Done: EndProcedure']:
            with self.subTest(code=code):
                self.assert_rejected_before_effects(code, "Ожидается ';'")

    def test_incomplete_label_and_jump_request_more_repl_input(self):
        for code in ['~', '~Name', 'Goto', 'Goto ~', 'Перейти ~',
                     'Procedure P() ~Name:', 'If True Then Goto ~Later;']:
            with self.subTest(code=code), self.assertRaises(IncompleteInput):
                parse(code)

    def test_failed_validation_does_not_register_declarations(self):
        vm = Interpreter()
        vm.execute('Function Stable() Return 7; EndFunction')
        with self.assertRaisesRegex(BSLError, 'Метка не определена'):
            vm.execute('Var newValue; Function Stable() Return 99; EndFunction Goto ~Missing;')
        self.assertEqual(vm.execute('Stable()'), Decimal(7))
        self.assertNotIn('newvalue', vm.variables)
        self.assertNotIn('newvalue', vm.module_names)

    def test_execute_program_revalidates_mutated_ast_before_effects(self):
        output = []
        vm = Interpreter(output=output.append)
        program = parse('Message("bad"); Goto ~Done; ~Done:', 'direct.bsl')
        program[1].name = 'Missing'
        with self.assertRaisesRegex(BSLError, 'Метка не определена'):
            vm.execute_program(program)
        self.assertEqual(output, [])

    def test_mutated_routine_cannot_leak_control_flow_into_callers_labels(self):
        output = []
        vm = Interpreter(output=output.append)
        vm.execute('Procedure P(Val ignored) Message("bad"); Goto ~Done; ~Done: EndProcedure')
        vm.routines['p'].body[1].name = 'Caller'
        with self.assertRaisesRegex(BSLError, 'Метка не определена'):
            vm.execute('P(Message("bad argument")); ~Caller: Message("bad caller");')
        self.assertEqual(output, [])
        self.assertIsNone(vm.locals)


class GotoImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.main = self.directory / 'Main.bsl'
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def write(self, name, code):
        path = self.directory / name
        path.write_text(code, encoding='utf-8')
        return path

    def execute(self, code):
        self.main.write_text(code, encoding='utf-8')
        return self.vm.execute(code, str(self.main))

    def test_same_labels_in_imports_module_initializers_and_exported_routines(self):
        self.write('Side.bsl', '''
            Goto ~Done; Message("bad"); ~Done: Message("side init");
            Function F() Export
                Goto ~Done; Return 0; ~Done: Return 42;
            EndFunction
        ''')
        self.write('Other.bsl', 'Goto ~Done; Message("bad"); ~Done: Message("other init");')
        self.execute('''// #Import Side.bsl
            // #Import Other.bsl
            Goto ~Done; Message("bad");
            ~Done: Message(Side.F()); Message("main");
        ''')
        self.assertEqual(self.output, ['side init', 'other init', '42', 'main'])
        self.assertEqual(self.vm.execute('Side.F()'), Decimal(42))
        with self.assertRaisesRegex(BSLError, 'Метка не определена'):
            self.vm.execute('Goto ~Done;')

    def test_imported_labels_are_not_visible_to_importing_module(self):
        self.write('Side.bsl', '~OnlySide: Message("bad init");')
        with self.assertRaisesRegex(BSLError, 'Метка не определена') as caught:
            self.execute('// #Import Side.bsl\nGoto ~OnlySide;')
        self.assertEqual(caught.exception.source, str(self.main))
        self.assertEqual(self.output, [])
        self.assertEqual(self.vm.imports, {})

    def test_imported_module_cannot_jump_to_importing_module_label(self):
        side = self.write('Side.bsl', 'Message("bad init");\nGoto ~OnlyMain;')
        with self.assertRaisesRegex(BSLError, 'Метка не определена') as caught:
            self.execute('// #Import Side.bsl\n~OnlyMain: Message("bad main");')
        self.assertEqual((caught.exception.source, caught.exception.line), (str(side), 2))
        self.assertEqual(self.output, [])
        self.assertNotIn('side', self.vm.imports)

    def test_imported_routine_cannot_jump_into_module_or_caller_routine(self):
        cases = [
            '~OnlyModule: Function F() Export Goto ~OnlyModule; EndFunction',
            'Function F() Export Goto ~OnlyCaller; EndFunction',
        ]
        for code in cases:
            with self.subTest(code=code):
                self.write('Side.bsl', code)
                with self.assertRaisesRegex(BSLError, 'Метка не определена'):
                    self.execute('// #Import Side.bsl\n'
                                 'Function Caller() ~OnlyCaller: Return Side.F(); EndFunction')
                self.assertNotIn('side', self.vm.imports)
        self.assertEqual(self.output, [])

    def test_invalid_import_can_be_corrected_and_retried_without_stale_targets(self):
        self.write('Side.bsl', 'Message("bad"); Goto ~Missing;')
        with self.assertRaisesRegex(BSLError, 'Метка не определена'):
            self.execute('// #Import Side.bsl\n')
        self.write('Side.bsl', 'Goto ~Done; Message("bad"); ~Done: Message("fixed");')
        self.execute('// #Import Side.bsl\nMessage("main");')
        self.assertEqual(self.output, ['fixed', 'main'])
        self.assertIn('side', self.vm.imports)

    def test_recursive_imported_routine_and_caller_use_independent_labels(self):
        self.write('Side.bsl', '''
            Function Sum(Val n) Export
                result = n;
                If n > 0 Then result = result + Sum(n - 1); EndIf;
                Goto ~Done; Return -1; ~Done: Return result;
            EndFunction
        ''')
        self.execute('''// #Import Side.bsl
            Function Caller(Val n)
                result = Side.Sum(n);
                Goto ~Done; Return -2; ~Done: Return result + 1;
            EndFunction
            Message(Caller(4)); Message(Caller(2));
        ''')
        self.assertEqual(self.output, ['11', '4'])
        self.assertIsNone(self.vm.locals)

    def test_imported_handler_jump_clears_shared_dynamic_error_context(self):
        self.write('Side.bsl', '''
            Function F() Export
                Try Raise "inner"; Except Goto ~Done; EndTry;
                ~Done: Return ErrorDescription();
            EndFunction
        ''')
        self.execute('''// #Import Side.bsl
            Try Raise "outer";
            Except Message(Side.F() = ""); Message(ErrorDescription() = ""); EndTry;
            Message(ErrorDescription() = "");
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да'])


class GotoCLITests(unittest.TestCase):
    def run_cli(self, *arguments, stdin=None):
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(
            filter(None, [str(ROOT), environment.get('PYTHONPATH')]))
        return subprocess.run([sys.executable, '-m', 'yadinassi', *arguments],
                              input=stdin, capture_output=True, encoding='utf-8',
                              cwd=ROOT, env=environment, timeout=10)

    def test_command_and_stdin_forward_jump_have_no_python_traceback(self):
        code = 'Перейти ~Done; Сообщить("bad"); ~Done: Сообщить("готово");'
        for arguments, stdin in [(('-c', code), None), (('-',), code)]:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments, stdin=stdin)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, 'готово\n', ''))

    def test_invalid_jump_has_clean_diagnostic_before_any_output(self):
        result = self.run_cli('-c', 'Message("bad"); Goto ~Missing;')
        self.assertEqual((result.returncode, result.stdout), (1, ''))
        self.assertIn('Метка не определена: Missing', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_repl_labels_do_not_leak_between_commands_and_recover_after_error(self):
        result = self.run_cli(stdin='~Done:\nGoto ~Done;\n'
                                   'Goto ~Done; Message("bad"); ~Done: Message("alive");\n/exit\n')
        self.assertEqual((result.returncode, result.stdout), (1, 'alive\n'))
        self.assertIn('Метка не определена: Done', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_multiline_repl_routine_resolves_forward_target_on_completion(self):
        result = self.run_cli(stdin='Function F()\nGoto ~Done;\nReturn 0;\n'
                                   '~Done:\nReturn 42;\nEndFunction\nF()\n/exit\n')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '42\n', ''))


if __name__ == '__main__':
    unittest.main()
