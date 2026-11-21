import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.types.values import Reference,HostFunction
from yadinassi.execution.codegen.experimental_naked_live_state import source_reference,_SlotReference
from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext

class CachedSourceRefsTests(unittest.TestCase):
    def test_cache_is_address_not_value_or_canonical_binding(self):
        state={'x':Decimal(1)};cached=_SlotReference(state,'x')
        self.assertIs(source_reference(state,'x',cached),cached)
        box=[Decimal(8)];ref=Reference(lambda:box[0],lambda v:box.__setitem__(0,v))
        state['x']=ref
        bound=source_reference(state,'x',cached);bound.value=Decimal(9)
        self.assertIs(state['x'],ref);self.assertEqual(box[0],9)
        state['x']=Decimal(3)
        self.assertIs(source_reference(state,'x',cached),cached)
        del state['x']
        with self.assertRaisesRegex(ValueError,'не определена'):source_reference(state,'x',cached)

    def test_source_aliases_and_callback_replacement(self):
        vm=Interpreter(allow_extensions=True);box=[Decimal(20)]
        ref=Reference(lambda:box[0],lambda v:box.__setitem__(0,v))
        vm.register_function('Swap',lambda:vm.variables.__setitem__('x',ref))
        vm.execute('Procedure F(a,b) a=a+1;b=b+2;EndProcedure x=1;F(x,x);first=x;Swap();F(x,x);')
        self.assertEqual(vm.variables['first'],4);self.assertEqual(box[0],23);self.assertIs(vm.variables['x'],ref)

    def test_missing_binding_before_callee_effect(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Seen',lambda:seen.append(1))
        vm.register_function('Drop',lambda:vm.variables.pop('x'))
        with self.assertRaisesRegex(Exception,'не определена'):
            vm.execute('Procedure F(a) Seen();EndProcedure x=1;F(x);Drop();F(x);')
        self.assertEqual(seen,[1])

    def test_retained_reference_and_repeated_program_run(self):
        kept=[]
        h=HostFunction('Keep',lambda x:kept.append(x),reference_parameters=frozenset({0}))
        source='Procedure F(a) Keep(a);EndProcedure x=1;F(x);'
        p=compile_owned(parse(source),source_text=source,source_name='refs.bsl')
        a={};b={}
        for state in (a,b):p.run(state,context=BoundaryContext(services={'Keep':h}))
        kept[0].set(Decimal(7));kept[1].set(Decimal(9))
        self.assertEqual(a['x'],7);self.assertEqual(b['x'],9)

    def test_partial_error_and_loop_counter_alias(self):
        vm=Interpreter()
        with self.assertRaises(Exception):
            vm.execute('Procedure F(a,b) a=a+1;b=1/0;EndProcedure x=0;For i=1 To 3 Do F(x,i);EndDo;')
        self.assertEqual(vm.variables['x'],1);self.assertEqual(vm.variables['i'],1)

    def test_one_slot_allocation_per_name_per_module_invocation(self):
        import yadinassi.execution.codegen.experimental_naked_live_state as live
        with patch.object(live,'_SlotReference',wraps=_SlotReference) as factory:
            vm=Interpreter();vm.execute('Procedure F(a,b) a=a+1;b=b+1;EndProcedure x=0;For i=1 To 20 Do F(x,x);EndDo;')
            self.assertEqual(factory.call_count,1);self.assertEqual(vm.variables['x'],40)

if __name__=='__main__':unittest.main()
