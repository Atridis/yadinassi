from compiled_contract_fixture import mutable_compiled_contract
"""Strict codegen tests: legacy visit dispatch is poisoned, not counted as coverage."""
from contextlib import ExitStack
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse



def execution_kinds(test, vm):
    """Keep actual Python translation evidence distinct from legacy tiers."""
    stats = vm.compiled_backend_stats
    if vm._compiled().FORCE_PYTHON_TRANSLATION:
        test.assertGreater(stats.get('python_translated_blocks', 0), 0)
        for name in ('emitted_executions', 'helper_executions', 'inline_blocks',
                     'inline_fragments', 'plain_adapter_blocks', 'interpreter_fallbacks'):
            test.assertEqual(stats.get(name, 0), 0, name)
        return stats.get('python_translated_node_kinds', {})
    return stats['node_kinds']


def registry_identity(engine):
    """Admission rollback must preserve every registry, not just node count."""
    registries = (engine._owned.memo, engine._owned.versions,
                  engine._origin_signatures, engine._origin_blocks,
                  engine._nodes, engine._blocks, engine._inline_ir,
                  engine._plain_routines, engine._plain_modules, engine._python_units)
    return tuple({key: id(value) for key, value in registry.items()}
                 for registry in registries)

class StrictCodegenTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        stats = patch.object(Engine, 'DETAILED_INLINE_STATS', True)
        stats.start(); self.addCleanup(stats.stop)

    def run_strict(self, source, source_name='<strict-test>', vm=None):
        output = []
        if vm is None:
            vm = Interpreter(execution_backend='compiled-strict', output=output.append)
        def forbidden(*args, **kwargs):
            raise AssertionError('legacy visitor entered in strict compiled execution')
        with ExitStack() as guards:
            for name in tuple(Interpreter.__dict__):
                if name.startswith('visit_'):
                    guards.enter_context(patch.object(Interpreter, name, forbidden))
            vm.execute(source, source_name)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)
        return vm, output

    def test_scalar_control_and_mutable_counter(self):
        vm, _ = self.run_strict('''
            r=0; For i=1 To 10 Do
                i=i+1;
                If i=4 Then Continue; EndIf;
                If i=8 Then Break; EndIf;
                r=r+i*3-7;
            EndDo;
            While r<10 Do r=r+1; EndDo;
        ''')
        self.assertEqual(vm.variables['r'], Decimal(10))
        self.assertEqual(vm.variables['i'], Decimal(8))

    def test_lazy_logic_and_conditional(self):
        vm, _ = self.run_strict('a=False And Missing();b=True Or Missing();r=?(a,Missing(),7);')
        self.assertFalse(vm.variables['a']);self.assertTrue(vm.variables['b'])
        self.assertEqual(vm.variables['r'], Decimal(7))

    def test_sync_calls_aliases_defaults_return_and_cleanup(self):
        vm, _ = self.run_strict('''
            Function F(x, y, Val z=3)
                x=x+1;y=y+2; Return x+y+z;
            EndFunction
            n=1;r=F(n,n);
        ''')
        self.assertEqual(vm.variables['n'], Decimal(4))
        self.assertEqual(vm.variables['r'], Decimal(11))
        self.assertIsNone(vm.locals)

    def test_foreach_constructors_members_and_indexes(self):
        vm, _ = self.run_strict('''
            a=New Array;a.Add(2);a.Add(3);a[0]=4;
            r=0;For Each x In a Do r=r+x;EndDo;
            t=Type("Array");b=New (t);b.Add(r);
        ''')
        self.assertEqual(vm.variables['r'], Decimal(7))
        self.assertEqual(vm.variables['b'].items, [Decimal(7)])

    def test_try_raise_and_goto_lexical_unwind(self):
        vm, output = self.run_strict('''
            n=0;
            ~Again:
            n=n+1;
            Try
                If n<3 Then Goto ~Again; EndIf;
                Raise "x";
            Except
                Message(ErrorDescription());
            EndTry;
            r=n;
        ''')
        self.assertEqual(vm.variables['r'], Decimal(3))
        self.assertTrue(any('x' in value for value in output))
        self.assertEqual(vm._handled_errors, [])

    def test_async_suspension_and_fifo(self):
        vm, output = self.run_strict('''
            Async Function F(Val n)
                Message(n);r=Await n;Message(r+10);Return r;
            EndFunction
            p=F(1);q=F(2);
        ''')
        self.assertEqual(output, ['1','2','11','12'])
        self.assertEqual(vm.variables['p'].result, Decimal(1))
        self.assertEqual(vm.variables['q'].result, Decimal(2))
        self.assertIsNone(vm.locals)

    def test_dynamic_execute_and_eval(self):
        vm, _ = self.run_strict('r=0;Execute "For i=1 To 3 Do r=r+i;EndDo;";v=Eval("r*2");')
        self.assertEqual(vm.variables['r'], Decimal(6))
        self.assertEqual(vm.variables['v'], Decimal(12))

    def test_import_enters_strict_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'helper.bsl').write_text('Function F() Export Return 7;EndFunction', encoding='utf-8')
            vm, _ = self.run_strict('// #Import helper.bsl\nr=helper.F();',str(root/'main.bsl'))
            self.assertEqual(vm.variables['r'],Decimal(7))
            child=vm.imports['helper'].interpreter
            self.assertEqual(child.execution_backend,'compiled-strict')
            self.assertGreater(child.compiled_backend_stats['prepared_nodes'],0)

    def test_every_executable_node_kind_has_strict_execution_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'helper.bsl').write_text('Function F() Export Return 1;EndFunction',encoding='utf-8')
            source = '''// #Import helper.bsl
                Var total;total=0;
                Function Step(Val x=1) Return x;EndFunction
                Async Function A() Return Await 1;EndFunction
                p=A();a=New Array;a.Add(1);t=Type("Array");b=New (t);
                s=New Structure("k",2);r=s.k+a[0];
                r=(-r)+?(True,1,Missing());
                For i=1 To 2 Do
                    If i=1 Then Continue;Else Break;EndIf;
                EndDo;
                For Each x In a Do total=total+x;EndDo;
                While total<3 Do total=total+1;EndDo;
                Try Raise "x";Except total=total+1;EndTry;
                Execute "r=Eval(""1+2"");";
                Goto ~Done;r=99;
                ~Done:
                Message(Step());helper.F();
            '''
            vm,_=self.run_strict(source,str(root/'main.bsl'))
            executed={kind for kind, count in execution_kinds(self, vm).items() if count > 0}
            required={name for name,tier in Engine.lowering_inventory().items()
                      if tier!='syntax-only'}
            self.assertEqual(required-executed,set())
            self.assertEqual(len(required),29)

    def test_unsupported_unit_has_no_prior_effects(self):
        @dataclass
        class Unknown(ast.Node):
            pass
        nodes=parse('r=1;')
        nodes.append(Unknown(nodes[0].token))
        vm=Interpreter(execution_backend='compiled-strict')
        with self.assertRaises(CompiledUnsupported): vm.execute_program(nodes)
        self.assertNotIn('r',vm.variables)
        self.assertEqual(vm.compiled_backend_stats['rejected_units'],1)

    def test_unknown_dead_routine_body_rejected_before_module_effects(self):
        @dataclass
        class Unknown(ast.Node):
            pass
        nodes=parse('r=1;Procedure Never() EndProcedure')
        nodes[1].body.append(Unknown(nodes[1].token))
        vm=Interpreter(execution_backend='compiled-strict')
        with self.assertRaises(CompiledUnsupported):vm.execute_program(nodes)
        self.assertNotIn('r',vm.variables)

    def test_missing_adapter_is_explicit_and_pre_effect(self):
        vm=Interpreter(execution_backend='compiled-strict')
        vm.semantic_new=None
        with self.assertRaises(CompiledUnsupported) as failure:
            vm.execute('r=1;a=New Array;')
        self.assertIn('semantic_new',failure.exception.reason)
        self.assertNotIn('r',vm.variables)

    def test_inventory_separates_declaration_and_execution(self):
        inventory=Engine.lowering_inventory()
        self.assertEqual(inventory['Await'],'emitted')
        self.assertEqual(inventory['Call'],'semantic-helper')
        self.assertEqual(inventory['Parameter'],'syntax-only')
        vm,_=self.run_strict('r=1;r=r+2;')
        observed = execution_kinds(self, vm)
        self.assertNotIn('Await', observed)
        self.assertGreater(observed.get('Assign', 0), 0)
        self.assertGreater(observed.get('Binary', 0), 0)
        if not vm._compiled().FORCE_PYTHON_TRANSLATION:
            self.assertGreater(vm.compiled_backend_stats['emitted_executions'],0)
            self.assertGreater(vm.compiled_backend_stats['helper_executions'],0)

    @mutable_compiled_contract
    def test_known_mutation_is_not_late_preflight(self):
        vm=Interpreter(execution_backend='compiled-strict')
        nodes=parse('r=1;')
        engine=Engine(vm);engine.prepare(nodes)
        self.assertTrue(engine.has_node(nodes[0]));self.assertTrue(engine.has_block(nodes))
        nodes[0].value=ast.Literal(nodes[0].token,Decimal(2))
        with self.assertRaises(CompiledUnsupported):next(engine.run_node(nodes[0]))
        self.assertTrue(engine.has_node(nodes[0]))

    @mutable_compiled_contract
    def test_block_mutation_between_statements_rejected(self):
        vm=Interpreter(execution_backend='compiled-strict')
        nodes=parse('For i=1 To 1 Do Change();r=1;EndDo;')
        def change(): nodes[0].body.append(parse('r=2;')[0])
        vm.register_function('Change',change)
        with self.assertRaises(CompiledUnsupported): vm.execute_program(nodes)
        self.assertNotIn('r',vm.variables)
        self.assertGreater(vm.compiled_backend_stats['unsupported_executions'],0)

    def test_explicit_reprepare_accepts_new_program_version(self):
        vm=Interpreter(execution_backend='compiled-strict')
        nodes=parse('r=1;');vm.execute_program(nodes)
        nodes[0].value.value=Decimal(9)
        vm.execute_program(nodes)
        self.assertEqual(vm.variables['r'],Decimal(9))

    def test_syntax_only_nodes_not_counted_as_executed(self):
        vm=Interpreter(execution_backend='compiled-strict')
        program=parse('Function F(Val a=1) Return a;EndFunction')
        vm.execute_program(program)
        self.assertNotIn('Parameter',vm.compiled_backend_stats['node_kinds'])
        with self.assertRaises(CompiledUnsupported):next(vm._compiled().run_node(program[0].parameters[0]))

    @mutable_compiled_contract
    def test_signature_checks_do_not_invoke_host_metaclass_equality(self):
        class Meta(type):
            def __eq__(cls,other):
                raise AssertionError('host metaclass equality invoked')
            __hash__=type.__hash__
        class A(metaclass=Meta):pass
        class B(metaclass=Meta):pass
        vm=Interpreter(execution_backend='compiled-strict')
        node=parse('r=1;')[0].value;node.value=A()
        engine=Engine(vm);engine.prepare_node(node)
        node.value=B()
        with self.assertRaises(CompiledUnsupported):next(engine.run_node(node))

    def test_literal_opaque_cyclic_value_has_no_recursive_admission(self):
        vm=Interpreter(execution_backend='compiled-strict');nodes=parse('r=1;')
        cycle=[];cycle.append(cycle);nodes[0].value.value=cycle
        engine=Engine(vm);engine.prepare_node(nodes[0].value)
        with self.assertRaises(StopIteration) as done:
            next(engine.run_node(nodes[0].value))
        self.assertIs(done.exception.value,cycle)

class MetadataMutationTests(unittest.TestCase):
    @mutable_compiled_contract
    def test_unvisited_callee_metadata_cannot_redirect_routine(self):
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('Procedure Original() Mark();EndProcedure Procedure Hijack() Mark();EndProcedure Mutate();Original();')
        marks = []
        vm.register_function('Mark', lambda: marks.append('called'))
        def mutate():
            program[-1].expression.callee.name = 'Hijack'
        vm.register_function('Mutate', mutate)
        with self.assertRaises(CompiledUnsupported):
            vm.execute_program(program)
        self.assertEqual(marks, [])

    @mutable_compiled_contract
    def test_rhs_cannot_mutate_assignment_target_before_write(self):
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('target=Mutate();')
        def mutate():
            program[0].target.name = 'hijacked'
            return Decimal(42)
        vm.register_function('Mutate', mutate)
        with self.assertRaises(CompiledUnsupported):
            vm.execute_program(program)
        self.assertNotIn('target', vm.variables)
        self.assertNotIn('hijacked', vm.variables)

    @mutable_compiled_contract
    def test_late_unit_cannot_readmit_known_mutated_descendant(self):
        vm = Interpreter(execution_backend='compiled-strict')
        engine = vm._compiled()
        node = parse('r=1;')[0]
        engine.prepare_node(node.value)
        node.value.value = Decimal(99)
        with self.assertRaises(CompiledUnsupported):
            engine.prepare_node(node)

    @mutable_compiled_contract
    def test_parameter_metadata_is_part_of_routine_guard(self):
        vm = Interpreter(execution_backend='compiled-strict')
        engine = vm._compiled()
        routine = parse('Function F(Val x=1) Return x;EndFunction')[0]
        engine.prepare_node(routine)
        routine.parameters[0].name = 'renamed'
        with self.assertRaises(CompiledUnsupported):
            engine.ensure_node(routine)


class RegistryLifecycleTests(unittest.TestCase):
    def make(self):
        vm=Interpreter(execution_backend='compiled-strict')
        engine=Engine(vm);vm._compiled_engine=engine
        return vm,engine

    def test_prepare_node_does_not_retain_synthetic_block(self):
        vm,engine=self.make();node=parse('r=1;')[0].value
        engine.prepare_node(node)
        self.assertEqual(len(engine._nodes),1)
        self.assertEqual(engine._blocks,{})

    def test_release_preserves_counters_and_drops_literal_objects(self):
        import gc,weakref
        class Value:pass
        vm,engine=self.make();value=Value();reference=weakref.ref(value)
        node=parse('r=1;')[0].value;node.value=value
        engine.prepare_node(node)
        count=engine.stats['prepared_nodes']
        del node,value;gc.collect()
        self.assertIsNotNone(reference())
        engine.release();gc.collect()
        self.assertIsNone(reference())
        self.assertEqual(engine.stats['prepared_nodes'],count)
        self.assertEqual(engine._nodes,{})

    def test_suspended_node_blocks_release_until_completion(self):
        vm,engine=self.make();literal=parse('r=1;')[0].value
        node=ast.Await(literal.token,literal);engine.prepare_node(node)
        frame=engine.run_node(node)
        self.assertEqual(next(frame).value,Decimal(1))
        self.assertGreater(engine.active_frames,0)
        with self.assertRaises(RuntimeError):engine.release()
        with self.assertRaises(StopIteration) as complete:frame.send(Decimal(7))
        self.assertEqual(complete.exception.value,Decimal(7))
        self.assertEqual(engine.active_frames,0)
        engine.release();self.assertEqual(engine._nodes,{})

    def test_suspended_block_close_releases_active_counts(self):
        vm,engine=self.make();literal=parse('r=1;')[0].value
        node=ast.Await(literal.token,literal);body=[node];engine.prepare(body)
        frame=engine.run_block(body);next(frame)
        with self.assertRaises(RuntimeError):engine.release()
        frame.close()
        self.assertEqual(engine.active_frames,0)
        engine.release()

    def test_aggregate_limit_is_explicit_and_transactional(self):
        # The same cap includes generated operand bindings in the Python path.
        # Its earlier refusal is required, not a reason to raise the limit.
        for force in (False, True):
            with self.subTest(force=force), patch.object(Engine, 'FORCE_PYTHON_TRANSLATION', force):
                vm,engine=self.make();engine.MAX_REGISTRY_ENTRIES=3
                engine.prepare_node(parse('r=1;')[0].value)
                if not force:
                    engine.prepare_node(parse('r=2;')[0].value)
                before=registry_identity(engine)
                with self.assertRaises(CompiledUnsupported) as failure:
                    engine.prepare_node(parse('r=3;')[0].value)
                self.assertIn('generated operand binding budget' if force else 'aggregate',failure.exception.reason)
                self.assertEqual(registry_identity(engine),before)
                self.assertEqual(engine._blocks,{})
                self.assertEqual(vm.variables,{})
                engine.release()
                engine.prepare_node(parse('r=4;')[0].value)
                self.assertEqual(len(engine._nodes),1)

if __name__=='__main__':unittest.main()

class BlockRoleCompilationTests(unittest.TestCase):
    def admitted_block(self, engine, statements):
        # Inspect the existing admitted view only; never prepare/rebaseline here.
        view = engine._owned.existing(statements) if engine.OWNED_SNAPSHOT else statements
        self.assertIsNotNone(view)
        plan = engine._blocks[id(view)]
        self.assertIs(plan.statements, view)
        return plan

    @patch.object(Engine, "DETAILED_INLINE_STATS", True)
    def test_structural_lists_emit_but_argument_lists_share_entry(self):
        from yadinassi.compiled_backend import _METADATA_BLOCK_ENTRY
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        program=parse('Function F(Val x=1) If x=1 Then Return x;Else Return 2;EndIf;EndFunction r=F(1);s=F(2);')
        engine.prepare(program)
        routine=program[0]
        self.assertEqual(self.admitted_block(engine,program).role,'structural')
        self.assertEqual(self.admitted_block(engine,routine.body).role,'structural')
        self.assertEqual(self.admitted_block(engine,routine.body[0].branches[0][1]).role,'structural')
        self.assertEqual(self.admitted_block(engine,routine.body[0].otherwise).role,'structural')
        metadata=[plan for plan in engine._blocks.values() if plan.role=='metadata']
        self.assertGreaterEqual(len(metadata),3)
        if engine.FORCE_PYTHON_TRANSLATION:
            self.assertTrue(all(plan.function is None for plan in engine._blocks.values()))
            self.assertEqual(engine.stats['compiled_block_functions'], 0)
            self.assertGreater(len(engine._python_units), 0)
            vm.execute_program(program)
            self.assertEqual((vm.variables['r'], vm.variables['s']), (1, 2))
            self.assertGreater(execution_kinds(self, vm).get('Return', 0), 0)
        else:
            self.assertTrue(all(plan.function is _METADATA_BLOCK_ENTRY for plan in metadata))
            structural=sum(plan.role=='structural' for plan in engine._blocks.values())
            self.assertEqual(engine.stats['compiled_block_functions'],structural)

    def test_metadata_expression_lists_keep_explicit_block_compatibility(self):
        from unittest.mock import patch
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        call=parse('Unused(1+2,4+5);')[0].expression
        engine.prepare_node(call)
        self.assertEqual(self.admitted_block(engine,call.arguments).role,'metadata')
        with patch.object(Interpreter,'visit_Literal',side_effect=AssertionError('legacy visitor')):
            result=vm._scheduler.run_inline(vm.block(call.arguments))
        self.assertEqual(result,9)
        if engine.FORCE_PYTHON_TRANSLATION:
            self.assertEqual(engine.stats['metadata_block_executions'], 0)
            self.assertEqual(execution_kinds(self, vm).get('Binary'), 2)
        else:
            self.assertEqual(engine.stats['metadata_block_executions'],1)
        self.assertEqual(engine.stats['interpreter_fallbacks'],0)

    @mutable_compiled_contract
    def test_shared_metadata_entry_preserves_lexical_goto_and_mutation_guards(self):
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        call=parse('Unused();')[0].expression
        call.arguments=parse('Goto ~Done;99;~Done:7;')
        engine.prepare_node(call)
        with self.assertRaises(StopIteration) as done:
            next(engine.run_block(call.arguments))
        self.assertEqual(done.exception.value,7)
        call.arguments.append(parse('8;')[0])
        with self.assertRaises(CompiledUnsupported):
            vm._scheduler.run_inline(vm.block(call.arguments))

    def test_metadata_lists_preflight_unsupported_nodes_and_source_budgets(self):
        from unittest.mock import patch
        from yadinassi.syntax import ast
        vm=Interpreter(execution_backend='compiled-strict')
        call=parse('Unused(1);')[0].expression
        call.arguments.append(ast.Node(call.token))
        with self.assertRaises(CompiledUnsupported):vm._compiled().prepare_node(call)
        self.assertEqual(vm.variables,{})
        with patch.object(Engine,'MAX_INLINE_UNIT_BYTES',1):
            with self.assertRaises(CompiledUnsupported):
                Interpreter(execution_backend='compiled-strict').execute('r=Unused(1);')

    def test_metadata_role_promotes_when_alias_is_statement_body(self):
        from yadinassi.syntax import ast
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        call=parse('Unused(1,2);')[0].expression
        body=call.arguments
        attempt=ast.Try(call.token,body,[])
        engine.prepare([call,attempt])
        self.assertEqual(self.admitted_block(engine,body).role,'structural')
        # Previously admitted metadata also upgrades on later structural use.
        other=Interpreter(execution_backend='compiled-strict')._compiled()
        other.prepare_node(call)
        self.assertEqual(self.admitted_block(other,body).role,'metadata')
        other.prepare_node(attempt)
        self.assertEqual(self.admitted_block(other,body).role,'structural')

    def test_reused_metadata_entry_is_charged_in_each_admission(self):
        from unittest.mock import patch
        from yadinassi.compiled_backend import _METADATA_BLOCK_SOURCE
        for force in (False, True):
            with self.subTest(force=force), patch.object(Engine, 'FORCE_PYTHON_TRANSLATION', force):
                engine=Interpreter(execution_backend='compiled-strict')._compiled()
                call=parse('Unused(1,2);')[0].expression;engine.prepare_node(call)
                before=registry_identity(engine)
                # FORCE has no legacy metadata function to charge. Re-admission
                # must instead enforce the actual generated function's cap.
                cap=1 if force else len(_METADATA_BLOCK_SOURCE.encode())-1
                reason='expression function source budget' if force else 'metadata entry function source budget'
                with patch.object(engine,'MAX_INLINE_FUNCTION_BYTES',cap):
                    with self.assertRaisesRegex(CompiledUnsupported,reason):
                        engine.prepare_node(call)
                self.assertEqual(registry_identity(engine),before)
