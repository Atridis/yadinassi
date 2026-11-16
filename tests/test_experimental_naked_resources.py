"""Resource contract parity without unsafe allocations or backend wrappers."""
import unittest
from decimal import Decimal as D
from unittest.mock import patch
from yadinassi import Interpreter,values
from yadinassi.values import BSLArray
from yadinassi import experimental_naked_resources as resources


def native_shape(value):
    return [native_shape(x) if isinstance(x,BSLArray) else x for x in value.items]

class NakedResourcesTests(unittest.TestCase):
    def compare(self,dimensions,cap=40,depth=64):
        outcomes=[]
        with patch.object(values,'_MAX_ARRAY_CONSTRUCTION',cap),patch.object(values,'_MAX_ARRAY_DIMENSIONS',depth):
            for direct in (False,True):
                try:
                    value=resources.bounded_array(*dimensions) if direct else native_shape(BSLArray(*dimensions))
                    outcomes.append(('ok',value))
                except Exception as error:outcomes.append((type(error),str(error)))
        self.assertEqual(*outcomes)
        return outcomes[0]
    def test_small_patched_vm_cap_refuses_before_array_publication(self):
        with patch.object(values,'_MAX_ARRAY_CONSTRUCTION',4):
            vm=Interpreter()
            with self.assertRaisesRegex(Exception,'предел ресурсов'):vm.execute('a=New Array(5);')
            self.assertNotIn('a',vm.variables)
            with self.assertRaisesRegex(ValueError,'предел ресурсов'):resources.bounded_array(D(5))
    def test_simple_boundaries_and_empty(self):
        for dimensions in ((),(D(0),),(D(4),),(D(5),)):self.compare(dimensions,cap=4)
    def test_nested_objects_count_not_just_leaf_slots(self):
        self.assertEqual(self.compare((D(2),D(3)),cap=10)[0],'ok')
        self.assertIs(self.compare((D(2),D(3)),cap=9)[0],ValueError)
    def test_independent_nested_arrays(self):
        array=resources.bounded_array(D(2),D(2));array[0][0]=7
        self.assertEqual(array,[[7,None],[None,None]])
        self.assertIsNot(array[0],array[1])
    def test_dimension_limit(self):
        self.compare((D(1),)*64,cap=127)
        self.compare((D(1),)*65,cap=129)
    def test_bad_values_match(self):
        for dimensions in ((D(-1),),(D('0.5'),),(True,),(D('NaN'),),(D('Infinity'),),(D(0),D(2)),(D(1),D(-2))):self.compare(dimensions)
    def test_huge_exponent_rejected_before_int(self):
        with patch.object(resources,'int',side_effect=AssertionError('integer materialized'),create=True):
            with self.assertRaisesRegex(ValueError,'предел ресурсов'):resources.bounded_array(D('1e1000000'))
            with self.assertRaisesRegex(ValueError,'предел роста'):resources.bounded_insert([],D('1e1000000'))
    def test_all_dimensions_validate_before_integer_conversion(self):
        with patch.object(resources,'int',side_effect=AssertionError('integer materialized'),create=True):
            with self.assertRaisesRegex(ValueError,'отрицательным'):resources.bounded_array(D(1),D(-1))
    def test_insert_cap_matches_and_failure_has_no_mutation(self):
        with patch.object(values,'_MAX_INSERT_GROWTH',4):
            for index in (D(0),D(1),D(2),D(5),D(6),D(-1),D('0.5'),True,D('Infinity')):
                reference=BSLArray();reference.items[:]=[1,2];direct=[1,2];outcomes=[]
                for action in (lambda:reference.insert(index,7),lambda:resources.bounded_insert(direct,index,7)):
                    try:outcomes.append(('ok',action()))
                    except Exception as error:outcomes.append((type(error),str(error)))
                self.assertEqual(*outcomes);self.assertEqual(reference.items,direct)
                if outcomes[0][0]!='ok':self.assertEqual(direct,[1,2])
    def test_insert_missing_value_and_explicit_caps(self):
        array=[];resources.bounded_insert(array,D(2),max_growth=3);self.assertEqual(array,[None,None,None])
        with self.assertRaises(ValueError):resources.bounded_array(D(3),max_slots=2)
        with self.assertRaises(ValueError):resources.bounded_array(D(1),D(1),max_dimensions=1)
    def test_caps_are_read_from_shared_runtime_constants(self):
        with patch.object(values,'_MAX_ARRAY_CONSTRUCTION',1):
            with self.assertRaises(ValueError):resources.bounded_array(D(2))
        self.assertEqual(resources.bounded_array(D(2)),[None,None])
