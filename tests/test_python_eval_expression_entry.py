import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import CompiledUnsupported
from yadinassi.syntax.parser import parse, parse_expression


def finish(task):
    try:next(task)
    except StopIteration as stopped:return stopped.value
    raise AssertionError('unexpected suspension')


class EvalExpressionEntryTests(unittest.TestCase):
    def test_expression_unit_has_no_wrapper_executable_but_keeps_anchor(self):
        vm=Interpreter();engine=vm._compiled();effects=[]
        vm.register_function('Host',lambda:effects.append('host') or Decimal(7))
        expression=parse_expression('Host()');program=[expression]
        lease=engine.prepare_transient(program,expression_entry=True)
        try:
            view=engine._owned.existing(expression);key=(id(view),)
            block,unit=engine._python_units[key]
            self.assertIsNone(unit.blocks[key][1])
            self.assertIn(id(view),unit.expressions.functions)
            self.assertFalse(engine.has_executable_block(program))
            self.assertEqual(finish(engine.run_node(expression)),7)
            with self.assertRaises(CompiledUnsupported):finish(engine.run_block(program))
            self.assertEqual(effects,['host'])
            self.assertEqual(finish(vm.block(program)),7)
            self.assertTrue(engine.has_executable_block(program))
        finally:lease.close()
        # Explicit independent block admission survives the shorter Eval lease.
        self.assertTrue(engine.has_executable_block(program))
        self.assertEqual(finish(vm.block(program)),7)
        self.assertEqual(effects,['host','host','host'])

    def test_expression_families_keep_generated_value_entries(self):
        for text,check in [('1+2',lambda v:v==3),('New Array(2)',lambda v:len(v.items)==2),
                           ('?(True,3,missing)',lambda v:v==3),('1',lambda v:v==1)]:
            with self.subTest(text=text):
                vm=Interpreter();engine=vm._compiled();expression=parse_expression(text)
                lease=engine.prepare_transient([expression],expression_entry=True)
                try:
                    self.assertTrue(check(finish(engine.run_node(expression))))
                    self.assertTrue(all(fn is None for _,unit in engine._python_units.values() for _,fn in unit.blocks.values()))
                finally:lease.close()
                self.assertFalse(engine._python_units)
                self.assertFalse(engine._nodes)
                self.assertEqual(engine.active_frames,0)

    def test_statement_entry_is_not_silently_reclassified(self):
        vm=Interpreter();engine=vm._compiled()
        with self.assertRaises(CompiledUnsupported):engine.prepare_transient(parse('x=1;'),expression_entry=True)
        self.assertFalse(engine._nodes);self.assertFalse(engine._owned.memo)
        program=parse('x=1;');lease=engine.prepare_transient(program)
        try:
            self.assertTrue(engine.has_executable_block(program))
            finish(engine.run_block(program));self.assertEqual(vm.variables['x'],1)
        finally:lease.close()

    def test_source_budget_rejects_expression_before_host_effect(self):
        vm=Interpreter();engine=vm._compiled();effects=[]
        vm.register_function('Host',lambda:effects.append('host') or Decimal(7))
        with patch.object(engine,'MAX_PLAIN_SOURCE_BYTES',1):
            with self.assertRaises(CompiledUnsupported):engine.prepare_transient([parse_expression('Host()')],expression_entry=True)
        self.assertEqual(effects,[]);self.assertFalse(engine._nodes);self.assertFalse(engine._owned.versions)

    def test_explicit_block_preflight_keeps_old_expression_after_failure(self):
        vm=Interpreter();engine=vm._compiled();effects=[]
        vm.register_function('Host',lambda:effects.append('host') or Decimal(7))
        expression=parse_expression('Host()');program=[expression]
        lease=engine.prepare_transient(program,expression_entry=True)
        try:
            used=sum(unit.source_bytes for unit in {id(unit):unit for _,unit in engine._python_units.values()}.values())
            with patch.object(engine,'MAX_PLAIN_SOURCE_BYTES',used):
                with self.assertRaises(CompiledUnsupported):finish(vm.block(program))
            self.assertEqual(effects,[])
            self.assertFalse(engine.has_executable_block(program))
            self.assertEqual(finish(engine.run_node(expression)),7)
        finally:lease.close()

    def test_eval_and_execute_scopes_and_errors_stay_distinct(self):
        outcomes=[]
        for backend in ('interpreter','compiled-strict'):
            vm=Interpreter(execution_backend=backend);output=[];vm.output=output.append
            vm.execute('x=3;r=Eval("x+2");Execute "x=x+4;localonly=9;";Try z=Eval("1/0");Except Message("caught");EndTry;')
            outcomes.append((vm.variables['x'],vm.variables['r'],'localonly' in vm.variables,output,vm._eval_depth[0],vm._execute_depth[0]))
        self.assertEqual(outcomes[0],outcomes[1])

    def test_invalid_entry_shape_rejects_without_host_protocols(self):
        events=[]
        class Meta(type):
            def __eq__(cls,other):events.append('eq');return False
        class Hostile(metaclass=Meta):
            def __iter__(self):events.append('iter');return iter(())
            def __len__(self):events.append('len');return 1
        vm=Interpreter();engine=vm._compiled()
        for program in (Hostile(),[Hostile()],[],[parse_expression('1'),parse_expression('2')]):
            with self.assertRaises(CompiledUnsupported):engine.prepare_transient(program,expression_entry=True)
        self.assertEqual(events,[])
        self.assertFalse(engine._nodes);self.assertFalse(engine._owned.versions);self.assertFalse(engine._python_units)

    def test_later_unit_retains_shared_expression_after_lease_close(self):
        vm=Interpreter();engine=vm._compiled();expression=parse_expression('1+2')
        lease=engine.prepare_transient([expression],expression_entry=True)
        owned=engine._owned.existing(expression)
        program=parse('r=0;');program[0].value=owned
        engine.prepare(program,allow_reprepare=False)
        lease.close()
        self.assertTrue(engine.has_node(owned));self.assertTrue(engine.has_node(owned.left));self.assertTrue(engine.has_node(owned.right))
        finish(engine.run_block(program));self.assertEqual(vm.variables['r'],3)

    def test_suspended_expression_entry_keeps_lease_until_unwind(self):
        from yadinassi.syntax import ast
        from yadinassi.async_runtime import AwaitRequest
        for outcome in ('resume','close','throw'):
            with self.subTest(outcome=outcome):
                vm=Interpreter();engine=vm._compiled();literal=parse_expression('1')
                expression=ast.Await(literal.token,literal)
                lease=engine.prepare_transient([expression],expression_entry=True)
                task=engine.run_node(expression)
                self.assertIsInstance(next(task),AwaitRequest)
                self.assertEqual(engine.active_frames,1)
                with self.assertRaises(RuntimeError):engine.release()
                if outcome=='resume':
                    with self.assertRaises(StopIteration) as done:task.send(Decimal(9))
                    self.assertEqual(done.exception.value,9)
                elif outcome=='close':task.close()
                else:
                    with self.assertRaisesRegex(ValueError,'cancelled'):task.throw(ValueError('cancelled'))
                self.assertEqual(engine.active_frames,0)
                lease.close()
                self.assertFalse(engine._nodes);self.assertFalse(engine._python_units)
