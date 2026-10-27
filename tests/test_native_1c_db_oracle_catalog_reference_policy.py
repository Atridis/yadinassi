"""Closed local prototype policy. No runner/native authorization implied."""
import copy
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import config_catalog_observation as policy
import inputs
import protocol
import test_native_1c_db_oracle_config_root_projection_policy as previous
from test_native_1c_db_oracle_catalog_reference_reader import successful_source,A,GUID
NONCE=previous.NONCE

def identity():
    result=previous.identity();result['actual_version']=protocol.VERSION;result['sources']={path:'c'*64 for path in policy.CATALOG_SOURCE_FILES};return result

def projection():
    source=successful_source();return policy.read_projection(source.read_at,source.size,limits=policy.reader.CatalogLimits())

def fixture():
    report,_=previous.fixture()
    del report['config_root_reference_projection']
    report.update(schema=policy.SCHEMA,lane=policy.LANE,provenance=identity(),config_catalog_observation=None)
    report['reader_validation']=report['observation_validation']=policy.VERDICT
    evidence=previous.evidence();evidence['reader']=projection()
    report['config_catalog_observation']=policy.bind_capture(evidence,report)
    return report

class CatalogReferencePolicyTests(unittest.TestCase):
    def test_closed_report_and_exact_owned_positive(self):
        report=fixture();policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity())
        report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
        policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity(),final=True)
        self.assertEqual(report['native_compatibility'],'not_claimed')
        self.assertNotIn(A,repr(report));self.assertNotIn(GUID,repr(report))

    def test_closed_fields_exact_types_and_no_semantic_promotions(self):
        value=projection()
        for key,item in value.items():
            missing=dict(value);missing.pop(key)
            with self.assertRaises(policy.OracleError):policy.validate_projection(missing)
            if type(item) is int:
                mutated=dict(value);mutated[key]=True
                with self.assertRaises(policy.OracleError):policy.validate_projection(mutated)
        for key,item in (('extra',1),('root_identity','accepted'),('catalog_validation','catalog_objects_validated'),
            ('catalog_declared_count',0),('catalog_positive_count',2),('catalog_collection_count',65)):
            mutated=dict(value);mutated[key]=item
            with self.assertRaises(policy.OracleError):policy.validate_projection(mutated)

    def test_inventory_binds_parser_and_old_modes_unchanged(self):
        self.assertEqual(len(policy.CATALOG_SOURCE_FILES),25)
        self.assertIn('yadinassi/storage/config_catalog_references.py',policy.CATALOG_SOURCE_FILES)
        self.assertNotIn(policy.MODULE_SOURCE,inputs.CONFIG_ROOT_REFERENCE_PROJECTION_SOURCE_FILES)
        self.assertNotIn('yadinassi/storage/config_catalog_references.py',inputs.CONFIG_ROOT_REFERENCE_PROJECTION_SOURCE_FILES)
        report=fixture()
        for mutate in ('missing','extra','changed'):
            candidate=copy.deepcopy(report);sources=candidate['provenance']['sources']
            if mutate=='missing':sources.pop('yadinassi/storage/config_catalog_references.py')
            elif mutate=='extra':sources['foreign.py']='f'*64
            else:sources['yadinassi/storage/config_catalog_references.py']='f'*64
            with self.assertRaises(policy.OracleError):policy.validate_report(protocol.encode(candidate),nonce=NONCE,provenance=identity())

    def test_new_inventory_is_explicitly_registered_only(self):
        self.assertEqual(inputs.inventory(config_catalog_observation=True),policy.CATALOG_SOURCE_FILES)
        self.assertNotIn(policy.MODULE_SOURCE,inputs.CONFIG_ROOT_REFERENCE_PROJECTION_SOURCE_FILES)

if __name__=='__main__':unittest.main()
