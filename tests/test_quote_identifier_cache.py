import unittest
from unittest.mock import patch
from yadinassi import sqlite_catalog_layout as layout
from yadinassi.catalog_backend import BackendError

class QuoteIdentifierCacheTests(unittest.TestCase):
    def tearDown(self):layout._quote_identifier.cache_clear()

    def test_exact_type_before_cache_hash_or_equality(self):
        layout.quote_identifier('safe')
        class Evil(str):
            def __hash__(self):raise AssertionError('host hash')
            def __eq__(self,other):raise AssertionError('host equality')
        for value in (Evil('safe'),[],None,True):
            with self.subTest(value=type(value).__name__),self.assertRaises(BackendError):layout.quote_identifier(value)

    def test_invalid_identifiers_never_become_successes(self):
        for value in ('','a\x00b','a\nb','\ud800','a'*1025,'я'*513):
            for _ in range(2):
                with self.subTest(value=repr(value)),self.assertRaises(BackendError):layout.quote_identifier(value)
        self.assertEqual(layout.quote_identifier('a"b'),'"a""b"')
        self.assertEqual(layout.quote_identifier('я'*512),'"'+'я'*512+'"')

    def test_bound_and_current_length_limit(self):
        layout.quote_identifier('abc')
        with patch.object(layout,'_MAX_IDENTIFIER_BYTES',2):
            with self.assertRaises(BackendError):layout.quote_identifier('abc')
        for i in range(600):layout.quote_identifier('field'+str(i))
        self.assertLessEqual(layout._quote_identifier.cache_info().currsize,512)
