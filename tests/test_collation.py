"""Fixed UCA baseline invariants; only the owner fixture asserts native parity."""

from hashlib import sha256
from itertools import product
from pathlib import Path
import unittest
from unittest.mock import patch

import pyuca

from yadinassi import BSLError, Interpreter
from yadinassi.collation import (
    MAX_STRING_LENGTH, TABLE_NAME, TABLE_SHA256, _collator, string_key,
)
from yadinassi.numeric.numbers import minimum, maximum


class CollationTests(unittest.TestCase):
    def test_selected_table_hash_and_explicit_version(self):
        self.assertEqual(sha256(Path(pyuca.__file__).with_name(TABLE_NAME).read_bytes()).hexdigest(),
                         TABLE_SHA256)
        self.assertEqual(_collator().UCA_VERSION, '10.0.0')

    def test_shared_relational_operators(self):
        vm = Interpreter()
        for lower, upper in [('a', 'A'), ('Aa', 'az'), ('е', 'ё'), ('я', 'Я')]:
            vm.variables.update(left=lower, right=upper)
            for expression in ('left < right', 'left <= right', 'right > left',
                               'right >= left', 'left <> right'):
                self.assertTrue(vm.execute(expression))
            self.assertFalse(vm.execute('(left = right)'))
            self.assertEqual(vm.execute('Min(left, right)'), lower)

    def test_order_invariants(self):
        values = ['', 'a', 'A', 'aa', 'az', 'Aa', 'е', 'ё', 'я', 'Я', '10', '2',
                  'é', 'e\u0301', '\x00', '🙂']
        keys = [string_key(value) for value in values]
        for a in keys:
            self.assertEqual(a, a)
            self.assertFalse(a < a)
        for a, b in product(keys, repeat=2):
            self.assertEqual(a < b, b > a)
            self.assertEqual(a <= b and b <= a, a == b)
        for a, b, c in product(keys, repeat=3):
            if a <= b and b <= c:
                self.assertLessEqual(a, c)

    def test_key_equivalence_keeps_exact_equality_separate(self):
        # UCA behavior, not a claim about unprobed native canonical equivalents.
        vm = Interpreter()
        for a, b in [('é', 'e\u0301'), ('', '\x00')]:
            self.assertEqual(string_key(a), string_key(b))
            vm.variables.update(a=a, b=b)
            self.assertFalse(vm.execute('(a = b)'))
            self.assertTrue(vm.execute('a <= b'))
            self.assertTrue(vm.execute('a >= b'))
            for function in (minimum, maximum):
                self.assertIs(function(a, b), a)
                self.assertIs(function(b, a), b)

    def test_bounded_work_and_no_input_cache(self):
        self.assertIs(_collator(), _collator())
        self.assertEqual(_collator.cache_info().maxsize, 1)
        self.assertFalse(hasattr(string_key, 'cache_info'))
        self.assertEqual(string_key('a' * MAX_STRING_LENGTH),
                         string_key('a' * MAX_STRING_LENGTH))
        with self.assertRaisesRegex(ValueError, 'ресурсный предел'):
            string_key('a' * (MAX_STRING_LENGTH + 1))
        with patch('yadinassi.collation.unicodedata.normalize', return_value='a' * 16385):
            with self.assertRaisesRegex(ValueError, 'нормализации'):
                string_key('a')
        vm = Interpreter()
        vm.variables['large'] = 'a' * (MAX_STRING_LENGTH + 1)
        for expression in ('Min(large)', 'Max("a", large)', 'large < "b"'):
            with self.assertRaises(BSLError):
                vm.execute(expression)
        # The ordering resource limit does not alter equality or string storage.
        self.assertTrue(vm.execute('(large = large)'))

    def test_rejects_modified_table(self):
        _collator.cache_clear()
        try:
            with patch('yadinassi.collation.Path.read_bytes', return_value=b'changed'):
                with self.assertRaisesRegex(ValueError, 'таблица'):
                    string_key('a')
                with self.assertRaises(BSLError):
                    Interpreter().execute('Min("a", "b")')
            with patch('yadinassi.collation.Path.read_bytes', side_effect=OSError('missing')):
                output = []
                Interpreter(output=output.append).execute(
                    'Try Max("a", "b"); Except Message("caught"); EndTry;')
                self.assertEqual(output, ['caught'])
        finally:
            _collator.cache_clear()


if __name__ == '__main__':
    unittest.main()
