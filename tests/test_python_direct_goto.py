"""Lexical Goto lowering with no interpreter or runtime label table."""
import ast
from contextlib import closing
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.syntax.parser import parse


class DirectGotoTests(unittest.TestCase):
    def run_code(self, code):
        output=[]
        with closing(Interpreter(output=output.append)) as vm:
            prepared=vm.prepare(code)
            result=vm.execute_prepared(prepared)
            return result,dict(vm.variables),output,prepared._plan.generated_source

    def test_unused_labels_and_empty_body(self):
        self.assertEqual(self.run_code('~Unused: ~Other:;')[1],{})
        self.assertEqual(self.run_code('Function F() ~unused: Return 7; EndFunction r=F();')[1]['r'],7)

    def test_forward_skip_no_effects_or_unbound_publication(self):
        _,state,out,source=self.run_code('Message("before"); Goto ~Done; x=1/0; Message("bad"); ~Done: Message("after");')
        self.assertEqual(out,['before','after']);self.assertNotIn('x',state)
        self.assertNotIn('while ',source)

    def test_last_expression_returns_value(self):
        self.assertEqual(self.run_code('Goto ~Done; x=1; ~Done: 17;')[0],17)

    def test_casefold_and_chained_forward_jumps(self):
        self.assertEqual(self.run_code('Goto ~a; r=0; ~A: Goto ~Б; r=1; ~б: r=2;')[1]['r'],2)

    def test_backward_cycle_return_and_flat_python(self):
        code='Function F() n=0; ~again: n=n+1; If n=2000 Then Return n; EndIf; Goto ~again; EndFunction r=F();'
        _,state,_,source=self.run_code(code)
        self.assertEqual(state['r'],2000)
        tree=ast.parse(source)
        self.assertEqual(sum(isinstance(n,ast.While) for n in ast.walk(tree)),1)
        self.assertNotIn('_visit',source);self.assertNotIn('_Goto',source)
        self.assertNotIn('_pc',source)

    def test_non_source_order_prefix(self):
        code='Function F() Goto ~last; ~first: Return n; ~last: n=9; Goto ~first; EndFunction r=F();'
        self.assertEqual(self.run_code(code)[1]['r'],9)

    def test_forward_skip_does_not_establish_assignment(self):
        with self.assertRaises(BSLError):self.run_code('Goto ~Done; missing=1; ~Done: missing;')
        with self.assertRaises((BSLError,NameError)):self.run_code('Function F() Goto ~Done; missing=1; ~Done: Return missing; EndFunction F();')

    def test_forward_skipped_var_does_not_hide_later_declaration(self):
        self.assertIsNone(self.run_code('Function F() Goto ~Done; Var x; ~Done: Var x; Return x; EndFunction r=F();')[1]['r'])

    def test_local_forward_jump_inside_real_loop_retains_continue(self):
        code='s=0; For i=1 To 4 Do Goto ~local; s=99; ~local: s=s+i; Continue; EndDo;'
        self.assertEqual(self.run_code(code)[1]['s'],10)

    def test_cycle_can_have_nested_real_loop_break(self):
        code='Function F() n=0; ~again: For i=1 To 4 Do Break; EndDo; n=n+1; If n=2 Then Return i+n; EndIf; Goto ~again; EndFunction r=F();'
        self.assertEqual(self.run_code(code)[1]['r'],3)

    def test_local_try_handler_jumps(self):
        code='Try Goto ~body; Raise "bad"; ~body: Raise "expected"; Except Goto ~handler; Message("bad"); ~handler: Message(ErrorDescription()); EndTry;'
        self.assertTrue(self.run_code(code)[2][0].endswith('expected'))

    def test_cycle_preserves_changes_before_error(self):
        output=[]
        with closing(Interpreter(output=output.append)) as vm:
            with self.assertRaises(BSLError):vm.execute('n=0; ~again: n=n+1; Message(n); If n=3 Then Raise "stop"; EndIf; Goto ~again;')
            self.assertEqual(vm.variables['n'],3);self.assertEqual(output,['1','2','3'])

    def test_outward_dispatch_keeps_the_real_loop_and_handler_controls(self):
        code='''
        s=0;
        For i=1 To 5 Do
            Try
                While True Do Goto ~in_loop; EndDo;
            Except Raise "jump was caught"; EndTry;
            s=1000;
            ~in_loop:
            If i=2 Then Continue; EndIf;
            If i=4 Then Break; EndIf;
            s=s+i;
        EndDo;
        '''
        _,state,_,source=self.run_code(code)
        self.assertEqual((state['s'],state['i']),(4,4))
        self.assertIn('_GotoTransfer',source)
        self.assertNotIn('_visit',source)
        self.assertNotIn('_context._check',source)
        self.assertNotIn('_context.checkpoint',source)

    def test_outward_dispatch_works_in_the_source_audit_lane(self):
        with closing(Interpreter()) as vm:
            code='n=0; ~again: n=n+1; If n<3 Then Goto ~again; EndIf; n;'
            # The only source rendering is diagnostic; its output is never
            # reparsed or executed, even on the outward-jump route.
            with patch('ast.unparse',return_value='not executable Python'):
                prepared=vm.prepare(code)
                self.assertEqual(prepared._plan.generated_source,'not executable Python')
            self.assertEqual((vm.execute_prepared(prepared),vm.variables['n']),(3,3))

    def test_outward_dispatch_only_repeats_the_target_segment(self):
        code=('Function F() prefix=1; n=0; ~again: n=n+1; '
              'If n<2000 Then Goto ~again; EndIf; Return prefix+n; EndFunction r=F();')
        self.assertEqual(self.run_code(code)[1]['r'],2001)

    def test_nested_dispatch_preserves_continue_target(self):
        code=('s=0; For i=1 To 3 Do If False Then Goto ~outer; EndIf; '
              'If True Then If True Then Goto ~inner; EndIf; ~inner: Continue; EndIf; '
              '~outer: s=100; EndDo;')
        self.assertEqual({k:v for k,v in self.run_code(code)[1].items() if k in ('s','i')},
                         {'s':0,'i':4})

    def test_same_list_chain_with_outward_jump_keeps_skip_semantics(self):
        _,state,out,_=self.run_code('x=0; If True Then Goto ~local; x=78; '
                                   '~local: Goto ~done; x=99; EndIf; '
                                   'x=10; ~done: x=x+1; Message(x);')
        self.assertEqual((state['x'],out),(1,['1']))

    def test_inactive_list_targets_still_fail_before_effects(self):
        for body in ('Goto ~inside; If False Then ~inside: EndIf;',
                     'If True Then Goto ~sibling; Else ~sibling: EndIf;'):
            output=[]
            with self.subTest(body=body),closing(Interpreter(output=output.append)) as vm:
                with self.assertRaisesRegex(BSLError,'Переход внутрь другого блока'):
                    vm.execute('Message("bad"); '+body)
                self.assertEqual(output,[])

    def test_remaining_complex_transfers_rejected_before_effects(self):
        for body in ['While True Do ~again: Break; Goto ~again; EndDo;',
                     'While True Do ~again: Continue; Goto ~again; EndDo;',
                     'Function F() ~again: Var x; Goto ~again; EndFunction',
                     'Function F() If True Then Goto ~out; EndIf; Var n; ~out: Return n; EndFunction']:
            with self.subTest(body=body):
                output=[]
                with closing(Interpreter(output=output.append)) as vm:
                    with self.assertRaises(PythonDirectUnsupported):vm.execute('Message("bad"); '+body)
                self.assertEqual(output,[])

    def test_mutated_ast_revalidated_before_effects(self):
        program=parse('Message("bad"); Goto ~Done; ~Done:')
        program[1].name='Missing';output=[]
        with closing(Interpreter(output=output.append)) as vm:
            with self.assertRaisesRegex(BSLError,'Метка не определена'):vm.execute_program(program)
        self.assertEqual(output,[])

    def test_aliased_host_ast_jump_cannot_cross_routine_ownership(self):
        program=parse('Procedure P() If True Then Goto ~out; EndIf; ~out: EndProcedure '
                      'Procedure Q() If True Then Goto ~out; EndIf; ~out: EndProcedure '
                      'Message("before"); P();')
        first=program[0].body[0].branches[0][1]
        program[1].body[0].branches[0][1][0]=first[0]
        output=[]
        with closing(Interpreter(output=output.append)) as vm:
            with self.assertRaisesRegex(PythonDirectUnsupported,'distinct AST nodes'):
                vm.execute_program(program)
        self.assertEqual(output,[])

    def test_self_jump_compiles_without_recursion(self):
        with closing(Interpreter()) as vm:
            source=vm.prepare('~Forever: Goto ~Forever;')._plan.generated_source
        self.assertIn('while True:',source)
        self.assertNotIn('_Goto',source)

    def test_type_facts_follow_execution_order_not_source_order(self):
        code='Goto ~setup; ~use: r=StrLen(x); Goto ~done; ~setup: x="abcd"; Goto ~use; ~done:'
        self.assertEqual(self.run_code(code)[1]['r'],4)

    def test_uninitialized_routine_shadow_cycle_explicitly_unsupported(self):
        with self.assertRaisesRegex(PythonDirectUnsupported,'routine shadow'):
            self.run_code('Function F() ~again: x=F; F=1; Goto ~again; EndFunction')

    def test_ordinary_program_has_no_extra_loop(self):
        with patch('yadinassi.execution.codegen.rules.direct_goto.plan',side_effect=AssertionError('unexpected Goto preflight')):
            source=self.run_code('x=1; x=x+2;')[3]
        self.assertFalse(any(isinstance(n,(ast.While,ast.Match)) for n in ast.walk(ast.parse(source))))
        self.assertNotIn('_GotoTransfer',source)


if __name__=='__main__':unittest.main()
