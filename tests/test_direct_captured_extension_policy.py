import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import make_boundary
from yadinassi.execution.direct.python_direct_error_info import read, snapshot, _ALL

class CapturedExtensionPolicyTests(unittest.TestCase):
    def test_injected_callback_and_foreign_method_stay_closed(self):
        seen=[]
        class Meta(type):
            def __eq__(self,other):seen.append('eq');raise AssertionError()
        class Foreign(metaclass=Meta):
            def method(self):seen.append('call')
        for function in (lambda:seen.append('call'),Foreign().method):
            vm=Interpreter();vm.variables['saved']=HostFunction('Saved',function)
            with self.assertRaises(BoundaryViolation):vm.execute('Saved();')
        self.assertEqual(seen,[])

    def test_runtime_method_mutation_stays_closed(self):
        vm=Interpreter();vm.execute('D=New TextDocument;D.SetText("ok");Saved=D.GetText;')
        seen=[];vm.variables['saved'].function=lambda:seen.append('call')
        with self.assertRaises(BoundaryViolation):vm.execute('Saved();')
        self.assertEqual(seen,[])

    def test_category_rechecked_after_policy_mutation(self):
        vm=Interpreter();context=make_boundary(vm);context.start()
        value=read(context,snapshot('x'),'IsErrorOfCategory');seen=[]
        bound=context.resolve_extension_value(value,require_value=True)
        def policy(*args):
            value.function=lambda *args:seen.append('call')
        context.policy=policy
        with self.assertRaises(BoundaryViolation):bound(_ALL)
        self.assertEqual(seen,[])

    def test_close_and_explicit_extension_contract(self):
        vm=Interpreter();vm.execute('D=New TextDocument;Saved=D.GetText;')
        context=make_boundary(vm);context.start();bound=context.resolve_extension_value(vm.variables['saved'])
        vm.close()
        with self.assertRaises(BoundaryViolation):bound()
        vm=Interpreter(allow_extensions=True);vm.variables['saved']=HostFunction('Saved',lambda:7)
        self.assertEqual(vm.execute('Saved()'),7)

    def test_copied_wrapper_does_not_inherit_private_provenance(self):
        vm=Interpreter();vm.execute('A=New Array;Saved=A.Count;')
        original=vm.variables['saved'];vm.variables['forged']=HostFunction(original.name,original.function)
        with self.assertRaises(BoundaryViolation):vm.execute('Forged();')
        self.assertEqual(vm.execute('Saved()'),0)

    def test_array_closure_code_mutation_denied(self):
        vm=Interpreter();vm.execute('A=New Array;Saved=A.Count;')
        fn=vm.variables['saved'].function
        def factory(receiver):
            def replacement():return len(receiver)
            return replacement
        original=fn.__code__
        try:
            fn.__code__=factory([]).__code__
            with self.assertRaises(BoundaryViolation):vm.execute('Saved();')
        finally:fn.__code__=original

    def test_weak_provenance_does_not_retain_array_wrapper_cycle(self):
        import gc,weakref
        from yadinassi.execution.direct.python_direct_captured_values import _RECORDS
        vm=Interpreter();vm.execute('A=New Array;Saved=A.Count;A.Add(Saved);')
        value=vm.variables['saved'];identity=id(value);weak=weakref.ref(value)
        vm.close();del value,vm;gc.collect()
        self.assertIsNone(weak());self.assertNotIn(identity,_RECORDS)

    def test_ordinary_noncallable_remains_catchable_bsl_error(self):
        for source in ('5','"text"','Undefined','New Array'):
            vm=Interpreter();vm.execute('X='+source+';Caught=False;Try X();Except Caught=True;EndTry;')
            self.assertIs(vm.variables['caught'],True)
