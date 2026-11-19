import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.types.values import HostFunction,Reference
from yadinassi.types.errors import BSLRuntimeError

class DynamicRefsTests(unittest.TestCase):
    def execute_case(self, source, expected, signature=(0,), reference_flags=None):
        vm=Interpreter();self.addCleanup(vm.close);events=[]
        def host(*args):
            events.append(tuple(isinstance(x,Reference) for x in args))
            for i,x in enumerate(args):
                if isinstance(x,Reference):x.set(Decimal(7) if len(args)==1 else x.get()+i+1)
        wrapper=HostFunction('h',host,reference_parameters=frozenset(signature))
        def change():wrapper.reference_parameters=frozenset({1});return Decimal(0)
        vm.register_function('Get',lambda:wrapper);vm.register_function('Change',change)
        vm.execute(source,'ref.bsl')
        self.assertEqual(vm.variables.get('r'),expected)
        if reference_flags is not None:self.assertEqual(events,reference_flags)

    def test_reference_locations(self):
        for source in ('x=1;f=Get();f(x);r=x;', 'm=New Map;f=Get();f(m["x"]);r=m["x"];', 'Function G() x=1;f=Get();f(x);Return x;EndFunction r=G();', 'Procedure G(x) f=Get();f(x);EndProcedure x=1;G(x);r=x;', 'Var x;Procedure G() f=Get();f(x);EndProcedure x=1;G();r=x;'):
            with self.subTest(source=source):self.execute_case(source,7,reference_flags=[(True,)])

    def test_expression_not_reference(self):
        self.execute_case('f=Get();f(1+2);',None,reference_flags=[(False,)])

    def test_same_actual_alias(self):
        self.execute_case('x=1;f=Get();f(x,x);r=x;',4,signature=(0,1),reference_flags=[(True,True)])

    def test_signature_mutation_is_live(self):
        self.execute_case('x=1;f=Get();f(Change(),x);r=x;',3,signature=(),reference_flags=[(False,True)])

    def test_missing_reference_has_no_host_effects(self):
        for source in ('f=Get();f(x);','a=New Array;f=Get();f(a[0]);','x=1;f=Get();f(,Arg(),x);'):
            vm=Interpreter();self.addCleanup(vm.close);events=[]
            wrapper=HostFunction('h',lambda *args:events.append('call'),reference_parameters=frozenset({0}))
            vm.register_function('Get',lambda:wrapper);vm.register_function('Arg',lambda:events.append('arg'))
            with self.subTest(source=source):
                with self.assertRaises(BSLRuntimeError):vm.execute(source)
                self.assertEqual(events,[])

    def test_escaped_reference_remains_live(self):
        vm=Interpreter();self.addCleanup(vm.close);kept=[]
        wrapper=HostFunction('save',lambda ref:kept.append(ref),reference_parameters=frozenset({0}))
        vm.register_function('Get',lambda:wrapper)
        vm.execute('x=1;f=Get();f(x);')
        self.assertIs(type(kept[0]),Reference)
        kept[0].set(Decimal(9))
        self.assertEqual(kept[0].get(),9)
        self.assertEqual(vm.variables['x'],9)

    def test_missing_reference_is_catchable(self):
        self.execute_case('f=Get();Try f(x);Except r=7;EndTry;',7,reference_flags=[])
