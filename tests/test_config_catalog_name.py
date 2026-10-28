"""Invented positional vectors; no captured native bytes or native claims."""
import dataclasses
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'yadinassi/storage'))
import config_catalog_name as parser
from filedb_catalog import CatalogLimits, ResourceLimit, _Budget


def node(*values):
    return '{' + ','.join(values) + '}'


def document(name='"NativeOracleItems"', *, skipped='0', suffix=''):
    inner = node('0', '0', name) + suffix
    return node(skipped, node(*(['0']*9), node('0', inner))).encode()


def prefix(name='"NativeOracleItems"'):
    # Stop at the real delimiter following [1][9][1][2].
    return ('{0,{' + '0,'*9 + '{0,{0,0,' + name + ',').encode()


class CatalogNameTests(unittest.TestCase):
    def parse(self, data, *, limits=None, shared=None):
        budget = shared or _Budget(CatalogLimits())
        result = parser.project_catalog_name_prefix(data, budget=budget, limits=limits)
        return result, budget

    def test_exact_name_and_frozen_private_result(self):
        result, budget = self.parse(document())
        self.assertEqual(result.name, 'NativeOracleItems')
        self.assertEqual(dataclasses.asdict(result), {'name': 'NativeOracleItems'})
        with self.assertRaises(dataclasses.FrozenInstanceError): result.name = 'other'
        self.assertEqual(budget.counts['bytes_processed'], 4*len(document()))
        self.assertEqual(budget.counts['output_bytes'], parser.OUTPUT_RESERVATION)

    def test_declared_path_not_search(self):
        self.assertEqual(self.parse(document('"Wanted"', skipped='"Decoy"'))[0].name, 'Wanted')
        self.assertEqual(self.parse(document('"Wanted"', skipped=node('"Wanted"')))[0].name, 'Wanted')
        wrong = document().replace(b'0,0,"NativeOracleItems"', b'0,"NativeOracleItems",0')
        self.assertEqual(self.parse(wrong)[0].name, '0')

    def test_bare_unicode_and_quote_escape_preserved(self):
        for spelling, expected in [('Имя', 'Имя'), ('"Имя😀"', 'Имя😀'),
                                   ('"a""b,{}"', 'a"b,{}'), ('Raw ', 'Raw '),
                                   ('" é "', ' é ')]:
            with self.subTest(spelling=spelling):
                self.assertEqual(self.parse(document(spelling))[0].name, expected)

    def test_null_positions_are_not_dropped(self):
        data=document().replace(b'{0,{0,0,', b'{,{,,')
        self.assertEqual(self.parse(data)[0].name, 'NativeOracleItems')

    def test_suffix_is_explicitly_unvalidated(self):
        for suffix in (b'', b'\xff', b'{unclosed', b'\xef\xbb\xbf', b'\x00'):
            self.assertEqual(self.parse(prefix()+suffix)[0].name, 'NativeOracleItems')
        self.assertEqual(self.parse(prefix()[:-1]+b'}\xff')[0].name, 'NativeOracleItems')

    def test_required_boundary_and_quote_closure(self):
        for data in (prefix()[:-1], prefix('"Name"junk'), prefix('"Name'), prefix('Name"')):
            with self.subTest(data=data), self.assertRaises(parser.CatalogNameError): self.parse(data)

    def test_missing_route_and_wrong_containers(self):
        for data in (b'{}', b'{0}', b'{0,0}', b'{0,{}}', document('{}')):
            with self.subTest(data=data), self.assertRaises(parser.CatalogNameError): self.parse(data)

    def test_empty_names_rejected(self):
        for name in ('', '""'):
            with self.subTest(name=name), self.assertRaisesRegex(parser.CatalogNameError, 'empty_name'):
                self.parse(document(name))

    def test_bom_and_boundary_whitespace(self):
        self.assertEqual(self.parse(b'\xef\xbb\xbf \r\n'+document())[0].name,'NativeOracleItems')
        with self.assertRaises(parser.CatalogNameError): self.parse(b'\xef\xbb\xbf\xef\xbb\xbf'+document())
        self.assertEqual(self.parse(document('"Name" \r\n'))[0].name, 'Name')

    def test_visited_encoding_rejections(self):
        for bad in (b'\xff', b'\xc0\x80', b'\xed\xa0\x80', b'\xf4\x90\x80\x80', b'\xe2\x82', b'\xc2A'):
            data=document().replace(b'NativeOracleItems', bad)
            with self.subTest(bad=bad), self.assertRaisesRegex(parser.CatalogNameError,'encoding'):
                self.parse(data)

    def test_visited_controls_and_embedded_bom(self):
        for bad in (b'\x00',b'\t',b'\x7f',b'\xef\xbb\xbf',b'\n'):
            with self.subTest(bad=bad),self.assertRaises(parser.CatalogNameError):
                self.parse(document().replace(b'NativeOracleItems',bad))

    def test_opaque_text_validated_without_name_limits(self):
        self.assertEqual(self.parse(document('"x"',skipped='"'+'a'*2000+'"'),
                         limits=parser.CatalogNameLimits(max_name_chars=1,max_name_bytes=1))[0].name,'x')
        with self.assertRaises(parser.CatalogNameError):
            self.parse(document(skipped='"x\t"'))

    def test_character_and_byte_limits(self):
        self.parse(document('"😀😀"'),limits=parser.CatalogNameLimits(max_name_chars=2,max_name_bytes=8))
        for limits,code in ((parser.CatalogNameLimits(max_name_chars=1),'name_chars'),
                            (parser.CatalogNameLimits(max_name_bytes=7),'name_bytes')):
            with self.assertRaisesRegex(parser.CatalogNameError,code):self.parse(document('"😀😀"'),limits=limits)
        self.parse(document('"'+'x'*256+'"'))
        with self.assertRaisesRegex(parser.CatalogNameError,'name_chars'):self.parse(document('"'+'x'*257+'"'))

    def test_limits_strict_and_lowering_only(self):
        for field in dataclasses.fields(parser.CatalogNameLimits):
            maximum=getattr(parser.CatalogNameLimits(),field.name)
            for invalid in (True,0,-1,maximum+1,1.0,'1',None):
                with self.subTest(field=field.name,value=invalid),self.assertRaises(parser.CatalogNameError):
                    parser.CatalogNameLimits(**{field.name:invalid})
        with self.assertRaisesRegex(parser.CatalogNameError,'limits_type'):self.parse(document(),limits={})

    def test_input_type_and_exact_length(self):
        for data in (bytearray(document()),'x',None,memoryview(document())):
            with self.assertRaisesRegex(parser.CatalogNameError,'input_type'):self.parse(data)
        self.parse(document(),limits=parser.CatalogNameLimits(max_input_bytes=len(document())))
        with self.assertRaisesRegex(parser.CatalogNameError,'input_bytes'):
            self.parse(document(),limits=parser.CatalogNameLimits(max_input_bytes=len(document())-1))

    def test_reservation_precedes_cursor_allocation(self):
        for shared in (_Budget(CatalogLimits(max_bytes_processed=4*len(document())-1)),
                       _Budget(CatalogLimits(max_output_bytes=parser.OUTPUT_RESERVATION-1))):
            with mock.patch.object(parser,'_Cursor') as cursor:
                with self.assertRaises(ResourceLimit):self.parse(document(),shared=shared)
                cursor.assert_not_called()

    def test_reservation_retained_on_failure_and_repeated_calls(self):
        budget=_Budget(CatalogLimits())
        for _ in range(2):
            with self.assertRaises(parser.CatalogNameError):self.parse(b'x',shared=budget)
        self.assertEqual(budget.counts['bytes_processed'],8)
        self.assertEqual(budget.counts['output_bytes'],2*parser.OUTPUT_RESERVATION)
        self.parse(document(),shared=budget)
        self.assertEqual(budget.counts['output_bytes'],3*parser.OUTPUT_RESERVATION)

    def test_existing_budget_not_reset(self):
        budget=_Budget(CatalogLimits(max_output_bytes=parser.OUTPUT_RESERVATION))
        budget.charge('output_bytes',1)
        with self.assertRaises(ResourceLimit):self.parse(document(),shared=budget)
        self.assertEqual(budget.counts['output_bytes'],1)
        self.assertEqual(budget.counts['bytes_processed'],4*len(document()))

    def test_exact_local_and_shared_event_limits(self):
        _,budget=self.parse(document());used=budget.counts['tokens']
        self.parse(document(),limits=parser.CatalogNameLimits(max_tokens=used))
        self.parse(document(),shared=_Budget(CatalogLimits(max_tokens=used)))
        with self.assertRaisesRegex(parser.CatalogNameError,'tokens'):
            self.parse(document(),limits=parser.CatalogNameLimits(max_tokens=used-1))
        with self.assertRaises(ResourceLimit):self.parse(document(),shared=_Budget(CatalogLimits(max_tokens=used-1)))

    def test_depth_bounds_on_route_and_opaque_nodes(self):
        self.parse(document(),limits=parser.CatalogNameLimits(max_depth=4))
        with self.assertRaisesRegex(parser.CatalogNameError,'depth'):self.parse(document(),limits=parser.CatalogNameLimits(max_depth=3))
        with self.assertRaisesRegex(parser.CatalogNameError,'depth'):self.parse(document(),shared=_Budget(CatalogLimits(max_tree_depth=3)))
        self.parse(document(skipped='{'*63+'0'+'}'*63))
        with self.assertRaisesRegex(parser.CatalogNameError,'depth'):self.parse(document(skipped='{'*64+'0'+'}'*64))

    def test_errors_never_echo_private_input(self):
        secret='PrivateSensitiveCandidate'
        with self.assertRaises(parser.CatalogNameError) as error:self.parse(prefix('"'+secret+'"junk'))
        self.assertNotIn(secret,str(error.exception))
        self.assertIn(str(error.exception),parser.CatalogNameError.codes)
        with self.assertRaises(ValueError):parser.CatalogNameError(secret)

    def test_expected_identity_is_not_an_input(self):
        with self.assertRaises(TypeError):
            parser.project_catalog_name_prefix(document(),budget=_Budget(CatalogLimits()),expected_name='NativeOracleItems')


if __name__=='__main__':unittest.main()
