"""The compiler must preserve node policy traces, not merely final values."""
import unittest
from yadinassi import Interpreter


class PolicyABITests(unittest.TestCase):
    def execute_trace(self, backend, source):
        vm = Interpreter(execution_backend=backend)
        trace = []
        before, after, exception = vm.compiled_before, vm.compiled_after, vm.compiled_exception
        def enter(node):
            trace.append(('before', type(node).__name__, node.token.line, node.token.column))
            return before(node)
        def leave(node, value):
            trace.append(('after', type(node).__name__, type(value).__name__))
            return after(node, value)
        def fail(node, error):
            converted = exception(node, error)
            trace.append(('error', type(node).__name__, type(converted).__name__))
            return converted
        if backend == 'compiled-strict':
            vm.compiled_before, vm.compiled_after, vm.compiled_exception = enter, leave, fail
        else:
            # Reference embedding instrumentation existed via _visit wrappers;
            # the new strict ABI is not imposed on the legacy base hot path.
            reference_visit = vm._visit
            def reference_policy(node):
                enter(node)
                try:
                    value = yield from reference_visit(node)
                except BaseException as error:
                    trace.append(('error', type(node).__name__, type(error).__name__))
                    raise
                return leave(node, value)
            vm._visit = reference_policy
        vm.execute(source)
        return trace

    def test_expression_control_flow_errors_and_routine_trace(self):
        source = '''Function F(x)
If x=2 Then Return 4; EndIf;
Return x+1;
EndFunction
s=0;
For i=1 To 3 Do s=s+F(i); EndDo;
Try q=1/0; Except s=s+1; EndTry;
If False And F(99) Then s=99; EndIf;
Goto ~done;
s=100;
~done:
s=s+1;'''
        self.assertEqual(self.execute_trace('interpreter', source),
                         self.execute_trace('compiled-strict', source))

    def test_async_suspension_trace(self):
        source = 'Async Function F() x=Await 2; Return x+1; EndFunction p=F();'
        self.assertEqual(self.execute_trace('interpreter', source),
                         self.execute_trace('compiled-strict', source))
