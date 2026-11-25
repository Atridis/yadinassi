"""Direct ErrorInfo snapshots, with explicit lifetime and observation boundaries."""
import unittest
from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.types.error_info import BSLErrorInfo
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectErrorInfoTests(unittest.TestCase):
    def vm(self, *, allow_extensions=False):
        vm=Interpreter(allow_extensions=allow_extensions);self.addCleanup(vm.close);return vm

    def test_source_ast_prepared_snapshot_and_fields_without_vm(self):
        from yadinassi.syntax.parser import parse
        source='Before=ErrorInfo();Try\n X=1/0;\nExcept E=ИнформацияОбОшибке();D=E.Описание;L=E.НомерСтроки;M=E.ИмяМодуля;S=E.ИсходнаяСтрока;EndTry;After=ErrorInfo();'
        for route in ('source','ast','prepared'):
            vm=self.vm()
            with ExitStack() as stack:
                if route=='source':vm.execute(source,'info.bsl')
                elif route=='ast':vm.execute_program(parse(source,'info.bsl'))
                else:vm.execute_prepared(vm.prepare(source,'info.bsl'))
            self.assertEqual(vm.variables['d'],'Деление на ноль');self.assertEqual(vm.variables['l'],Decimal(2))
            self.assertEqual(vm.variables['m'],'info.bsl');self.assertEqual(vm.variables['s'],' X=1/0;')
            self.assertTrue(vm.variables['before']._empty);self.assertTrue(vm.variables['after']._empty)
            vm.execute('Saved=E.Description;');self.assertEqual(vm.variables['saved'],'Деление на ноль')

    def test_nested_handlers_discard_outer_and_rethrow_keeps_snapshot(self):
        source='Try Raise "outer";Except A=ErrorInfo();Try Raise "inner";Except B=ErrorInfo();EndTry;C=ErrorInfo();EndTry;Try Try Raise "origin";Except E=ErrorInfo();Raise;EndTry;Except F=ErrorInfo();EndTry;'
        vm=self.vm();vm.execute(source)
        self.assertEqual(vm.variables['a'].description,'outer');self.assertEqual(vm.variables['b'].description,'inner')
        self.assertTrue(vm.variables['c']._empty);self.assertIs(vm.variables['e'],vm.variables['f'])

    def test_eval_does_not_inherit_caller_but_same_side_routine_does(self):
        source='Function F() Return ErrorInfo();EndFunction Try Raise "outer";Except A=F();B=Eval("ErrorInfo()");C=ErrorInfo();EndTry;'
        vm=self.vm();vm.execute(source)
        self.assertEqual(vm.variables['a'].description,'outer');self.assertTrue(vm.variables['b']._empty)
        self.assertIs(vm.variables['a'],vm.variables['c'])

    def test_server_crossing_is_fresh(self):
        vm=self.vm();vm.execute('&AtServerNoContext\nFunction F() Return ErrorInfo().Description;EndFunction Try Raise "outer";Except A=F();B=ErrorInfo().Description;EndTry;')
        self.assertEqual(vm.variables['a'],'');self.assertEqual(vm.variables['b'],'outer')

    def test_custom_registration_and_class_override_are_not_wrapped(self):
        vm=self.vm(allow_extensions=True);vm.register_function('ErrorInfo',lambda:'custom');self.assertEqual(vm.execute('ErrorInfo()'),'custom')
        with patch.object(Interpreter,'_error_info',lambda self:'class custom'):
            vm=self.vm(allow_extensions=True);self.assertEqual(vm.execute('ErrorInfo()'),'class custom')
        with self.assertRaises(BSLRuntimeError):self.vm().execute('ErrorInfo(1)')

    def test_readonly_assignment_evaluates_rhs_but_does_not_mutate(self):
        vm=self.vm(allow_extensions=True);events=[];vm.register_function('Touch',lambda:events.append(1) or 'changed')
        vm.execute('Try Raise "real";Except E=ErrorInfo();EndTry;Try E.Description=Touch();Except Caught=True;EndTry;')
        self.assertEqual(events,[1]);self.assertTrue(vm.variables['caught']);self.assertEqual(vm.variables['e'].description,'real')

    def test_hostile_subclass_and_malformed_field_not_dispatched(self):
        vm=self.vm();events=[]
        class Hostile(BSLErrorInfo):
            def get_member(self,name):events.append(name);raise AssertionError
        vm.variables['e']=Hostile('bad')
        with self.assertRaises(BoundaryViolation):vm.execute('E.Description')
        forged=BSLErrorInfo('before');object.__setattr__(forged,'description',object());vm.variables['e']=forged
        with self.assertRaises(BoundaryViolation):vm.execute('E.Description')
        self.assertEqual(events,[])
        vm.variables['e']=BSLErrorInfo('safe')
        def hostile_getattribute(self,name):events.append(name);raise AssertionError('host attribute')
        with patch.object(BSLErrorInfo,'__getattribute__',hostile_getattribute):
            self.assertEqual(vm.execute('E.Description'),'safe')
        self.assertEqual(events,[])

    def test_observation_is_lazy_and_cached(self):
        from yadinassi.execution.codegen import experimental_naked_errors as errors
        with patch.object(errors,'convert_error',wraps=errors.convert_error) as convert:
            vm=self.vm();vm.execute('Try X=1/0;Except A=ErrorInfo();B=ErrorInfo();D=ErrorDescription();EndTry;')
            self.assertEqual(convert.call_count,1);self.assertIs(vm.variables['a'],vm.variables['b'])
        with patch.object(errors,'convert_error',side_effect=AssertionError('unused')):
            self.vm().execute('Try X=1/0;Except Saved=1;EndTry;')

    def test_failed_handler_and_revoked_owner_do_not_leak(self):
        vm=self.vm(allow_extensions=True)
        with self.assertRaises(BSLRuntimeError):vm.execute('Try Raise "one";Except E=ErrorInfo();Raise "two";EndTry;')
        self.assertTrue(vm.execute('ErrorInfo()')._empty)
        vm.register_function('Close',vm.close)
        with self.assertRaises(BoundaryViolation):vm.execute('Try Raise "one";Except Close();E=ErrorInfo();EndTry;')

    def test_transaction_denial_remains_explicit_and_structured(self):
        from contextlib import closing
        from pathlib import Path
        import tempfile
        from yadinassi.configuration.configuration_accumulation_references import PROFILE
        from yadinassi.configuration.configuration_profile_import import prepare_directory,create_prepared
        root=Path(__file__).resolve().parents[1]
        prepared=prepare_directory(root/'scripts/inventory_reference_behavior/runtime_source',profile=PROFILE)
        with tempfile.TemporaryDirectory() as temp,closing(create_prepared(Path(temp)/'test.sqlite',prepared)) as context:
            with closing(Interpreter(database_context=context, allow_extensions=True)) as vm:
                vm._transaction_activation_allowed=False
                captured=[];vm.register_function('Capture',lambda info:captured.append(info.get_member('Description')),returns_value=False)
                vm.execute('Try BeginTransaction();Except E=ErrorInfo();Capture(E);EndTry;')
                self.assertEqual(captured,['Transactions require synchronous execution without pending tasks'])
                self.assertIsNone(getattr(context.backend,'_bsl_transaction',None))
                self.assertFalse(vm._transaction_activation_allowed)

    def test_public_snapshot_rebinding_never_calls_foreign_constructor(self):
        from yadinassi.types import error_info
        calls=[]
        class Fake:
            def __init__(self,*args,**kwargs):calls.append('constructor')
        def forged_empty():calls.append('empty');return Fake()
        with patch.object(error_info,'BSLErrorInfo',Fake),patch.object(error_info,'empty_error_info',forged_empty):
            vm=self.vm();vm.execute('Before=ErrorInfo();Try Raise "real";Except E=ErrorInfo();D=E.Description;EndTry;')
            self.assertIs(type(vm.variables['e']),BSLErrorInfo)
            self.assertEqual(vm.variables['d'],'real');self.assertTrue(vm.variables['before']._empty)
        self.assertEqual(calls,[])

    def test_custom_bound_diagnostics_never_use_callable_equality(self):
        from types import MethodType
        for name in ('ErrorInfo','ErrorDescription','ИнформацияОбОшибке','ОписаниеОшибки'):
            for mode in ('equal','hostile'):
                with self.subTest(name=name,mode=mode):
                    calls=[]
                    class Custom:
                        def __call__(self,owner):calls.append('call');return 'custom'
                        def __eq__(self,other):
                            calls.append('equality')
                            if mode=='hostile':raise AssertionError('foreign equality')
                            return True
                    vm=self.vm(allow_extensions=True);vm.register_function(name,MethodType(Custom(),vm))
                    vm.execute('R='+name+'();Try Raise "real";Except S='+name+'();EndTry;')
                    self.assertEqual(vm.variables['r'],'custom');self.assertEqual(vm.variables['s'],'custom')
                    self.assertEqual(calls,['call','call'])
