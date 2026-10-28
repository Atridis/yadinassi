"""Invented UUID-bearing Catalog prefixes; no captured native metadata."""
import dataclasses
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'yadinassi/storage'))
import config_catalog_name as parser
from filedb_catalog import CatalogLimits, ResourceLimit, _Budget


UUID = '12345678-9abc-def0-1234-56789abcdef0'


def node(*values):
    return '{' + ','.join(values) + '}'


def document(uuid=UUID, name='"Invented"', code='2', kind='1', description='0', skipped='0'):
    fields = ['0'] * 20
    fields[9] = node('0', node('0', node('1', '0', uuid), name))
    fields[17:20] = [code, kind, description]
    return node(skipped, node(*fields)).encode()


class CatalogIdentityTests(unittest.TestCase):
    def parse(self, data=None, *, limits=None, budget=None):
        budget = budget if budget is not None else _Budget(CatalogLimits())
        result = parser.project_catalog_identity_prefix(
            document() if data is None else data, limits=limits, budget=budget)
        return result, budget

    def test_private_fields_frozen_and_accounted(self):
        result, budget = self.parse()
        self.assertEqual(dataclasses.asdict(result), dict(metadata_uuid=UUID,
            name='Invented', code_length=2, code_type=1, description_length=0))
        with self.assertRaises(dataclasses.FrozenInstanceError): result.metadata_uuid = 'x'
        self.assertEqual(budget.counts['bytes_processed'], 4 * len(document()))
        self.assertEqual(budget.counts['output_bytes'], parser.IDENTITY_OUTPUT_RESERVATION)
        self.assertGreater(budget.counts['tokens'], 20)

    def test_case_normalization_without_uuid_version_restriction(self):
        for value in (UUID, UUID.upper(), 'ffffffff-ffff-ffff-ffff-ffffffffffff',
                      '00000000-0000-0000-0000-000000000001'):
            self.assertEqual(self.parse(document(uuid=value))[0].metadata_uuid, value.lower())

    def test_uuid_strict_admission_grammar(self):
        invalid = ('', '"' + UUID + '"', '{' + UUID + '}', UUID.replace('-', ''),
                   '{' + UUID, UUID + ' ', UUID + '\n', UUID + 'x', UUID[:-1],
                   UUID.replace('a', 'g'), UUID.replace('1', '１'),
                   UUID.replace('-', '_', 1), 'urn:uuid:' + UUID, 'PrivateCandidate')
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(parser.CatalogIdentityError):
                self.parse(document(uuid=value))
        with self.assertRaisesRegex(parser.CatalogIdentityError, '^uuid_zero$'):
            self.parse(document(uuid='00000000-0000-0000-0000-000000000000'))
        self.assertEqual(self.parse(document(uuid=' \r\n' + UUID))[0].metadata_uuid, UUID)

    def test_each_uuid_character_is_validated(self):
        for i in range(36):
            bad = UUID[:i] + ('0' if i in (8, 13, 18, 23) else '-') + UUID[i + 1:]
            with self.subTest(position=i), self.assertRaisesRegex(parser.CatalogIdentityError, '^uuid_syntax$'):
                self.parse(document(uuid=bad))

    def test_no_search_or_decoy_binding(self):
        other = 'abcdef01-2345-6789-abcd-ef0123456789'
        data = document(skipped='"' + other + '"', name='"' + other + '"')
        result, _ = self.parse(data)
        self.assertEqual(result.metadata_uuid, UUID)
        self.assertEqual(result.name, other)
        with self.assertRaises(parser.CatalogIdentityError):
            self.parse(document(uuid='', skipped=UUID, name='"' + UUID + '"'))

    def test_real_delimiter_required_before_uuid_acceptance(self):
        before = document().split(UUID.encode())[0]
        for end in (b'', b' ', b'\xff', b'\x00', b'"'):
            with self.assertRaisesRegex(parser.CatalogIdentityError, '^uuid_syntax$'):
                self.parse(before + UUID.encode() + end)
        for size in range(36):
            with self.assertRaises(parser.CatalogIdentityError):
                self.parse(before + UUID.encode()[:size])

    def test_old_entrypoints_do_not_start_validating_identity(self):
        for uuid in ('bad', '""', '{0}', '00000000-0000-0000-0000-000000000000'):
            data = document(uuid=uuid)
            self.assertEqual(parser.project_catalog_name_prefix(data,
                budget=_Budget(CatalogLimits())).name, 'Invented')
            self.assertEqual(parser.project_catalog_standard_prefix(data,
                budget=_Budget(CatalogLimits())).name, 'Invented')
            with self.assertRaises(parser.CatalogIdentityError): self.parse(data)

    def test_no_call_to_old_entrypoints_or_second_traversal(self):
        with mock.patch.object(parser, 'project_catalog_name_prefix', side_effect=AssertionError), \
             mock.patch.object(parser, 'project_catalog_standard_prefix', side_effect=AssertionError):
            self.parse()

    def test_suffix_unvalidated_only_after_description_boundary(self):
        prefix = document()[:-2] + b','
        for suffix in (b'', b'\xff', b'\x00', b'{unterminated', b'\xef\xbb\xbf'):
            self.assertEqual(self.parse(prefix + suffix)[0].description_length, 0)
        with self.assertRaises(parser.CatalogIdentityError): self.parse(prefix[:-1])
        with self.assertRaises(parser.CatalogIdentityError): self.parse(document(description='bad'))

    def test_missing_fields_wrong_containers_and_null_positions(self):
        for data in (b'{}', b'{0}', b'{0,0}', b'{0,{}}', document(name='{}'),
                     document().replace(b'{1,0,' + UUID.encode() + b'}', b'0'),
                     document().replace(b',2,1,0', b',2,1')):
            with self.subTest(data=data), self.assertRaises(parser.CatalogIdentityError): self.parse(data)
        data = document().replace(b'{0,{0,{1,0,', b'{,{,{,,')
        self.assertEqual(self.parse(data)[0].metadata_uuid, UUID)

    def test_name_and_standard_fields_preserve_grammar(self):
        result, _ = self.parse(document(name='"a""b,{}😀"', code='123', kind='0', description='456'))
        self.assertEqual((result.name, result.code_length, result.code_type, result.description_length),
                         ('a"b,{}😀', 123, 0, 456))
        for value in ('', '"2"', '-1', '+1', '00', '01', '1.0', '1e0', '１', '2 ', 'NaN', '{2}'):
            for field in ('code', 'kind', 'description'):
                with self.subTest(field=field, value=value), self.assertRaises(parser.CatalogIdentityError):
                    self.parse(document(**{field: value}))
        self.parse(document(code='2147483647'))
        with self.assertRaisesRegex(parser.CatalogIdentityError, '^integer_bound$'):
            self.parse(document(code='2147483648'))
        with self.assertRaisesRegex(parser.CatalogIdentityError, '^code_type$'):
            self.parse(document(kind='2'))
        self.parse(document(code='0'), limits=parser.CatalogIdentityLimits(max_length=0))

    def test_consumed_utf8_and_controls_fail_privately(self):
        for invalid in (b'\xff', b'\xc0\x80', b'\xed\xa0\x80', b'\xf4\x90\x80\x80',
                        b'\xe2\x82', b'\x00', b'\t', b'\x7f', b'\xef\xbb\xbf'):
            for marker in (UUID.encode(), b'Invented'):
                with self.subTest(invalid=invalid, marker=marker), self.assertRaises(parser.CatalogIdentityError):
                    self.parse(document().replace(marker, invalid))
        self.parse(b'\xef\xbb\xbf \r\n' + document())
        self.parse(document(name='"x"', skipped='"' + 'a' * 2000 + '"'),
                   limits=parser.CatalogIdentityLimits(max_name_chars=1, max_name_bytes=1))
        for limits in (parser.CatalogIdentityLimits(max_name_chars=1),
                       parser.CatalogIdentityLimits(max_name_bytes=3)):
            with self.assertRaises(parser.CatalogIdentityError): self.parse(document(name='"😀😀"'), limits=limits)

    def test_limits_exact_types_and_separate_old_contracts(self):
        for field in dataclasses.fields(parser.CatalogIdentityLimits):
            maximum = getattr(parser.CatalogIdentityLimits(), field.name)
            for invalid in (True, -1, maximum + 1, 1.0, '1', None):
                with self.subTest(field=field.name, invalid=invalid), self.assertRaises(parser.CatalogIdentityError):
                    parser.CatalogIdentityLimits(**{field.name: invalid})
        for limits in ({}, parser.CatalogNameLimits(), parser.CatalogStandardLimits()):
            with self.assertRaisesRegex(parser.CatalogIdentityError, '^limits_type$'): self.parse(limits=limits)
        for old in (parser.project_catalog_name_prefix, parser.project_catalog_standard_prefix):
            with self.assertRaisesRegex(parser.CatalogNameError, '^limits_type$'):
                old(document(), budget=_Budget(CatalogLimits()), limits=parser.CatalogIdentityLimits())
        for data in (bytearray(document()), memoryview(document()), 'x'):
            with self.assertRaisesRegex(parser.CatalogIdentityError, '^input_type$'): self.parse(data)

    def test_boundary_input_depth_tokens_and_shared_budget(self):
        self.parse(limits=parser.CatalogIdentityLimits(max_input_bytes=len(document()), max_depth=5))
        for limits, code in ((parser.CatalogIdentityLimits(max_input_bytes=len(document()) - 1), 'input_bytes'),
                             (parser.CatalogIdentityLimits(max_depth=4), 'depth')):
            with self.assertRaisesRegex(parser.CatalogIdentityError, '^' + code + '$'): self.parse(limits=limits)
        with self.assertRaisesRegex(parser.CatalogIdentityError, '^depth$'):
            self.parse(budget=_Budget(CatalogLimits(max_tree_depth=4)))
        _, budget = self.parse()
        used = budget.counts['tokens']
        self.parse(limits=parser.CatalogIdentityLimits(max_tokens=used))
        self.parse(budget=_Budget(CatalogLimits(max_tokens=used)))
        with self.assertRaisesRegex(parser.CatalogIdentityError, '^tokens$'):
            self.parse(limits=parser.CatalogIdentityLimits(max_tokens=used - 1))
        with self.assertRaises(ResourceLimit): self.parse(budget=_Budget(CatalogLimits(max_tokens=used - 1)))
        self.parse(document(skipped='{' * 63 + '0' + '}' * 63))
        with self.assertRaisesRegex(parser.CatalogIdentityError, '^depth$'):
            self.parse(document(skipped='{' * 64 + '0' + '}' * 64))

    def test_reservation_precedes_cursor_allocation_and_is_never_refunded(self):
        for budget in (_Budget(CatalogLimits(max_bytes_processed=4 * len(document()) - 1)),
                       _Budget(CatalogLimits(max_output_bytes=parser.IDENTITY_OUTPUT_RESERVATION - 1))):
            with mock.patch.object(parser, '_IdentityCursor') as cursor:
                with self.assertRaises(ResourceLimit): self.parse(budget=budget)
                cursor.assert_not_called()
        budget = _Budget(CatalogLimits())
        for _ in range(2):
            with self.assertRaises(parser.CatalogIdentityError): self.parse(b'x', budget=budget)
        self.assertEqual(budget.counts['bytes_processed'], 8)
        self.assertEqual(budget.counts['output_bytes'], 2 * parser.IDENTITY_OUTPUT_RESERVATION)
        self.parse(budget=budget)
        self.assertEqual(budget.counts['output_bytes'], 3 * parser.IDENTITY_OUTPUT_RESERVATION)

    def test_finite_errors_and_expectation_free_signature(self):
        self.assertEqual(tuple(inspect.signature(parser.project_catalog_identity_prefix).parameters),
                         ('data', 'budget', 'limits'))
        for key in ('expected_name', 'expected_uuid', 'declaration_uuid', 'xml'):
            with self.assertRaises(TypeError):
                parser.project_catalog_identity_prefix(document(), budget=_Budget(CatalogLimits()), **{key: UUID})
        with self.assertRaises(parser.CatalogIdentityError) as error: self.parse(document(uuid='PrivateCandidate'))
        self.assertEqual(str(error.exception), 'uuid_syntax')
        self.assertIn(error.exception.code, parser.CatalogIdentityError.codes)
        with self.assertRaises(ValueError): parser.CatalogIdentityError('PrivateCandidate')


if __name__ == '__main__': unittest.main()
