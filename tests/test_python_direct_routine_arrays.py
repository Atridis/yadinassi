"""Private routine arrays use existing facts, never assumed caller types."""
from decimal import Decimal
from unittest import TestCase
from yadinassi import Interpreter
from yadinassi.python_direct import REPAIRS
from tests.retired_text_compiler import prepare
from yadinassi.experimental_naked_boundaries import BoundaryContext,BoundaryViolation

BODY='a=New Array;For i=0 To 99 Do a.Add(i);EndDo;s=0;For j=0 To 99 Do s=s+a.Get(j);EndDo;Return s;'
class RoutineArrayTests(TestCase):
    def plan(self,code,**kwargs):return prepare(code,repairs=REPAIRS,_trusted_entry=True,**kwargs)
    def test_private_loop_uses_native_array_without_caller_facts(self):
        code='Function F() '+BODY+' EndFunction r=F();'
        p=self.plan(code)
        self.assertNotIn('id(type(',p.generated_source);self.assertNotIn('_checked_array_index(',p.generated_source)
        for backend in ('interpreter','python-direct'):
            vm=Interpreter(execution_backend=backend)
            try:vm.execute(code);self.assertEqual(vm.variables['r'],4950)
            finally:vm.close()
    def test_explicit_local_and_val_shadow_module_or_external_names(self):
        for declaration,params,actuals in [('Var a;','',''),('','Val a','7')]:
            code='Function F('+params+') '+declaration+BODY+' EndFunction r=F('+actuals+');'
            for options in ({'module_names':('a',)},{'external_names':('a',),'constructors':('Query',)}):
                p=self.plan(code,**options)
                self.assertNotIn('id(type(',p.generated_source)
                state={'a':Decimal(123)} if 'module_names' in options else {}
                p.run(state,context=BoundaryContext());self.assertEqual(state['r'],4950)
                if 'module_names' in options:self.assertEqual(state['a'],123)
    def test_byref_parameters_and_globals_remain_opaque(self):
        for code in ('Procedure F(a) a=New Array;a.Add(1);EndProcedure F(x);',
                     'Var a;Procedure F() a=New Array;a.Add(1);EndProcedure F();'):
            self.assertIn('id(type(',self.plan(code).generated_source)
        code='Procedure F(a,b) a=New Array;b=42;a.Add(1);EndProcedure x=0;F(x,x);'
        vm=Interpreter()
        try:
            with self.assertRaises((Exception,BoundaryViolation)):vm.execute(code)
            self.assertEqual(vm.variables['x'],42)
        finally:vm.close()
    def test_host_byref_replacement_invalidates_private_array(self):
        code='Function F() a=New Array;Replace(a);a.Add(1);Return 0;EndFunction r=F();'
        seen=[]
        vm=Interpreter()
        def replace(slot):seen.append(slot.get());slot.set(Decimal(42))
        vm.register_function('Replace',replace)
        vm.functions['replace'].reference_parameters=frozenset({0})
        try:
            with self.assertRaises((Exception,BoundaryViolation)):vm.execute(code)
            self.assertEqual(seen,[[]]);self.assertNotIn('r',vm.variables)
        finally:vm.close()
    def test_unknown_val_bounds_and_authority_are_not_assumed_pure(self):
        code='Function F(Val n) a=New Array;For i=0 To n Do a.Add(i);EndDo;Return a.Count();EndFunction r=F(3);'
        self.assertIn('id(type(',self.plan(code).generated_source)
        p=prepare('Function F() '+BODY+' EndFunction r=F();',repairs=REPAIRS+('authority_checkpoints',),_trusted_entry=True)
        self.assertIn('id(type(',p.generated_source)
    def test_local_alias_clear_and_error_partial_effects(self):
        code='Function F() a=New Array;a.Add(3);b=a;b.Clear();Observe(a.Count());Return a.Get(0);EndFunction r=F();'
        events=[];vm=Interpreter();vm.register_function('Observe',events.append)
        try:
            with self.assertRaises(Exception):vm.execute(code)
            self.assertEqual(events,[Decimal(0)]);self.assertNotIn('r',vm.variables)
        finally:vm.close()

    def test_count_derived_bounds_use_local_array_facts(self):
        code='Function F() a=New Array;a.Add(2);a.Add(3);s=0;For i=0 To a.Count()-1 Do s=s+a.Get(i);EndDo;Return s;EndFunction r=F();'
        p=self.plan(code);self.assertNotIn('id(type(',p.generated_source)
        self.assertNotIn('_checked_array_index(',p.generated_source)
        state={};p.run(state,context=BoundaryContext());self.assertEqual(state['r'],5)
