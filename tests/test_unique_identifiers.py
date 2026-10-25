"""Local candidate expectations only: no test here is native evidence."""
from dataclasses import FrozenInstanceError
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.values import BSLType, equal
from yadinassi.type_values import type_of
from yadinassi.value_checks import value_is_filled
from yadinassi.maps import BSLMap, BSLFixedMap

A = '01234567-89ab-4cde-8f01-23456789abcd'
B = '01234567-89ab-4cde-8f01-23456789abce'
ZERO = '00000000-0000-0000-0000-000000000000'


class UUIDCandidateTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda _: None)

    def test_canonical_parser_and_immutable_value_identity(self):
        a, b = BSLUUID(A), BSLUUID(A.upper())
        self.assertEqual(str(b), A)
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertFalse(equal(a, A))
        self.assertNotEqual(a, BSLUUID(B))
        self.assertIs(type_of(a), BSLType.UUID)
        with self.assertRaises((FrozenInstanceError, TypeError)):
            a.text = B
        with self.assertRaises((FrozenInstanceError, TypeError)):
            del a.text

    def test_strict_bounded_local_grammar_not_python_uuid_grammar(self):
        for text in ['', ' '+A, A+' ', A+'\n', '{'+A+'}', A.replace('-', ''),
                     'urn:uuid:'+A, A[:-1]+'g', '１'+A[1:], 'x'*100000]:
            with self.subTest(text=text[:40]), self.assertRaises(ValueError):
                BSLUUID(text)
        class Hostile(str):
            def __len__(self):
                raise AssertionError('host hook')
        for value in [None, True, Decimal(1), BSLUUID(A), Hostile(A)]:
            with self.assertRaises(TypeError):
                BSLUUID(value)

    def test_generation_policy_is_local_provisional_and_omission_is_distinct(self):
        with patch('yadinassi.unique_identifiers.secrets.token_bytes', return_value=bytes(16)):
            self.assertEqual(str(BSLUUID()), '00000000-0000-4000-8000-000000000000')
        with self.assertRaises(TypeError):
            BSLUUID(None)
        value = BSLUUID()
        self.assertRegex(str(value), r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$')
        self.assertEqual(value, BSLUUID(str(value)))

    def test_filled_local_candidate_zero_policy(self):
        self.assertFalse(value_is_filled(BSLUUID(ZERO)))
        self.assertTrue(value_is_filled(BSLUUID(A)))
        with self.assertRaises(TypeError):
            value_is_filled(BSLType.UUID)  # no inference about type-value filled

    def test_map_value_keys_distinct_from_strings_and_fixed_lookup(self):
        m = BSLMap(); a = BSLUUID(A)
        m.insert(a, 'first'); m.insert(BSLUUID(A.upper()), 'second'); m.insert(A, 'string')
        self.assertEqual(len(m._items), 2)
        self.assertEqual(m.get(BSLUUID(A)), 'second')
        self.assertEqual(BSLFixedMap(m).get_index(BSLUUID(A)), 'second')
        m.delete(BSLUUID(A)); self.assertEqual(len(m._items), 1)
        self.assertEqual(m.get(A), 'string')

    def test_static_dynamic_constructors_aliases_and_collection_find(self):
        self.vm.execute(f'''u = New UUID("{A}");
            args = New Array; args.Add("{A.upper()}");
            a = New Array; a.Add(u);''')
        for expr in ['TypeOf(u) = Type("УникальныйИдентификатор")',
                     'TypeOf(u) = Type("uUiD")',
                     'u = New УникальныйИдентификатор(String(u))',
                     'u = New("UUID", args)', 'u = New(Type("UUID"), args)',
                     'a.Find(New UUID(String(u))) = 0',
                     'ValueIsFilled(u)', 'TypeOf(New UUID) = Type("UUID")']:
            with self.subTest(expr=expr):
                self.assertIs(self.vm.execute("(" + expr + ")"), True)
        for expr in ['New UUID(Undefined)', 'New UUID(,)', 'New UUID("'+A+'", 1)',
                     'Type("UniqueIdentifier")', 'New UniqueIdentifier',
                     'u.text', 'u.is_filled()', 'u < u', 'u + 1', 'Type("UnknownTree")']:
            with self.subTest(expr=expr), self.assertRaises(BSLError):
                self.vm.execute(expr)

    def test_unmeasured_surfaces_fail_closed(self):
        self.vm.execute(f'u = New UUID("{A}"); ts = New Array; ts.Add(Type("UUID"));')
        for expr in ['ValueToStringInternal(u)', 'ValueToStringInternal(Type("UUID"))',
                     'XMLString(u)', 'XMLValue(Type("UUID"), String(u))',
                     'New TypeDescription("UUID")', 'New TypeDescription(ts)',
                     'New TypeDescription("String,UUID")']:
            with self.subTest(expr=expr), self.assertRaises(BSLError):
                self.vm.execute(expr)
        with self.assertRaises(TypeError):
            Interpreter._copy_context_packet([BSLUUID(A)])
        with self.assertRaises(TypeError):
            Interpreter._copy_context_packet([self.vm.execute('a = New Array; a.Add(u); a')])


if __name__ == '__main__':
    unittest.main()
