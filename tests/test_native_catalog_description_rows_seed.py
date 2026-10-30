"""Actual seed/injection/redump; native executable boundaries are mocked."""
import unittest
from unittest import mock
import test_native_catalog_codec_seed as old
import catalog_description_rows as policy
import inject_metadata as metadata

class DescriptionRowsSeedTests(unittest.TestCase):
    def setUp(self):old.CodecSeedTests.setUp(self)
    @unittest.skipUnless(old.REAL_SEED_SUPPORTED,'seed source reader needs O_NOFOLLOW')
    def test_seed_cases_exact_render_and_redump_without_extra_catalogs(self):
        for case in ('description8','description17'):
            native,operations=old.CodecSeedTests.backend(self,'distinct_a')
            native.reference_case=None;native.reference_codec=False;native.catalog_binding=False
            native.catalog_field_matrix=False;native.record_policy=None
            native.description_rows=True;native.description_case=case;native.description_policy=policy;native.description_witness=None
            native.seed()
            self.assertEqual(operations,list(old.fixture.protocol.SEED_OPERATIONS))
            raw=(native.v1/'CommonModules/NativeOracleServer/Ext/Module.bsl').read_bytes()
            self.assertEqual(raw,metadata._module('NativeOracleServer.bsl',native.nonce,str(native.evidence),description_case=case,description_rows=True))
            self.assertEqual(len(list((native.v1/'Catalogs').glob('*.xml'))),1)
            self.assertEqual(metadata.inspect(native.v2,2,description_case=case)['payload_length'],64)
            self.assertFalse(list(native.root.glob('redump-*')))
            self.assertIsNone(native.identity_manifest)

if __name__=='__main__':unittest.main()
