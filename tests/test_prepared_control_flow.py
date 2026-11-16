"""Legacy mutable indexes and default snapshot control-flow versions."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.runtime import _CONTROL_FLOW_PLANS
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse, prepare_control_flow, PreparedBlock


class PreparedControlFlowTests(unittest.TestCase):
    # Tests inspecting _prepared_control_flow or live-origin invalidation select
    # the legacy oracle explicitly. Generic async/server paths keep the default.
    def vm(self, code='', *, backend=None):
        output=[]
        vm=Interpreter(output.append, execution_backend=backend)
        self.addCleanup(vm.close)
        if code:vm.execute(code)
        return vm,output

    def test_thousand_calls_build_once_and_indexes_are_read_only(self):
        vm,_=self.vm('Function P(Val X) Goto ~Done; Return 0; ~Done: Return X; EndFunction', backend='interpreter')
        with patch('yadinassi.runtime.prepare_control_flow',wraps=prepare_control_flow) as build:
            self.assertEqual(vm.execute('For I=1 To 1000 Do R=P(I);EndDo;R'),Decimal(1000))
            self.assertEqual(build.call_count,1)
        plan=vm.routines['p']._prepared_control_flow
        self.assertIs(type(plan),PreparedBlock)
        with self.assertRaises(TypeError):plan.labels['done']=0
        with self.assertRaises(AttributeError):plan.statements=()

    def test_label_and_goto_renames_revalidated_before_argument(self):
        for index in (0,1):
            vm,output=self.vm('Procedure P(Val X) Goto ~Done; ~Done: EndProcedure', backend='interpreter')
            vm.execute('P(0)')
            vm.routines['p'].body[index].name='Other'
            with self.subTest(index=index),self.assertRaises(BSLError):vm.execute('P(Message("bad"))')
            self.assertEqual(output,[])

        vm,output=self.vm('Procedure P(Val X) Goto ~Done; ~Done: EndProcedure', backend='interpreter')
        vm.execute('P(0)')
        vm.routines['p'].body[1].__class__=ast.Name
        with self.assertRaises(BSLError):vm.execute('P(Message("bad"))')
        self.assertEqual(output,[])

    def test_append_and_replace_and_reorder_invalidate_plan(self):
        vm,_=self.vm('Function P() Return 1; EndFunction', backend='interpreter')
        self.assertEqual(vm.execute('P()'),Decimal(1));old=vm.routines['p']._prepared_control_flow
        vm.routines['p'].body[:]=parse('Function Q() Return 2; EndFunction')[0].body
        self.assertEqual(vm.execute('P()'),Decimal(2));self.assertIsNot(old,vm.routines['p']._prepared_control_flow)
        body=vm.routines['p'].body
        body.append(ast.Goto(body[0].token,'Missing'))
        with self.assertRaises(BSLError):vm.execute('P()')
        body[:]=parse('Function Q() Return 3;Return 4; EndFunction')[0].body
        self.assertEqual(vm.execute('P()'),Decimal(3))
        body.reverse()
        self.assertEqual(vm.execute('P()'),Decimal(4))

    def test_nested_mutation_cannot_jump_into_inactive_block(self):
        vm,output=self.vm('Procedure P(Val X) If True Then Goto ~Done; ~Done: EndIf; EndProcedure', backend='interpreter')
        vm.execute('P(0)')
        node=vm.routines['p'].body[0]
        node.otherwise.append(node.branches[0][1].pop())
        with self.assertRaises(BSLError):vm.execute('P(Message("bad"))')
        self.assertEqual(output,[])

    def test_host_callback_mutation_between_calls_is_revalidated(self):
        vm,output=self.vm('Procedure P(Val X) Goto ~Done; ~Done: EndProcedure', backend='interpreter')
        def mutate():vm.routines['p'].body[0].name='Missing'
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BSLError):vm.execute('P(0);Mutate();P(Message("bad"))')
        self.assertEqual(output,[])
        self.assertNotIn(_CONTROL_FLOW_PLANS,vm._scheduler.active_context.state)

    def test_argument_mutation_also_checked_before_body(self):
        vm,output=self.vm('Procedure P(Val X) Message("bad");Goto ~Done;~Done:EndProcedure', backend='interpreter')
        def mutate():vm.routines['p'].body[1].name='Missing'
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BSLError):vm.execute('P(Mutate())')
        self.assertEqual(output,[])

    def test_literal_payload_is_not_copied_compared_or_hashed(self):
        class Payload:
            def __eq__(self,other):raise AssertionError('equality')
            def __hash__(self):raise AssertionError('hash')
            def __deepcopy__(self,memo):raise AssertionError('copy')
        vm,_=self.vm('Function P() Return Undefined; EndFunction', backend='interpreter')
        value=Payload();vm.routines['p'].body[0].value.value=value
        self.assertIs(vm.execute('P()'),value)
        self.assertIs(vm.execute('P()'),value)

    def test_redeclaration_owns_new_plan(self):
        vm,_=self.vm('Function P() ~Done: Return 1; EndFunction', backend='interpreter')
        vm.execute('P()');old=vm.routines['p']._prepared_control_flow
        vm.execute('Function P() ~Done: Return 2; EndFunction')
        self.assertEqual(vm.execute('P()'),Decimal(2))
        self.assertIsNot(vm.routines['p']._prepared_control_flow,old)

    def test_nested_loop_and_outward_jump_reuse_plan(self):
        vm,_=self.vm('Function P() For I=1 To 10 Do If I=4 Then Goto ~Done;EndIf;EndDo;~Done: Return I;EndFunction', backend='interpreter')
        with patch('yadinassi.runtime.prepare_control_flow',wraps=prepare_control_flow) as build:
            self.assertEqual(vm.execute('P()'),Decimal(4))
            self.assertEqual(build.call_count,1)
        self.assertNotIn(_CONTROL_FLOW_PLANS,vm._scheduler.active_context.state)

    def test_async_suspension_has_task_local_plan(self):
        vm,output=self.vm('Async Function P(Val X) Await 0;Goto ~Done;Message("bad");~Done:Return X;EndFunction')
        vm.execute('A=P(1);B=P(2);')
        self.assertEqual(vm.variables['a'].result,Decimal(1))
        self.assertEqual(vm.variables['b'].result,Decimal(2))
        self.assertEqual(output,[])
        self.assertNotIn(_CONTROL_FLOW_PLANS,vm._scheduler.active_context.state)

    def test_server_activation_and_execute_keep_separate_indexes(self):
        vm,_=self.vm('&AtServer\nFunction P() Execute "Goto ~Done;~Done:";Goto ~Done;~Done:Return 7;EndFunction')
        self.assertEqual(vm.execute('P()'),Decimal(7))
        self.assertEqual(vm.execute('P()'),Decimal(7))
        self.assertNotIn(_CONTROL_FLOW_PLANS,vm._scheduler.active_context.state)

    def test_default_snapshot_freezes_control_flow_until_explicit_readmission(self):
        vm, output = self.vm()
        self.assertEqual(vm.execution_backend, 'compiled-strict')
        self.assertEqual(vm.compiled_ast_contract, 'snapshot')
        program = parse('Function P(Val X) Goto ~Done;Return 0;~Done:Return X;EndFunction')
        vm.execute_program(program)
        self.assertEqual(vm.execute('P(1)'), Decimal(1))
        # Origin mutation must not change the retained code, even when performed
        # by a host callback during argument evaluation.
        def mutate():
            program[0].body[0].name = 'Missing'
            return Decimal(2)
        vm.register_function('Mutate', mutate)
        self.assertEqual(vm.execute('P(Mutate())'), Decimal(2))
        self.assertEqual(output, [])
        program[0].body[:] = parse('Function Q(Val X) Return X+10;EndFunction')[0].body
        self.assertEqual(vm.execute('P(3)'), Decimal(3))
        vm.execute_program(program)  # Explicit quiescent admission: new version.
        self.assertEqual(vm.execute('P(3)'), Decimal(13))
        stats = vm.compiled_backend_stats
        self.assertEqual(stats['active_ast_contract'], 'snapshot')
        self.assertEqual(stats['interpreter_fallbacks'], 0)
        self.assertGreater(sum(stats[k] for k in
            ('emitted_executions', 'inline_blocks', 'inline_fragments')), 0)

    def test_iterative_match_rejects_empty_child_replacement_and_new_branch(self):
        body = parse('If True Then Else EndIf;')
        plan = prepare_control_flow(body)
        self.assertTrue(plan.matches(body))
        body[0].otherwise = []
        self.assertFalse(plan.matches(body))
        plan = prepare_control_flow(body)
        body[0].branches.append((body[0].branches[0][0], []))
        self.assertFalse(plan.matches(body))

    def test_matching_leaf_does_not_reenumerate_nonexistent_children(self):
        from yadinassi.syntax import parser
        body = parse('X=1;')
        plan = prepare_control_flow(body)
        with patch.object(parser, '_control_flow_children', side_effect=AssertionError('leaf traversal')):
            self.assertTrue(plan.matches(body))
        body[0] = parse('X=2;')[0]
        self.assertFalse(plan.matches(body))

    def test_matching_preserves_depth_first_container_read_order(self):
        from yadinassi.syntax import parser
        body = parse('If True Then While False Do EndDo; Else For I=1 To 1 Do EndDo; EndIf; Try Except EndTry;')
        plan = prepare_control_flow(body)
        expected = [body[0], body[0].branches[0][1][0], body[0].otherwise[0], body[1]]
        observed = []
        original = parser._control_flow_children
        def record(node):
            observed.append(node)
            return original(node)
        with patch.object(parser, '_control_flow_children', side_effect=record):
            self.assertTrue(plan.matches(body))
        self.assertEqual([id(node) for node in observed], [id(node) for node in expected])
