"""Independent invented CONFIG bytes, not native metadata captures."""
import dataclasses
import importlib.util
import inspect
from pathlib import Path
import subprocess
import sys
import types
import unittest

STORAGE = Path(__file__).resolve().parents[1] / 'yadinassi/storage'
PACKAGE = '_catalog_attributes_tests_storage'
package = types.ModuleType(PACKAGE)
package.__path__ = [str(STORAGE)]
sys.modules[PACKAGE] = package
parser = __import__(PACKAGE + '.config_catalog_attributes', fromlist=['*'])
catalog = __import__(PACKAGE + '.filedb_catalog', fromlist=['*'])

UUID1 = '12345678-9abc-def0-1234-56789abcdef0'
UUID2 = 'fedcba98-7654-3210-fedc-ba9876543210'


def node(*values):
    return '{' + ','.join(values) + '}'


def attribute(uuid=UUID1, name='"Payload"', pattern='{"Pattern",{"S",32,0}}'):
    # Construct nesting explicitly, without importing production path constants.
    header = node('0', node('1', '0', uuid), name)
    typed = node('0', header, pattern)
    return node(node('0', node('0', typed)))


def document(items=None, count=None, collection_uuid='cf4abea7-37b2-11d4-940f-008048da11f9', prefix='0'):
    if items is None:
        items = [attribute(), attribute(UUID2, '"Amount"', '{"Pattern",{"N",9,2,0}}')]
    collection = node(collection_uuid, str(len(items) if count is None else count), *items)
    return node(prefix, '0', '0', '0', '0', '0', collection).encode()


class CatalogAttributeTests(unittest.TestCase):
    def parse(self, data=None, *, limits=None, budget=None):
        budget = budget if budget is not None else catalog._Budget(catalog.CatalogLimits())
        return parser.project_catalog_attributes(document() if data is None else data,
                                                limits=limits, budget=budget), budget

    def test_two_independent_attributes_and_immutable_result(self):
        result, budget = self.parse()
        self.assertEqual([(x.metadata_uuid, x.name, x.type_token, x.qualifiers)
                          for x in result.attributes],
                         [(UUID1, 'Payload', 'S', (32, 0)), (UUID2, 'Amount', 'N', (9, 2, 0))])
        with self.assertRaises(dataclasses.FrozenInstanceError): result.attributes = ()
        with self.assertRaises(dataclasses.FrozenInstanceError): result.attributes[0].name = 'Changed'
        self.assertEqual(budget.counts['bytes_processed'], 8 * len(document()))
        self.assertEqual(budget.counts['output_bytes'], parser.OUTPUT_RESERVATION)
        self.assertGreater(budget.counts['tokens'], 30)

    def test_configuration_lengths_precision_and_kind_not_fixture_constants(self):
        for pattern, expected in [('{"Pattern",{"S",7,1}}', ('S', (7, 1))),
                                  ('{"Pattern",{"S",456,0}}', ('S', (456, 0))),
                                  ('{"Pattern",{"S",0,0}}', ('S', (0, 0))),
                                  ('{"Pattern",{"N",17,5,1}}', ('N', (17, 5, 1))),
                                  ('{"Pattern",{"N",1,0,0}}', ('N', (1, 0, 0))),
                                  ('{"Pattern",{"S",2147483647,0}}', ('S', (2147483647, 0))),
                                  ('{"Pattern",{"N",2147483647,2147483647,1}}', ('N', (2147483647, 2147483647, 1)))]:
            with self.subTest(pattern=pattern):
                value = self.parse(document([attribute(pattern=pattern)]))[0].attributes[0]
                self.assertEqual((value.type_token, value.qualifiers), expected)

    def test_empty_collection(self):
        self.assertEqual(self.parse(document([]))[0].attributes, ())
        self.assertEqual(self.parse(document([]), limits=parser.CatalogAttributeLimits(max_attributes=0))[0].attributes, ())

    def test_order_retained_not_role_search(self):
        values = [attribute(UUID2, '"First"', '{"Pattern",{"N",3,1,0}}'), attribute(UUID1, '"Second"')]
        result, _ = self.parse(document(values, prefix='"Payload"'))
        self.assertEqual([a.name for a in result.attributes], ['First', 'Second'])
        self.assertEqual(result.attributes[0].metadata_uuid, UUID2)

    def test_no_expected_or_fixture_inputs(self):
        self.assertEqual(tuple(inspect.signature(parser.project_catalog_attributes).parameters), ('data', 'budget', 'limits'))

    def test_name_unicode_and_escaped_quotes(self):
        value = self.parse(document([attribute(name='"Свойство😀""X"')]))[0].attributes[0]
        self.assertEqual(value.name, 'Свойство😀"X')

    def test_uuid_normalized_and_nonzero(self):
        self.assertEqual(self.parse(document([attribute(UUID1.upper())]))[0].attributes[0].metadata_uuid, UUID1)
        for value in ('0' * 36, '00000000-0000-0000-0000-000000000000', '"' + UUID1 + '"', UUID1 + ' ', UUID1[:-1], UUID1 + 'a'):
            with self.subTest(uuid=value), self.assertRaises(parser.CatalogAttributeError):
                self.parse(document([attribute(value)]))

    def test_collection_tag_count_and_exact_arity(self):
        invalid = [document(count=n) for n in ('0', '1', '3', '-1', '02', '"2"', '', '2147483648')]
        invalid += [document(collection_uuid=UUID1), document(collection_uuid='"cf4abea7-37b2-11d4-940f-008048da11f9"')]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(parser.CatalogAttributeError): self.parse(data)

    def test_duplicate_identity_or_name(self):
        for items, code in [([attribute(), attribute(UUID1.upper(), '"Other"')], 'duplicate_uuid'),
                            ([attribute(), attribute(UUID2)], 'duplicate_name')]:
            with self.assertRaisesRegex(parser.CatalogAttributeError, '^' + code + '$'):
                self.parse(document(items))

    def test_name_case_not_locale_binding_claim(self):
        result, _ = self.parse(document([attribute(name='"Field"'), attribute(UUID2, '"field"')]))
        self.assertEqual(len(result.attributes), 2)

    def test_closed_single_primitive_grammar(self):
        bad = ('{}', '{"Pattern"}', '{"Wrong",{"S",32,0}}', '{Pattern,{"S",32,0}}',
               '{"Pattern",{S,32,0}}', '{"Pattern",{"S"}}', '{"Pattern",{"S",32}}',
               '{"Pattern",{"S",32,0,1}}', '{"Pattern",{"S",32,0},{"N",9,2,0}}',
               '{"Pattern",{"N",9,2}}', '{"Pattern",{"N",9,2,0,0}}',
               '{"Pattern",{"B"}}', '{"Pattern",{"#",' + UUID1 + '}}',
               '{"Pattern",{"D"}}', '{"Pattern",{"S",32,2}}',
               '{"Pattern",{"N",9,2,2}}', '{"Pattern",{"N",0,0,0}}',
               '{"Pattern",{"N",2,3,0}}', '{"Pattern",{"S",{32},0}}',
               '{"Pattern",0}', '{"Pattern",{"S",32,0},}', '{"Pattern",{},0}')
        for pattern in bad:
            with self.subTest(pattern=pattern), self.assertRaises(parser.CatalogAttributeError):
                self.parse(document([attribute(pattern=pattern)]))

    def test_integer_lexical_and_bound_rejection(self):
        for value in ('-1', '+1', '01', '1.0', '1e2', '"32"', '３２', '1 ', '1\n', '2147483648', '99999999999', ''):
            with self.subTest(value=value), self.assertRaises(parser.CatalogAttributeError):
                self.parse(document([attribute(pattern='{"Pattern",{"S",' + value + ',0}}')]))

    def test_missing_nested_fields_and_no_suffix_search(self):
        for value in ('{}', '{0}', '{{0}}', '{{0,{0}}}', '{{0,{0,{0}}}}',
                      attribute(name='{}'), attribute(name='""')):
            with self.subTest(value=value), self.assertRaises(parser.CatalogAttributeError):
                self.parse(document([value]))
        with self.assertRaises(parser.CatalogAttributeError): self.parse(b'{0,0}')
        with self.assertRaises(parser.CatalogAttributeError): self.parse(b'{0,0,0,0,0,0,0,' + document() + b'}')

    def test_partial_prefix_suffix_boundary_not_full_document(self):
        complete = document()
        self.assertEqual(self.parse(complete[:-1] + b',\xff private suffix')[0], self.parse(complete)[0])
        # A completed collection still needs its parent comma/close boundary.
        for end in (b'', b'x', b'\xff', b'\x00'):
            with self.assertRaises(parser.CatalogAttributeError): self.parse(complete[:-1] + end)

    def test_every_truncation_through_collection_fails(self):
        data = document()
        for i in range(len(data) - 1):
            with self.subTest(length=i), self.assertRaises(parser.CatalogAttributeError): self.parse(data[:i])

    def test_bad_utf8_and_syntax_in_opaque_prefix(self):
        for prefix in (b'"\xff"', b'{0,}', b'{', b'"x\x00y"', b'"\xef\xbb\xbf"'):
            data = document().replace(b'{0,', b'{' + prefix + b',', 1)
            with self.subTest(prefix=prefix), self.assertRaises(parser.CatalogAttributeError): self.parse(data)

    def test_local_limits_and_budget_not_reset(self):
        for limit in (parser.CatalogAttributeLimits(max_attributes=1),
                      parser.CatalogAttributeLimits(max_name_chars=3),
                      parser.CatalogAttributeLimits(max_name_bytes=3),
                      parser.CatalogAttributeLimits(max_depth=3),
                      parser.CatalogAttributeLimits(max_tokens=10),
                      parser.CatalogAttributeLimits(max_qualifier=10),
                      parser.CatalogAttributeLimits(max_input_bytes=10)):
            with self.subTest(limit=limit), self.assertRaises(parser.CatalogAttributeError): self.parse(limits=limit)
        budget = catalog._Budget(catalog.CatalogLimits())
        budget.charge('output_bytes', 37)
        self.parse(budget=budget)
        self.parse(budget=budget)
        self.assertEqual(budget.counts['output_bytes'], 37 + 2 * parser.OUTPUT_RESERVATION)
        before = dict(budget.counts)
        with self.assertRaises(parser.CatalogAttributeError): self.parse(document(count=3), budget=budget)
        self.assertGreater(budget.counts['output_bytes'], before['output_bytes'])
        self.assertGreater(budget.counts['bytes_processed'], before['bytes_processed'])

    def test_independent_lowered_field_limits(self):
        value = self.parse(document([attribute(name='"A"', pattern='{"Pattern",{"S",0,0}}')]),
                           limits=parser.CatalogAttributeLimits(max_name_chars=1, max_name_bytes=1,
                                                                max_qualifier=0))[0]
        self.assertEqual(value.attributes[0].qualifiers, (0, 0))

    def test_shared_resource_failure_propagates(self):
        for field, value in [('max_output_bytes', 1), ('max_bytes_processed', 1), ('max_tokens', 1)]:
            with self.subTest(field=field), self.assertRaises(catalog.ResourceLimit):
                self.parse(budget=catalog._Budget(catalog.CatalogLimits(**{field: value})))

    def test_input_and_limits_types(self):
        for value in (None, 'text', bytearray(document()), memoryview(document())):
            with self.assertRaisesRegex(parser.CatalogAttributeError, '^input_type$'):
                parser.project_catalog_attributes(value, budget=catalog._Budget(catalog.CatalogLimits()))
        for limits in (False, {}, parser.CatalogNameLimits()):
            with self.assertRaisesRegex(parser.CatalogAttributeError, '^limits_type$'): self.parse(limits=limits)
        for kwargs in ({'max_attributes': 65}, {'max_attributes': True}, {'max_attributes': -1},
                       {'max_qualifier': 2147483648}, {'max_qualifier': False}):
            with self.assertRaises(parser.CatalogAttributeError): parser.CatalogAttributeLimits(**kwargs)

    def test_maximum_attributes_with_dynamic_properties(self):
        items = [attribute(f'{i:08x}-0000-0000-0000-000000000001', f'"Field{i}"',
                           '{"Pattern",{"S",' + str(i + 10) + ',0}}') for i in range(64)]
        result, _ = self.parse(document(items))
        self.assertEqual(len(result.attributes), 64)
        self.assertEqual(result.attributes[-1].qualifiers, (73, 0))
        with self.assertRaisesRegex(parser.CatalogAttributeError, '^attribute_limit$'):
            self.parse(document(items + [attribute()]))

    def test_isolated_stdlib_import(self):
        code = ('import sys,types; p=types.ModuleType("storage"); p.__path__=[' + repr(str(STORAGE)) + ']; '
                'sys.modules["storage"]=p; import storage.config_catalog_attributes; '
                'assert "yadinassi" not in sys.modules; assert "decimal" not in sys.modules')
        subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
