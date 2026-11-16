"""Live invocation semantics for immutable compiled call-site descriptions.

These compare ordinary translated defaults with the explicit interpreter oracle;
no test substitutes a cached callable, grants, arguments or reference binding.
"""
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.values import InterpreterCall


class CallShapeContracts(unittest.TestCase):
    def pair(self, operation):
        results=[]
        for oracle in (True,False):
            vm=Interpreter(execution_backend='interpreter') if oracle else Interpreter()
            events=[]
            try:
                result=operation(vm,events)
                results.append((result,events))
                self.assertIsNone(vm.locals)
                if not oracle:
                    stats=vm.compiled_backend_stats
                    self.assertGreater(stats.get('python_translated_blocks',0),0)
                    self.assertEqual(stats.get('interpreter_fallbacks',0),0)
                    self.assertEqual(stats.get('plain_adapter_blocks',0),0)
            finally:vm.close()
        self.assertEqual(results[0],results[1])
        return results[1]

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
            vm.execute('r=Caller();')
            return first,vm.variables['r']
        self.assertEqual(self.pair(run)[0],(2,9))

    def test_interpreter_call_reauthorizes_after_argument_revocation(self):
        def run(vm,events):
            active=[True]
            def authorize(caller):
                events.append(('authorize',active[0]))
                if not active[0]:raise PermissionError('revoked')
            def dispatch(caller,values):
                events.append('dispatch')
                if False:yield
                return values[0]
            def revoke():
                events.append('argument');active[0]=False;return Decimal(1)
            vm.register_function('Guarded',InterpreterCall(1,1,authorize,dispatch))
            vm.register_function('Revoke',revoke)
            with self.assertRaisesRegex(PermissionError,'revoked'):
                vm.execute('r=0;Try r=Guarded(Revoke());Except r=9;EndTry;')
            return vm.variables['r']
        result,events=self.pair(run)
        self.assertEqual(result,0)
        self.assertEqual(events,[('authorize',True),'argument',('authorize',False)])

    def test_denied_interpreter_call_rejects_before_argument(self):
        def run(vm,events):
            def deny(caller):events.append('deny');raise PermissionError('denied')
            def dispatch(caller,values):
                events.append('dispatch')
                if False:yield
            vm.register_function('Guarded',InterpreterCall(1,1,deny,dispatch))
            vm.register_function('Tick',lambda:events.append('argument') or Decimal(1))
            with self.assertRaisesRegex(PermissionError,'denied'):
                vm.execute('r=0;Try r=Guarded(Tick());Except r=9;EndTry;')
            return vm.variables['r']
        self.assertEqual(self.pair(run),(0,['deny']))
