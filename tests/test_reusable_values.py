import unittest
from decimal import Decimal
from yadinassi.reusable_values import ReusableValueCache,argument_key,MAX_RETAINED_UNITS,MAX_ENTRIES
from yadinassi.structures import BSLStructure
from yadinassi.values import NULL
class CacheTests(unittest.TestCase):
    def setUp(self):self.time=0;self.c=ReusableValueCache(clock=lambda:self.time)
    def put(self,key=('x',),value=None):self.c.publish(self.c.reserve(key),value,1)
    def test_missing(self):self.assertEqual(self.c.lookup(('x',)),(False,None))
    def test_undefined_hit(self):self.put();self.assertEqual(self.c.lookup(('x',)),(True,None))
    def test_alias(self):
        a=[];self.put(value=a);a.append(1);self.assertIs(self.c.lookup(('x',))[1],a)
    def test_refresh(self):self.put();self.c.refresh();self.assertFalse(self.c.lookup(('x',))[0])
    def test_epoch(self):
        r=self.c.reserve(('x',));self.c.refresh();self.assertFalse(self.c.publish(r,1,1))
    def test_foreign_reservation(self):
        with self.assertRaises(ValueError):self.c.publish(ReusableValueCache().reserve(('x',)),1,1)
    def test_close(self):
        self.c.close()
        with self.assertRaises(ValueError):self.c.lookup(('x',))
    def test_idempotent_close(self):self.c.close();self.c.close()
    def test_replace_accounting(self):self.put();u=self.c._units;self.put();self.assertEqual(self.c._units,u)
    def test_lru(self):
        for i in range(MAX_ENTRIES+1):self.put((i,))
        self.assertFalse(self.c.lookup((0,))[0]);self.assertTrue(self.c.lookup((MAX_ENTRIES,))[0])
    def test_touch_lru(self):
        for i in range(MAX_ENTRIES):self.put((i,))
        self.c.lookup((0,));self.put((MAX_ENTRIES,));self.assertTrue(self.c.lookup((0,))[0]);self.assertFalse(self.c.lookup((1,))[0])
    def test_idle_before(self):self.put();self.time=359;self.assertTrue(self.c.lookup(('x',))[0])
    def test_idle_boundary(self):self.put();self.time=360;self.assertFalse(self.c.lookup(('x',))[0])
    def test_idle_reset(self):self.put();self.time=300;self.c.lookup(('x',));self.time=600;self.assertTrue(self.c.lookup(('x',))[0])
    def test_absolute_age(self):
        self.put()
        for time in (300,600,900):self.time=time;self.c.lookup(('x',))
        self.time=1200;self.assertFalse(self.c.lookup(('x',))[0])
    def test_discard(self):self.put();self.c.discard(('x',));self.assertEqual(self.c._units,0)
    def test_remeasure(self):self.put();u=self.c._units;self.c.revalidate(('x',),100);self.assertEqual(self.c._units,u+99)
    def test_remeasure_oversize(self):
        self.put()
        with self.assertRaises(ValueError):self.c.revalidate(('x',),MAX_RETAINED_UNITS)
        self.assertFalse(self.c.lookup(('x',))[0])
    def test_bad_key(self):
        with self.assertRaises(TypeError):self.c.reserve((object(),))
    def test_deep_key(self):
        key=()
        for _ in range(34):key=(key,)
        with self.assertRaises(ValueError):self.c.reserve(key)
    def test_oversize_publish(self):
        with self.assertRaises(ValueError):self.c.publish(self.c.reserve(('x',)),1,MAX_RETAINED_UNITS)
    def test_units_reject_bool(self):
        with self.assertRaises(ValueError):self.c.publish(self.c.reserve(('x',)),1,True)
class KeysTests(unittest.TestCase):
    def test_typed_boolean(self):self.assertNotEqual(argument_key((True,)),argument_key((Decimal(1),)))
    def test_null(self):self.assertNotEqual(argument_key((None,)),argument_key((NULL,)))
    def test_decimal_scale(self):self.assertEqual(argument_key((Decimal('1.00'),)),argument_key((Decimal('1'),)))
    def test_zero(self):self.assertEqual(argument_key((Decimal('-0.00'),)),argument_key((Decimal('0'),)))
    def test_structure_order(self):self.assertEqual(argument_key((BSLStructure('A,B',Decimal(1),'x'),)),argument_key((BSLStructure('B,A','x',Decimal(1)),)))
    def test_nested_closed(self):self.assertIsNone(argument_key((BSLStructure('A',BSLStructure()),)))
    def test_unsupported(self):self.assertIsNone(argument_key(([],)))
    def test_bounds(self):self.assertIsNone(argument_key(('x'*65537,)))
