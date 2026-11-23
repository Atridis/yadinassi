"""Classification of direct iterator pairs grants no receiver capabilities."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.formats.storage.serialization import value_to_string_internal
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.types.values import BSLType
from yadinassi.types.type_values import type_of
from yadinassi.execution.codegen.experimental_naked_collections import _MapEntry
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.direct.python_direct_services import ServicesBoundary


class DirectEntryTypeOfTests(unittest.TestCase):
    def vm(self, backend='python-direct', *, allow_extensions=False):
        vm=Interpreter(allow_extensions=allow_extensions, execution_backend=backend);self.addCleanup(vm.close);return vm

    def test_map_and_structure_pairs_have_canonical_type_without_vm(self):
        source='''M=New Map;M.Insert("K",1);S=New Structure("K",1);
For Each P In M Do MT=TypeOf(P);MR=(MT=Type("KeyAndValue"));EndDo;
For Each P In S Do ST=ТипЗнч(P);SR=(ST=Тип("КлючИЗначение"));EndDo;'''
        vm=self.vm()
        with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
            vm.execute(source)
        self.assertIs(vm.variables['mt'],BSLType.KEY_AND_VALUE)
        self.assertIs(vm.variables['st'],BSLType.KEY_AND_VALUE)
        self.assertIs(vm.variables['mr'],True);self.assertIs(vm.variables['sr'],True)

    def test_alias_override_and_late_function_revocation(self):
        vm=self.vm(allow_extensions=True);pair=_MapEntry('K',1);vm.variables['p']=pair
        vm.register_function('Alias',type_of)
        self.assertIs(vm.execute('Alias(P)'),BSLType.KEY_AND_VALUE)
        vm.register_function('TypeOf',lambda value:'custom')
        self.assertEqual(vm.execute('TypeOf(P)'),'custom')
        vm=self.vm(allow_extensions=True)
        def change():vm.functions['typeof'].function=lambda value:'wrong';return pair
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):vm.execute('R=TypeOf(Change());')
        self.assertNotIn('r',vm.variables)

    def test_policy_and_lifetime_still_gate_classification(self):
        class Context(ServicesBoundary,BoundaryContext):pass
        vm=self.vm(allow_extensions=True);events=[]
        context=Context(services=vm.functions,policy=lambda action,name:events.append((action,name)) or False)
        context.vm=vm;context.enter()
        try:
            with self.assertRaises(BoundaryViolation):context.resolve_service('typeof')(_MapEntry('K',1))
        finally:context.leave()
        self.assertEqual(events,[('call','typeof')])
        def close():vm.close();return _MapEntry('K',1)
        vm.register_function('CloseNow',close)
        with self.assertRaises(BoundaryViolation):vm.execute('R=TypeOf(CloseNow());')
        self.assertNotIn('r',vm.variables)

    def test_exact_identity_only_and_payloads_are_not_inspected(self):
        events=[]
        class Evil:
            def __getattribute__(self,name):events.append('attribute');raise AssertionError(name)
            def __hash__(self):events.append('hash');raise AssertionError('hash')
            def __eq__(self,other):events.append('eq');raise AssertionError('eq')
            def __str__(self):events.append('str');raise AssertionError('str')
        class Child(_MapEntry):pass
        class Counterfeit:
            key=property(lambda self:events.append('key'))
            value=property(lambda self:events.append('value'))
        vm=self.vm();vm.variables['p']=_MapEntry(Evil(),Evil())
        self.assertIs(vm.execute('TypeOf(P)'),BSLType.KEY_AND_VALUE)
        for value in (Child(Evil(),Evil()),Counterfeit(),Evil()):
            vm.variables['p']=value
            with self.assertRaises(BSLRuntimeError):vm.execute('TypeOf(P)')
        self.assertEqual(events,[])

    def test_classification_does_not_expand_global_api_or_receiver_protocols(self):
        vm=self.vm();pair=_MapEntry('K',1);vm.variables['p']=pair
        self.assertIs(vm.execute('TypeOf(P)'),BSLType.KEY_AND_VALUE)
        with self.assertRaises(TypeError):type_of(pair)
        with self.assertRaises(TypeError):value_to_string_internal(pair)
        for source in ('P.Unknown()','P[0]','P.Value=2'):
            with self.subTest(source=source),self.assertRaises((BSLRuntimeError,BoundaryViolation)):vm.execute(source)
        self.assertEqual(pair.value,1)
        # The separately admitted BSL codec can round-trip the pair without
        # changing its read-only member protocol or the generic host API.
        vm.execute('Wire=ValueToStringInternal(P); Q=ValueFromStringInternal(Wire);')
        self.assertIs(vm.execute('TypeOf(Q)'),BSLType.KEY_AND_VALUE)
        self.assertEqual((vm.execute('Q.Key'),vm.execute('Q.Value')),('K',1))
        with self.assertRaises((BSLRuntimeError,BoundaryViolation)):vm.execute('Q.Value=2;')
        self.assertEqual(vm.execute('Q.Value'),1)

    def test_late_module_class_rebinding_is_not_blessed(self):
        vm=self.vm();pair=_MapEntry('K',1)
        class Fake:pass
        with patch('yadinassi.execution.codegen.experimental_naked_collections._MapEntry',Fake):
            vm.variables['p']=pair
            self.assertIs(vm.execute('TypeOf(P)'),BSLType.KEY_AND_VALUE)
            vm.variables['p']=Fake()
            with self.assertRaises(BSLRuntimeError):vm.execute('TypeOf(P)')

    def test_pre_lazy_class_rebinding_does_not_bless_counterfeit(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            import sys
            from unittest.mock import patch
            from yadinassi import Interpreter
            from yadinassi.execution.codegen import experimental_naked_collections as compiler
            from yadinassi.types.errors import BSLRuntimeError
            from yadinassi.types.values import BSLType
            pair=compiler._MapEntry('K',1)
            class Fake:pass
            if 'yadinassi.execution.direct.python_direct_services' in sys.modules:raise AssertionError('services imported early')
            with patch.object(compiler,'_MapEntry',Fake):
                vm=Interpreter();vm.variables['p']=Fake()
                try:vm.execute('TypeOf(P)')
                except BSLRuntimeError:pass
                else:raise AssertionError('counterfeit type admitted')
                vm.variables['p']=pair
                if vm.execute('TypeOf(P)') is not BSLType.KEY_AND_VALUE:raise AssertionError('canonical pair rejected')
                vm.close()
        ''')
        result=subprocess.run([sys.executable]+(['-O'] if not __debug__ else [])+['-c',script],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
