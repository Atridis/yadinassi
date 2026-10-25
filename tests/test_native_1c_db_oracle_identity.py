"""Owned synthetic identity-policy checks, never native acceptance evidence."""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import itertools
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'yadinassi/storage'),
                str(ROOT/'scripts'), str(ROOT/'tests')]
import dbnames_identity as policy
import inputs
import params_extraction as extraction
import protocol
from snapshots import OracleError
import inject_metadata
import test_native_1c_db_oracle_stage as fixtures
import test_native_1c_db_oracle_record_route as old
import test_native_1c_db_oracle_extraction as transport
from test_filedb_catalog import Source, P, descriptor
from test_filedb_records import serialize

NONCE, TOKEN = old.NONCE, old.TOKEN
UUIDS = ('abcdef01-0000-0000-0000-000000000001',
         'abcdef02-0000-0000-0000-000000000002',
         'abcdef03-0000-0000-0000-000000000003')
ENTRIES = ((UUIDS[0], 'Reference', 100), (UUIDS[1], 'Fld', 54), (UUIDS[2], 'Fld', 55))


def identity():
    value = fixtures.provenance()
    value['sources'] = {name: 'c'*64 for name in inputs.IDENTITY_SOURCE_FILES}
    return value


def manifest():
    return {'schema': 1, 'nonce': NONCE, 'metadata_version': 1,
        'expected_sources_sha256': 'a'*64, 'catalog_sha256': 'b'*64,
        'roles': [{'role': role, 'uuid': value} for role, value in zip(policy.ROLES, UUIDS)]}


def payload(entries=ENTRIES, header=77):
    text = '{' + str(header) + ',{' + str(len(entries)) + ''.join(
        ',{' + uuid + ',"' + kind + '",' + str(number) + '}' for uuid, kind, number in entries) + '}}'
    return b'\xef\xbb\xbf' + text.encode('ascii')


def native_projection():
    return {'schema': 1, 'target': policy.TARGET, 'table': {
        'storage_name': '_Reference100', 'logical_name': policy.TARGET, 'metadata_name': policy.TARGET,
        'fields': [{'storage_name': '_Fld' + str(number), 'logical_name': logical,
                    'metadata_name': policy.TARGET + '.Реквизит.' + logical, 'type_text': 'Uninterpreted'}
                   for logical, number in (('Payload', 54), ('Amount', 55))]}}


def marker(token=TOKEN):
    value = old.marker(token)
    value['record_metadata'] = native_projection()
    return value


def source(data=None):
    """Small independent extraction fixture plus the exact physical target table."""
    value = transport.source(payload() if data is None else data)
    table = serialize(('_Reference100', 0,
        ('Fields', ('_FLD55', 'N', 0, 9, 2, 'CS'), ('_FLD54', 'NVC', 0, 32, 0, 'CS')),
        ('Indexes',), ('Recordlock', '0'), ('Files', 0, 0, 0))).encode('utf-8')
    value.catalog((8, 2))
    value.chain((8,), table)
    return value


def private(entries=ENTRIES, *, fields=None, tables=None):
    """Independently parsed complete index/catalog, useful for isolated joins."""
    if fields is None:
        fields = '{"_FLD55","N",0,9,2,"CS"},{"_FLD54","NVC",0,32,0,"CS"}'
    raw = payload(entries)
    data = Source().ready(tables if tables is not None else {2: descriptor('_Reference100', fields=fields)})
    owner = policy.reader.CatalogReader(data.read_at, data.size)
    catalog = owner.read_catalog()
    index = policy.parser.parse_dbnames(raw, profile=policy.parser.DBNamesParseProfile(policy.PROFILE_ID),
                                       limits=policy.parser.DBNamesParseLimits())
    projection = {'schema': 1, 'target': extraction.TARGET, 'profile_id': extraction.PROFILE_ID,
        'profile_sha256': extraction.PROFILE_SHA256, 'packed_bytes': 10, 'packed_sha256': 'd'*64,
        'plain_bytes': len(raw), 'plain_sha256': hashlib.sha256(raw).hexdigest()}
    owner._budget.charge('output_bytes', policy.MAX_PROJECTION_BYTES)
    return policy._ReaderEvidence(index, catalog, tuple(projection.items()), owner._budget)


def projection():
    return policy.compare_identity(private(), manifest(), native_projection(), nonce=NONCE)


def evidence(token=TOKEN):
    data = source()
    parsed = policy.read_projection(data.read_at, data.size, limits=policy.reader.CatalogLimits())
    return {'marker': marker(token), 'origin': {'nonce': NONCE, 'token': token, 'clone': 'auditor',
        **{key: fixtures.physical('baseline')[key] for key in ('bytes', 'sha256')}},
        'postimage': {'bytes': data.size, 'sha256': hashlib.sha256(data.full_bytes()).hexdigest()},
        'identity_manifest': manifest(), 'reader': parsed}


class Backend(fixtures.FixtureNative):
    def observe_record_metadata(self, identifier):
        self.event('record_metadata', identifier)
        return evidence()


def fixture(fail=None, cleanup=(True, True)):
    provenance = identity(); report = policy.empty_report(NONCE, provenance)
    backend = Backend(provenance, fail); backend.clean = cleanup
    controller = fixtures.stage.Controller(backend, report); backend.controller = controller
    return controller.run(), backend


class IdentityComparatorTests(unittest.TestCase):
    def compare(self, parsed=None, expected=None, native=None):
        return policy.compare_identity(private() if parsed is None else parsed,
            manifest() if expected is None else expected,
            native_projection() if native is None else native, nonce=NONCE)

    def assert_code(self, code, parsed=None, expected=None, native=None):
        with self.assertRaises(policy.ObservationFailure) as context:
            self.compare(parsed, expected, native)
        self.assertEqual(context.exception.code, code)
        self.assertNotIn('abcdef', str(context.exception))
        self.assertNotIn('PRIVATE', str(context.exception))

    def test_complete_shuffled_entries_and_native_fields_match_three_fixed_roles(self):
        for order in itertools.permutations(ENTRIES):
            expected = native_projection(); expected['table']['fields'].reverse()
            result = self.compare(private(order), native=expected)
            self.assertEqual([row['role'] for row in result['rows']], list(policy.ROLES))
            self.assertEqual([row['ordinal'] for row in result['rows']], [order.index(entry) for entry in ENTRIES])
            self.assertEqual(result['summary']['header_value'], 77)
            self.assertEqual(result['summary']['declared_count'], 3)
            self.assertEqual(result['rows'][1]['native_name'], '_Fld54')
            self.assertEqual(result['rows'][1]['physical_name'], '_FLD54')
            self.assertNotEqual(result['rows'][1]['native_name'], result['rows'][1]['physical_name'])

    def test_zero_opaque_and_unrelated_duplicates_remain_private_in_summary(self):
        extras = ((policy.ZERO_UUID, 'Mystery', 0),
                  ('99999999-0000-0000-0000-000000000009', 'PRIVATE', 17))
        entries = (extras[0], ENTRIES[2], extras[1], ENTRIES[0], extras[1], ENTRIES[1])
        parsed = private(entries)
        self.assertEqual(len(parsed.index.entries), 6)
        result = self.compare(parsed)
        self.assertEqual(result['summary']['opaque_kind_count'], 3)
        self.assertEqual(result['summary']['zero_uuid_count'], 1)
        public = protocol.encode(result)
        for secret in (b'99999999', b'PRIVATE', policy.ZERO_UUID.encode()):
            self.assertNotIn(secret, public)
        self.assertEqual(result['summary']['entry_count'], 6)

    def test_raw_uuid_case_is_preserved_but_identity_is_canonical(self):
        parsed = private(tuple((uuid.upper(), kind, number) for uuid, kind, number in ENTRIES))
        rows = self.compare(parsed)['rows']
        self.assertEqual([row['raw_uuid'] for row in rows], [uuid.upper() for uuid in UUIDS])
        self.assertEqual([row['parsed_uuid'] for row in rows], list(UUIDS))

    def test_missing_duplicate_competing_kind_and_zero_id_are_not_first_match(self):
        self.assert_code('target_identity_missing', private(ENTRIES[:2]))
        self.assert_code('target_identity_ambiguous', private(ENTRIES + (ENTRIES[1],)))
        self.assert_code('target_identity_ambiguous', private(ENTRIES + ((UUIDS[1], 'Other', 54),)))
        self.assert_code('target_kind_mismatch', private((ENTRIES[0], (UUIDS[1], 'fld', 54), ENTRIES[2])))
        self.assert_code('target_id_not_positive', private((ENTRIES[0], (UUIDS[1], 'Fld', 0), ENTRIES[2])))
        self.assert_code('duplicate_physical_target', private((ENTRIES[0], ENTRIES[1], (UUIDS[2], 'Fld', 54))))
        self.assert_code('duplicate_physical_target', private(ENTRIES + ((policy.ZERO_UUID, 'Fld', 54),)))
        self.assert_code('duplicate_physical_target', private(ENTRIES + ((policy.ZERO_UUID, 'Reference', 100),)))

    def test_native_exact_full_path_and_spelling_are_independent(self):
        for key in ('logical_name', 'metadata_name'):
            changed = native_projection(); changed['table'][key] = 'Catalog.NativeOracleItems'
            self.assert_code('native_role_mismatch', native=changed)
        for spelling in ('_FLD54', '_fld54', '_Fld054', 'prefix_Fld54', '_Fld54_suffix'):
            changed = native_projection(); changed['table']['fields'][0]['storage_name'] = spelling
            self.assert_code('native_name_mismatch', native=changed)
        for key, value in (('logical_name', 'payload'), ('metadata_name', 'Other.Реквизит.Payload')):
            changed = native_projection(); changed['table']['fields'][0][key] = value
            self.assert_code('native_role_mismatch', native=changed)
        changed = native_projection(); changed['table']['fields'].pop(0)
        self.assert_code('native_role_missing', native=changed)
        changed = native_projection()
        changed['table']['fields'].append({**changed['table']['fields'][0], 'storage_name': '_Fld99'})
        self.assert_code('native_role_ambiguous', native=changed)
        # A correct-looking suffix alone cannot select an unrelated metadata row.
        changed = native_projection(); changed['table']['fields'][0].update(
            logical_name='Unrelated', metadata_name='Private.Реквизит.Payload')
        self.assert_code('native_role_missing', native=changed)

    def test_physical_exact_spelling_and_containment_without_suffix_search(self):
        for spelling in ('_Fld54', '_fld54', '_FLD054', 'prefix_FLD54', '_FLD54_suffix'):
            fields = '{"' + spelling + '","NVC",0,32,0,"CS"},{"_FLD55","N",0,9,2,"CS"}'
            self.assert_code('physical_field_missing', private(fields=fields))
        self.assert_code('physical_table_missing', private(tables={2: descriptor('_Reference0100')}))
        parsed = private()
        duplicate = replace(parsed.catalog, tables=parsed.catalog.tables * 2)
        self.assert_code('physical_table_ambiguous', replace(parsed, catalog=duplicate))
        duplicate_field = replace(parsed.catalog.tables[0], fields=parsed.catalog.tables[0].fields * 2)
        self.assert_code('physical_field_ambiguous', replace(parsed,
            catalog=replace(parsed.catalog, tables=(duplicate_field,))))
        # Both fields exist, but only in a different table; no global suffix scan.
        self.assert_code('physical_field_missing', private(tables={
            2: descriptor('_Reference100', fields='{"_FLD55","N",0,9,2,"CS"}'),
            3: descriptor('Other', fields='{"_FLD54","NVC",0,32,0,"CS"}')}))

    def test_projection_is_closed_and_rechecks_derived_values(self):
        for path, value in ((('schema',), True), (('profile_id',), 'fallback'),
                (('profile_sha256',), 'a'*64), (('summary', 'root_arity'), 3),
                (('summary', 'header_value'), True), (('summary', 'declared_count'), 4),
                (('summary', 'opaque_kind_count'), 1), (('summary', 'zero_uuid_count'), 1),
                (('rows', 1, 'parsed_uuid'), UUIDS[2]), (('rows', 1, 'raw_uuid'), UUIDS[2]),
                (('rows', 1, 'id'), True), (('rows', 1, 'ordinal'), 0),
                (('rows', 1, 'logical_name'), 'Other'), (('rows', 1, 'metadata_name'), 'Other.Payload'),
                (('rows', 1, 'native_name'), '_FLD54'), (('rows', 1, 'physical_name'), '_Fld54'),
                (('rows', 1, 'native_equal'), 1), (('rows', 1, 'kind'), 'fld')):
            changed = projection(); target = changed
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.assertRaises(OracleError): policy.validate_projection(changed, manifest=manifest())
        changed = projection(); changed['rows'][0]['private'] = 'PRIVATE'
        with self.assertRaises(OracleError): policy.validate_projection(changed, manifest=manifest())
        changed = projection(); changed['summary']['private_uuid'] = 'PRIVATE'
        with self.assertRaises(OracleError): policy.validate_projection(changed, manifest=manifest())

    def test_finite_parser_failure_inventory_has_no_fallback_or_exception_text(self):
        for class_name, (category, codes) in policy.PARSER_ERRORS.items():
            cls = getattr(policy.parser, class_name)
            self.assertEqual(codes, cls.codes)
            for code in codes:
                classified = policy.reader_failure(cls(code))
                self.assertEqual((classified.category, classified.code), (category, code))
        class Derived(policy.parser.InvalidDBNames): pass
        with self.assertRaises(OracleError): policy.reader_failure(Derived('dbnames_grammar'))
        for category, code in (('PRIVATE', 'PRIVATE'), ('identity_mismatch', 'PRIVATE')):
            with self.assertRaises(OracleError): policy.ObservationFailure(category, code)


class IdentityManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        source = self.root/'source'; source.mkdir()
        shutil.copyfile(ROOT/'tests/fixtures/native_bootstrap/Configuration.xml', source/'Configuration.xml')
        (source/'ConfigDumpInfo.xml').write_text('synthetic bookkeeping', encoding='utf-8')
        self.expected = self.root/'expected'
        # Pure source construction, not a native invocation.
        if sys.platform == 'win32':
            patch = mock.patch.object(inject_metadata, 'Path', PurePosixPath)
            patch.start(); self.addCleanup(patch.stop)
        inject_metadata.inject(source, self.expected, nonce=NONCE, evidence=PurePosixPath('/tmp/identity-evidence'))
        self.actual = self.root/'actual'; shutil.copytree(self.expected, self.actual)

    def build(self, **kwargs):
        inject_metadata.verify_redump(self.expected, self.actual, 1)
        return policy.build_identity_manifest(self.expected, self.actual,
            nonce=kwargs.get('nonce', NONCE), version=kwargs.get('version', 1))

    def catalog(self):
        return inject_metadata.read_xml(self.actual/'Catalogs/NativeOracleItems.xml')[1]

    def test_verified_manifest_binds_v1_nonce_sources_and_canonical_catalog(self):
        first = self.build()
        self.assertEqual(first['metadata_version'], 1)
        self.assertEqual(first['nonce'], NONCE)
        self.assertEqual([row['role'] for row in first['roles']], list(policy.ROLES))
        self.assertEqual(first['expected_sources_sha256'], hashlib.sha256(protocol.encode(
            dict(sorted(inject_metadata._hashes(self.expected).items())))).hexdigest())
        self.assertEqual(first['catalog_sha256'], hashlib.sha256(protocol.encode(
            inject_metadata._canonical(self.catalog()))).hexdigest())
        self.assertEqual(first, self.build())
        self.assertLessEqual(len(protocol.encode(first)), policy.MAX_MANIFEST_BYTES)
        for version in (True, 0, 2, '1', None):
            with self.assertRaises(OracleError): self.build(version=version)
        for nonce in ('', 'a'*31, 'g'*32, True, None):
            with self.assertRaises(OracleError): self.build(nonce=nonce)

    def test_uuid_roles_use_exact_paths_not_child_order_or_generated_type_ids(self):
        root = self.catalog(); expected = policy._xml_identities(root)
        ns = '{' + inject_metadata.NS + '}'
        catalog = root.find(ns+'Catalog')
        children = catalog.find(ns+'ChildObjects'); children[:] = list(reversed(list(children)))
        self.assertEqual(policy._xml_identities(root), expected)
        generated = catalog.find(ns+'InternalInfo')
        for element in generated.iter():
            if element.tag.endswith('TypeId') or element.tag.endswith('ValueId'):
                element.text = policy.ZERO_UUID
        self.assertEqual(policy._xml_identities(root), expected)
        # Names, not UUID attribute order or a generated UUID, identify each role.
        children[0].attrib = dict(reversed(list(children[0].attrib.items())))
        self.assertEqual(policy._xml_identities(root), expected)

    def test_wrong_namespace_path_role_zero_and_colliding_uuids_fail(self):
        ns = '{' + inject_metadata.NS + '}'
        changes = [lambda root: setattr(root, 'tag', '{wrong}MetaDataObject'),
            lambda root: root.set('version', '2.19'),
            lambda root: root.find(ns+'Catalog').set('uuid', policy.ZERO_UUID),
            lambda root: root.find('.//'+ns+'Attribute/'+ns+'Properties/'+ns+'Name').__setattr__('text', 'Other'),
            lambda root: root.find(ns+'Catalog/'+ns+'ChildObjects')[0].__setattr__('tag', '{wrong}Attribute'),
            lambda root: root.find(ns+'Catalog/'+ns+'ChildObjects')[0].set('uuid', root.find(ns+'Catalog').get('uuid')),
            lambda root: root.find(ns+'Catalog/'+ns+'ChildObjects').append(copy.deepcopy(root.find(ns+'Catalog/'+ns+'ChildObjects')[0]))]
        for change in changes:
            root = self.catalog(); change(root)
            with self.assertRaises(policy.ObservationFailure): policy._xml_identities(root)
        # Moving the target Name below an unrelated wrapper is not a match.
        root = self.catalog(); props = root.find(ns+'Catalog/'+ns+'Properties')
        name = props.find(ns+'Name'); props.remove(name); ET.SubElement(props, ns+'Wrapper').append(name)
        with self.assertRaises(policy.ObservationFailure): policy._xml_identities(root)

    def test_manifest_validation_rejects_forged_version_nonce_role_and_duplicate(self):
        for mutation in (lambda v: v.update(metadata_version=2), lambda v: v.update(schema=True),
                lambda v: v.update(nonce='f'*32), lambda v: v.update(expected_sources_sha256='PRIVATE'),
                lambda v: v['roles'][0].update(role='other'),
                lambda v: v['roles'][0].update(uuid=policy.ZERO_UUID),
                lambda v: v['roles'][0].update(uuid=UUIDS[1]),
                lambda v: v['roles'].reverse(), lambda v: v.update(private='PRIVATE')):
            value = manifest(); mutation(value)
            with self.assertRaises(OracleError): policy.validate_manifest(value, nonce=NONCE)


class IdentityReportTests(unittest.TestCase):
    def check(self, report, final=False):
        return policy.validate_report(protocol.encode(report), nonce=NONCE, provenance=identity(), final=final)

    def test_report_claim_is_narrow_and_all_bindings_are_required(self):
        report, backend = fixture(); self.check(report)
        capture = report['dbnames_identity']
        self.assertEqual((report['schema'], capture['schema']), (9, 10))
        self.assertEqual(report['reader_validation'], policy.VERDICT)
        self.assertEqual(report['mapping_validation'], policy.VERDICT)
        self.assertEqual(report['extraction_validation'], extraction.VERDICT)
        self.assertEqual(report['native_byte_equivalence'], 'not_observed')
        self.assertEqual(report['native_compatibility'], 'not_claimed')
        self.assertEqual(report['record_validation'], 'not_run')
        self.assertEqual(capture['identity_basis'], policy.IDENTITY_BASIS)
        self.assertEqual(backend.events.count(('record_metadata', 'baseline')), 1)
        self.assertEqual((len(report['stages']), len(report['snapshots']), len(report['comparisons'])), (13, 11, 5))
        for key in ('nonce', 'token', 'source_manifest_sha256', 'reader_source_sha256',
                'policy_source_sha256', 'extractor_source_sha256', 'parser_source_sha256',
                'image', 'platform', 'locale', 'timezone', 'xml_manifest_sha256', 'identity_basis'):
            changed = copy.deepcopy(report); changed['dbnames_identity'][key] = 'PRIVATE'
            with self.assertRaises(OracleError): self.check(changed)
        for key in ('origin', 'postimage'):
            changed = copy.deepcopy(report); changed['dbnames_identity'][key]['sha256'] = 'PRIVATE'
            with self.assertRaises(OracleError): self.check(changed)
        changed = copy.deepcopy(report); changed['dbnames_identity']['xml_manifest']['roles'][0]['uuid'] = UUIDS[1]
        with self.assertRaises(OracleError): self.check(changed)
        changed = copy.deepcopy(report); changed['dbnames_identity']['metadata_version'] = True
        with self.assertRaises(OracleError): self.check(changed)
        for key in ('mapping_validation', 'reader_validation', 'extraction_validation'):
            changed = copy.deepcopy(report); changed[key] = 'not_run'
            with self.assertRaises(OracleError): self.check(changed)
        for key in ('record_validation', 'layout_validation'):
            changed = copy.deepcopy(report); changed[key] = 'validated'
            with self.assertRaises(OracleError): self.check(changed)
        changed = copy.deepcopy(report); changed['dbnames_identity']['reader']['entries'] = ['PRIVATE']
        with self.assertRaises(OracleError): self.check(changed)

    def test_every_later_stage_and_all_four_cleanup_gates_discard_success(self):
        for failed in protocol.STAGES[3:-1]:
            report, _ = fixture(failed); self.check(report)
            self.assertIsNone(report['dbnames_identity'])
            self.assertEqual(report['mapping_validation'], 'discarded')
        for cleanup in ((False, True), (True, False), (False, False)):
            report, _ = fixture(cleanup=cleanup); self.check(report)
            self.assertIsNone(report['dbnames_identity'])
        for gate in ('container_removed', 'private_staging_removed'):
            report, _ = fixture()
            report['cleanup'].update(container_removed=True, private_staging_removed=True)
            report['cleanup'][gate] = False
            old.host.fail_report(report, 'cleanup_unverified', 'cleanup', preserve_primary=True)
            self.check(report, final=True)
            self.assertIsNone(report['dbnames_identity'])

    def test_failed_capture_is_finite_and_requires_successful_cleanup(self):
        for failure in (policy.ObservationFailure('identity_mismatch', 'target_identity_ambiguous'),
                        policy.ObservationFailure('structural_rejection', 'dbnames_utf8_bom'),
                        OracleError('timeout'), AssertionError('PRIVATE')):
            provenance = identity(); report = policy.empty_report(NONCE, provenance)
            backend = Backend(provenance); backend.reader_attempted = True
            backend.observe_record_metadata = mock.Mock(side_effect=failure)
            controller = fixtures.stage.Controller(backend, report); backend.controller = controller
            result = controller.run(); self.check(result)
            self.assertNotIn(b'PRIVATE', protocol.encode(result))
            self.assertNotEqual(result['reader_validation'], policy.VERDICT)
            if type(failure) is policy.ObservationFailure:
                self.assertEqual(result['dbnames_identity'], {'schema': 10, 'status': 'failed',
                    'category': failure.category, 'code': failure.code})
                for gate in ('container_removed', 'private_staging_removed'):
                    late = copy.deepcopy(result)
                    late['cleanup'].update(container_removed=True, private_staging_removed=True)
                    late['cleanup'][gate] = False
                    old.host.fail_report(late, 'cleanup_unverified', 'cleanup', preserve_primary=True)
                    self.check(late, final=True); self.assertIsNone(late['dbnames_identity'])

    def test_older_closed_validators_reject_new_lane_and_new_failures(self):
        import comparison
        import params_observation
        import record_observation
        import record_validation
        report, _ = fixture()
        for old_policy in (protocol, comparison, record_observation, record_validation,
                           params_observation, extraction):
            with self.assertRaises(OracleError):
                old_policy.validate_report(protocol.encode(report), nonce=NONCE, provenance=identity())
        for kind in ('catalog_comparison_failed', 'record_observation_failed',
                     'record_readback_failed', 'params_observation_failed', extraction.FAILURE_KIND):
            changed = copy.deepcopy(report); changed.update(status='failed', failure_kind=kind, failed_stage='baseline')
            with self.assertRaises(OracleError): self.check(changed)


if __name__ == '__main__':
    unittest.main()
