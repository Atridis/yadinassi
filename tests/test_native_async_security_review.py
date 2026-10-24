"""Independent offline review: private Async evidence and stage boundaries.

All native invocations are fake. Passing does not establish native behavior.
"""
import json
from pathlib import Path
import re
import time
import unittest
from unittest import mock

import test_native_async_execution as execution

suite = execution.suite
NONCE = execution.NONCE


class AsyncSecurityReviewTests(unittest.TestCase):
    argument = staticmethod(execution.AsyncExecutionTests.argument)
    setUp = execution.AsyncExecutionTests.setUp
    reset = execution.AsyncExecutionTests.reset
    fake_native = execution.AsyncExecutionTests.fake_native
    fake_async = execution.AsyncExecutionTests.fake_async
    run_async = execution.AsyncExecutionTests.run_async

    def test_replaced_evidence_and_rewritten_manifest_cannot_rebase_continuity(self):
        result = self.run_async()
        self.assertEqual(result['status'], 'ok', result)
        target = self.work / 'case-0/completed.json'
        replacement = target.with_suffix('.replacement')
        replacement.write_bytes(target.read_bytes())
        replacement.replace(target)
        manifest = self.work / 'continuity.json'
        data = json.loads(manifest.read_bytes())
        identity, raw = suite.async_file_snapshot(target, suite.ASYNC_MAX_MARKER)
        data['files'][str(target)] = [list(map(str, identity)), suite.digest(raw)]
        manifest.write_text(json.dumps(data, sort_keys=True, separators=(',', ':')))
        # The completed stage result, not this mutable manifest, must anchor the
        # final emitter check. Same-content inode substitution is still stale.
        with self.assertRaises(suite.FullError):
            suite.final_async_evidence_check(self.work, self.inputs, NONCE, result['continuity_sha256'])

    def test_snapshot_replacement_at_each_retained_case_boundary_is_rejected(self):
        targets = ('src/Launcher.xml', 'src/' + suite.CLIENT_MODULE,
                   'roundtrip/Launcher.xml', 'roundtrip/' + suite.CLIENT_MODULE,
                   'AsyncClientProbe.epf', 'build.result', 'dump.result',
                   'request.json', 'entered.json', 'completed.json')
        for relative in targets:
            with self.subTest(relative=relative):
                result = self.run_async()
                self.assertEqual(result['status'], 'ok', result)
                path = self.work / 'case-0' / relative
                replacement = path.with_suffix('.replacement')
                replacement.write_bytes(path.read_bytes())
                replacement.replace(path)
                with self.assertRaises(suite.FullError):
                    suite.final_async_evidence_check(self.work, self.inputs, NONCE, result['continuity_sha256'])
                self.reset()

    def test_changed_session_bus_cannot_accept_terminal_markers(self):
        with mock.patch.object(suite, 'require_session_bus', side_effect=suite.FullError('process_failed')):
            result = self.run_async()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['cases'][0][4:], [0, [], [], []])
        self.assertFalse((self.work / 'continuity.json').exists())

    def test_shell_deadline_writer_is_accepted_by_private_deadline_reader(self):
        script = (execution.probe.ROOT / 'scripts/native_1c_smoke_probe.sh').read_text()
        source = re.search(r"<<'PYASYNCDEADLINE'\n(.*?)\nPYASYNCDEADLINE", script, re.S).group(1)
        deadline_file = self.root / 'async-deadline.json'
        source = source.replace("Path('/tmp/onec-smoke/async-deadline.json')", 'Path(' + repr(str(deadline_file)) + ')')
        with mock.patch('sys.argv', ['-', '0', NONCE]):
            exec(compile(source, '<offline-shell-deadline-writer>', 'exec'), {})
        original = suite.secure_bytes
        with mock.patch.object(suite, 'secure_bytes', side_effect=lambda path, limit: original(deadline_file, limit)):
            deadline = suite.read_async_deadline(NONCE)
        self.assertGreater(deadline, time.monotonic())
        self.assertLessEqual(deadline, time.monotonic() + 2340)
