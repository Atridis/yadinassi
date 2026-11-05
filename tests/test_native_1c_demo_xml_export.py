"""Offline export security: synthetic native bytes, no Docker or 1C execution."""
import base64
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import native_1c_demo_designer as demo
import native_1c_docker_lifecycle as lifecycle
import native_1c_smoke as smoke


class XmlExportTests(unittest.TestCase):
    def fixture(self, changed=True):
        expected = demo.source_files()
        actual = dict(expected)
        if changed:
            actual['Configuration.xml'] = b'<changed />'
        mismatches = demo.redump_mismatches(expected, actual)
        report = dict(schema=demo.SCHEMA, nonce='a'*32, status='failed' if changed else 'ok',
                      phase='witness' if changed else 'complete', failure='witness_mismatch' if changed else 'none',
                      input_sha256=demo.inventory(demo.ROOT),
                      redump_sha256={} if changed else {name: demo.digest(raw) for name, raw in actual.items()},
                      mismatches=mismatches, xml_diagnostics=demo.xml_diagnostics(expected, actual, mismatches))
        wire = dict(schema=demo.WIRE_SCHEMA, report=report, export=demo.xml_export(actual))
        return expected, actual, wire

    def validate(self, wire, expected):
        return demo.validate_wire(demo.json_bytes(wire), 'a'*32, demo.inventory(demo.ROOT), expected)

    def summary(self, report):
        return dict(schema=demo.SCHEMA+'-host', source_sha='b'*40, native=report,
                    container_cleanup_verified=True, docker_cli_reap_verified=True,
                    enterprise_executed=False, security_settings_changed=False)

    def test_failed_witness_exports_exact_fifteen_without_success(self):
        expected, actual, wire = self.fixture()
        report, export, result = self.validate(wire, expected)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['failure'], 'witness_mismatch')
        self.assertEqual(set(result), set(demo.XML_FILES))
        self.assertEqual(export['state'], 'available')
        self.assertLessEqual(len(demo.json_bytes(report)), 16384)
        self.assertLessEqual(len(demo.json_bytes(wire)), demo.WIRE_MAX_BYTES)
        self.assertNotIn('base64', json.dumps(self.summary(report)))

    def test_success_binding_and_preserved_bsl_mismatch(self):
        expected, actual, wire = self.fixture(False)
        report, _, result = self.validate(wire, expected)
        self.assertEqual(report['status'], 'ok')
        self.assertEqual(result['Configuration.xml'], actual['Configuration.xml'])
        wire['report']['redump_sha256']['Configuration.xml'] = 'a'*64
        with self.assertRaises(demo.DemoError):
            self.validate(wire, expected)
        expected, actual, wire = self.fixture()
        name = next(name for name in demo.SOURCE_FILES if name.endswith('.bsl'))
        wire['report']['mismatches'][name] = 'module_changed'
        report, _, result = self.validate(wire, expected)
        self.assertEqual(report['mismatches'][name], 'module_changed')
        self.assertNotIn(name, result)

    def test_forbidden_inventory_and_missing_entries_withheld(self):
        _, actual, _ = self.fixture()
        for extra in ('private.log', 'db/1Cv8.1CD', 'extra.xml', '../Configuration.xml'):
            result = demo.xml_export({**actual, extra: b'SECRET'})
            self.assertEqual(result, dict(state='unavailable', reason='invalid_inventory', files=[]))
        for name in demo.SOURCE_FILES:
            result = demo.xml_export({key: raw for key, raw in actual.items() if key != name})
            self.assertEqual(result['reason'], 'invalid_inventory')
            self.assertEqual(result['files'], [])
        result = demo.xml_export({**actual, 'ConfigDumpInfo.xml': b'PRIVATE'})
        self.assertEqual(len(result['files']), 15)
        self.assertNotIn(base64.b64encode(b'PRIVATE').decode(), json.dumps(result))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'dump'
            root.mkdir()
            outside = Path(directory)/'private.xml'
            outside.write_bytes(b'<private/>')
            (root/'known.xml').symlink_to(outside)
            with self.assertRaises(demo.DemoError): demo.dump_files(root)
            (root/'known.xml').unlink()
            os.link(outside, root/'known.xml')
            with self.assertRaises(demo.DemoError): demo.dump_files(root)

    def test_hostile_xml_withheld_and_host_rejected(self):
        expected, actual, wire = self.fixture()
        for raw in (b'<!DOCTYPE a [<!ENTITY x "private">]><a>&x;</a>', b'<a><?secret value?></a>',
                    b'<a>', b'\xff', '<a/>'.encode('utf-16'), b'<a>'*97+b'</a>'*97):
            altered = dict(actual, **{'Configuration.xml': raw})
            self.assertEqual(demo.xml_export(altered)['reason'], 'invalid_xml')
            bad = copy.deepcopy(wire)
            item = bad['export']['files'][demo.XML_FILES.index('Configuration.xml')]
            item.update(size=len(raw), sha256=demo.digest(raw), base64=base64.b64encode(raw).decode())
            with self.subTest(raw=raw[:20]), self.assertRaises(demo.DemoError):
                self.validate(bad, expected)

    def test_canonical_base64_sizes_hashes_and_types(self):
        expected, _, wire = self.fixture()
        original = wire['export']['files'][0]
        for key, value in (('file', True), ('file', 99), ('size', True), ('size', 0), ('size', demo.EXPORT_MAX_FILE+1),
                           ('size', original['size']+1), ('sha256', 'a'*64), ('sha256', 'secret'),
                           ('base64', original['base64']+'\n'), ('base64', '!'), ('base64', 'é'),
                           ('base64', 'A'*(4*((demo.EXPORT_MAX_FILE+2)//3)+1))):
            bad = copy.deepcopy(wire)
            bad['export']['files'][0][key] = value
            with self.subTest(key=key), self.assertRaises(demo.DemoError):
                self.validate(bad, expected)
        # Same decoded one-byte value, but nonzero padding bits are noncanonical.
        bad = copy.deepcopy(wire)
        bad['export']['files'][0].update(size=1, sha256=demo.digest(b'a'), base64='YR==')
        with self.assertRaises(demo.DemoError):
            self.validate(bad, expected)

    def test_all_export_and_wire_limits(self):
        expected, actual, wire = self.fixture()
        too_large = b'<r>'+b'x'*demo.EXPORT_MAX_FILE+b'</r>'
        self.assertEqual(demo.xml_export(dict(actual, **{'Configuration.xml': too_large}))['reason'], 'export_limit')
        large = b'<r><a>'+b'x'*40000+b'</a><b>'+b'y'*40000+b'</b></r>'
        oversized = {name: large if name.endswith('.xml') else raw for name, raw in actual.items()}
        self.assertEqual(demo.xml_export(oversized), dict(state='unavailable', reason='export_limit', files=[]))
        with patch.object(demo, 'EXPORT_MAX_TOTAL', 1), self.assertRaises(demo.DemoError):
            self.validate(wire, expected)
        with self.assertRaises(demo.DemoError):
            demo.validate_wire(b' '*(demo.WIRE_MAX_BYTES+1), 'a'*32, {}, expected)
        bad = copy.deepcopy(wire)
        bad['report']['extra'] = 'x'*16385
        with self.assertRaises(demo.DemoError):
            self.validate(bad, expected)

    def test_duplicate_json_keys_indexes_and_arbitrary_fields(self):
        expected, _, wire = self.fixture()
        raw = demo.json_bytes(wire).replace(b'"file":0', b'"file":0,"file":0', 1)
        with self.assertRaises(demo.DemoError):
            demo.validate_wire(raw, 'a'*32, demo.inventory(demo.ROOT), expected)
        for mutate in (lambda x: x.update(secret='raw'),
                       lambda x: x['export'].update(path='../secret'),
                       lambda x: x['export']['files'][0].update(path='secret.log'),
                       lambda x: x['export']['files'].pop(),
                       lambda x: x['export']['files'].append(x['export']['files'][0]),
                       lambda x: x['export']['files'].__setitem__(1, x['export']['files'][0])):
            bad = copy.deepcopy(wire)
            mutate(bad)
            with self.assertRaises(demo.DemoError):
                self.validate(bad, expected)

    def test_nonce_source_and_recomputed_diagnostics_binding(self):
        expected, _, wire = self.fixture()
        for mutate in (lambda x: x['report'].update(nonce='b'*32),
                       lambda x: x['report'].update(input_sha256={}),
                       lambda x: x['report']['xml_diagnostics']['files'][0].update(after_sha256='a'*64),
                       lambda x: x['report'].update(mismatches={}, xml_diagnostics={'state':'available','files':[]})):
            bad = copy.deepcopy(wire)
            mutate(bad)
            with self.assertRaises(demo.DemoError):
                self.validate(bad, expected)
        bad = copy.deepcopy(wire)
        item = bad['export']['files'][0]
        raw = b'<attacker />'
        item.update(size=len(raw), sha256=demo.digest(raw), base64=base64.b64encode(raw).decode())
        with self.assertRaises(demo.DemoError):
            self.validate(bad, expected)

    def test_unavailable_export_explicit_and_consistent(self):
        expected, _, wire = self.fixture()
        wire['export'] = dict(state='unavailable', reason='invalid_xml', files=[])
        report, export, result = self.validate(wire, expected)
        self.assertEqual(report['failure'], 'witness_mismatch')
        self.assertEqual(result, {})
        for fields in ({'state':'available'}, {'reason':'none'}, {'reason':'raw private error'},
                       {'reason':'not_reached'}, {'files':[{}]}):
            bad = copy.deepcopy(wire)
            bad['export'].update(fields)
            with self.assertRaises(demo.DemoError):
                self.validate(bad, expected)
        wire['report'].update(phase='load', failure='process_failed', mismatches={},
                              xml_diagnostics=dict(state='not_reached', files=[]))
        wire['export']['reason'] = 'not_reached'
        self.assertEqual(self.validate(wire, expected)[2], {})

    def test_atomic_publication_manifest_and_fixed_paths(self):
        expected, _, wire = self.fixture()
        report, _, result = self.validate(wire, expected)
        summary = self.summary(report)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'export'
            demo.publish_xml_evidence(target, summary, result)
            payload = target/'payload'
            self.assertEqual(sorted(p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()),
                             sorted(['report.json','manifest.json']+[f'xml/{i:02d}.xml' for i in range(15)]))
            manifest = json.loads((payload/'manifest.json').read_bytes())
            self.assertEqual(manifest['source_sha'], 'b'*40)
            self.assertEqual(manifest['nonce'], 'a'*32)
            self.assertEqual(manifest['input_sha256'], report['input_sha256'])
            self.assertEqual(manifest['report_sha256'], demo.digest((payload/'report.json').read_bytes()))
            for row in manifest['files']:
                self.assertEqual(demo.digest((payload/row['path']).read_bytes()), row['sha256'])
            self.assertFalse((target/'.staging').exists())

    def test_preexisting_and_symlink_destinations_preserved(self):
        expected, _, wire = self.fixture()
        report, _, result = self.validate(wire, expected)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, kind in (('file','file'),('dir','dir'),('link','link')):
                target = root/name
                if kind == 'file': target.write_text('do not modify')
                elif kind == 'dir': target.mkdir()
                else: target.symlink_to(root/'file')
                with self.assertRaises((FileExistsError, demo.DemoError)):
                    demo.publish_xml_evidence(target, self.summary(report), result)
                self.assertTrue(target.exists())
            self.assertEqual((root/'file').read_text(), 'do not modify')
            parent = root/'parent-link'
            parent.symlink_to(root/'dir', target_is_directory=True)
            with self.assertRaises(demo.DemoError):
                demo.publish_xml_evidence(parent/'export', self.summary(report), result)

    def test_partial_write_or_rename_failure_never_publishes(self):
        expected, _, wire = self.fixture()
        report, _, result = self.validate(wire, expected)
        original_open = Path.open
        def fail_xml(path, *args, **kwargs):
            if path.name == '03.xml': raise OSError('PRIVATE error')
            return original_open(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'export'
            with patch.object(Path, 'open', fail_xml), self.assertRaises(OSError):
                demo.publish_xml_evidence(target, self.summary(report), result)
            self.assertFalse(target.exists())
            with patch.object(Path, 'rename', side_effect=OSError('PRIVATE error')), self.assertRaises(OSError):
                demo.publish_xml_evidence(target, self.summary(report), result)
            self.assertFalse(target.exists())
        self.assertNotIn('PRIVATE', json.dumps(demo.failure_report(OSError('PRIVATE error'))))

    def host_context(self, root, wire, runner):
        # Patches cover every external action: no native commands can execute.
        import contextlib
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(demo, 'ROOT', root))
        stack.enter_context(patch.object(demo.subprocess, 'check_output', return_value=b'b'*40))
        stack.enter_context(patch.object(demo.subprocess, 'run', return_value=SimpleNamespace(returncode=0)))
        stack.enter_context(patch.object(demo.uuid, 'uuid4', return_value=SimpleNamespace(hex='a'*32)))
        stack.enter_context(patch.dict(os.environ, GITHUB_SHA='b'*40, GHCR_TOKEN='FAKE_TEST_TOKEN', GHCR_USER='Atridis'))
        stack.enter_context(patch.object(smoke, 'run_silent'))
        stack.enter_context(patch.object(lifecycle, 'run_owned', side_effect=runner))
        return stack

    def checkout(self, parent):
        root = Path(parent)/'checkout'
        demo.stage_inputs(demo.ROOT, root)
        return root

    def test_host_publishes_only_after_cleanup_and_no_credentials(self):
        _, _, wire = self.fixture()
        seen = []
        def runner(command, env, **kwargs):
            self.assertEqual(kwargs['output_limit'], demo.WIRE_MAX_BYTES)
            self.assertNotIn('FAKE_TEST_TOKEN', str(command)+str(env))
            work = Path(env['DOCKER_CONFIG']).parent
            self.assertFalse((work/'auth').exists())
            seen.append(work)
            return 1, demo.json_bytes(wire)
        with tempfile.TemporaryDirectory() as directory:
            root = self.checkout(directory)
            original_publish = demo.publish_xml_evidence
            def publish(*args):
                self.assertTrue(seen and all(not path.exists() for path in seen))
                return original_publish(*args)
            with self.host_context(root, wire, runner), patch.object(demo, 'publish_xml_evidence', side_effect=publish):
                summary = demo.run_host()
            self.assertEqual(summary['native']['status'], 'failed')
            self.assertTrue((root/'demo-native-evidence/payload/manifest.json').is_file())

    def test_host_cleanup_uncertainty_and_source_mutation_do_not_publish(self):
        _, _, wire = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = self.checkout(directory)
            for runner in (lambda *a, **k: (_ for _ in ()).throw(lifecycle.LifecycleError(
                    'container_cleanup_unverified', cli_reap_verified=True, container_cleanup_verified=False)),
                    lambda *a, **k: (1, b'{invalid}')):
                with self.host_context(root, wire, runner), patch.object(demo, 'publish_xml_evidence') as publish:
                    with self.assertRaises((demo.DemoError,lifecycle.LifecycleError)):
                        demo.run_host()
                    publish.assert_not_called()
            def mutate(*args, **kwargs):
                (root/demo.INPUTS[0]).write_text('source changed')
                return 1, demo.json_bytes(wire)
            with self.host_context(root, wire, mutate), patch.object(demo, 'publish_xml_evidence') as publish:
                with self.assertRaises(demo.DemoError): demo.run_host()
                publish.assert_not_called()

    def test_tempdir_cleanup_failure_and_unverified_publication_blocked(self):
        expected, _, wire = self.fixture()
        report, _, result = self.validate(wire, expected)
        with tempfile.TemporaryDirectory() as directory:
            root = self.checkout(directory)
            original_temp = tempfile.TemporaryDirectory
            class BrokenCleanup:
                def __init__(self, *args, **kwargs): self.inner=original_temp(*args, **kwargs)
                def __enter__(self): return self.inner.__enter__()
                def __exit__(self, *args):
                    self.inner.__exit__(*args)
                    raise OSError('cleanup failed')
            with self.host_context(root, wire, lambda *a, **k:(1,demo.json_bytes(wire))), \
                    patch.object(demo.tempfile,'TemporaryDirectory',BrokenCleanup), \
                    patch.object(demo,'publish_xml_evidence') as publish:
                with self.assertRaises(OSError): demo.run_host()
                publish.assert_not_called()
            for field in ('container_cleanup_verified','docker_cli_reap_verified'):
                summary=self.summary(report);summary[field]=False
                with self.assertRaises(demo.DemoError):
                    demo.publish_xml_evidence(root/'unverified',summary,result)
                self.assertFalse((root/'unverified').exists())

    def test_workflow_upload_gate_and_exact_seventeen_paths(self):
        workflow=(demo.ROOT/'.github/workflows/native-1c-demo-designer.yml').read_text()
        block=workflow[workflow.index('      - name: Upload validated public-demo XML only'):]
        self.assertIn("if: always() && steps.designer.outputs.xml_export == 'available'",block)
        paths=[line.strip() for line in block.splitlines() if line.strip().startswith('demo-native-evidence/')]
        self.assertEqual(paths,['demo-native-evidence/payload/report.json','demo-native-evidence/payload/manifest.json']+
                         [f'demo-native-evidence/payload/xml/{i:02d}.xml' for i in range(15)])
        self.assertNotIn('*','\n'.join(paths))
        self.assertIn('status=$?',workflow)
        self.assertIn('exit "$status"',workflow)
        self.assertNotIn('hashFiles(',block)


if __name__ == '__main__':
    unittest.main()
