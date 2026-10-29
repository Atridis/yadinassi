"""Actual seed/injection/redump path; only external 1C boundaries are stubbed."""
import ast
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import unittest
from unittest import mock

import test_native_1c_db_oracle_stage as fixture
import inject_metadata as metadata
import catalog_reference_codec as policy
import catalog_reference_identity as measurement

ROOT = Path(__file__).resolve().parents[1]


class CodecSeedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        if os.name == 'nt':
            patch = mock.patch.object(metadata, 'Path', PurePosixPath)
            patch.start(); self.addCleanup(patch.stop)

    def backend(self, case):
        root = self.root / ('case-' + str(len(list(self.root.iterdir())))); root.mkdir()
        native = fixture.stage.Native(fixture.NONCE, fixture.provenance(),
                                      reference_case=case, reference_codec=True)
        native.root = root
        native.v1, native.v2 = root/'v1', root/'v2'
        # The production renderer's logical path, never opened by this stub.
        native.evidence = PurePosixPath('/tmp/onec-db-oracle/evidence')
        native.begin_stage('seed_v1')
        operations = []
        def launched(expected):
            self.assertEqual(native.seed_pending, expected)
            native.seed_launched = expected
            operations.append(expected)
        def create_db(name):
            launched('create')
            self.assertEqual(name, 'seed')
            result = root/'database'; result.mkdir()
            return result
        def batch(database, arguments, label, user):
            self.assertEqual(database, root/'database')
            if label == 'dump-empty':
                launched('dump_empty')
                self.assertEqual(arguments[::2], ['/DumpConfigToFiles','-Format'])
                target = Path(arguments[1]); target.mkdir()
                shutil.copyfile(ROOT/'tests/fixtures/native_bootstrap/Configuration.xml', target/'Configuration.xml')
                (target/'ConfigDumpInfo.xml').write_text('synthetic bookkeeping',encoding='utf-8')
            elif label == 'seed-import':
                launched('import')
                self.assertEqual(arguments, ['/LoadConfigFromFiles',str(native.v1)])
                self.assertTrue((native.v1/'CommonModules/NativeOracleServer/Ext/Module.bsl').is_file())
                self.assertTrue((native.v2/'CommonModules/NativeOracleServer/Ext/Module.bsl').is_file())
            elif label == 'seed-apply':
                launched('apply')
                self.assertEqual(arguments, ['/UpdateDBCfg'])
            elif label == 'redump':
                launched('redump')
                self.assertEqual(arguments[::2], ['/DumpConfigToFiles','-Format'])
                shutil.copytree(native.v1, Path(arguments[1]))
            else:
                self.fail('unexpected external command')
            native.counter += 1
        def enterprise(database, operation):
            launched('bootstrap')
            self.assertEqual(database, root/'database')
            self.assertEqual(operation, 'bootstrap')
        native.create_db, native.batch, native.enterprise = create_db, batch, enterprise
        return native, operations

    def test_real_seed_both_cases_hashes_module_and_builds_manifest(self):
        for case in policy.CASES:
            native, operations = self.backend(case)
            with mock.patch.object(policy, 'canonical_module_sha256',
                                   wraps=measurement.canonical_module_sha256) as canonical:
                database = native.seed()
            self.assertEqual(database, native.root/'database')
            self.assertEqual(operations,list(fixture.protocol.SEED_OPERATIONS))
            canonical.assert_called_once()
            raw = (native.v1/'CommonModules/NativeOracleServer/Ext/Module.bsl').read_bytes()
            self.assertEqual(canonical.call_args.args, (raw,))
            self.assertEqual(native.reference_module_sha256, policy.rendered_module_sha256(native.nonce,case))
            self.assertIsNotNone(native.identity_manifest)
            self.assertEqual(len(native.identity_manifest.catalogs),3)
            self.assertFalse(native.identity_baseline_verified)
            self.assertIsNone(native.seed_pending)
            self.assertIsNone(native.seed_launched)
            self.assertFalse(list(native.root.glob('redump-*')))

    def test_missing_alias_reproduces_failure_after_dump_before_import(self):
        native, operations = self.backend('distinct_a')
        with mock.patch.object(policy,'canonical_module_sha256',measurement.canonical_module_sha256):
            del policy.canonical_module_sha256
            with self.assertRaises(AttributeError):
                native.seed()
        self.assertEqual(operations,['create','dump_empty'])
        self.assertIsNone(native.reference_module_sha256)
        self.assertIsNone(native.identity_manifest)
        self.assertIsNone(native.seed_pending)
        self.assertIsNone(native.seed_launched)

    def test_every_runtime_record_policy_attribute_is_present(self):
        tree = ast.parse((ROOT/'scripts/native_1c_db_oracle/run.py').read_text(encoding='utf-8'))
        def record_policy(node):
            return (isinstance(node,ast.Attribute) and node.attr=='record_policy'
                    and isinstance(node.value,ast.Name) and node.value.id=='self')
        attributes = {'SCHEMA','build_identity_manifest'}  # redump conditional alias
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute) and record_policy(node.value):
                attributes.add(node.attr)
        for function in (n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))):
            aliases = {target.id for node in ast.walk(function) if isinstance(node,ast.Assign)
                       and record_policy(node.value) for target in node.targets if isinstance(target,ast.Name)}
            attributes.update(node.attr for node in ast.walk(function) if isinstance(node,ast.Attribute)
                              and isinstance(node.value,ast.Name) and node.value.id in aliases)
        self.assertIn('canonical_module_sha256',attributes)
        self.assertIn('verify_reference',attributes)
        self.assertIn('discard_capture',attributes)
        for name in sorted(attributes):
            with self.subTest(attribute=name):
                self.assertTrue(hasattr(policy,name),name)
        self.assertIs(policy.canonical_module_sha256,measurement.canonical_module_sha256)
