"""Reverse keys reflect live membership, not cached module admission."""
import unittest

from yadinassi.configuration.source_instances import SourceInstances


class SourceInstancesTests(unittest.TestCase):
    def test_alias_replacement_follows_forward_order_and_identity(self):
        class EqualOwners:
            def __eq__(self, other):
                raise AssertionError('instance indexing must not compare owners')

        first, second = EqualOwners(), EqualOwners()
        registry = SourceInstances()
        a, b, c = ('a','client',False), ('b','client',False), ('c','client',False)
        registry.update({a:first, b:second, c:first})
        self.assertEqual(registry.keys_for_owner(first),(a,c))
        registry[b] = first
        self.assertEqual(registry.keys_for_owner(first),(a,b,c))
        self.assertEqual(registry.keys_for_owner(second),())
        self.assertIs(registry.pop(a),first)
        registry[a] = second
        self.assertEqual(registry.keys_for_owner(first),(b,c))
        self.assertEqual(registry.keys_for_owner(second),(a,))
        self.assertEqual(tuple(registry),(b,c,a))
        registry.clear()
        self.assertFalse(registry)
        self.assertEqual(registry.keys_for_owner(first),())
        self.assertEqual(registry.keys_for_owner(second),())
