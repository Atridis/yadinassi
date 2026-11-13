import copy
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest
from scripts import native_1c_demo_designer as demo
from scripts import native_1c_demo_ci_policy as policy


class DemoDesignerTests(unittest.TestCase):
    def test_exact_plain_source(self):
        files = demo.source_files()
        self.assertEqual(len(files), 19)
        self.assertEqual(sum(name.endswith('.xml') for name in files), 15)
        self.assertEqual(sum(name.endswith('.bsl') for name in files), 4)
        self.assertEqual(len(demo.INPUTS), 22)
        self.assertNotIn('original.zip', '\n'.join(demo.INPUTS))
        self.assertNotIn('manifest.json', '\n'.join(demo.INPUTS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            demo.stage_inputs(demo.ROOT, root / 'stage')
            self.assertEqual(demo.source_files(root / 'stage'), files)
            original_root = root / 'stage' / demo.HISTORICAL_ROOT
            original_root.write_bytes(original_root.read_bytes() + b'\n')
            with self.assertRaises(demo.DemoError):
                demo.source_files(root / 'stage')
            original_root.unlink()
            with self.assertRaises(demo.DemoError):
                demo.source_files(root / 'stage')
        self.assertNotIn('validate_dump.py', '\n'.join(demo.INPUTS))

    def test_stage_fixed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'stage'
            hashes = demo.stage_inputs(demo.ROOT, root)
            self.assertEqual(hashes, demo.inventory(demo.ROOT))
            self.assertEqual(set(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()), set(demo.INPUTS))
            with self.assertRaises(demo.DemoError):
                demo.stage_inputs(demo.ROOT, root)

    def test_designer_only_order(self):
        commands = demo.operations(Path('/tmp/demo-designer'))
        self.assertEqual([x[0] for x in commands], ['create', 'load', 'check', 'update', 'redump'])
        self.assertEqual([x[1][1] for x in commands], ['CREATEINFOBASE'] + ['DESIGNER'] * 4)
        self.assertTrue(set(demo.CHECK_FLAGS) <= set(commands[2][1]))
        self.assertNotIn('ENTERPRISE', str(commands))

    def test_container_isolation(self):
        cmd = demo.container_command(PurePosixPath('/tmp/owned'), 'a' * 32)
        self.assertEqual(cmd[:2], ['docker', 'create'])
        for flag, expected in {'--network': 'none', '--user': '1000:1000', '--cap-drop': 'ALL',
                               '--security-opt': 'no-new-privileges:true', '--pull': 'never',
                               '--log-driver': 'none'}.items():
            self.assertEqual(cmd[cmd.index(flag) + 1], expected)
        self.assertIn('--read-only', cmd)
        self.assertIn(demo.IMAGE, cmd)
        self.assertEqual(cmd.count('--mount'), 1)
        self.assertTrue(cmd[cmd.index('--mount') + 1].endswith(',readonly'))

    def test_redump_unchanged(self):
        files = demo.source_files()
        self.assertEqual(set(demo.verify_redump(files, files)), set(files))

    def test_module_changed_refused(self):
        files = demo.source_files()
        actual = dict(files)
        name = next(n for n in files if n.endswith('.bsl'))
        actual[name] += b'\n// unexpected source\n'
        with self.assertRaises(demo.DemoError):
            demo.verify_redump(files, actual)

    def test_metadata_changed_refused(self):
        files = demo.source_files()
        actual = dict(files)
        actual['Configuration.xml'] = b'<replaced/>'
        with self.assertRaises(demo.DemoError):
            demo.verify_redump(files, actual)

    def test_extra_or_missing_files_refused(self):
        files = demo.source_files()
        for actual in ({**files, 'extra.bsl': b''}, {n: b for n, b in files.items() if n != 'Configuration.xml'}):
            with self.assertRaises(demo.DemoError):
                demo.verify_redump(files, actual)

    def test_only_transport_normalization(self):
        self.assertEqual(demo.xml_signature(b'<a>\n <b x="1"/>\n</a>'), demo.xml_signature(b'<a><b x="1" /></a>'))
        self.assertNotEqual(demo.xml_signature('<a>\u00a0<b/>\u00a0</a>'.encode()), demo.xml_signature(b'<a><b/></a>'))
        self.assertNotEqual(demo.xml_signature(b'<a> x </a>'), demo.xml_signature(b'<a>x</a>'))
        self.assertNotEqual(demo.xml_signature(b'<a xmlns:x="one">x:T</a>'),
                            demo.xml_signature(b'<a xmlns:x="two">x:T</a>'))
        for raw in (b'<!DOCTYPE a><a/>', '<!DOCTYPE a><a/>'.encode('utf-16'), b'<a><?unknown x?></a>'):
            with self.assertRaises(demo.DemoError):
                demo.xml_signature(raw)

    def test_dump_symlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'link').symlink_to(demo.ROOT / 'README.md')
            with self.assertRaises(demo.DemoError):
                demo.dump_files(root)

    def test_zero_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result'
            for raw in (b'0\n', '0'.encode('utf-16')):
                path.write_bytes(raw)
                demo.zero_result(path)
            for raw in (b'', b'1', b'error', b'0' * 129):
                path.write_bytes(raw)
                with self.assertRaises(demo.DemoError):
                    demo.zero_result(path)

    def test_report_strict(self):
        import native_1c_docker_lifecycle as lifecycle
        failure = demo.failure_report(lifecycle.LifecycleError('container_cleanup_unverified',
                                      cli_reap_verified=True, container_cleanup_verified=False))
        self.assertEqual(failure['failure'], 'container_cleanup_unverified')
        self.assertIs(failure['container_cleanup_verified'], False)
        self.assertIs(failure['docker_cli_reap_verified'], True)
        self.assertNotIn('secret', json.dumps(demo.failure_report(ValueError('secret'))))
        hashes = demo.inventory(demo.ROOT)
        report = dict(schema=demo.SCHEMA, nonce='a'*32, status='ok', phase='complete', failure='none',
                      input_sha256=hashes, mismatches={}, xml_diagnostics=dict(state='available', files=[]),
                      redump_sha256={n: demo.digest(b) for n, b in demo.source_files().items()})
        demo.validate_report(json.dumps(report).encode(), 'a'*32, hashes)
        for key, value in [('schema', 'native-demo-designer-v1'), ('archive_sha256', 'a'*64), ('nonce', 'b'*32), ('failure', 'native raw log'), ('redump_sha256', {}), ('input_sha256', {})]:
            bad = {**report, key: value}
            with self.assertRaises(demo.DemoError):
                demo.validate_report(json.dumps(bad).encode(), 'a'*32, hashes)
        with self.assertRaises(demo.DemoError):
            demo.validate_report(b'{"schema":1,"schema":2}', 'a'*32, hashes)

    def test_workflow_admission_literal(self):
        source = (demo.ROOT / 'scripts/native_1c_demo_ci_policy.py').read_text()
        workflow = (demo.ROOT / '.github/workflows/native-1c-demo-designer.yml').read_text()
        block = source[source.index('# BEGIN DEMO ADMISSION'):source.index('# END DEMO ADMISSION')+len('# END DEMO ADMISSION')]
        normalized = '\n'.join(line[10:] if line.startswith(' '*10) else line for line in workflow.splitlines())
        self.assertIn(block, normalized)
        self.assertNotIn('pull_request:', workflow)
        self.assertNotIn('write', workflow)
        self.assertIn('if: ${{ false }} # Retired: historical redump is offline-only.', workflow)

    def test_admission_owner_exact_sha(self):
        sha, ref = 'a'*40, 'refs/heads/demo-reviewed'
        user = dict(login='Atridis', id=30860798, type='User')
        event = dict(repository=dict(full_name='Atridis/yadinassi', id=359770628, fork=False, owner=user),
                     sender=user, ref=ref, inputs={'reviewed_sha': sha})
        context = dict(GITHUB_REPOSITORY='Atridis/yadinassi', GITHUB_REPOSITORY_ID='359770628',
                       GITHUB_REPOSITORY_OWNER='Atridis', GITHUB_REPOSITORY_OWNER_ID='30860798',
                       GITHUB_ACTOR='Atridis', GITHUB_ACTOR_ID='30860798', NATIVE_TRIGGERING_ACTOR='Atridis',
                       GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF_TYPE='branch',
                       GITHUB_BASE_REF='', GITHUB_HEAD_REF='', GITHUB_SHA=sha, GITHUB_REF=ref,
                       GITHUB_WORKFLOW_SHA=sha, GITHUB_WORKFLOW_REF='Atridis/yadinassi/.github/workflows/native-1c-demo-designer.yml@'+ref,
                       NATIVE_DISPATCH_INPUTS=json.dumps({'reviewed_sha': sha}))
        self.assertEqual(policy.admission(event, context), sha)
        for key in context:
            with self.subTest(key=key), self.assertRaises(ValueError):
                policy.admission(event, {**context, key: 'invalid'})
        for key, value in [('inputs', {'reviewed_sha': 'b'*40}), ('sender', {**user, 'id': 1}),
                           ('repository', {**event['repository'], 'fork': True}), ('ref', 'wrong')]:
            with self.assertRaises(ValueError):
                policy.admission({**event, key: value}, context)


if __name__ == '__main__':
    unittest.main()
