"""Actual prototype schema envelope with full capture cap and final newline."""
import copy
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import config_catalog_observation as policy
import protocol
import snapshots
import test_native_1c_db_oracle_config_root_projection_budget as previous
import test_native_1c_db_oracle_catalog_reference_policy as fixture
wire=previous.wire

def projection_envelope():
    value=previous.projection_envelope()
    value.update(recipe_id=policy.RECIPE_ID,recipe_sha256=policy.RECIPE_SHA256,
        catalog_collection_count=64,catalog_declared_count=256,catalog_resolved_count=256,
        catalog_positive_count=256,catalog_validation='declared_references_positive')
    return value

def capture_skeleton():
    value=copy.deepcopy(fixture.fixture()['config_catalog_observation']);value['reader']=None
    value['origin']['bytes']=value['postimage']['bytes']=snapshots.MAX_FILE_BYTES
    return value

def report_envelope():
    value=previous.report_envelope();del value['config_root_reference_projection']
    value.update(schema=policy.SCHEMA,lane=policy.LANE,provenance=fixture.identity(),config_catalog_observation=None)
    for key in ('reader_validation','observation_validation'):
        value[key]=previous.old.longest(('not_run','failed','discarded',policy.VERDICT))
    return value

def proof_results():
    skeleton=len(wire(capture_skeleton()));report=len(wire(report_envelope()))
    return dict(source_count=len(policy.CATALOG_SOURCE_FILES),projection_envelope=len(wire(projection_envelope())),
        projection_cap=policy.MAX_PROJECTION_BYTES,capture_skeleton=skeleton,
        capture_with_full_projection_cap=skeleton-4+policy.MAX_PROJECTION_BYTES,capture_cap=policy.MAX_CAPTURE_BYTES,
        failure_capture=len(wire(dict(schema=policy.CAPTURE_SCHEMA,status='failed',category=previous.old.longest(policy.DIAGNOSTICS),
            code=previous.old.longest(code for codes in policy.DIAGNOSTICS.values() for code in codes)))),
        report_without_capture=report,report_with_full_capture_cap_and_newline=report-4+policy.MAX_CAPTURE_BYTES+1,
        report_cap=protocol.MAX_REPORT_BYTES,margin=protocol.MAX_REPORT_BYTES-(report-4+policy.MAX_CAPTURE_BYTES+1))

class CatalogReferenceBudgetTests(unittest.TestCase):
    def test_complete_actual_envelope(self):
        result=proof_results();self.assertEqual(result,EXPECTED)
        self.assertLessEqual(result['projection_envelope'],result['projection_cap'])
        self.assertLessEqual(result['capture_with_full_projection_cap'],result['capture_cap'])
        self.assertLessEqual(result['report_with_full_capture_cap_and_newline'],result['report_cap'])
        report=report_envelope()
        self.assertEqual((len(report['stages']),len(report['snapshots']),len(report['comparisons']),len(report['artifacts'])),(13,11,5,3))
        self.assertEqual(len(report['cleanup']),4)
        self.assertTrue(all(type(code) is str and code.isascii() and len(code)<=128 for codes in policy.DIAGNOSTICS.values() for code in codes))

    def test_rectangular_envelope_covers_actual_projection(self):
        value=fixture.projection();bound=projection_envelope()
        self.assertEqual(set(value),set(bound))
        for key,item in value.items():
            if type(item) is int:self.assertLessEqual(len(str(item)),len(str(bound[key])))
            else:self.assertEqual(item,bound[key])

EXPECTED={'source_count': 25, 'projection_envelope': 1871, 'projection_cap': 2048, 'capture_skeleton': 953, 'capture_with_full_projection_cap': 2997, 'capture_cap': 12288, 'failure_capture': 118, 'report_without_capture': 19432, 'report_with_full_capture_cap_and_newline': 31717, 'report_cap': 32768, 'margin': 1051}
if __name__=='__main__':unittest.main()
