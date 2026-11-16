import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.experimental_naked_scalar_semantics import (
    truth, typed_find, presentation, concatenate, order, UnsupportedScalarSemantics)
from yadinassi.experimental_naked_collections import _NakedMap, _TypedMap
from yadinassi.experimental_naked_structure import _DirectStructure


class ScalarSemanticsTests(unittest.TestCase):
    def baseline(self, expression):
        vm = Interpreter(execution_backend='interpreter')
        vm.execute('result='+expression+';')
        return vm.variables['result']

    def test_truth_exact_numeric_and_boolean(self):
        for value, expected in [(True,True),(False,False),(Decimal(0),False),(Decimal(-2),True)]:
            self.assertIs(truth(value),expected)
        for value in [0,1,1.0,'',[],{},None]:
            with self.assertRaises(TypeError):truth(value)

    def test_typed_find_number_boolean_and_missing(self):
        self.assertEqual(typed_find([True,Decimal(1)],Decimal(1)),Decimal(1))
        self.assertIs(type(typed_find([True,Decimal(1)],Decimal(1))),Decimal)
        self.assertIsNone(typed_find([],Decimal(1)))
        self.assertEqual(typed_find([True,Decimal(1)],True),Decimal(0))

    def test_typed_find_collections_identity_not_contents(self):
        for value,other in [([],[]),({},{}),(_NakedMap(),_NakedMap()),(_TypedMap(),_TypedMap()),(_DirectStructure(),_DirectStructure())]:
            self.assertIsNone(typed_find([value],other))
            self.assertEqual(typed_find([value],value),Decimal(0))

    def test_presentations_match_interpreter(self):
        for value,expression in [([], 'New Array'),({}, 'New Structure'),(_NakedMap(),'New Map'),
                                 (_TypedMap(),'New Map'),(_DirectStructure(),'New Structure'),(True,'True'),(False,'False'),
                                 (Decimal('1234.50'),'1234.50'),(None,'Undefined')]:
            self.assertEqual(concatenate('x',value),self.baseline('"x"+'+expression))

    def test_native_string_order_is_explicit_divergence(self):
        for left,right in [('арбуз','Банан'),('apple','Banana'),('a','A'),('ё','ж'),('a_b','a-b')]:
            self.assertEqual(order(left,right,'<'),left<right)
            self.assertNotEqual(order(left,right,'<'),self.baseline(f'"{left}"<"{right}"'))
        self.assertFalse('é'=='e\u0301')
        self.assertEqual(order('é','e\u0301','<='),'é'<='e\u0301')

    def test_order_number_boolean_coercion_not_python_int(self):
        self.assertTrue(order(True,Decimal(1),'<='))
        self.assertFalse(order(Decimal(1),False,'<'))
        with self.assertRaises(TypeError):order(1,Decimal(1),'<')

    def test_surrogate_pair_join(self):
        self.assertEqual(concatenate('\ud83d','\ude00'),'😀')

    def test_host_hooks_never_called(self):
        events=[]
        class Host:
            def __str__(self):events.append('str');return 'host'
            def __eq__(self,other):events.append('eq');return True
            def __bool__(self):events.append('bool');return True
        value=Host()
        with self.assertRaises(UnsupportedScalarSemantics):presentation(value)
        with self.assertRaises(UnsupportedScalarSemantics):typed_find([value],value)
        with self.assertRaises(TypeError):truth(value)
        with self.assertRaises(TypeError):order(value,value,'<')
        self.assertIsNone(typed_find([value],Decimal(1)))
        self.assertEqual(events,[])

    def test_reference_backends_agree_while_native_variant_differs(self):
        import os
        from unittest.mock import patch
        from yadinassi.experimental_naked_collections import prepare
        for a,b in [('a','A'),('ё','ж'),('apple','Banana')]:
            source=f'result="{a}"<"{b}";'
            results=[]
            for backend in ('interpreter','compiled-strict'):
                vm=Interpreter(execution_backend=backend);vm.execute(source);results.append(vm.variables['result'])
            self.assertEqual(results[0],results[1])
            with patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'}):
                native=prepare(source,repairs=('native_order',)).run()['result']
            self.assertEqual(native,a<b);self.assertNotEqual(native,results[0])

    def test_hostile_metaclass_does_not_run_during_scalar_admission(self):
        events=[]
        class Meta(type):
            def __eq__(cls,other):events.append('meta');return True
        class Host(metaclass=Meta):
            def __str__(self):events.append('str');return 'unsafe'
            def __eq__(self,other):events.append('eq');return True
        value=Host()
        with self.assertRaises(UnsupportedScalarSemantics):presentation(value)
        with self.assertRaises(UnsupportedScalarSemantics):typed_find([],value)
        with self.assertRaises(TypeError):order(value,value,'<')
        self.assertEqual(events,[])
