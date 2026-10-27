"""Finite synthetic report controls for partial reference projection only."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'yadinassi/storage'),
               str(ROOT/'scripts'), str(ROOT/'tests')]
import config_root_reference_projection as policy
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as fixtures
import test_native_1c_db_oracle_record_route as old
from test_native_1c_db_oracle_config_root_projection_reader import successful_source, GUID
NONCE, TOKEN = old.NONCE, old.TOKEN
host = old.host


def identity():
    result = fixtures.provenance()
    result['sources'] = {name: 'c'*64 for name in inputs.CONFIG_ROOT_REFERENCE_PROJECTION_SOURCE_FILES}
    return result


def projection():
    source = successful_source()
    return policy.read_projection(source.read_at, source.size, limits=policy.reader.CatalogLimits())


def evidence(token=TOKEN):
    return {'marker': old.marker(token),
        'origin': {'nonce': NONCE, 'token': token, 'clone': 'auditor',
            **{key: fixtures.physical('baseline')[key] for key in ('bytes', 'sha256')}},
        'postimage': {'bytes': 20*8192, 'sha256': 'e'*64}, 'reader': projection()}


class Backend(fixtures.FixtureNative):
    def observe_record_metadata(self, identifier):
        self.event('record_metadata', identifier)
        return evidence()


def fixture(fail=None, cleanup=(True, True)):
    provenance = identity(); report = policy.empty_report(NONCE, provenance)
    backend = Backend(provenance, fail); backend.clean = cleanup
    controller = fixtures.stage.Controller(backend, report); backend.controller = controller
    return controller.run(), backend


class ConfigRootProjectionPolicyTests(unittest.TestCase):
    def check(self, report, final=False):
        return policy.validate_report(protocol.encode(report), nonce=NONCE, provenance=identity(), final=final)

    def test_literal_recipe_and_finite_projection(self):
        self.assertEqual(policy.RECIPE_SHA256, '839bf2937921e5880cf25ff079b17f735d71b34fa06b3ffdb8ba344748a19694')
        self.assertEqual(policy.framing.ConfigRootReferenceProjectionProfile(policy.DECLARATIONS, '0', 0).recipe(), policy.RECIPE_DESCRIPTION)
        value = projection(); raw = policy.encode(value)
        self.assertLessEqual(len(raw), 2048)
        self.assertNotIn(GUID.encode(), raw)
        self.assertNotIn(b'not-a-valid-tail', raw)
        self.assertEqual(value['root_document_validation'], 'not_performed')
        self.assertEqual(value['root_suffix_validation'], 'not_performed')

    def test_report_is_valid_but_not_native_equivalence(self):
        report, _ = fixture(); self.check(report)
        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['native_byte_equivalence'], 'not_observed')
        self.assertEqual(report['native_compatibility'], 'not_claimed')
        self.assertEqual(report['config_root_reference_projection']['reader']['root_identity'], 'not_observed')
        report['cleanup'].update(container_removed=True, private_staging_removed=True)
        report['accepted'] = True; self.check(report, final=True)

    def test_partial_contract_cannot_be_promoted_or_extended(self):
        for key, value in (('root_document_validation','accepted'), ('root_suffix_validation','accepted'),
                ('root_identity','accepted'), ('file_identity','accepted'), ('applied_state','accepted'),
                ('reference_validation','complete_document'), ('projected_root_count',True),
                ('resolved_target_count',2), ('positive_target_count',0), ('guid', GUID)):
            candidate = projection(); candidate[key] = value
            with self.assertRaises(OracleError): policy.validate_projection(candidate)

    def test_missing_extra_and_boolean_numeric_fields_rejected(self):
        value = projection()
        for key in value:
            candidate = copy.deepcopy(value); candidate.pop(key)
            with self.assertRaises(OracleError): policy.validate_projection(candidate)
        for key, item in value.items():
            if type(item) is int:
                candidate = copy.deepcopy(value); candidate[key] = True
                with self.assertRaises(OracleError): policy.validate_projection(candidate)

    def test_source_inventory_binds_projector(self):
        report, _ = fixture()
        for modify in ('missing', 'extra', 'changed'):
            candidate = copy.deepcopy(report)
            source = 'yadinassi/storage/config_root_projection.py'
            if modify == 'missing': candidate['provenance']['sources'].pop(source)
            elif modify == 'extra': candidate['provenance']['sources']['foreign.py'] = 'f'*64
            else: candidate['provenance']['sources'][source] = 'f'*64
            with self.assertRaises(OracleError): self.check(candidate)

    def test_old_schemas_and_foreign_failure_lanes_cannot_be_reused(self):
        report,_=fixture()
        for schema in (4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,24,True):
            candidate=copy.deepcopy(report);candidate['schema']=schema
            with self.assertRaises(OracleError): self.check(candidate)
        import config_content_decode
        for validator in (protocol.validate_report, config_content_decode.validate_report):
            with self.assertRaises(OracleError):
                validator(protocol.encode(report),nonce=NONCE,provenance=identity())
        for kind in ('config_content_decode_failed','config_root_reference_failed','config_root_diagnostic_failed'):
            candidate=copy.deepcopy(report);candidate['failure_kind']=kind
            with self.assertRaises(OracleError): self.check(candidate)

    def test_finite_errors_never_accept_arbitrary_input_text(self):
        for category,code in (('PRIVATE','config_projection_prefix'),
                ('structural_rejection','PRIVATE'), ('resource_limit','config_projection_prefix')):
            with self.assertRaises(OracleError): policy.ObservationFailure(category,code)
        for kind,code in ((policy.reader.InvalidStructure,'config_projection_prefix'),
                (policy.reader.UnsupportedLayout,'config_projection_root_missing'),
                (policy.reader.UnsupportedLayout,'config_projection_target_missing'),
                (policy.reader.UnsupportedLayout,'config_projection_target_empty'),
                (policy.reader.ResourceLimit,'config_projection_prefix_bytes')):
            self.assertEqual(policy.reader_failure(kind(code)).code,code)

    def test_partial_and_final_failure_cleanup(self):
        for category, code in (('structural_rejection','config_projection_prefix'),
                ('unsupported_layout','config_projection_target_missing'),
                ('resource_limit','config_projection_prefix_bytes')):
            provenance=identity(); initial=policy.empty_report(NONCE, provenance)
            backend=Backend(provenance); backend.reader_attempted=True
            failure=policy.ObservationFailure(category, code)
            backend.observe_record_metadata=mock.Mock(side_effect=failure)
            controller=fixtures.stage.Controller(backend, initial); backend.controller=controller
            report=controller.run()
            self.check(report)
            self.assertEqual(report['config_root_reference_projection']['code'], code)
            report['cleanup'].update(container_removed=True, private_staging_removed=True)
            policy.discard_capture(report, failure, final=True); self.check(report, final=True)
            for key in report['cleanup']:
                candidate = copy.deepcopy(report); candidate['cleanup'][key] = False
                with self.assertRaises(OracleError): self.check(candidate, final=True)

if __name__ == '__main__': unittest.main()
