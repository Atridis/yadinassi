import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.experimental_naked_collections import prepare
from yadinassi.python_direct import REPAIRS

class ArraySpecializationTests(unittest.TestCase):
    def pair(self,source):
        out=[]
        for backend in ('interpreter','python-direct'):
            vm=Interpreter(execution_backend=backend);events=[]
            vm.register_function('Observe',lambda n:events.append(n) or n)
            error=None
            try:vm.execute(source)
            except Exception as exc:error=type(exc).__name__
            out.append((vm.variables.get('r'),events,error))
        self.assertEqual(*out);return out[1]

    def source(self,code):return prepare(code,repairs=REPAIRS,_trusted_entry=True).generated_source

    def test_triplet_uses_native_receiver_and_integer_index(self):
        code='a=New Array;For i=0 To 99 Do a.Add(i);EndDo;r=0;For j=0 To 99 Do r=r+a.Get(j);EndDo;'
        self.assertEqual(self.pair(code)[0],4950)
        generated=self.source(code)
        self.assertNotIn('_checked_array_index(',generated)
        self.assertNotIn('id(type(',generated)

    def test_fractional_negative_and_boolean_indexes_stay_checked(self):
        for key in ('-1','0.5','True'):
            code=f'a=New Array;a.Add(7);r=a.Get({key});'
            self.assertIsNotNone(self.pair(code)[2])
            self.assertIn('_checked_array_index(',self.source(code))

    def test_empty_loop_does_not_invent_array_or_contents(self):
        self.pair('a=New Array;r=3;For i=0 To -1 Do a.Add(i);EndDo;r=r+a.Count();')

    def test_alias_and_clear_native_bounds_still_reject(self):
        self.pair('a=New Array;a.Add(1);b=a;b.Clear();r=a.Get(0);')

    def test_callback_receiver_rebinding_uses_captured_receiver(self):
        for backend in ('interpreter','python-direct'):
            vm=Interpreter(execution_backend=backend)
            def change():vm.variables['a']=Decimal(99);return Decimal(7)
            vm.register_function('Change',change)
            vm.execute('a=New Array;b=a;a.Add(Change());r=b.Get(0);')
            self.assertEqual(vm.variables['r'],7);self.assertEqual(vm.variables['a'],99)

    def test_callback_deletion_and_counter_write_decline_proof(self):
        code='a=New Array;For i=0 To 2 Do a.Add(Observe(i));EndDo;r=a.Count();'
        self.assertEqual(self.pair(code)[:2],(3,[0,1,2]))
        self.assertIn('id(type(',self.source(code))
        code='a=New Array;a.Add(7);r=0;For i=0 To 0 Do i=-1;r=a.Get(i);EndDo;'
        self.assertIsNotNone(self.pair(code)[2])
        self.assertIn('_checked_array_index(',self.source(code))

    def test_opaque_contents_stop_operator_proof(self):
        code='a=New Array;a.Add(host);r=a.Get(0);'
        generated=self.source(code)
        self.assertNotIn('id(type(',generated)
        class Payload:
            def __add__(self,other):return 77
        vm=Interpreter(execution_backend='python-direct');vm.variables['host']=Payload()
        vm.execute(code)
        self.assertIs(vm.variables['r'],vm.variables['host'])

    def test_array_append_arg_effects_keep_receiver_once(self):
        # Argument dispatch must not be evaluated twice by receiver branching.
        self.pair('a=New Array;a.Add(Observe(7));r=a.Get(0);')

    def test_constructor_arguments_invalidate_between_effects(self):
        from yadinassi.maps import BSLMap
        from yadinassi.experimental_naked_collections import _TypedMap
        for backend in ('interpreter','python-direct'):
            events=[];vm=Interpreter(execution_backend=backend)
            def change():
                events.append('host');vm.variables['a']=BSLMap() if backend=='interpreter' else _TypedMap()
                return Decimal(1)
            vm.register_function('Change',change)
            vm.register_function('Observe',lambda n:events.append(n) or n)
            with self.assertRaises(Exception):vm.execute('a=New Array;a.Add(1);r=New Array(Change(),a.Get(0),Observe(7));')
            self.assertEqual(events,['host',Decimal(7)])

    def test_explicit_constructor_override_does_not_get_native_facts(self):
        code='a=New Array;r=a.Count();'
        generated=prepare(code,repairs=REPAIRS,constructors=('array',),_trusted_entry=True).generated_source
        self.assertIn('id(type(',generated)

    def test_unknown_operator_and_host_array_values_invalidate(self):
        class Payload:
            def __add__(self,value):
                vm.variables['a']=Decimal(9)
                return Decimal(0)
        vm=Interpreter(execution_backend='python-direct');vm.variables['payload']=Payload()
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        with self.assertRaises(BoundaryViolation):
            vm.execute('a=New Array;a.Add(payload);x=a.Get(0)+1;r=a.Count();')
        self.assertEqual(vm.variables['a'],9)

    def test_effectful_receiver_invalidates_argument_facts(self):
        from yadinassi.experimental_naked_collections import _TypedMap
        from yadinassi.experimental_naked_boundaries import BoundaryContext
        state={};captured=[]
        def make():state['a']=_TypedMap();return captured
        code='a=New Array;a.Add(1);Make().Add(a.Get(0));'
        plan=prepare(code,repairs=REPAIRS,_trusted_entry=True)
        plan.run(state,context=BoundaryContext(services={'Make':make}))
        self.assertEqual(captured,[None])

    def test_huge_literal_and_loop_bound_keep_decimal_first_check(self):
        from yadinassi.syntax.parser import parse
        from yadinassi.syntax import ast
        from yadinassi import experimental_naked_collections as emitter
        # Inject a finite huge Decimal into a normal literal AST; no giant int
        # or source text is materialized to demonstrate the boundary.
        program=parse('a=New Array;r=a.Get(1);')
        program[-1].value.arguments[0].value=Decimal('1e1000000000')
        plan=prepare('',parsed_ast=program,repairs=REPAIRS,_trusted_entry=True)
        self.assertIn('_checked_array_index(',plan.generated_source)
        from yadinassi.experimental_naked_boundaries import BoundaryContext
        with patch.object(emitter,'int',side_effect=AssertionError('huge integer conversion'),create=True):
            # Functions hold their own globals: patch the actual admitted alias.
            plan.function.__globals__['int']=lambda x:(_ for _ in ()).throw(AssertionError('huge integer conversion'))
            with self.assertRaises(Exception) as caught:plan.run({},context=BoundaryContext())
            self.assertNotIsInstance(caught.exception,AssertionError)
        code='a=New Array;For i=0 To 2*9223372036854775807 Do r=a.Get(i);EndDo;'
        self.assertIn('_checked_array_index(',self.source(code))

    def test_count_minus_one_index_loop_remains_bounded(self):
        code='a=New Array;a.Add(7);r=0;For i=0 To a.Count()-1 Do r=r+a.Get(i);EndDo;'
        self.assertEqual(self.pair(code)[0],7)
        self.assertNotIn('_checked_array_index(',self.source(code))


    def test_raw_count_profile_keeps_python_int_rejection(self):
        plan=prepare('a=New Array;a.Add(7);r=a.Get(a.Count());',
            repairs=('byref_routines','live_module_state','array_index_contract'),_trusted_entry=True)
        self.assertIn('_checked_array_index(',plan.generated_source)
        with self.assertRaisesRegex(TypeError,'Ожидается число'):plan.run({})
