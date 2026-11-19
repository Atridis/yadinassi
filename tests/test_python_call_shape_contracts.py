"""Live invocation semantics for immutable compiled call-site descriptions.

These assert direct invocation results and effect order independently;
no test substitutes a cached callable, grants, arguments or reference binding.
"""
import unittest
from decimal import Decimal
from yadinassi import Interpreter, BSLError
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.types.values import InterpreterCall


class CallShapeContracts(unittest.TestCase):
    def pair(self, operation):
        vm=Interpreter(allow_extensions=True);events=[]
        try:
            result=operation(vm,events)
            self.assertIsNone(vm.locals)
            return result,events
        finally:vm.close()

    def test_byref_default_grouped_and_member_actuals(self):
        def run(vm,events):
            vm.execute('Function F(x, Val y=2) x=x+y;Return x;EndFunction '
                       'a=New Array;a.Add(3);r=F(a[0]);n=7;s=(F)(n,4);'
                       'r=r+a[0];')
            return tuple(vm.variables[k] for k in ('r','n','s'))
        self.assertEqual(self.pair(run)[0],(10,11,11))

    def test_callee_rebinding_is_live_between_but_not_inside_invocations(self):
        def run(vm,events):
            vm.register_function('Host',lambda x:events.append(('old',x)) or x+1)
            def rebind():
                events.append('arg')
                vm.register_function('Host',lambda x:events.append(('new',x)) or x+10)
                return Decimal(2)
            vm.register_function('Rebind',rebind)
            vm.execute('r=Host(Rebind());s=Host(3);')
            return vm.variables['r'],vm.variables['s']
        result,events=self.pair(run)
        self.assertEqual(result,(3,13));self.assertEqual(events,['arg',('old',2),('new',3)])

    def test_omission_rejected_before_factory_receiver_effect(self):
        def run(vm,events):
            vm.register_function('Factory',lambda:events.append('factory'))
            vm.execute('r=0;Try Factory().Add(,1);Except r=1;EndTry;')
            return vm.variables['r']
        self.assertEqual(self.pair(run),(1,[]))

    def test_bad_routine_arity_rejected_before_actual_effects(self):
        def run(vm,events):
            vm.register_function('Tick',lambda:events.append('tick') or Decimal(1))
            vm.execute('Function F(Val x) Return x;EndFunction '
                       'r=0;Try r=F(Tick(),Tick());Except r=7;EndTry;')
            return vm.variables['r']
        self.assertEqual(self.pair(run),(7,[]))

    def test_retained_caller_resolves_new_routine_and_default(self):
        def run(vm,events):
            vm.execute('Function F(Val x=2) Return x;EndFunction '
                       'Function Caller() Return F();EndFunction r=Caller();')
            first=vm.variables['r']
            vm.execute('unrelated=100;')
            vm.execute('Function F(Val x=8) Return x+1;EndFunction')
            with self.assertRaisesRegex(PythonDirectUnsupported,'partially replaced'):
                vm.execute('r=Caller();')
            self.assertEqual(vm.variables['r'],first)
            vm.execute('Function F(Val x=8) Return x+1;EndFunction Function Caller() Return F();EndFunction r=Caller();')
            return first,vm.variables['r']
        self.assertEqual(self.pair(run)[0],(2,9))

    def test_interpreter_aware_callable_rejected_before_arguments_or_authorization(self):
        # This old adapter is not a capability for direct execution. Its own
        # authorization/dispatch hooks must not run, even if they would allow it.
        for denied in (False,True):
            vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);events=[]
            def authorize(caller):
                events.append('authorize')
                if denied:raise PermissionError('denied')
            def dispatch(caller,values):
                events.append('dispatch')
                if False:yield
                return values[0]
            vm.register_function('Guarded',InterpreterCall(1,1,authorize,dispatch))
            vm.register_function('Tick',lambda:events.append('argument'))
            with self.subTest(denied=denied), self.assertRaisesRegex(BSLError,'explicit interpreter dispatch'):
                vm.execute('R=0;R=Guarded(Tick());After=True;')
            self.assertEqual(events,[])
            self.assertEqual(vm.variables['r'],0)
            self.assertNotIn('after',vm.variables)
