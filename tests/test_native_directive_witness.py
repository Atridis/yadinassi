"""Source-bound scalar directive witness; synthetic checks are not native captures."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_native_client_probe import suite, full, ROOT


def linux_fixture(path):
    raw = path.read_bytes()
    return raw.replace(b"\r\n", b"\n") if os.name == "nt" else raw


class NativeDirectiveWitnessTests(unittest.TestCase):
    def test_native_and_host_contracts_match_with_old_values_retained(self):
        self.assertEqual(suite.CLIENT_VALUES, full.CLIENT_VALUES)
        self.assertEqual(full.CLIENT_VALUES[:4], [42, "client-probe", 3, 6])
        self.assertEqual(len(full.CLIENT_VALUES), 15)
        self.assertEqual(len(set(value.split(":", 1)[0]
                                 for value in full.CLIENT_VALUES[4:])), 11)

    @unittest.skipIf(os.name == "nt", "native host bounded subprocess is POSIX-only")
    def test_exact_native_module_computes_contract_in_real_interpreter(self):
        source = ROOT / full.CLIENT_SOURCE
        full.verify_client_interpreter(ROOT, source, full.digest(source.read_bytes()))

    @unittest.skipIf(os.name == "nt", "native host bounded subprocess is POSIX-only")
    def test_changed_callee_is_rejected_by_real_interpreter_gate(self):
        source = (ROOT / full.CLIENT_SOURCE).read_bytes()
        changed = source.replace(b"Return A + B;", b"Return A + B + 1;")
        self.assertNotEqual(source, changed)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "probe.bsl"
            path.write_bytes(changed)
            with self.assertRaisesRegex(full.FullError, "^interpreter_failed$"):
                full.verify_client_interpreter(ROOT, path, full.digest(changed))

    def test_hash_mismatch_never_executes(self):
        source = ROOT / full.CLIENT_SOURCE
        runner = mock.Mock()
        with self.assertRaisesRegex(full.FullError, "^source_changed$"):
            full.verify_client_interpreter(ROOT, source, "0" * 64, runner=runner)
        runner.assert_not_called()

    def test_child_failure_stderr_and_wrong_typed_result_fail_closed(self):
        source = ROOT / full.CLIENT_SOURCE
        good = json.dumps(full.CLIENT_VALUES, ensure_ascii=False,
                          separators=(",", ":")).encode()
        for result in [(1, good, b""), (0, good, b"error"),
                       (0, b"[]", b""), (0, good.replace(b"42,", b"42.0,", 1), b"")]:
            with self.subTest(result=result), self.assertRaisesRegex(
                    full.FullError, "^interpreter_failed$"):
                full.verify_client_interpreter(ROOT, source, full.digest(source.read_bytes()),
                                               runner=lambda *args: result)

    def test_each_directive_label_is_required_by_native_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "completed.json"
            for index in range(4, len(suite.CLIENT_VALUES)):
                values = list(suite.CLIENT_VALUES)
                values[index] = values[index].split(":", 1)[0] + ": wrong"
                path.write_text(json.dumps(dict(schema=1, nonce="a" * 32,
                    phase="completed", witness="client", values=values)))
                with self.subTest(index=index), self.assertRaises(suite.FullError):
                    suite.client_marker(path, "a" * 32, "completed")

    def test_inverse_preserves_all_four_existing_parity_modules(self):
        template = linux_fixture(ROOT / full.CLIENT_SOURCE)
        restored = suite.client_parity_template(template)
        self.assertEqual(suite.digest(restored),
                         '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328')
        for case in ('dates', 'values', 'collections', 'numbers'):
            source = linux_fixture(ROOT / f'integrational_tests/tests/{case}.bsl')
            adapter = getattr(suite, f'client_{case}_module')
            with self.subTest(case=case):
                self.assertEqual(adapter(source, template), adapter(source, restored))
                self.assertNotIn(b'&AtServer', adapter(source, template))
                self.assertNotIn('НаСервере'.encode(), adapter(source, template))

    def test_inverse_rejects_modified_old_or_partial_template(self):
        template = linux_fixture(ROOT / full.CLIENT_SOURCE)
        restored = suite.client_parity_template(template)
        for changed in (template + b' ', template[:-1], restored,
                        template.replace(b'Return A + B;', b'Return A - B;'),
                        template.replace(b'// BEGIN', b'// CHANGED')):
            with self.subTest(size=len(changed)), self.assertRaises(suite.FullError):
                suite.client_parity_template(changed)

    def test_native_keeps_exact_types_for_legacy_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "completed.json"
            for changed in (True, 42.0, "42"):
                values = list(suite.CLIENT_VALUES)
                values[0] = changed
                path.write_text(json.dumps(dict(schema=1, nonce="a" * 32,
                    phase="completed", witness="client", values=values)))
                with self.subTest(changed=changed), self.assertRaises(suite.FullError):
                    suite.client_marker(path, "a" * 32, "completed")
