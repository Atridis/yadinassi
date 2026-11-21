import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from yadinassi import Interpreter, BSLError
from yadinassi.application.direct_callbacks import CallbackDescription
from yadinassi.types.values import BSLType
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectCallbackDescriptionTests(unittest.TestCase):
    def test_constructor_properties_bilingual_and_passive(self):
        for prepared in (False,True):
            vm=Interpreter()
            source='''Count=0; Procedure Handler(A,B) Count=Count+1;EndProcedure;
Extra=New Array;Extra.Add(1);
C=New ОписаниеОповещения("Handler",Undefined,Extra);
Name=C.ИмяПроцедуры;Copy=C.ДополнительныеПараметры;
Kind=TypeOf(C);Text=String(C);'''
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertEqual(vm.variables['count'],0)
            self.assertEqual(vm.variables['name'],'Handler')
            self.assertIs(vm.variables['copy'],vm.variables['extra'])
            self.assertIs(vm.variables['kind'],BSLType.CALLBACK_DESCRIPTION)
            self.assertEqual(vm.variables['text'],'ОписаниеОповещения')
            with self.assertRaises(FrozenInstanceError):vm.variables['c'].procedure_name='Other'
    def test_empty_omissions_and_validation(self):
        vm=Interpreter()
        for expression in ('New CallbackDescription','New CallbackDescription(,,,,)','New CallbackDescription(Undefined,Undefined)'):
            vm.execute('C='+expression+';');self.assertIsNone(vm.variables['c'].procedure_name)
        for expression in ('New CallbackDescription(1)','New CallbackDescription("P",Undefined,Undefined,"Error")','New CallbackDescription(1,2,3,4,5,6)'):
            with self.assertRaises(BSLError):vm.execute('C='+expression+';')
    def test_no_dispatch_or_host_target_lookup(self):
        class Opaque:
            def __getattr__(self,name):raise AssertionError('target reflection')
        opaque=Opaque();vm=Interpreter();vm.variables['target']=opaque
        vm.execute('C=New CallbackDescription("Handler",Target,7);')
        self.assertIs(vm.variables['c'].module,opaque)
        with self.assertRaises(BSLError):vm.execute('RunCallback(C,1);')
    def test_prepared_dispatch_accepts_only_ready_current_module(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Var Seen; Procedure Store(V,E) Export Seen=V+E; EndProcedure '
                   'Function Add(V,E,Tail=3) Export Return V+E+Tail; EndFunction '
                   'Proc=New CallbackDescription("Store",ThisObject,5); '
                   'Fun=New CallbackDescription("Add",ThisObject,2); Seen=0;')
        call = vm.prepare('P=RunCallback(Proc,7); F=ВыполнитьОбработкуОповещения(Fun,4);')
        vm.execute_prepared(call)
        self.assertEqual((vm.variables['seen'], vm.variables['p'], vm.variables['f']), (12, None, 9))

    def test_eval_and_execute_call_same_module_without_service_capture(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Function Add(V,E) Export Return V+E; EndFunction '
                   'D=New CallbackDescription("Add",ThisObject,5); A=0;')
        self.assertEqual(vm.execute('Eval("RunCallback(D,3)")'), 8)
        vm.execute('Execute("A=RunCallback(D,4);");')
        self.assertEqual(vm.variables['a'], 9)

    def test_argument_closing_owner_blocks_prepared_dispatch(self):
        events = []
        def output(message):
            events.append(message)
            vm.close()

        vm = Interpreter(output)
        self.addCleanup(vm.close)
        vm.execute('Var Seen; Seen=0; '
                   'Procedure Store(V,E) Export Seen=1; EndProcedure '
                   'Function Value() Message("close"); Return 2; EndFunction '
                   'D=New CallbackDescription("Store",ThisObject);')
        call = vm.prepare('RunCallback(D,Value());')
        with self.assertRaises(BoundaryViolation):
            vm.execute_prepared(call)
        self.assertEqual(events, ['close'])
        self.assertEqual(vm.variables['seen'], 0)

    def test_readonly_and_private_attributes_closed(self):
        vm=Interpreter();vm.execute('C=New CallbackDescription("P");')
        for expr in ('C.ProcedureName="Other"','C.__class__','C.procedure_name','C.ProcedureName()'):
            with self.subTest(expr=expr),self.assertRaises((BSLError,BoundaryViolation)):vm.execute(expr)
        self.assertEqual(vm.variables['c'].procedure_name,'P')
