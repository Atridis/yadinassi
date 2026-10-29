"""Synthetic verification controls, not a claim of native codec acceptance."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest import mock
from uuid import UUID

import test_native_catalog_reference_identity as old
import test_native_catalog_reference_lifecycle as lifecycle
import catalog_reference_codec as policy
import catalog_reference_identity as measurement
import catalog_reference_uuid as codec
import inputs
import protocol
from contract import source_binding


def fixture(case='distinct_a', nonce=None):
    report = old.fixture(case, nonce)
    report.update(schema=policy.SCHEMA, lane=policy.LANE, record_validation=policy.VERDICT)
    report['provenance']['sources'] = {key:'c'*64 for key in inputs.CATALOG_CODEC_SOURCE_FILES}
    capture = report['record_readback']
    capture.update(schema=policy.CAPTURE_SCHEMA, profile_id=policy.PROFILE_ID,
                   profile_sha256=policy.PROFILE_SHA256)
    capture['audit']['source_manifest_sha256'] = source_binding(report['provenance'])
    for state in capture['states']:
        state['codec'] = 'NNNN' if state['snapshot'] == 'baseline' else 'TTTT'
    return report


def validate(report):
    return policy.validate_report(protocol.encode(report), nonce=report['nonce'],
                                  provenance=report['provenance'], final=True)


class CodecPolicyTests(unittest.TestCase):
    def test_closed_new_profile_and_unchanged_measurement(self):
        validate(fixture())
        old.validate(old.fixture(permutation=list(range(16))))
        with self.assertRaises(Exception): old.validate(fixture())
        with self.assertRaises(Exception): validate(old.fixture())
        altered = old.fixture()
        altered['provenance']['sources'][policy.CODEC_SOURCE] = 'c'*64
        altered['record_readback']['audit']['source_manifest_sha256'] = source_binding(altered['provenance'])
        with self.assertRaises(Exception): old.validate(altered)

    def test_every_direction_stage_and_image_is_required(self):
        for stage in (1, 2):
            for position in range(4):
                report = fixture()
                value = list('TTTT'); value[position] = 'F'
                report['record_readback']['states'][stage]['codec'] = ''.join(value)
                with self.assertRaises(Exception): validate(report)
        for index in range(3):
            for invalid in (None, True, 'TT', 'TTTTT', ['TT','TT'], 'NNNN' if index else 'TTTT'):
                report = fixture(); report['record_readback']['states'][index]['codec'] = invalid
                with self.assertRaises(Exception): validate(report)
            report = fixture(); del report['record_readback']['states'][index]['codec']
            with self.assertRaises(Exception): validate(report)
        report = fixture(); report['record_readback']['states'].reverse()
        with self.assertRaises(Exception): validate(report)

    def test_unknown_fields_and_wrong_source_are_rejected_before_acceptance(self):
        for mutate in (
            lambda r:r['record_readback']['states'][1].update(private='secret'),
            lambda r:r['record_readback'].update(codec_source_sha256='f'*64),
            lambda r:r['record_readback'].update(profile_sha256='f'*64),
            lambda r:r['provenance']['sources'].pop(policy.CODEC_SOURCE),
            lambda r:r['record_readback']['states'][1]['reference'].update(witness_sha256='invalid'),
            lambda r:r.update(schema=39),
        ):
            report = fixture(); mutate(report)
            with self.assertRaises(Exception): validate(report)

    def test_codec_success_cannot_contradict_distinct_byte_measurement(self):
        report = fixture()
        for state in report['record_readback']['states'][1:]:
            state['reference'].update(permutation=list(range(16)),hypothesis_match=False)
        with self.assertRaises(Exception): validate(report)
        old.validate(old.fixture(permutation=list(range(16))))

    def test_aggregate_requires_both_distinct_cases_and_complete_reports(self):
        a, b = fixture(), fixture('distinct_b', 'b'*32)
        result = policy.aggregate_reports(protocol.encode(a), protocol.encode(b), provenance=a['provenance'])
        self.assertEqual(result['schema'], 44)
        self.assertIs(result['codec_verified'], True)
        self.assertEqual(result['codec_source_sha256'], a['provenance']['sources'][policy.CODEC_SOURCE])
        self.assertNotIn('record_readback', result)
        for bad in (fixture('distinct_a','b'*32), fixture('distinct_b'), old.fixture('distinct_b','b'*32)):
            with self.assertRaises(Exception):
                policy.aggregate_reports(protocol.encode(a), protocol.encode(bad), provenance=a['provenance'])
        b['record_readback']['states'][2]['codec'] = 'TTTF'
        with self.assertRaises(Exception):
            policy.aggregate_reports(protocol.encode(a), protocol.encode(b), provenance=a['provenance'])


class ByteBackend(lifecycle.ByteBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.record_policy = policy
        self.reference_codec = True

    def freeze(self, database, identifier):
        original = lifecycle.old.row
        physical = bytes.fromhex({
            'distinct_a':'8899aabbccddeeff4677445500112233',
            'distinct_b':'95c02e74b836fa614b8fe652d3a17c09'}[self.reference_case])
        def row(*args, **kwargs):
            raw = original(*args, **kwargs)
            return raw[:17] + physical + raw[33:]
        with mock.patch.object(lifecycle.old, 'row', row):
            return lifecycle.old.ByteBackend.freeze(self, database, identifier)


def run_fixture(test, **kwargs):
    temp = tempfile.TemporaryDirectory(); test.addCleanup(temp.cleanup)
    provenance = lifecycle.old.identity()
    provenance['sources'] = {key:'c'*64 for key in inputs.CATALOG_CODEC_SOURCE_FILES}
    report = policy.empty_report(lifecycle.old.old.NONCE, provenance,
                                 reference_case=kwargs.get('case','distinct_a'))
    backend = ByteBackend(Path(temp.name).resolve(), provenance, **kwargs)
    controller = lifecycle.old.old.fixture.stage.Controller(backend, report)
    backend.controller = controller
    return controller.run(), backend


@unittest.skipUnless(lifecycle.old.old.POSIX, 'requires descriptor-relative POSIX operations')
class CodecLifecycleTests(unittest.TestCase):
    def setUp(self): lifecycle.old.old.normalize_owners(self)

    def test_both_cases_real_six_reader_paths_and_eight_direction_checks(self):
        for case in policy.CASES:
            calls = []
            original = lifecycle.old.coordinator.read_catalog_binding
            def read(read_at, size, **kwargs):
                calls.append(set(kwargs))
                return original(read_at, size, **kwargs)
            with mock.patch.object(lifecycle.old.coordinator, 'read_catalog_binding', side_effect=read), \
                 mock.patch.object(codec, 'decode_catalog_reference_uuid', wraps=codec.decode_catalog_reference_uuid) as dec, \
                 mock.patch.object(codec, 'encode_catalog_reference_uuid', wraps=codec.encode_catalog_reference_uuid) as enc:
                report, backend = run_fixture(self, case=case)
            self.assertEqual(report['status'], 'ok', report)
            self.assertEqual((dec.call_count,enc.call_count), (4,4))
            self.assertEqual(calls, [{'catalog_name','limits'}]*6)
            self.assertEqual([s['codec'] for s in report['record_readback']['states']], ['NNNN','TTTT','TTTT'])
            report['cleanup'].update(container_removed=True,private_staging_removed=True); report['accepted']=True
            validate(report)
            self.assertFalse(list(backend.artifacts.iterdir()))

    def test_wrong_but_inverse_and_single_direction_codecs_fail(self):
        variants = (
            (lambda p: UUID(bytes=p), lambda u:u.bytes),
            (lambda p: UUID(int=0), codec.encode_catalog_reference_uuid),
            (codec.decode_catalog_reference_uuid, lambda u:bytes(16)),
        )
        for dec, enc in variants:
            with mock.patch.object(codec,'decode_catalog_reference_uuid',side_effect=dec), \
                 mock.patch.object(codec,'encode_catalog_reference_uuid',side_effect=enc):
                report, backend = run_fixture(self)
            self.assertEqual(report['status'],'failed')
            self.assertFalse(report['accepted'])
            self.assertTrue(report['cleanup']['raw_files_removed'])
            self.assertFalse(list(backend.artifacts.iterdir()))
            report['cleanup'].update(container_removed=True,private_staging_removed=True)
            validate(report)

    def test_bad_image_or_token_fails_before_codec(self):
        for fault in ('origin','postimage','token','module'):
            with mock.patch.object(codec,'decode_catalog_reference_uuid', wraps=codec.decode_catalog_reference_uuid) as dec:
                report, backend = run_fixture(self, fault=fault)
            self.assertEqual(report['status'],'failed')
            # postimage mismatch is discovered after the first (origin) call.
            self.assertEqual(dec.call_count, 1 if fault == 'postimage' else 0)
            self.assertTrue(report['cleanup']['raw_files_removed'])


class CodecRedumpTests(unittest.TestCase):
    def test_codec_profile_creates_and_rechecks_real_manifest_for_both_cases(self):
        import test_native_catalog_reference_redump as redump
        fixture_case = redump.ReferenceRedumpTests()
        fixture_case.setUp()
        self.addCleanup(fixture_case.doCleanups)
        for case in policy.CASES:
            native = fixture_case.backend({'reference_case':case,'reference_codec':True})
            self.assertIs(native.record_policy,policy)
            fixture_case.redump(native,'seed_v1')
            self.assertIsNotNone(native.identity_manifest)
            fixture_case.redump(native,'baseline')
            self.assertTrue(native.identity_baseline_verified)
            self.assertEqual(native.record_policy.rendered_module_sha256(native.nonce,case),
                             measurement.rendered_module_sha256(native.nonce,case))
