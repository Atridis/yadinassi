"""Invented source bytes and independently typed XML expectations; no native claim."""
import copy
import dataclasses
import unittest
from unittest import mock
import test_native_1c_db_oracle_field_matrix_binding as matrix
import test_config_catalog_attributes as constructed
import config_catalog_attribute_binding as policy
import config_framing_reader as core
import config_catalog_name as identity_parser
import protocol
from test_native_1c_db_oracle_catalog_reference_reader import entries, stored_literal, content_source

NONCE = matrix.NONCE
KEYS = matrix.KEYS
ATTRIBUTES = ((('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'Payload', 'S', (32, 1)),
               ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'Amount', 'N', (9, 2, 0))), (), ())


def identity():
    result = matrix.identity()
    result['sources'] = {p: 'c' * 64 for p in policy.CATALOG_SOURCE_FILES}
    return result


def manifest():
    return policy._MatrixManifest(NONCE, 'a' * 64, tuple(
        policy._IdentityManifest(NONCE, 'a' * 64, 'b' * 64, key, *fields, attributes)
        for key, fields, attributes in zip(KEYS, policy.MATRIX, ATTRIBUTES)))


def source():
    payloads = []
    for index, (key, (name, code, kind, description)) in enumerate(zip(KEYS, policy.MATRIX)):
        prefix = matrix.names.document(name='"' + name + '"', code=str(code), kind=str(kind),
                                       description=str(description), metadata_uuid=key)
        attrs = [] if index else [constructed.attribute('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '"Payload"', '{"Pattern",{"S",32,1}}'),
                                 constructed.attribute('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '"Amount"', '{"Pattern",{"N",9,2,0}}')]
        collection = constructed.node('cf4abea7-37b2-11d4-940f-008048da11f9', str(len(attrs)), *attrs)
        payloads.append(stored_literal(prefix[:-1] + b',0,0,0,0,' + collection.encode() + b'}'))
    return content_source(entries(refs=KEYS, payload=payloads[0], tail=tuple(
        (key, payload, 0) for key, payload in zip(KEYS[1:], payloads[1:]))))


def private():
    image = source()
    return policy.read_owned_projection(image.read_at, image.size, limits=policy.reader.CatalogLimits())


def projection():
    return policy.compare_private(private(), manifest(), nonce=NONCE)


def evidence():
    value = matrix.evidence()
    value.update(reader=private(), identity_manifest=manifest())
    return value


def fixture():
    value = matrix.fixture()
    del value['config_catalog_field_matrix']
    value.update(schema=policy.SCHEMA, lane=policy.LANE, provenance=identity(),
                 config_catalog_attribute_binding=None, reader_validation=policy.VERDICT,
                 observation_validation=policy.VERDICT)
    value['config_catalog_attribute_binding'] = policy.bind_capture(evidence(), value)
    return value


class AttributeBindingTests(unittest.TestCase):
    def test_complete_report_private_fields_never_serialized(self):
        report = fixture()
        report['cleanup'].update(container_removed=True, private_staging_removed=True)
        report['accepted'] = True
        policy.validate_report(protocol.encode(report), nonce=NONCE, provenance=identity(), final=True)
        raw = protocol.encode(report)
        for secret in (*KEYS, *(x[0] for x in ATTRIBUTES[0]), 'Payload', 'Amount', 'NativeOracleItems'):
            self.assertNotIn(secret.encode(), raw)
        self.assertEqual(report['config_catalog_attribute_binding']['reader']['attribute_count'], 2)

    def test_same_reader_two_parsers_same_budget_no_expectations(self):
        ap = core.load_catalog_attribute_projector()
        budgets, calls = [], []
        original_init = core.CatalogReader.__init__
        original_identity = identity_parser.project_catalog_identity_prefix
        original_attributes = ap.project_catalog_attributes
        def create(obj, *a, **kw):
            original_init(obj, *a, **kw); budgets.append(obj._budget)
        def id_parse(data, **kw):
            calls.append(('identity', kw, len(data))); return original_identity(data, **kw)
        def attr_parse(data, **kw):
            calls.append(('attributes', kw, len(data))); return original_attributes(data, **kw)
        with mock.patch.object(core.CatalogReader, '__init__', create), \
                mock.patch.object(identity_parser, 'project_catalog_identity_prefix', id_parse), \
                mock.patch.object(ap, 'project_catalog_attributes', attr_parse):
            actual = private()
        self.assertEqual(len(budgets), 1)
        self.assertEqual([x[0] for x in calls], ['identity', 'attributes'] * 3)
        for kind, kwargs, size in calls:
            self.assertEqual(set(kwargs), {'budget', 'limits'} if kind == 'identity' else {'budget'})
            self.assertIs(kwargs['budget'], budgets[0])
        self.assertGreaterEqual(budgets[0].counts['bytes_processed'], sum((4 if kind == 'identity' else 8) * size for kind, _, size in calls))
        self.assertEqual([len(row[2].attributes) for row in actual.names], [2, 0, 0])

    def test_every_attribute_component_independently_compared(self):
        actual = private()
        key, fields, attributes = actual.names[0]
        for name, value in [('metadata_uuid', 'cccccccc-cccc-cccc-cccc-cccccccccccc'),
                            ('name', 'Other'), ('type_token', 'N'), ('qualifiers', (7, 1))]:
            first = dataclasses.replace(attributes.attributes[0], **{name: value})
            changed = dataclasses.replace(attributes, attributes=(first, attributes.attributes[1]))
            rows = ((key, fields, changed), *actual.names[1:])
            with self.subTest(name=name), self.assertRaises(policy.ObservationFailure):
                policy.compare_private(dataclasses.replace(actual, names=rows), manifest(), nonce=NONCE)

    def test_complete_collection_bijection_including_empty_catalogs(self):
        actual = private()
        for index, replacement in [(0, ()), (0, actual.names[0][2].attributes[:1]),
                                    (1, actual.names[0][2].attributes)]:
            rows = list(actual.names)
            key, fields, attrs = rows[index]
            rows[index] = (key, fields, dataclasses.replace(attrs, attributes=replacement))
            with self.assertRaises(policy.ObservationFailure):
                policy.compare_private(dataclasses.replace(actual, names=tuple(rows)), manifest(), nonce=NONCE)
        key, fields, attrs = actual.names[0]
        reordered = ((key, fields, dataclasses.replace(attrs, attributes=attrs.attributes[::-1])), *actual.names[1:])
        self.assertEqual(policy.compare_private(dataclasses.replace(actual, names=reordered), manifest(), nonce=NONCE), projection())

    def test_metadata_values_not_hardcoded_to_fixture_in_comparator(self):
        actual, wanted = private(), manifest()
        key, fields, attrs = actual.names[0]
        changed = dataclasses.replace(attrs.attributes[0], name='Configured', qualifiers=(456, 0))
        rows = ((key, fields, dataclasses.replace(attrs, attributes=(changed, attrs.attributes[1]))), *actual.names[1:])
        expected_attrs = ((ATTRIBUTES[0][0][0], 'Configured', 'S', (456, 0)), ATTRIBUTES[0][1])
        catalogs = (dataclasses.replace(wanted.catalogs[0], attributes=expected_attrs), *wanted.catalogs[1:])
        self.assertEqual(policy.compare_private(dataclasses.replace(actual, names=rows),
            dataclasses.replace(wanted, catalogs=catalogs), nonce=NONCE), projection())

    def test_parser_failure_and_budget_failure_have_no_private_result(self):
        ap = core.load_catalog_attribute_projector()
        for error, expected in [(ap.CatalogAttributeError('type_shape'), 'config_catalog_attribute_prefix'),
                                (ap.CatalogAttributeError('tokens'), 'config_catalog_attribute_limits')]:
            with mock.patch.object(ap, 'project_catalog_attributes', side_effect=error):
                with self.assertRaisesRegex((policy.reader.InvalidStructure, policy.reader.ResourceLimit), expected): private()

    def test_final_success_requires_all_cleanup_gates(self):
        report = fixture()
        report['cleanup'].update(container_removed=True, private_staging_removed=True)
        report['accepted'] = True
        for key in report['cleanup']:
            bad = copy.deepcopy(report)
            bad['cleanup'][key] = False
            with self.subTest(key=key), self.assertRaises(protocol.OracleError):
                policy.validate_report(protocol.encode(bad), nonce=NONCE, provenance=identity(), final=True)

    def test_later_failure_discards_success_and_private_payload(self):
        report = fixture()
        report.update(status='failed', failure_kind='logical_mismatch', failed_stage='update')
        policy.discard_capture(report, final=True)
        self.assertIsNone(report['config_catalog_attribute_binding'])
        self.assertEqual(report['reader_validation'], 'discarded')
        self.assertEqual(report['observation_validation'], 'discarded')
        self.assertEqual(report['decompression_validation'], 'discarded')

    def test_finite_failure_retained_only_after_all_final_cleanup(self):
        failure = policy.ObservationFailure('structural_rejection', 'config_catalog_attribute_mismatch')
        report = fixture()
        report.update(status='failed', failure_kind=policy.FAILURE_KIND, failed_stage='baseline')
        report['cleanup'].update(container_removed=True, private_staging_removed=True)
        policy.discard_capture(report, failure, final=True)
        self.assertEqual(set(report['config_catalog_attribute_binding']), {'schema', 'status', 'category', 'code'})
        for key in report['cleanup']:
            bad = copy.deepcopy(report)
            bad['cleanup'][key] = False
            policy.discard_capture(bad, failure, final=True)
            self.assertIsNone(bad['config_catalog_attribute_binding'])

    def test_old_lane_and_wrong_reader_recipe_rejected(self):
        self.assertNotEqual(policy.READER_RECIPE_SHA256, matrix.policy.READER_RECIPE_SHA256)
        with self.assertRaises(protocol.OracleError):
            policy.validate_report(protocol.encode(matrix.fixture()), nonce=NONCE, provenance=matrix.identity())
        observe = core.observe_config_catalog_attributes
        def wrong(*a, **kw): return dataclasses.replace(observe(*a, **kw), recipe_sha256='0' * 64)
        with mock.patch.object(core, 'observe_config_catalog_attributes', wrong), self.assertRaises(protocol.OracleError): private()


class AttributeXMLTests(unittest.TestCase):
    setUp = matrix.MatrixXMLManifestTests.setUp
    def build(self):
        return policy.build_identity_manifest(self.expected, self.actual, nonce=NONCE, version=1)

    def test_existing_matrix_xml_has_two_and_zero_collections(self):
        value = self.build()
        self.assertEqual([len(x.attributes) for x in value.catalogs], [2, 0, 0])
        self.assertEqual([row[1:] for row in value.catalogs[0].attributes], [('Payload', 'S', (32, 1)), ('Amount', 'N', (9, 2, 0))])
        self.assertEqual(len(policy.manifest_digest(value)), 64)

    def test_xml_change_rejected_before_comparison(self):
        path = self.actual / 'Catalogs/NativeOracleItems.xml'
        raw = path.read_bytes()
        for old, new in [(b'<v8:Length>32</v8:Length>', b'<v8:Length>7</v8:Length>'),
                         (b'<Name>Payload</Name>', b'<Name>Other</Name>'),
                         (b'<v8:Digits>9</v8:Digits>', b'<v8:Digits>17</v8:Digits>'),
                         (b'<v8:FractionDigits>2</v8:FractionDigits>', b'<v8:FractionDigits>5</v8:FractionDigits>')]:
            self.assertIn(old, raw)
            path.write_bytes(raw.replace(old, new, 1))
            with self.assertRaises(policy.ObservationFailure): self.build()
            path.write_bytes(raw)


if __name__ == '__main__': unittest.main()
