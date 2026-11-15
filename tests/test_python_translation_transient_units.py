import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.syntax.parser import parse, parse_expression
from yadinassi.async_runtime import AwaitRequest
from yadinassi.values import InterpreterCall


def units(vm):
    return {id(unit):unit for _,unit in vm._compiled()._python_units.values()}

class TransientUnits(unittest.TestCase):
    def test_completed_dynamic_units_do_not_accumulate(self):
        vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
        samples=[]
        vm.register_function('Sample',lambda:samples.append((len(units(vm)),sum(unit.source_bytes for unit in units(vm).values()),len(vm._compiled()._nodes))))
        source='''x=0;
        For i=1 To 30 Do
          r=Eval("Eval(""1+2"")");
          Try bad=Eval("1/0");Except EndTry;
          Execute "x=x+1;localnew=9;";
          Sample();
        EndDo;'''
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):vm.execute(source)
        self.assertEqual(vm.variables['x'],30);self.assertEqual(vm.variables['r'],3)
        self.assertNotIn('localnew',vm.variables);self.assertEqual(len(samples),30)
        self.assertEqual(len(set(samples)),1)
        self.assertEqual(vm._eval_depth[0],0);self.assertEqual(vm._execute_depth[0],0)

    def test_independent_admission_during_eval_is_preserved(self):
        vm=Interpreter(execution_backend='compiled-strict');sibling=parse_expression('42')
        def admit():vm._compiled().prepare_node(sibling);return Decimal(7)
        vm.register_function('AdmitSibling',admit)
        observed=[]
        vm.register_function('CheckSibling',lambda:observed.append(vm._compiled().has_node(sibling)))
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            vm.execute('r=Eval("AdmitSibling()");CheckSibling();')
        self.assertEqual(vm.variables['r'],7);self.assertEqual(observed,[True])

    def test_retained_routine_and_default_survive_dynamic_scope(self):
        vm=Interpreter(execution_backend='compiled-strict')
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            vm.execute('Function F(Val x=2) Return x+1;EndFunction')
            vm.execute('a=Eval("F()");r=F();')
        self.assertEqual(vm.variables['a'],3);self.assertEqual(vm.variables['r'],3)

    def test_pending_eval_keeps_unit_until_resume_and_cleans_after(self):
        vm=Interpreter(execution_backend='compiled-strict');signal=vm._scheduler.new_pending()
        def suspend(caller,values):return (yield AwaitRequest(signal))
        vm.register_function('Suspend',InterpreterCall(0,0,lambda vm:None,suspend))
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            vm.execute('Async Function Worker() Return Eval("Suspend()");EndFunction p=Worker();')
            pending_ids=set(units(vm));self.assertEqual(vm.variables['p'].state,'pending')
            vm._scheduler.resolve(signal,Decimal(9));vm.run_until_idle()
            self.assertEqual(vm.variables['p'].result,9)
            self.assertLess(len(units(vm)),len(pending_ids))
        self.assertEqual(vm._eval_depth[0],0);self.assertIsNone(vm.locals)

    def test_pending_eval_cancellation_cleans_scope(self):
        vm=Interpreter(execution_backend='compiled-strict');signal=vm._scheduler.new_pending()
        def suspend(caller,values):return (yield AwaitRequest(signal))
        vm.register_function('Suspend',InterpreterCall(0,0,lambda vm:None,suspend))
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            vm.execute('Async Function Worker() Return Eval("Suspend()");EndFunction p=Worker();')
            vm.close()
        self.assertFalse(vm._scheduler._tasks);self.assertEqual(vm._eval_depth[0],0)
        self.assertTrue(vm._compiled()._python_units)  # Declared Worker remains retained.
        self.assertFalse(any(plan.node.token.source == '<Вычислить>' for plan in vm._compiled()._nodes.values()))

    def test_rejected_admission_rolls_back_and_limit_stays_enforced(self):
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True),patch.object(Engine,'MAX_PLAIN_SOURCE_BYTES',1):
            with self.assertRaises(CompiledUnsupported):engine.prepare_transient([parse_expression('1+2')])
        self.assertEqual(engine._nodes,{});self.assertEqual(engine._python_units,{})
        self.assertEqual(engine._owned.memo,{})

    def test_declarations_cannot_acquire_transient_lifetime(self):
        vm=Interpreter(execution_backend='compiled-strict')
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            with self.assertRaises(CompiledUnsupported):vm._compiled().prepare_transient(parse('Function F() Return 1;EndFunction'))

    def test_later_unit_retains_shared_owned_expression_and_descendants(self):
        from tests.test_python_translation_expressions import finish
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            expression=parse_expression('1+2')
            lease=engine.prepare_transient([expression])
            owned=engine._owned.existing(expression)
            program=parse('r=0;');program[0].value=owned
            engine.prepare(program,allow_reprepare=False)
            lease.close()
            self.assertTrue(engine.has_node(owned));self.assertTrue(engine.has_node(owned.left));self.assertTrue(engine.has_node(owned.right))
            finish(engine.run_block(program))
        self.assertEqual(vm.variables['r'],3)

    def test_shared_dependency_through_branch_tuple(self):
        from tests.test_python_translation_expressions import finish
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            expression=parse_expression('1=1');lease=engine.prepare_transient([expression])
            owned=engine._owned.existing(expression)
            program=parse('If False Then r=7;EndIf;')
            program[0].branches[0]=(owned,program[0].branches[0][1])
            engine.prepare(program,allow_reprepare=False);lease.close()
            self.assertTrue(engine.has_node(owned))
            finish(engine.run_block(program))
        self.assertEqual(vm.variables['r'],7)

    def test_finished_transient_dependent_does_not_pin_parent_graph(self):
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            expression=parse_expression('1+2');parent=engine.prepare_transient([expression])
            owned=engine._owned.existing(expression)
            program=parse('r=0;');program[0].value=owned
            child=engine.prepare_transient(program)
            child.close();parent.close()
            self.assertFalse(engine.has_node(owned));self.assertFalse(engine._python_units)
        self.assertEqual(engine._transient_leases,[])

    def test_parent_close_keeps_suspended_dependent_source(self):
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        signal=vm._scheduler.new_pending()
        def suspend(caller,values):return (yield AwaitRequest(signal))
        vm.register_function('Suspend',InterpreterCall(0,0,lambda vm:None,suspend))
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            expression=parse_expression('Suspend()');parent=engine.prepare_transient([expression])
            owned=engine._owned.existing(expression)
            program=parse('r=0;');program[0].value=owned
            engine.prepare(program,allow_reprepare=False)
            execution=engine.run_block(program)
            self.assertIsInstance(next(execution),AwaitRequest)
            parent.close()
            self.assertTrue(engine.has_node(owned))
            with self.assertRaises(StopIteration):execution.send(Decimal(9))
        self.assertEqual(vm.variables['r'],9)
