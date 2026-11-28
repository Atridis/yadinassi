"""Behavior retained from retired translation engines; only the direct backend runs.

Implementation-only registry, fusion emitter, instrumentation and inline-budget
checks belonged to deleted engines and are retired, not skipped or emulated.
Unsupported behavioral cases deliberately remain ordinary failing tests.
"""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
class DirectSpecialCalls(unittest.TestCase):

    def run_source(self, source, setup=lambda vm: None):
        vm = Interpreter()
        self.addCleanup(vm.close)
        setup(vm)
        for part in source.split('//TEST_BODY'):
            vm.execute(part, 'direct-special.bsl')
        self.assertIsNone(vm.locals)
        self.assertEqual(vm._eval_depth[0], 0)
        return vm.variables.get('r')

    def test_eval_live_names_and_nested(self):
        self.assertEqual(self.run_source('x=3;r=Eval("x+Eval(""2"")");'), 5)

    def test_eval_whole_expression_parsed_before_effect(self):
        for backend in ('python-direct',):
            vm = Interpreter(execution_backend=backend, allow_extensions=True)
            events = []
            vm.register_function('Tick', lambda: events.append(1))
            with self.assertRaises(BSLError):
                vm.execute('r=Eval("Tick()+");')
            self.assertEqual(events, [])
            self.assertEqual(vm._eval_depth[0], 0)

    def test_json_roundtrip(self):
        self.assertEqual(self.run_source('w=New JSONWriter;w.SetString();WriteJSON(w,New Structure("n",7));s=w.Close();reader=New JSONReader;reader.SetString(s);v=ReadJSON(reader);reader.Close();r=v.n;'), 7)

    def test_json_conversion_callback(self):
        source = 'Function Convert(Name,Value,Extra,Cancel) Export\n            Return Extra;\n        EndFunction\n        //TEST_BODY\n        w=New JSONWriter;w.SetString();WriteJSON(w,New Structure("n",New UUID("12345678-1234-1234-1234-123456789abc")),,"Convert",ThisObject,2);s=w.Close();\n        reader=New JSONReader;reader.SetString(s);v=ReadJSON(reader);reader.Close();r=v.n;'
        self.assertEqual(self.run_source(source), 2)

    def test_callback_procedure_and_result(self):
        source = 'Var Result;\n        Procedure Record(Value,Extra) Export Result=Value+Extra;EndProcedure\n        //TEST_BODY\n        c=New CallbackDescription("Record",ThisObject,4);RunCallback(c,3);r=Result;'
        self.assertEqual(self.run_source(source), 7)

    def test_callback_invalid_arity_before_argument_effect(self):
        for backend in ('python-direct',):
            events = []
            vm = Interpreter(execution_backend=backend, allow_extensions=True)
            vm.register_function('Tick', lambda: events.append(1))
            with self.assertRaises(BSLError):
                vm.execute('RunCallback(Tick(),Tick(),Tick());')
            self.assertEqual(events, [])
