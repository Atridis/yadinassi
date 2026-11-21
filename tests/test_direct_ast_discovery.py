"""Regression for imported oracle TestCases duplicating partition identities."""
import importlib
import unittest
from collections import Counter

class DirectASTDiscoveryTests(unittest.TestCase):
    def test_oracle_fixture_is_discovered_only_in_its_defining_module(self):
        names = ('externals', 'callables', 'dynamic_new', 'omissions', 'native_methods', 'raise')
        counts = Counter()
        loader = unittest.TestLoader()
        for suffix in names:
            module = importlib.import_module('test_experimental_direct_ast_' + suffix)
            for group in loader.loadTestsFromModule(module):
                for test in group:
                    counts[test.id()] += 1
        self.assertTrue(counts)
        self.assertTrue(all(count == 1 for count in counts.values()), counts)
        original = [name for name in counts if '.DirectASTExternalTests.' in name]
        self.assertEqual(len(original), 2)
