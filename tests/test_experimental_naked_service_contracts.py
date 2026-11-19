"""Public direct host binding contracts with independent effect assertions."""
import unittest
from yadinassi import Interpreter
from yadinassi.types.values import HostFunction
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation

class ServiceContracts(unittest.TestCase):
    def vm(self, *, allow_extensions=False):
        vm=Interpreter(allow_extensions=allow_extensions);self.addCleanup(vm.close);return vm

    def test_registration_change_keeps_bound_callee(self):
        vm=self.vm(allow_extensions=True);events=[]
        vm.register_function('Host',lambda x:events.append('old') or 1)
        def change():vm.register_function('Host',lambda x:events.append('new') or 2);return 0
        vm.register_function('Change',change)
        vm.execute('r=Host(Change());')
        self.assertEqual((vm.variables['r'],events),(1,['old']))

    def test_registered_service_outranks_variable(self):
        vm=self.vm(allow_extensions=True);vm.register_function('Host',lambda:1)
        vm.execute('Host=7;r=Host();')
        self.assertEqual(vm.variables['r'],1)

    def test_canonical_dynamic_host_and_raw_rejection(self):
        for source in ('r=(Get())();','f=Get();r=f();'):
            for canonical in (False,True):
                with self.subTest(source=source,canonical=canonical):
                    vm=self.vm(allow_extensions=True);events=[]
                    function=lambda:events.append('called') or 7
                    value=HostFunction('chosen',function) if canonical else function
                    vm.register_function('Get',lambda:value)
                    if canonical:
                        vm.execute(source)
                        self.assertEqual(vm.variables['r'],7);self.assertEqual(events,['called'])
                    else:
                        with self.assertRaisesRegex(BSLRuntimeError,'Значение не является функцией'):vm.execute(source)
                        self.assertEqual(events,[])

    def test_procedure_value_rejected_before_arguments(self):
        vm=self.vm(allow_extensions=True);events=[]
        vm.register_function('Get',lambda:HostFunction('P',lambda x:events.append('body'),returns_value=False))
        vm.register_function('Arg',lambda:events.append('arg'))
        with self.assertRaises(BSLRuntimeError):vm.execute('r=(Get())(Arg());')
        self.assertEqual(events,[])

    def test_policy_changed_by_argument_checked_after_binding(self):
        from tests.direct_boundary_compile import compile_boundary
        events=[];ctx=BoundaryContext(services={'host':lambda x:events.append('host')})
        def change():ctx.policy=lambda op,name:name!='host';return 0
        ctx._services['change']=change
        with self.assertRaises(BoundaryViolation):
            compile_boundary('Host(Change());').run({},context=ctx)
        self.assertEqual(events,[])
