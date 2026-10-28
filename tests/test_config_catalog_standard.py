"""Entirely invented positional inputs; no native bytes or platform claim."""
import dataclasses
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'yadinassi/storage'))
import config_catalog_name as parser
from filedb_catalog import CatalogLimits, ResourceLimit, _Budget


def node(*values):
    return '{' + ','.join(values) + '}'


def document(name='"Invented"', code='2', kind='1', description='0', skipped='0'):
    fields = ['0'] * 20
    fields[9] = node('0', node('0', '0', name))
    fields[17:20] = [code, kind, description]
    return node(skipped, node(*fields)).encode()


def prefix(**options):
    # Replace the closing delimiter for field19 with a comma, discard closes.
    return document(**options)[:-2] + b','


class CatalogStandardTests(unittest.TestCase):
    def parse(self, data=None, *, limits=None, budget=None):
        budget = budget if budget is not None else _Budget(CatalogLimits())
        result = parser.project_catalog_standard_prefix(
            document() if data is None else data, limits=limits, budget=budget)
        return result, budget

    def test_fields_frozen_and_accounting(self):
        result, budget = self.parse()
        self.assertEqual(dataclasses.asdict(result), dict(
            name='Invented', code_length=2, code_type=1, description_length=0))
        with self.assertRaises(dataclasses.FrozenInstanceError): result.name = 'x'
        self.assertEqual(budget.counts['bytes_processed'], 4*len(document()))
        self.assertEqual(budget.counts['output_bytes'], parser.STANDARD_OUTPUT_RESERVATION)
        self.assertGreater(budget.counts['tokens'], 20)

    def test_positional_fields_and_both_code_types(self):
        for kind in ('0', '1'):
            result, _ = self.parse(document('"Имя😀"', '123', kind, '456', '"decoy"'))
            self.assertEqual((result.name, result.code_length, result.code_type,
                              result.description_length), ('Имя😀', 123, int(kind), 456))
        result, _ = self.parse(document('"a""b,{}"', '0', '0', '0', '{}'))
        self.assertEqual(result.name, 'a"b,{}')

    def test_delimiter_and_suffix_contract(self):
        for tail in (b'', b'\xff', b'\x00', b'{unterminated', b'\xef\xbb\xbf'):
            self.assertEqual(self.parse(prefix()+tail)[0].description_length, 0)
            self.assertEqual(self.parse(document()+tail)[0].description_length, 0)
        with self.assertRaisesRegex(parser.CatalogStandardError, 'integer_syntax'):
            self.parse(prefix()[:-1])

    def test_old_entrypoint_does_not_validate_extended_prefix(self):
        for data in (document(code='bad'), document(description='{}'),
                     document().replace(b'},0,0,0', b'},\xff,0,0', 1)):
            old = parser.project_catalog_name_prefix(data, budget=_Budget(CatalogLimits()))
            self.assertEqual(old.name, 'Invented')
            with self.assertRaises(parser.CatalogStandardError): self.parse(data)

    def test_numeric_grammar_is_deliberately_canonical_subset(self):
        for spelling in ('', '"2"', '-1', '+1', '00', '01', '1.0', '1e0',
                         '１', '2 ', '2\n', 'NaN', '{2}'):
            for field in ('code', 'kind', 'description'):
                with self.subTest(field=field, spelling=spelling):
                    with self.assertRaises(parser.CatalogStandardError):
                        self.parse(document(**{field: spelling}))
        # Boundary whitespace before a scalar belongs to the walker, not digits.
        self.assertEqual(self.parse(document(code=' \r\n2'))[0].code_length, 2)

    def test_numeric_bounds_and_domain_separate(self):
        self.assertEqual(self.parse(document(code='2147483647'))[0].code_length, 2147483647)
        for value in ('2147483648', '99999999999'):
            with self.assertRaisesRegex(parser.CatalogStandardError, 'integer_bound'):
                self.parse(document(description=value))
        for kind in ('2', '2147483647'):
            with self.assertRaisesRegex(parser.CatalogStandardError, 'code_type'):
                self.parse(document(kind=kind))
        self.parse(document(code='0'), limits=parser.CatalogStandardLimits(max_length=0))
        with self.assertRaisesRegex(parser.CatalogStandardError, 'integer_bound'):
            self.parse(limits=parser.CatalogStandardLimits(max_length=1))

    def test_missing_fields_and_wrong_containers(self):
        for data in (b'{}', b'{0}', b'{0,0}', b'{0,{}}', document(name='{}'),
                     document().replace(b',2,1,0', b',2'),
                     document().replace(b',2,1,0', b',2,1')):
            with self.subTest(data=data), self.assertRaises(parser.CatalogStandardError):
                self.parse(data)
        data = document().replace(b'{0,{0,0,"Invented"}}', b'{0,0}')
        with self.assertRaisesRegex(parser.CatalogStandardError, 'expected_object'):
            self.parse(data)

    def test_null_positions_preserved(self):
        data = document().replace(b'{0,{0,0,"Invented"}}', b'{,{,,"Invented"}}')
        self.assertEqual(self.parse(data)[0].name, 'Invented')

    def test_visited_utf8_controls_and_opaque_name_limits(self):
        for bad in (b'\xff', b'\xc0\x80', b'\xed\xa0\x80', b'\xf4\x90\x80\x80',
                    b'\xe2\x82', b'\x00', b'\t', b'\x7f', b'\xef\xbb\xbf'):
            with self.subTest(bad=bad), self.assertRaises(parser.CatalogStandardError):
                self.parse(document().replace(b'Invented', bad))
        self.parse(document('"x"', skipped='"'+'a'*2000+'"'),
                   limits=parser.CatalogStandardLimits(max_name_chars=1, max_name_bytes=1))
        self.parse(b'\xef\xbb\xbf \r\n'+document())
        for limits, code in ((parser.CatalogStandardLimits(max_name_chars=1), 'name_chars'),
                             (parser.CatalogStandardLimits(max_name_bytes=3), 'name_bytes')):
            with self.assertRaisesRegex(parser.CatalogStandardError, code):
                self.parse(document('"😀😀"'), limits=limits)

    def test_strict_limits_and_types(self):
        for field in dataclasses.fields(parser.CatalogStandardLimits):
            maximum = getattr(parser.CatalogStandardLimits(), field.name)
            for invalid in (True, -1, maximum+1, 1.0, '1', None):
                with self.subTest(field=field.name, invalid=invalid):
                    with self.assertRaises(parser.CatalogStandardError):
                        parser.CatalogStandardLimits(**{field.name: invalid})
        for limits in ({}, parser.CatalogNameLimits()):
            with self.assertRaisesRegex(parser.CatalogStandardError, 'limits_type'):
                self.parse(limits=limits)
        for data in (bytearray(document()), memoryview(document()), 'x'):
            with self.assertRaisesRegex(parser.CatalogStandardError, 'input_type'): self.parse(data)
        with self.assertRaisesRegex(parser.CatalogNameError, 'limits_type'):
            parser.project_catalog_name_prefix(document(), budget=_Budget(CatalogLimits()),
                                               limits=parser.CatalogStandardLimits())

    def test_input_token_and_depth_edges(self):
        self.parse(limits=parser.CatalogStandardLimits(max_input_bytes=len(document())))
        with self.assertRaisesRegex(parser.CatalogStandardError, 'input_bytes'):
            self.parse(limits=parser.CatalogStandardLimits(max_input_bytes=len(document())-1))
        _, budget = self.parse()
        used = budget.counts['tokens']
        self.parse(limits=parser.CatalogStandardLimits(max_tokens=used, max_depth=4))
        self.parse(budget=_Budget(CatalogLimits(max_tokens=used)))
        with self.assertRaisesRegex(parser.CatalogStandardError, 'tokens'):
            self.parse(limits=parser.CatalogStandardLimits(max_tokens=used-1))
        with self.assertRaises(ResourceLimit): self.parse(budget=_Budget(CatalogLimits(max_tokens=used-1)))
        with self.assertRaisesRegex(parser.CatalogStandardError, 'depth'):
            self.parse(limits=parser.CatalogStandardLimits(max_depth=3))
        with self.assertRaisesRegex(parser.CatalogStandardError, 'depth'):
            self.parse(budget=_Budget(CatalogLimits(max_tree_depth=3)))
        self.parse(document(skipped='{'*63+'0'+'}'*63))
        with self.assertRaisesRegex(parser.CatalogStandardError, 'depth'):
            self.parse(document(skipped='{'*64+'0'+'}'*64))

    def test_reserve_before_allocation_and_retain_on_failure(self):
        for budget in (_Budget(CatalogLimits(max_bytes_processed=4*len(document())-1)),
                       _Budget(CatalogLimits(max_output_bytes=parser.STANDARD_OUTPUT_RESERVATION-1))):
            with mock.patch.object(parser, '_StandardCursor') as cursor:
                with self.assertRaises(ResourceLimit): self.parse(budget=budget)
                cursor.assert_not_called()
        budget = _Budget(CatalogLimits())
        for _ in range(2):
            with self.assertRaises(parser.CatalogStandardError): self.parse(b'x', budget=budget)
        self.assertEqual(budget.counts['bytes_processed'], 8)
        self.assertEqual(budget.counts['output_bytes'], 2*parser.STANDARD_OUTPUT_RESERVATION)
        self.parse(budget=budget)
        self.assertEqual(budget.counts['output_bytes'], 3*parser.STANDARD_OUTPUT_RESERVATION)

    def test_private_errors_and_expectation_free_signature(self):
        self.assertEqual(tuple(inspect.signature(parser.project_catalog_standard_prefix).parameters),
                         ('data', 'budget', 'limits'))
        for key in ('expected_name', 'expected_code_length', 'expected_uuid'):
            with self.assertRaises(TypeError):
                parser.project_catalog_standard_prefix(document(), budget=_Budget(CatalogLimits()), **{key: 2})
        with self.assertRaises(parser.CatalogStandardError) as error:
            self.parse(document(code='PrivateCandidate'))
        self.assertEqual(str(error.exception), 'integer_syntax')
        self.assertIn(error.exception.code, parser.CatalogStandardError.codes)
        with self.assertRaises(ValueError): parser.CatalogStandardError('PrivateCandidate')
        with mock.patch.object(parser, 'project_catalog_name_prefix', side_effect=AssertionError):
            self.parse()


if __name__ == '__main__': unittest.main()
