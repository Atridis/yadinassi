"""Public-runtime report identities must not use Python numeric aliases."""
import unittest

import test_metadata_catalog_runtime_integration as fixture
import metadata_catalog_runtime_report as policy
from snapshots import OracleError


class RuntimePostimageTypeTests(unittest.TestCase):
    def test_equal_float_byte_count_rejected_in_full_report(self):
        value = fixture.report()
        actual = value['runtime_readbacks'][0]['postimage']
        original = actual['bytes']
        actual['bytes'] = float(original)
        self.assertEqual(actual, value['states'][0]['postimage'])
        with self.assertRaises(OracleError):
            policy.validate_report(policy.encode_report(value), nonce=fixture.NONCE,
                                   provenance=fixture.identity())

    def test_summary_rejects_boolean_float_and_other_noninteger_aliases(self):
        for count in (True, False, 1.0, '1', None, 0, -1, 67108865):
            with self.subTest(count=count), self.assertRaises(OracleError):
                policy._validate_postimage({'bytes': count, 'sha256': 'a' * 64})
        for count in (1, 12288, 67108864):
            policy._validate_postimage({'bytes': count, 'sha256': 'a' * 64})

    def test_reordered_valid_summary_still_accepted(self):
        value = fixture.report()
        previous = value['runtime_readbacks'][0]['postimage']
        value['runtime_readbacks'][0]['postimage'] = {
            'sha256': previous['sha256'], 'bytes': previous['bytes']}
        result = policy.validate_report(policy.encode_report(value), nonce=fixture.NONCE,
                                        provenance=fixture.identity())
        self.assertTrue(result['runtime_readbacks'][0]['comparison']['supported_match'])

if __name__ == '__main__': unittest.main()
