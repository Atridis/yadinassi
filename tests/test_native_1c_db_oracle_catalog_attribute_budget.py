"""Independent encoded majorants for fixed matrix; no cap changes/native claim."""
import copy
import unittest
import test_native_1c_db_oracle_catalog_attribute_binding as matrix
import test_native_1c_db_oracle_catalog_reference_budget as base
import protocol
import snapshots

policy = matrix.policy


def projected_envelope():
    value = base.projection_envelope()
    value.update(recipe_id=policy.RECIPE_ID, recipe_sha256=policy.RECIPE_SHA256,
                 catalog_name_count=3, catalog_name_validation='owned_declared_key_name_matched',
                 catalog_identity_validation='owned_uuid_fields_attributes_matched', attribute_count=2)
    return value


def envelope():
    capture = copy.deepcopy(matrix.fixture()['config_catalog_attribute_binding'])
    capture['reader'] = None
    capture['origin']['bytes'] = capture['postimage']['bytes'] = snapshots.MAX_FILE_BYTES
    report = base.report_envelope()
    del report['config_catalog_observation']
    report.update(schema=policy.SCHEMA, lane=policy.LANE, provenance=matrix.identity(),
                  config_catalog_attribute_binding=None)
    for field in ('reader_validation', 'observation_validation'):
        report[field] = max(('not_run', 'failed', 'discarded', policy.VERDICT), key=len)
    return {'sources': len(policy.CATALOG_SOURCE_FILES),
            'projection': len(protocol.encode(projected_envelope())),
            'capture': len(protocol.encode(capture)) - len(b'null') + policy.MAX_PROJECTION_BYTES,
            'report': len(protocol.encode(report)) - len(b'null') + policy.MAX_CAPTURE_BYTES + 1,
            'report_cap': protocol.MAX_REPORT_BYTES}


class AttributeBudgetTests(unittest.TestCase):
    def test_complete_envelopes_stay_inside_unchanged_caps(self):
        value = envelope()
        self.assertEqual((policy.MAX_PROJECTION_BYTES, policy.MAX_CAPTURE_BYTES,
                          protocol.MAX_REPORT_BYTES), (2048, 12288, 32768))
        self.assertLessEqual(value['projection'], policy.MAX_PROJECTION_BYTES)
        self.assertLessEqual(value['capture'], policy.MAX_CAPTURE_BYTES)
        self.assertLessEqual(value['report'], protocol.MAX_REPORT_BYTES)
        self.assertEqual(value, {'sources': 28, 'projection': 2033, 'capture': 3097,
                                 'report': 32094, 'report_cap': 32768})
        fixture = matrix.fixture()
        self.assertEqual(tuple(len(fixture[key]) for key in ('stages','snapshots','comparisons','cleanup')),
                         (13, 11, 5, 4))

    def test_majorants_cover_each_real_projection_field(self):
        actual, bound = matrix.projection(), projected_envelope()
        self.assertEqual(set(actual), set(bound))
        for field, value in actual.items():
            with self.subTest(field=field):
                self.assertLessEqual(len(protocol.encode(value)), len(protocol.encode(bound[field])))
        self.assertEqual(actual['catalog_name_count'], 3)
        self.assertEqual(actual['catalog_declared_count'], 3)

    def test_all_failure_captures_are_closed_and_bounded(self):
        for category, diagnostics in policy.DIAGNOSTICS.items():
            for code in diagnostics:
                value = {'schema': policy.CAPTURE_SCHEMA, 'status': 'failed', 'category': category, 'code': code}
                self.assertLessEqual(len(protocol.encode(value)), policy.MAX_CAPTURE_BYTES)
                self.assertNotIn('catalogs', value)


if __name__ == '__main__': unittest.main()
