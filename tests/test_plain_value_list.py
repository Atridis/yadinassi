import unittest
from unittest.mock import patch
from decimal import Decimal as D
from yadinassi.collections.plain_value_list import PlainValueList, PlainValueListItem
from yadinassi.collections.value_lists import BSLValueList


class PlainValueListTests(unittest.TestCase):
    def test_move_and_delete_use_internal_position_not_public_decimal(self):
        for kind in (PlainValueList, BSLValueList):
            with self.subTest(kind=kind):
                values = kind()
                first = values.add(D(3))
                second = values.add(D(5))
                foreign = kind().add(D(7))
                self.assertIs(type(values.index_of(second)), D)
                self.assertIs(type(values._index_of(second)), int)
                self.assertEqual(values.index_of(foreign), D(-1))
                with patch.object(kind, 'index_of', side_effect=AssertionError('public conversion')):
                    values.move(second, D(-1))
                    self.assertIs(values.get(D(0)), second)
                    values.delete(first)
                    with self.assertRaises(ValueError):
                        values.delete(foreign)
                    with self.assertRaises(ValueError):
                        values.delete(first)
                self.assertEqual(values.index_of(first), D(-1))
                self.assertEqual(values.count(), D(1))

    def test_build_read_and_item_metadata(self):
        values = PlainValueList()
        first = values.add(D(3), 'three', True, None)
        values.add(D(5))
        self.assertIsInstance(values, list)
        self.assertFalse(hasattr(first, '__dict__'))
        self.assertEqual(values.count(), D(2))
        self.assertIs(values.get(D(0)), first)
        self.assertEqual(sum(item[0] for item in values), D(8))
        first.set_member('Значение', D(4))
        self.assertEqual(first.get_member('Value'), D(4))
        self.assertEqual(first[1], 'three')
        self.assertTrue(first[2])

    def test_retain_identity_and_linear_id_lookup(self):
        values = PlainValueList()
        first = values.add(1); second = values.add(2)
        values.insert(0, 3)
        self.assertIs(values.get(1), first)
        values.delete(first)
        self.assertEqual(first.get_id(), D(0))
        self.assertIsNone(values.find_by_id(0))
        self.assertIs(values.find_by_id(second.get_id()), second)
        values.move(second, -1)
        self.assertIs(values.get(0), second)

    def test_copy_and_load_are_independent_but_payload_is_shared(self):
        payload = object()
        values = PlainValueList(); item = values.add(payload)
        clone = values.copy()
        self.assertIsNot(clone[0], item)
        self.assertIs(clone[0][0], payload)
        clone.fill_checks(True)
        self.assertFalse(item[2])
        clone.load_values([1, 2]); self.assertEqual(clone.unload_values(), [1, 2])
        self.assertEqual(len(values), 1)

    def test_no_opaque_conversion_comparison_or_iteration(self):
        called = []
        class Opaque:
            def __int__(self): called.append('int'); return 0
            def __index__(self): called.append('index'); return 0
            def __eq__(self, other): called.append('eq'); return True
            def __lt__(self, other): called.append('lt'); return True
            def __iter__(self): called.append('iter'); return iter(())
        a = Opaque(); b = Opaque(); values = PlainValueList(); values.add(a)
        self.assertIsNone(values.find_by_value(b))
        self.assertIs(values.find_by_value(a), values[0])
        for action in (lambda: values.get(a), lambda: values.insert(a, 1),
                       lambda: values.delete(a), lambda: values.move(0, a),
                       lambda: values.load_values(a),
                       lambda: values.sort_by_value()):
            with self.assertRaises(TypeError): action()
        self.assertEqual(called, [])
        self.assertNotEqual(values, PlainValueList())

    def test_tampered_item_cannot_run_storage_hooks(self):
        called = []
        class Foreign:
            def __getitem__(self, key): called.append('get'); return 1
            def __setitem__(self, key, value): called.append('set')
        values = PlainValueList(); list.append(values, Foreign())
        for operation in (lambda: values.get(0), lambda: values.find_by_value(1),
                          lambda: values.find_by_id(0), lambda: values.fill_checks(True),
                          values.unload_values, values.copy, values.sort_by_value):
            with self.assertRaises(TypeError): operation()
        self.assertEqual(called, [])

    def test_large_value_list_supports_add_insert_and_reordering(self):
        values = PlainValueList()
        values.load_values([1] * 100_001)
        values.add(2)
        values.insert(0, 3)
        self.assertEqual(len(values), 100_003)
        self.assertEqual(values.get(0)[0], 3)
        values.move(0, 1)
        self.assertEqual(values.get(1)[0], 3)

    def test_foreign_metaclass_equality_never_runs(self):
        called = []
        class Meta(type):
            def __eq__(self, other): called.append('meta_eq'); return False
        class Opaque(metaclass=Meta): pass
        values = PlainValueList(); values.add(Opaque())
        self.assertIsNone(values.find_by_value(Opaque()))
        with self.assertRaises(TypeError): values.sort_by_value()
        self.assertEqual(called, [])

    def test_native_sorting_and_negative_index_tradeoff(self):
        values = PlainValueList(); values.add(3, 'c'); values.add(1, 'a')
        values.sort_by_value(); self.assertEqual(values.unload_values(), [1, 3])
        values.sort_by_presentation(True); self.assertEqual(values.unload_values(), [3, 1])
        self.assertEqual(values.get(D(-1))[0], 1)
        self.assertEqual(values.get(D('0.5'))[0], 3)

if __name__ == '__main__': unittest.main()
