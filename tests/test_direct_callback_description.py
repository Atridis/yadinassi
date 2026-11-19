import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from yadinassi import Interpreter, BSLError
from yadinassi.direct_callbacks import CallbackDescription
from yadinassi.values import BSLType
from yadinassi.experimental_naked_boundaries import BoundaryViolation

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
    def test_readonly_and_private_attributes_closed(self):
        vm=Interpreter();vm.execute('C=New CallbackDescription("P");')
        for expr in ('C.ProcedureName="Other"','C.__class__','C.procedure_name','C.ProcedureName()'):
            with self.subTest(expr=expr),self.assertRaises((BSLError,BoundaryViolation)):vm.execute(expr)
        self.assertEqual(vm.variables['c'].procedure_name,'P')
