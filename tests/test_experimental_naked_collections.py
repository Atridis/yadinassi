"""Experiment-only controls; no claim of production BSL equivalence."""
import os
import unittest
from unittest.mock import patch
from decimal import Decimal
from tests.retired_text_compiler import prepare,ENV

class NakedCollectionExperimentTests(unittest.TestCase):
    def setUp(self):
        self.enabled=patch.dict(os.environ,{ENV:'1'});self.enabled.start();self.addCleanup(self.enabled.stop)
    def test_explicit_opt_in_on_prepare_and_run(self):
        program=prepare('x=1;')
        with patch.dict(os.environ,{ENV:'0'}):
            with self.assertRaises(RuntimeError):prepare('x=1;')
            with self.assertRaises(RuntimeError):program.run()
    def test_direct_python_loop_and_routine(self):
        p=prepare('Function Inc(Val x) Return x+1;EndFunction a=New Array;For i=1 To 10 Do a.Add(Inc(i));EndDo;s=0;For Each x In a Do s=s+x;EndDo;')
        self.assertEqual(p.run()['s'],65)
        for helper in ('_method(', '_new(', '_get(', '_set(', '_iterate('):self.assertNotIn(helper,p.generated_source)
    def test_partial_state_survives_raw_exception(self):
        p=prepare('x=1;y=1/0;')
        with self.assertRaises(ArithmeticError):p.run()
        self.assertEqual(p.last_state['x'],1)
    def test_typed_map_keys_independent(self):
        source='m=New Map;m.Insert(True,1);m.Insert(1,2);n=m.Count();'
        self.assertEqual(prepare(source).run()['n'],1)
        self.assertEqual(prepare(source,repairs=('typed_map_keys',)).run()['n'],2)
        source='a=New Array;m=New Map;m.Insert(a,7);n=m.Get(a);'
        self.assertEqual(prepare(source,repairs=('typed_map_keys',)).run()['n'],7)
    def test_index_repair_independent(self):
        source='a=New Array;a.Add(7);n=a[-1];'
        self.assertEqual(prepare(source).run()['n'],7)
        with self.assertRaises(IndexError):prepare(source,repairs=('array_index_contract',)).run()
        for index in ('True','0.5'):
            with self.assertRaises((TypeError,ValueError)):
                prepare('a=New Array;a.Add(7);n=a['+index+'];',repairs=('array_index_contract',)).run()
    def test_insert_shape_repair_independent(self):
        source='a=New Array;a.Insert(3,7);n=a.Count();'
        self.assertEqual(prepare(source).run()['n'],1)
        self.assertEqual(prepare(source,repairs=('array_insert_shape',)).run()['a'],[None,None,None,Decimal(7)])
    def test_constructor_bounds_repair_independent(self):
        self.assertEqual(prepare('a=New Array(-1);').run()['a'],[])
        with self.assertRaises(ValueError):prepare('a=New Array(-1);',repairs=('constructor_bounds',)).run()
    def test_unknown_flag_rejected(self):
        with self.assertRaises(ValueError):prepare('x=1;',repairs=('unrequested_fix',))
