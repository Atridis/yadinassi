import sys
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.types.values import Reference,HostFunction
from yadinassi.execution.codegen.experimental_naked_live_state import source_reference,_SlotReference
from yadinassi.execution.codegen.direct_emitter import compile_owned
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
        p=compile_owned(parse(source),source_text=source,source_name='refs.bsl',reference_names=('keep',))
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
        from yadinassi.execution.direct.python_direct_cells import (
            CellReference, NativeCell, PublishedModuleCell,
        )

        # Observe real allocations without swapping factories and changing
        # the prepared code's native call path.
        allocators = {factory.__code__ for factory in (
            NativeCell, CellReference.__init__, PublishedModuleCell.__init__,
            _SlotReference.__init__,
        )}
        for prepared in (False, True):
            for iterations, names in ((20, ('x',)), (1, ('x', 'y')), (101, ('x', 'y'))):
                with self.subTest(prepared=prepared, iterations=iterations, names=names):
                    vm = Interpreter()
                    self.addCleanup(vm.close)
                    assignments = ''.join(f'{name}=0;' for name in names)
                    calls = ''.join(f'F({name},{name});' for name in names)
                    source = ('Procedure F(a,b) a=a+1;b=b+1;EndProcedure '
                              f'{assignments}For i=1 To {iterations} Do {calls}EndDo;')
                    plan = vm.prepare(source) if prepared else None
                    for _ in range(2):
                        allocations = 0

                        def profile(frame, event, arg):
                            nonlocal allocations
                            if event == 'call' and frame.f_code in allocators:
                                allocations += 1

                        previous = sys.getprofile()
                        sys.setprofile(profile)
                        try:
                            if prepared:
                                vm.execute_prepared(plan)
                            else:
                                vm.execute(source)
                        finally:
                            sys.setprofile(previous)

                        self.assertEqual(allocations, len(names))
                        self.assertEqual([vm.variables[name] for name in names],
                                         [2 * iterations] * len(names))


if __name__=='__main__':unittest.main()
