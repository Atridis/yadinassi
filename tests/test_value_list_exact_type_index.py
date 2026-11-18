"""ValueList validation uses canonical exact identities without host callbacks."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi.value_lists import BSLValueList, _value
from yadinassi import type_values

class ValueListExactTypeIndexTests(unittest.TestCase):
    def test_every_registered_exact_type_preserves_old_classification(self):
        # Construction is not necessary to check the acceptance predicate. Some
        # canonical families require application-owned factories.
        for kind, _, _ in type_values._VALUE_TYPES:
            with self.subTest(kind=kind.__name__):
                entry=type_values._STATIC_VALUE_TYPES.get(id(kind))
                self.assertIsNotNone(entry)
                self.assertIs(entry[0],kind)

    def test_real_scalar_add_and_set_preserve_values(self):
        values=BSLValueList()
        for value in (None, True, False, Decimal('12.25'), 'text'):
            item=values.add(value)
            self.assertIs(item.value,value)
            item.set_member('Value',value)
            self.assertIs(item.value,value)

    def test_hostile_metaclass_and_decimal_subclass_rejected_without_callbacks(self):
        effects=[]
        class Meta(type):
            def __hash__(cls):effects.append('hash');raise AssertionError
            def __eq__(cls,other):effects.append('eq');raise AssertionError
        class Hostile(metaclass=Meta):pass
        class Number(Decimal):pass
        for value in (Hostile(),Number(1)):
            with self.assertRaises(ValueError):_value(value)
        self.assertEqual(effects,[])

    def test_retained_identity_is_checked_not_only_integer_key(self):
        class Unknown:pass
        with patch.dict(type_values._STATIC_VALUE_TYPES,{id(Unknown):(Decimal,None)}):
            with self.assertRaises(ValueError):_value(Unknown())

    def test_value_constraints_and_failed_add_are_unchanged(self):
        values=BSLValueList()
        for value in (Decimal('NaN'),Decimal('Infinity'),Decimal('1'*4097),'x'*1000001):
            with self.subTest(kind=type(value)):
                with self.assertRaises(ValueError):values.add(value)
                self.assertEqual(values.items,[])
                self.assertEqual(values._by_id,{})
                self.assertEqual(values._next_id,0)

    def test_replaced_registry_preserves_live_membership(self):
        class Added:pass
        value=Added()
        with patch.object(type_values,'_VALUE_TYPES',((Added,None,''),)):
            self.assertIs(_value(value),value)
            with self.assertRaises(ValueError):_value(Decimal(3))
        with self.assertRaises(ValueError):_value(value)

if __name__=='__main__':unittest.main()
