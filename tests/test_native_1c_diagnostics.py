"""Offline, synthetic diagnostic regressions; no native execution or log export."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_native_1c_stage2 import Stage2Harness
from test_native_1c_smoke import bootstrap_report, smoke

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / 'scripts/native_1c_bootstrap'
spec = importlib.util.spec_from_file_location('diagnostics_tests', HELPERS / 'diagnostics.py')
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)
RUN = '0123456789abcdef0123456789abcdef'
MANIFEST = {'run_id': RUN, 'user': 'NativeSmoke'}
ERROR = '{МодульСеанса(74, 13)}: Поле объекта не обнаружено (ЗащитаОтОпасныхДействий)'


def error_marker(hook='session', **overrides):
    value = {'protocol': 'native-bootstrap-v1', 'run_id': RUN, 'stage': 'bootstrap',
             'hook': hook, 'user': 'NativeSmoke', 'status': 'error', 'error': ERROR}
    value.update(overrides)
    return value


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def marker(self, value, hook='session'):
        path = self.root / ('bootstrap-' + hook + '.json')
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return path

    def test_source_limits_equal_unchanged_bsl_sources(self):
        for name, limit in diag.SOURCE_LINE_LIMITS.items():
            self.assertEqual(len((HELPERS / 'modules' / (name + '.bsl')).read_text(encoding='utf-8-sig').splitlines()), limit)

    def test_utf16_utf8_and_cp1251_known_error_classification(self):
        for data in (ERROR.encode('utf-16'), b'\xfe\xff' + ERROR.encode('utf-16-be'),
                     ERROR.encode('utf-8-sig'), ERROR.encode('utf-8'), ERROR.encode('cp1251')):
            with self.subTest(data=data[:12]):
                (self.root / 'bootstrap.log').write_bytes(data)
                result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
                self.assertEqual(result['category'], 'unsupported_api')
                self.assertEqual((result['module'], result['line']), ('SessionModule', 74))
                self.assertEqual(result['identifier'], 'ЗащитаОтОпасныхДействий')
                self.assertEqual(result['native_exit_code'], 1)
                self.assertNotIn(ERROR, json.dumps(result, ensure_ascii=False))

    def test_bad_bom_and_undefined_cp1251_byte_are_not_lossily_decoded(self):
        for data in (b'\xff\xfe\x00', b'\xfe\xff\x00', b'\xef\xbb\xbf\xff', b'\x98'):
            with self.subTest(data=data):
                with self.assertRaises(UnicodeError): diag.native_text(data)
                (self.root / 'bootstrap.log').write_bytes(data)
                self.assertEqual(diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST)['category'], 'unknown')

    def test_exact_russian_and_english_locations(self):
        for source, canonical in diag.MODULE_ALIASES.items():
            for suffix in ('(7)', '(7,12)', '(7, 12)'):
                result = diag.summarize_text('Ошибка выполнения: {' + source + suffix + '}')
                self.assertEqual((result['module'], result['line']), (canonical, 7))

    def test_unknown_partial_out_of_bounds_locations_are_not_exported(self):
        values = ['{/private/SessionModule(12)}', '{SecretModule(12)}', 'SessionModule(12)',
                  '{PrefixSessionModule(12)}', '{SessionModule(0)}', '{SessionModule(145)}',
                  '{ManagedApplicationModule(84)}', '{SessionModule(999999999999)}',
                  '{SessionModule(True)}', '{SessionModule(12.2)}']
        for text in values:
            with self.subTest(text=text):
                value = diag.summarize_text(text)
                self.assertIsNone(value['module'])
                self.assertIsNone(value['line'])

    def test_multiple_source_locations_do_not_select_arbitrary_line(self):
        value = diag.summarize_text('Ошибка выполнения {SessionModule(7)} {ManagedApplicationModule(8)}')
        self.assertIsNone(value['line'])
        self.assertIsNone(value['module'])

    def test_identifier_requires_exact_known_native_syntax_and_allowlist(self):
        for text in ('Secret ЗащитаОтОпасныхДействий', 'Поле объекта не обнаружено (Secret)',
                     'Поле объекта не обнаружено (ЗащитаОтОпасныхДействий/private)',
                     'Поле объекта не обнаружено (ЗащитаОтОпасныхДействийSuffix)'):
            self.assertIsNone(diag.summarize_text(text)['identifier'])
        self.assertEqual(diag.summarize_text('Переменная не определена (ТипЗнч)')['identifier'], 'ТипЗнч')
        self.assertIsNone(diag.summarize_text('<?>ПараметрЗапуска')['identifier'])
        self.assertEqual(diag.summarize_text('Переменная не определена: <?>ПараметрЗапуска')['identifier'], 'ПараметрЗапуска')

    def test_unrelated_known_frame_cannot_claim_unknown_module_error(self):
        text = '{МодульСеанса(67)}: Старт\n{CommonModule.OtherModule(10)}: Поле объекта не обнаружено (Роли)'
        result = diag.summarize_text(text)
        self.assertEqual(result['category'], 'unsupported_api')
        self.assertIsNone(result['module'])
        self.assertIsNone(result['line'])
        self.assertEqual(result['identifier'], 'Роли')

    def test_remote_source_pointer_cannot_supply_identifier_to_another_error(self):
        result = diag.summarize_text('Ошибка выполнения {МодульСеанса(67)}\n<?>ПараметрЗапуска')
        self.assertEqual(result['line'], 67)
        self.assertIsNone(result['identifier'])

    def test_same_category_conflicting_locations_never_pick_first(self):
        self.marker(error_marker())
        (self.root / 'bootstrap.log').write_text(ERROR.replace('(74, 13)', '(75, 13)'), encoding='utf-8')
        result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(result['category'], 'unsupported_api')
        self.assertIsNone(result['module'])
        self.assertIsNone(result['line'])
        self.assertIsNone(result['identifier'])

    def test_finite_license_authentication_training_and_startup_categories(self):
        samples = {'license_unavailable': 'Не обнаружен ключ защиты: PRIVATE',
                   'authentication_failed': 'Ошибка аутентификации: PRIVATE',
                   'training_restriction': 'Ограничение учебной версии: PRIVATE',
                   'startup_failed': 'Application startup failed: PRIVATE',
                   'runtime_error': 'Ошибка при вызове метода контекста: PRIVATE',
                   'compile_error': 'Variable is not defined: PRIVATE'}
        for expected, text in samples.items():
            result = diag.summarize_text(text)
            self.assertEqual(result['category'], expected)
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_generic_runtime_wrapper_does_not_hide_specific_api_failure(self):
        self.assertEqual(diag.summarize_text('Ошибка при вызове метода контекста. ' + ERROR)['category'], 'unsupported_api')

    def test_conflicting_categories_are_not_guessed(self):
        self.marker(error_marker())
        (self.root / 'bootstrap.log').write_text('Не найдена лицензия', encoding='utf-8')
        result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST)
        self.assertEqual(result['category'], 'conflicting_evidence')
        self.assertEqual(result['origin'], 'none')
        self.assertIsNone(result['line'])
        self.assertIsNone(result['identifier'])

    def test_unknown_category_conflicting_locations_are_not_selected(self):
        (self.root / 'bootstrap.log').write_text('{SessionModule(7)}: unknown', encoding='utf-8')
        (self.root / 'bootstrap-console.log').write_text('{SessionModule(8)}: unknown', encoding='utf-8')
        result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(result['category'], 'unknown')
        self.assertIsNone(result['module'])
        self.assertIsNone(result['line'])

    def test_matching_error_marker_is_read_even_with_nonzero_exit(self):
        self.marker(error_marker())
        result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, -11)
        self.assertEqual(result['category'], 'unsupported_api')
        self.assertEqual(result['origin'], 'session_marker')
        self.assertEqual(result['session_marker'], 'error')
        self.assertEqual(result['managed_marker'], 'absent')
        self.assertEqual(result['native_exit_code'], -11)

    def test_managed_error_marker_is_independently_usable(self):
        self.marker(error_marker('managed', error='{ManagedApplicationModule(19)}: Ошибка выполнения'), 'managed')
        result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual((result['origin'], result['module'], result['line']), ('managed_marker', 'ManagedApplicationModule', 19))
        self.assertEqual(result['session_marker'], 'absent')

    def test_success_markers_cannot_provide_private_error_diagnostics(self):
        self.marker(error_marker(status='ok', error=''))
        result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST)
        self.assertEqual(result['session_marker'], 'ok')
        self.assertEqual(result['category'], 'unknown')
        self.assertIsNone(result['line'])
        self.marker(error_marker(status='ok'))
        self.assertEqual(diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST)['session_marker'], 'invalid')

    def test_foreign_marker_identity_never_provides_details(self):
        for changes in ({'run_id': 'wrong'}, {'user': 'Other'}, {'stage': 'verify'},
                        {'hook': 'managed'}, {'protocol': 'other'}, {'status': []}, {'error': []}):
            with self.subTest(changes=changes):
                self.marker(error_marker(**changes))
                result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
                self.assertEqual(result['session_marker'], 'invalid')
                self.assertEqual(result['category'], 'evidence_invalid')
                self.assertIsNone(result['line'])
                self.assertIsNone(result['identifier'])

    def test_malformed_duplicate_nonfinite_deep_or_oversize_markers_are_bounded(self):
        path = self.root / 'bootstrap-session.json'
        for raw in (b'{"error":"SECRET","error":"second"}', b'[]', b'{"error":NaN}',
                    b'[' * 1500, b'x' * 65537, b'\xff', b''):
            with self.subTest(raw=raw[:25]):
                path.write_bytes(raw)
                result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 7)
                self.assertEqual(result['category'], 'evidence_invalid')
                self.assertEqual(result['native_exit_code'], 7)
                self.assertNotIn('SECRET', json.dumps(result))

    def test_earlier_stage_logs_and_markers_are_not_read(self):
        (self.root / 'load.log').write_text('Ошибка компиляции: SECRET', encoding='utf-8')
        self.marker(error_marker(stage='verify'))
        result = diag.collect_diagnostics(self.root, 'verify', MANIFEST)
        self.assertEqual(result['category'], 'unknown')
        self.assertEqual(result['session_marker'], 'absent')

    def test_simple_enterprise_failure_ignores_previous_build_logs(self):
        case = self.root / 'simple-case'
        case.mkdir()
        (case / 'TestModule.designer.log').write_text('Ошибка компиляции: old', encoding='utf-8')
        (case / 'enterprise-console.log').write_text('ordinary', encoding='utf-8')
        result = diag.collect_diagnostics(self.root, 'simple_epf', MANIFEST)
        self.assertEqual(result['category'], 'unknown')

    def test_oversize_empty_and_mocked_symlink_logs_are_ignored(self):
        path = self.root / 'bootstrap.log'
        for raw in (b'', b'x' * 1_048_577):
            path.write_bytes(raw)
            self.assertEqual(diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST)['category'], 'unknown')
        (self.root / 'load.log').write_text(ERROR, encoding='utf-8')
        with mock.patch.object(Path, 'is_symlink', return_value=True):
            result = diag.collect_diagnostics(self.root, 'load', MANIFEST)
        self.assertEqual(result['category'], 'unknown')

    def test_unexpected_diagnostic_parser_error_is_conservative(self):
        with mock.patch.object(diag, 'stage_logs', side_effect=OSError('PRIVATE')):
            value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['category'], 'evidence_invalid')
        self.assertEqual(value['native_exit_code'], 1)
        self.assertNotIn('PRIVATE', json.dumps(value))

    def test_exit_code_is_not_coerced_and_is_bounded(self):
        for code in (-64, -11, 1, 255): self.assertEqual(diag.bounded_exit_code(code), code)
        for code in (True, False, '1', 1.0, -65, 256, 0, None): self.assertIsNone(diag.bounded_exit_code(code))

    def test_host_rejects_nonfinite_and_untrusted_diagnostic_fields(self):
        edits = [lambda d: d.update(extra='PRIVATE'), lambda d: d.update(category='PRIVATE'),
                 lambda d: d.update(origin=[]), lambda d: d.update(native_exit_code=True),
                 lambda d: d.update(native_exit_code=1.0), lambda d: d.update(native_exit_code=256),
                 lambda d: d.update(native_exit_code=0), lambda d: d.update(category='compile_error'),
                 lambda d: d.update(line=1), lambda d: d.update(module='SessionModule', line=True),
                 lambda d: d.update(module='SessionModule', line=145),
                 lambda d: d.update(module='PRIVATE', line=1),
                 lambda d: d.update(identifier='PRIVATE'),
                 lambda d: d.update(origin='session_marker', category='unknown')]
        for edit in edits:
            data = bootstrap_report()
            data.update(status='stage2_failed', runtime_version=None, runtime_version_source='not_measured', security_settings_changed=None)
            data['stage2'].update(status='failed', failed_stage='bootstrap', failure_kind='process_failed',
                                  actual_version=None, version_source='not_measured', simple_output_sha256=None,
                                  security_settings_state='unverified',
                                  **{key: key == 'modules_reimported' for key in smoke.STAGE_FLAGS})
            data['stage2']['diagnostics'].update(category='unknown', native_exit_code=1,
                                                   session_marker='absent', managed_marker='absent')
            smoke.validate_report(json.dumps(data).encode(), bootstrap=True)
            edit(data['stage2']['diagnostics'])
            with self.subTest(diagnostic=data['stage2']['diagnostics']), self.assertRaises(smoke.SmokeError):
                smoke.validate_report(json.dumps(data).encode(), bootstrap=True)

    def test_observed_exit_requires_primary_process_failure_not_timeout(self):
        value = diag.empty_diagnostics()
        value.update(category='unknown', native_exit_code=1)
        diag.validate_diagnostics(value, primary_kind='process_failed')
        for kind in ('timeout', 'stale_evidence', 'marker_invalid', None):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                diag.validate_diagnostics(value, primary_kind=kind)

    def test_host_rejects_diagnostic_claim_from_stale_failed_report(self):
        data = bootstrap_report()['stage2']
        data.update(status='failed', failed_stage='bootstrap', failure_kind='stale_evidence',
                    actual_version=None, version_source='not_measured', simple_output_sha256=None,
                    security_settings_state='unverified',
                    **{key: key == 'modules_reimported' for key in smoke.STAGE_FLAGS})
        smoke.validate_stage2(data)
        data['diagnostics'].update(category='compile_error', origin='native_log',
                                   module='SessionModule', line=7)
        with self.assertRaises(ValueError): smoke.validate_stage2(data)

    def test_success_diagnostics_must_be_empty(self):
        value = diag.empty_diagnostics()
        diag.validate_diagnostics(value, success=True)
        value['native_exit_code'] = 1
        with self.assertRaises(ValueError): diag.validate_diagnostics(value, success=True)


class DiagnosticFlowTests(Stage2Harness):
    def test_nonzero_bootstrap_reports_error_marker_without_changing_security_or_version_gates(self):
        def fail(stage, _command, _directory):
            if stage == 'bootstrap':
                value = self.marker('bootstrap', 'session')
                value.update(status='error', error=ERROR + '\nPRIVATE SECRET')
                (self.evidence / 'bootstrap-session.json').write_text(json.dumps(value), encoding='utf-8')
                raise self.module.StageError('process_failed', exit_code=1)
        self.native_hook = fail
        report = self.module.run()
        self.assert_failed(report, 'bootstrap', 'process_failed')
        self.assertIsNone(report['actual_version'])
        self.assertEqual(report['security_settings_state'], 'unverified')
        self.assertFalse(report['bootstrap_verified'])
        self.assertEqual(report['diagnostics']['native_exit_code'], 1)
        self.assertEqual(report['diagnostics']['origin'], 'session_marker')
        self.assertEqual(report['diagnostics']['category'], 'unsupported_api')
        self.assertNotIn('PRIVATE', json.dumps(report))
        smoke.validate_stage2(report)

    def test_timeout_is_primary_even_if_log_contains_a_compile_phrase(self):
        self.failures['bootstrap'] = 'timeout'
        self.logs['bootstrap'] = 'Ошибка компиляции: PRIVATE'
        report = self.module.run()
        self.assert_failed(report, 'bootstrap', 'timeout')
        self.assertEqual(report['diagnostics']['category'], 'compile_error')
        self.assertIsNone(report['diagnostics']['native_exit_code'])
        smoke.validate_stage2(report)

    def test_malformed_marker_does_not_reset_primary_failure_or_verified_modules(self):
        def fail(stage, _command, _directory):
            if stage == 'bootstrap':
                (self.evidence / 'bootstrap-session.json').write_bytes(b'[' * 1500)
                raise self.module.StageError('process_failed', exit_code=2)
        self.native_hook = fail
        report = self.module.run()
        self.assert_failed(report, 'bootstrap', 'process_failed')
        self.assertTrue(report['modules_reimported'])
        self.assertEqual(report['diagnostics']['category'], 'evidence_invalid')
        self.assertEqual(report['diagnostics']['native_exit_code'], 2)
        smoke.validate_stage2(report)

    def test_stale_evidence_does_not_read_logs_or_error_markers(self):
        self.failures['bootstrap'] = 'stale_evidence'
        with mock.patch.object(self.module, 'collect_diagnostics', side_effect=AssertionError('must not read rejected evidence')):
            report = self.module.run()
        self.assert_failed(report, 'bootstrap', 'stale_evidence')
        self.assertEqual(report['diagnostics'], self.module.empty_diagnostics())

    def test_direct_process_failure_retains_observed_exit_not_timeout_kill(self):
        child = mock.MagicMock()
        child.__enter__.return_value = child
        child.wait.return_value = 23
        # Bypass the harness mock only for the unbound original function.
        real_module = importlib.util.module_from_spec(importlib.util.spec_from_file_location('stage_original', HELPERS / 'run_stage.py'))
        real_module.__spec__.loader.exec_module(real_module)
        with mock.patch.object(real_module.subprocess, 'Popen', return_value=child), self.assertRaises(real_module.StageError) as raised:
            real_module.process(['never executed'], self.directory, self.directory / 'exit.log')
        self.assertEqual(raised.exception.exit_code, 23)


if __name__ == '__main__':
    unittest.main()
