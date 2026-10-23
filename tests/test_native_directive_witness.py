"""Source-bound scalar directive witness; synthetic checks are not native captures."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_native_client_probe import suite, full, ROOT, stage_fixture


def linux_fixture(path):
    raw = path.read_bytes()
    return raw.replace(b"\r\n", b"\n") if os.name == "nt" else raw


class NativeDirectiveWitnessTests(unittest.TestCase):
    def setUp(self):
        # Pure marker-schema fixtures do not exercise Linux descriptor security.
        # Match the existing Windows client marker fixture adapter; keep the
        # production reader and real POSIX security tests unchanged.
        if os.name == 'nt':
            reader = mock.patch.object(suite, 'secure_bytes',
                                       new=stage_fixture.portable_fixture_bytes)
            reader.start()
            self.addCleanup(reader.stop)

    def test_native_and_host_contracts_match_with_old_values_retained(self):
        self.assertEqual(suite.CLIENT_VALUES, full.CLIENT_VALUES)
        self.assertEqual(full.CLIENT_VALUES[:4], [42, "client-probe", 3, 6])
        self.assertEqual(len(full.CLIENT_VALUES), 15)
        self.assertEqual(len(set(value.split(":", 1)[0]
                                 for value in full.CLIENT_VALUES[4:])), 11)

    def test_positive_witness_uses_execution_context_not_platform_target_flags(self):
        for relative in (full.CLIENT_SOURCE,
                         'integrational_tests/directive_probes/client_server.bsl'):
            source = (ROOT / relative).read_text(encoding='utf-8-sig')
            self.assertIn('#Если НаСервере И Не НаКлиенте Тогда', source)
            self.assertIn('#If AtClient And Not AtServer Then', source)
            self.assertNotIn('#Если Сервер И Не Клиент Тогда', source)
            self.assertNotIn('#If Client And Not Server Then', source)
            self.assertNotIn('DirectiveClientProfile', source)
            self.assertNotIn('DirectiveServerProfile', source)

    @unittest.skipIf(os.name == "nt", "native host bounded subprocess is POSIX-only")
    def test_exact_restored_shared_module_computes_contract_in_real_interpreter(self):
        source = ROOT / full.CLIENT_SOURCE
        full.verify_client_interpreter(ROOT, source, full.digest(source.read_bytes()))

    @unittest.skipIf(os.name == "nt", "native host bounded subprocess is POSIX-only")
    def test_changed_shared_callee_is_rejected_by_real_interpreter_gate(self):
        source = full.client_interpreter_source((ROOT / full.CLIENT_SOURCE).read_bytes())
        changed = source.replace(b"Return A + B;", b"Return A + B + 1;")
        self.assertNotEqual(source, changed)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "probe.bsl"
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
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        source = Path(temporary.name).resolve() / "probe.bsl"
        source.write_bytes(linux_fixture(ROOT / full.CLIENT_SOURCE))
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
            path = Path(temporary).resolve() / "completed.json"
            for index in range(4, len(suite.CLIENT_VALUES)):
                values = list(suite.CLIENT_VALUES)
                values[index] = values[index].split(":", 1)[0] + ": wrong"
                path.write_text(json.dumps(dict(schema=1, nonce="a" * 32,
                    phase="completed", witness="client", values=values)), encoding="utf-8")
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
            path = Path(temporary).resolve() / "completed.json"
            for changed in (True, 42.0, "42"):
                values = list(suite.CLIENT_VALUES)
                values[0] = changed
                path.write_text(json.dumps(dict(schema=1, nonce="a" * 32,
                    phase="completed", witness="client", values=values)), encoding="utf-8")
                with self.subTest(changed=changed), self.assertRaises(suite.FullError):
                    suite.client_marker(path, "a" * 32, "completed")


class NativeDirectiveDiagnosticTests(unittest.TestCase):
    def setUp(self):
        # Pure marker-schema fixtures do not exercise Linux descriptor security.
        # Match the existing Windows client marker fixture adapter; keep the
        # production reader and real POSIX security tests unchanged.
        if os.name == 'nt':
            reader = mock.patch.object(suite, 'secure_bytes',
                                       new=stage_fixture.portable_fixture_bytes)
            reader.start()
            self.addCleanup(reader.stop)

    def diagnose(self, values, phase='completed', **changes):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / 'marker.json'
            marker = dict(schema=1, nonce='a' * 32, phase=phase, witness='client', values=values)
            marker.update(changes)
            path.write_bytes(json.dumps(marker).encode("utf-8"))
            result = suite.client_marker_diagnostics(path, 'a' * 32)
            full.validate_marker_diagnostics(result)
            return result

    def test_missing_malformed_nonce_and_error_phase(self):
        for change in ({'nonce': 'b' * 32}, {'schema': True}, {'phase': 'unknown'},
                       {'witness': 'server'}, {'extra': 'PRIVATE'}, {'values': None}):
            values = change.pop('values', [])
            self.assertEqual(self.diagnose(values, **change)['phase'], 'invalid')
        self.assertEqual(self.diagnose([], phase='error'),
                         dict(phase='error', kind='none', ordinal=-1, error_stage=0))
        self.assertEqual(self.diagnose(['PRIVATE'], phase='error')['phase'], 'invalid')

    def test_first_mismatch_count_type_value_never_exports_payload(self):
        for index in range(15):
            for replacement, kind in [(None, 'type'), ('PRIVATE', 'value' if index >= 4 or index == 1 else 'type')]:
                values = list(suite.CLIENT_VALUES)
                values[index] = replacement
                result = self.diagnose(values)
                self.assertEqual(result, dict(phase='completed', kind=kind, ordinal=index, error_stage=0))
                self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(self.diagnose(suite.CLIENT_VALUES[:7])['ordinal'], 7)
        self.assertEqual(self.diagnose(suite.CLIENT_VALUES + [0])['ordinal'], 15)

    def test_fixed_bsl_error_stage_is_bounded_and_not_success(self):
        for stage in range(1, 12):
            values = suite.CLIENT_VALUES[:4] + ['directive.runtime-error', stage]
            self.assertEqual(self.diagnose(values), dict(phase='completed', kind='runtime_error',
                                                       ordinal=stage + 3, error_stage=stage))
        for stage in (True, 0, 12, 'PRIVATE'):
            self.assertNotEqual(self.diagnose(suite.CLIENT_VALUES[:4] +
                ['directive.runtime-error', stage])['kind'], 'runtime_error')

    def test_real_interpreter_records_literal_stage_without_native_error_text(self):
        from yadinassi import Interpreter
        source = full.client_interpreter_source(linux_fixture(ROOT / full.CLIENT_SOURCE)).decode('utf-8-sig')
        source = source.replace('Return A + B;', 'Raise "PRIVATE_ERROR";')
        vm = Interpreter()
        vm.execute(source)
        values = list(vm.execute('ВычислитьПробу()'))
        self.assertEqual(values[4:], ['directive.runtime-error', 1])
        self.assertNotIn('PRIVATE_ERROR', str(values))

    def test_host_rejects_unknown_unbounded_and_inconsistent_metadata(self):
        good = dict(phase='completed', kind='runtime_error', ordinal=4, error_stage=1)
        for changes in ({'phase': 'PRIVATE'}, {'kind': 'PRIVATE'}, {'ordinal': 16},
                        {'ordinal': True}, {'error_stage': 12}, {'error_stage': True},
                        {'extra': 'PRIVATE'}, {'ordinal': 5}, {'phase': 'error'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                full.validate_marker_diagnostics({**good, **changes})

    def test_original_acceptance_rejects_diagnostic_sentinel(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / 'marker.json'
            path.write_text(json.dumps(dict(schema=1, nonce='a' * 32,
                phase='completed', witness='client', values=suite.CLIENT_VALUES[:4] +
                ['directive.runtime-error', 1])))
            with self.assertRaises(suite.FullError):
                suite.client_marker(path, 'a' * 32, 'completed')

    def test_host_accepts_only_failed_invalid_result_diagnostic_records(self):
        record = suite.empty_client_report()
        record.update(status='failed', failure_kind='invalid_result',
                      marker_diagnostics=dict(phase='completed', kind='value', ordinal=4, error_stage=0))
        full.validate_client_probe(record, 'a' * 64, 'b' * 64)
        for change in ({'status': 'ok'}, {'witness_verified': True}, {'failure_kind': 'timeout'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                full.validate_client_probe({**record, **change}, 'a' * 64, 'b' * 64)
