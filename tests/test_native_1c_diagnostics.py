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

    def test_rendered_projection_full_limit_inputs_finish_within_bounded_timeout(self):
        source = """
import importlib.util
spec = importlib.util.spec_from_file_location('diagnostics_bounded', __import__('sys').argv[1])
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)
for text in ('x' * 65536, 'x-' * 32768, 'x.' * 32768, '!' * 65536,
             'x' * 65000 + '@password', 'x' * 65000 + '/password', '"' + 'x' * 65000):
    value = diag.rendered_context(text, 'session_marker')
    assert len(value['head']) + len(value['tail']) <= 64
    assert 'password' not in value['head'] + value['tail']
"""
        result = subprocess.run([sys.executable, '-c', source, str(HELPERS / 'diagnostics.py')],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_rendered_projection_preserves_bilingual_requirement_and_negation(self):
        samples = {
            'Первый пользователь должен иметь права администрирования. Нельзя записать без роли.':
                ['first', 'user', 'must', 'unknown', 'rights', 'administration', 'sentence_end', 'cannot', 'write', 'without', 'role', 'sentence_end'],
            'At least one user must have administrative rights; no roles.':
                ['at_least', 'one', 'user', 'must', 'has', 'administrative', 'rights', 'clause_break', 'no', 'role', 'sentence_end'],
            'Последнего пользователя с административными правами нельзя удалить.':
                ['last', 'user', 'unknown', 'administrative', 'rights', 'cannot', 'delete', 'sentence_end'],
            'May can может': ['unknown'],
            'ни одного пользователя': ['none', 'user'],
            'ни роли': ['not', 'role'],
        }
        for text, expected in samples.items():
            with self.subTest(text=text):
                value = diag.rendered_context(text, 'session_marker')
                self.assertEqual(value['head'], expected)
                self.assertFalse(value['omitted_middle'])
                self.assertEqual(value['tail'], [])

    def test_rendered_projection_preserves_contractions_not_quotes(self):
        for token in ("isn't", "aren't", "wasn't", "weren't", "don't", "doesn't", "didn't",
                      "hasn't", "haven't", "hadn't", "won't", "wouldn't", "shouldn't", "mustn't", "needn't"):
            for text in (token, token.replace("'", '’')):
                self.assertEqual(diag.rendered_context(text, 'session_marker')['head'], ['not'])
        for text in ("can't", "couldn't", 'can’t', 'couldn’t'):
            self.assertEqual(diag.rendered_context(text, 'session_marker')['head'], ['cannot'])

    def test_rendered_projection_masks_opaque_values_before_vocabulary(self):
        samples = ['"Administrator password"', "'license password'", '«first user»',
                   '“first user”', '‘first user’', '’first user’', '`first user`',
                   '"first user', '/license/password', 'C:\\license\\password',
                   '\\\\license\\password', '../license/password', 'license/password',
                   'https://license.invalid/password', 'password@license.invalid',
                   'user=Administrator', 'username: Administrator', 'Пользователь: Администратор',
                   'User.Password', '{SessionModule(80)}', '"license\\"password"']
        for text in samples:
            with self.subTest(text=text):
                self.assertEqual(diag.rendered_context(text, 'session_marker')['head'], ['redacted'])

    def test_rendered_projection_masks_sensitive_labeled_and_authorization_values(self):
        labels = ('password', 'passwd', 'pwd', 'passphrase', 'token', 'access_token',
                  'refresh-token', 'secret', 'client_secret', 'credential', 'credentials',
                  'api_key', 'api-key', 'api key', 'authorization', 'cookie', 'пароль',
                  'токен', 'секрет', 'учетные данные', 'учётные данные', 'ключ API')
        for label in labels:
            for separator in (':', '='):
                text = label + separator + ' administrative,password;license first user'
                with self.subTest(text=text):
                    self.assertEqual(diag.rendered_context(text, 'session_marker')['head'], ['redacted'])
        for text in ('Bearer administrative,password;license', 'Basic password license'):
            self.assertEqual(diag.rendered_context(text, 'session_marker')['head'], ['redacted'])
        self.assertEqual(diag.rendered_context('Password: secret\nnot administrator', 'session_marker')['head'],
                         ['redacted', 'line_break', 'not', 'administrator'])

    def test_rendered_projection_rejects_substrings_mixed_scripts_and_unknown_text(self):
        for text in ('adminSecret', 'administratorSecret', 'licenseSecret', 'password_SECRET',
                     'license-secret', 'pаssword', 'адministrative', 'SECRET42', '123456789'):
            with self.subTest(text=text):
                self.assertEqual(diag.rendered_context(text, 'session_marker')['head'], ['unknown'])
        self.assertEqual(diag.rendered_context('not PRIVATE PASSWORD_SECRET password', 'session_marker')['head'],
                         ['not', 'unknown', 'password'])

    def test_rendered_projection_boundaries_and_tail_cover_full_bounded_text(self):
        value = diag.rendered_context('user\nnot; role.\npassword', 'session_marker')
        self.assertEqual(value['head'], ['user', 'line_break', 'not', 'clause_break', 'role',
                                         'sentence_end', 'line_break', 'password'])
        for size in (32, 64, 65, 1000):
            tokens = ['user'] * size + ['not', 'administrator']
            value = diag.rendered_context(' '.join(tokens), 'session_marker')
            self.assertLessEqual(len(value['head']) + len(value['tail']), 64)
            if len(tokens) <= 64:
                self.assertEqual(value['head'], tokens)
                self.assertFalse(value['omitted_middle'])
            else:
                self.assertEqual(value['head'], tokens[:32])
                self.assertEqual(value['tail'], tokens[-32:])
                self.assertTrue(value['omitted_middle'])

    def test_rendered_projection_keeps_final_private_cause_at_near_marker_limit(self):
        self.marker(error_marker(error='user ' * 12000 + '\nnot administrative rights'))
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        context = value['rendered_context']
        self.assertEqual(context['origin'], 'session_marker')
        self.assertTrue(context['omitted_middle'])
        self.assertEqual(context['tail'][-4:], ['line_break', 'not', 'administrative', 'rights'])
        self.assertLess(len(json.dumps(value).encode()), 8192)

    def test_rendered_projection_has_independent_matching_marker_origin(self):
        self.marker(error_marker(error='Error calling context method (Write)\nFirst user must have administrative rights.'))
        (self.root / 'bootstrap.log').write_text('No license found', encoding='utf-8')
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual((value['category'], value['origin']), ('license_unavailable', 'native_log'))
        self.assertEqual(value['rendered_context']['origin'], 'session_marker')
        self.assertIn('first', value['rendered_context']['head'])
        self.assertNotIn('license', value['rendered_context']['head'])
        self.marker(error_marker(error='Object field not found (Роли)\nFirst user must have administrative rights.'))
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual((value['category'], value['origin']), ('conflicting_evidence', 'none'))
        self.assertEqual(value['rendered_context']['origin'], 'session_marker')
        diag.validate_diagnostics(value, primary_kind='process_failed')

    def test_rendered_projection_prefers_session_then_managed_never_invalid_markers(self):
        self.marker(error_marker(hook='managed', error='password required'), hook='managed')
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['rendered_context']['origin'], 'managed_marker')
        self.marker(error_marker(error='not role'))
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['rendered_context']['head'], ['not', 'role'])
        self.marker(error_marker(run_id='FOREIGN', error='first user'))
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['rendered_context']['origin'], 'managed_marker')
        self.marker(error_marker(hook='managed', error='first user', status='ok'), hook='managed')
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['rendered_context'], diag.empty_rendered_context())

    def test_rendered_projection_empty_and_log_only_do_not_claim_marker(self):
        for text in ('', ' \r\n\t'):
            self.assertEqual(diag.rendered_context(text, 'session_marker'), diag.empty_rendered_context())
            self.marker(error_marker(error=text))
            (self.root / 'bootstrap.log').write_text('First user must have administrator rights', encoding='utf-8')
            self.assertEqual(diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)['rendered_context'],
                             diag.empty_rendered_context())

    def test_host_rejects_rendered_context_after_positive_failed_report(self):
        self.marker(error_marker(error='First user must have administrative rights.'))
        valid = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        edits = [lambda c: c.update(extra='PRIVATE'), lambda c: c.update(origin='native_log'),
                 lambda c: c.update(origin='none'), lambda c: c.update(origin='managed_marker'),
                 lambda c: c.update(representation='Cause'), lambda c: c.update(representation=[]),
                 lambda c: c.update(head=['PRIVATE']), lambda c: c.update(head=[True]),
                 lambda c: c.update(head=[{}]), lambda c: c.update(head=['user'] * 65),
                 lambda c: c.update(head='user'), lambda c: c.update(head=[]),
                 lambda c: c.update(tail=['user']), lambda c: c.update(tail=None),
                 lambda c: c.update(omitted_middle=0), lambda c: c.update(omitted_middle=True)]
        for edit in edits:
            data = bootstrap_report()
            data.update(status='stage2_failed', runtime_version=None, runtime_version_source='not_measured', security_settings_changed=None)
            data['stage2'].update(status='failed', failed_stage='bootstrap', failure_kind='process_failed',
                actual_version=None, version_source='not_measured', simple_output_sha256=None,
                security_settings_state='unverified', protection_observation=diag.empty_protection_observation(),
                diagnostics=copy.deepcopy(valid), **{key: key == 'modules_reimported' for key in smoke.STAGE_FLAGS})
            smoke.validate_report(json.dumps(data).encode(), bootstrap=True)
            edit(data['stage2']['diagnostics']['rendered_context'])
            with self.subTest(context=data['stage2']['diagnostics']['rendered_context']), self.assertRaises(smoke.SmokeError):
                smoke.validate_report(json.dumps(data).encode(), bootstrap=True)
        value = diag.empty_diagnostics()
        value['rendered_context']['omitted_middle'] = 0
        with self.assertRaises(ValueError): diag.validate_diagnostics(value)

    def test_rendered_context_cannot_appear_on_success_or_stale_failure(self):
        self.marker(error_marker(error='First user must have administrative rights'))
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        value['native_exit_code'] = None
        with self.assertRaises(ValueError): diag.validate_diagnostics(value, success=True)
        with self.assertRaises(ValueError): diag.validate_diagnostics(value, primary_kind='stale_evidence')

    def test_serialized_worst_case_projection_fits_unchanged_stage_and_host_caps(self):
        # Conservative field-by-field upper bound; combinations need not be a
        # reachable success/failure state. ASCII JSON matches both actual writers.
        longest = lambda values: max(values, key=lambda value: len(json.dumps(value)))
        context = {'origin': 'managed_marker', 'representation': 'detailed_error_text',
                   'head': [longest(diag.CONTEXT_TOKENS)] * 64, 'tail': [], 'omitted_middle': False}
        value = diag.empty_diagnostics()
        value.update(category=longest(diag.CATEGORIES), origin='managed_marker',
                     module='ManagedApplicationModule', line=9999,
                     identifier=longest(diag.IDENTIFIERS), native_exit_code=-64,
                     source_frames=[{'module': 'ManagedApplicationModule', 'line': 9999}] * 4,
                     source_frames_truncated=False, rendered_context=context,
                     session_marker=longest(diag.MARKER_STATES), managed_marker=longest(diag.MARKER_STATES))
        data = bootstrap_report()
        data['stage2'].update(status='failed', failed_stage=longest(smoke.STAGES),
                             failure_kind=longest(smoke.FAILURE_KINDS), actual_version='9999.9999.9999.9999',
                             security_settings_state='not_attempted', security_change_attempted=False, diagnostics=value,
                             **{key: False for key in smoke.STAGE_FLAGS})
        data['stage2']['protection_observation']['stage'] = 'bootstrap'
        stage_size = len(json.dumps(data['stage2'], sort_keys=True).encode())
        self.assertLess(stage_size, 8192)
        # Explicit upper bound for every remaining bounded outer field. Known
        # elements may repeat under the existing schema, so use the longest.
        data.update(status=longest(smoke.STATUS), python_version='99.99.999',
                    runtime_version='9999.9999.9999.9999', runtime_version_source='SystemInfo.AppVersion',
                    **{key: False for key in smoke.BOOL_KEYS})
        data['configuration_format'].update(schema_version='99.999.999.999', element_count=4096,
            known_elements=[longest(smoke.KNOWN_ELEMENTS)] * len(smoke.KNOWN_ELEMENTS))
        self.assertLess(len(json.dumps(data, sort_keys=True).encode()) + 1, smoke.MAX_OUTPUT)
        self.assertIn('<= 8192', smoke.PROBE.read_text())
        self.assertEqual(smoke.MAX_OUTPUT, 32768)

    def test_source_limits_equal_trusted_bsl_sources(self):
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
                  '{PrefixSessionModule(12)}', '{SessionModule(0)}', '{SessionModule(' + str(diag.SOURCE_LINE_LIMITS['SessionModule'] + 1) + ')}',
                  '{ManagedApplicationModule(' + str(diag.SOURCE_LINE_LIMITS['ManagedApplicationModule'] + 1) + ')}', '{SessionModule(999999999999)}',
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
        self.assertEqual(result['identifier'], 'ЗащитаОтОпасныхДействий')
        self.assertEqual(result['source_frames'], [{'module': 'SessionModule', 'line': 74}])
        self.assertEqual(result['origin'], 'session_marker')

    def test_context_method_identifier_with_multiple_stack_frames(self):
        for message in ('Ошибка при вызове метода контекста (Записать)',
                        'Error calling context method (Write)',
                        'Error calling context method (Записать)'):
            text = '{МодульСеанса(80)}: ' + message + '\n{МодульСеанса(110)}: caller'
            self.marker(error_marker(error=text))
            value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
            self.assertEqual(value['category'], 'runtime_error')
            self.assertEqual(value['identifier'], 'Записать')
            self.assertEqual(value['source_frames'], [{'module': 'SessionModule', 'line': 80},
                                                     {'module': 'SessionModule', 'line': 110}])
            self.assertFalse(value['source_frames_truncated'])
            self.assertNotIn('_identifier_candidates', value)
            diag.validate_diagnostics(value, primary_kind='process_failed')

    def test_context_identifier_does_not_require_choosing_an_ambiguous_line(self):
        text = '{МодульСеанса(80)}: Ошибка при вызове метода контекста (Записать) {МодульСеанса(110)}'
        self.marker(error_marker(error=text))
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['identifier'], 'Записать')
        self.assertIsNone(value['module'])
        self.assertIsNone(value['line'])
        self.assertEqual([f['line'] for f in value['source_frames']], [80, 110])

    def test_context_wrapper_method_survives_specific_cause_on_another_line(self):
        for wrapper, cause, category in (
                ('Ошибка при вызове метода контекста (Записать)', 'Недостаточно прав', 'permission_denied'),
                ('Error calling context method (Write)', 'Permission denied', 'permission_denied'),
                ('Error calling context method (Write)', 'Authentication failed', 'authentication_failed')):
            text = '{SessionModule(80)}: ' + wrapper + '\nПричина: ' + cause
            self.marker(error_marker(error=text))
            value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
            self.assertEqual(value['category'], category)
            self.assertEqual(value['identifier'], 'Записать')
            self.assertIsNone(value['line'])
            self.assertEqual(value['source_frames'], [{'module': 'SessionModule', 'line': 80}])
        self.marker(error_marker(error='Error calling context method (Write)\nError calling context method (Роли)\nPermission denied'))
        self.assertIsNone(diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)['identifier'])

    def test_context_identifier_requires_exact_known_token_and_syntax(self):
        for token in ('PRIVATE', 'WriteSuffix', 'Write/private', 'ЗаписатьSuffix', 'Записать/private', 'write'):
            value = diag.summarize_text('Error calling context method (' + token + ')')
            self.assertIsNone(value['identifier'])
            self.assertNotIn(token, str(value['_identifier_candidates']))
        self.assertIsNone(diag.summarize_text('Variable not defined (Write)')['identifier'])
        self.assertIsNone(diag.summarize_text('Write Записать')['identifier'])

    def test_frame_list_deduplicates_aliases_preserves_order_and_caps_four(self):
        text = '{SessionModule(8)} {МодульСеанса(8)} {ManagedApplicationModule(9)} {SessionModule(10)} {SessionModule(11)}'
        frames, truncated = diag.source_frames(text)
        self.assertEqual(frames, [{'module': 'SessionModule', 'line': 8},
                                 {'module': 'ManagedApplicationModule', 'line': 9},
                                 {'module': 'SessionModule', 'line': 10},
                                 {'module': 'SessionModule', 'line': 11}])
        self.assertFalse(truncated)
        self.assertEqual(diag.source_frames(text + ' {SessionModule(12)}'), (frames, True))
        self.assertEqual(diag.source_frames(text + ' {SessionModule(11)}'), (frames, False))

    def test_unknown_paths_and_out_of_bounds_frames_are_not_exported(self):
        text = '{/private/SessionModule(3)} {SecretModule(4)} {PrefixSessionModule(5)} {SessionModule(0)} ' + \
               '{SessionModule(' + str(diag.SOURCE_LINE_LIMITS['SessionModule'] + 1) + ')} {SessionModule(True)}'
        self.assertEqual(diag.source_frames(text), ([], False))
        text += ' {МодульСеанса(6)}'
        self.assertEqual(diag.source_frames(text), ([{'module': 'SessionModule', 'line': 6}], False))

    def test_frame_list_keeps_selected_origin_not_foreign_log_locations(self):
        self.marker(error_marker(error='{SessionModule(80)}: Error calling context method (Write)'))
        (self.root / 'bootstrap.log').write_text('{SessionModule(100)}: Error calling context method (Write)', encoding='utf-8')
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['origin'], 'session_marker')
        self.assertEqual(value['source_frames'], [{'module': 'SessionModule', 'line': 80}])
        self.assertEqual(value['identifier'], 'Записать')
        self.assertIsNone(value['line'])

    def test_conflicting_context_identifiers_never_choose_one(self):
        self.marker(error_marker(error='{SessionModule(80)}: Error calling context method (Write)'))
        for other in ('Error calling context method (Роли)',
                      'Error calling context method (Write)\nError calling context method (Роли)'):
            (self.root / 'bootstrap.log').write_text(other, encoding='utf-8')
            value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
            self.assertIsNone(value['identifier'])
            self.assertEqual(value['source_frames'], [{'module': 'SessionModule', 'line': 80}])

    def test_unrecognized_context_method_suppresses_known_method_without_export(self):
        for token in ('PRIVATE', 'Write/private', 'WriteSuffix'):
            text = 'Error calling context method (Write)\nError calling context method (' + token + ')'
            value = diag.summarize_text(text)
            self.assertIsNone(value['identifier'])
            self.assertNotIn(token, str(value))
            self.marker(error_marker(error='Error calling context method (Write)'))
            (self.root / 'bootstrap.log').write_text('Error calling context method (' + token + ')', encoding='utf-8')
            result = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
            self.assertIsNone(result['identifier'])
            self.assertNotIn(token, json.dumps(result))

    def test_identifier_from_another_source_is_not_attributed_to_preferred_marker(self):
        self.marker(error_marker(error='{SessionModule(80)}: runtime error'))
        (self.root / 'bootstrap.log').write_text('Error calling context method (Write)', encoding='utf-8')
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['origin'], 'session_marker')
        self.assertIsNone(value['identifier'])

    def test_ambiguous_unknown_stack_keeps_observed_frames_without_single_cause(self):
        self.marker(error_marker(error='{SessionModule(80)} {SessionModule(81)} unknown'))
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['category'], 'unknown')
        self.assertEqual(value['origin'], 'session_marker')
        self.assertEqual([f['line'] for f in value['source_frames']], [80, 81])
        self.assertIsNone(value['module'])
        self.assertIsNone(value['identifier'])

    def test_conflicting_categories_export_no_frames(self):
        self.marker(error_marker(error='{SessionModule(80)}: Object field not found (Роли)'))
        (self.root / 'bootstrap.log').write_text('{SessionModule(100)}: No license found', encoding='utf-8')
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        self.assertEqual(value['category'], 'conflicting_evidence')
        self.assertEqual(value['source_frames'], [])
        self.assertFalse(value['source_frames_truncated'])

    def test_host_rejects_invalid_frames_on_positive_then_failed_report(self):
        edits = [lambda d: d.update(source_frames=None),
                 lambda d: d.update(source_frames=[{'module': 'SessionModule', 'line': True}]),
                 lambda d: d.update(source_frames=[{'module': 'SessionModule', 'line': 1.0}]),
                 lambda d: d.update(source_frames=[{'module': 'PRIVATE', 'line': 1}]),
                 lambda d: d.update(source_frames=[{'module': 'SessionModule', 'line': 0}]),
                 lambda d: d.update(source_frames=[{'module': 'SessionModule', 'line': 1, 'extra': 'PRIVATE'}]),
                 lambda d: d.update(source_frames=[{'module': 'SessionModule', 'line': diag.SOURCE_LINE_LIMITS['SessionModule'] + 1}]),
                 lambda d: d.update(source_frames=[{'module': 'SessionModule', 'line': 1}] * 2),
                 lambda d: d.update(source_frames=[{'module': 'SessionModule', 'line': i} for i in range(1, 6)]),
                 lambda d: d.update(source_frames_truncated=1),
                 lambda d: d.update(source_frames_truncated=True),
                 lambda d: d.update(origin='none'),
                 lambda d: d.update(module='SessionModule', line=99)]
        self.marker(error_marker(error='{SessionModule(80)}: Error calling context method (Write)'))
        valid = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        for edit in edits:
            data = bootstrap_report()
            data.update(status='stage2_failed', runtime_version=None, runtime_version_source='not_measured', security_settings_changed=None)
            data['stage2'].update(status='failed', failed_stage='bootstrap', failure_kind='process_failed',
                        actual_version=None, version_source='not_measured', simple_output_sha256=None,
                        security_settings_state='unverified', protection_observation=diag.empty_protection_observation(),
                        diagnostics=copy.deepcopy(valid),
                        **{key: key == 'modules_reimported' for key in smoke.STAGE_FLAGS})
            smoke.validate_report(json.dumps(data).encode(), bootstrap=True)
            edit(data['stage2']['diagnostics'])
            with self.subTest(diagnostic=data['stage2']['diagnostics']), self.assertRaises(smoke.SmokeError):
                smoke.validate_report(json.dumps(data).encode(), bootstrap=True)

    def test_success_and_stale_reports_cannot_export_frames(self):
        self.marker(error_marker(error='{SessionModule(80)}: Error calling context method (Write)'))
        value = diag.collect_diagnostics(self.root, 'bootstrap', MANIFEST, 1)
        value['native_exit_code'] = None
        with self.assertRaises(ValueError): diag.validate_diagnostics(value, success=True)
        with self.assertRaises(ValueError): diag.validate_diagnostics(value, primary_kind='stale_evidence')

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
                 lambda d: d.update(module='SessionModule', line=diag.SOURCE_LINE_LIMITS['SessionModule'] + 1),
                 lambda d: d.update(module='PRIVATE', line=1),
                 lambda d: d.update(identifier='PRIVATE'),
                 lambda d: d.update(origin='session_marker', category='unknown')]
        for edit in edits:
            data = bootstrap_report()
            data.update(status='stage2_failed', runtime_version=None, runtime_version_source='not_measured', security_settings_changed=None)
            data['stage2'].update(status='failed', failed_stage='bootstrap', failure_kind='process_failed',
                                  actual_version=None, version_source='not_measured', simple_output_sha256=None,
                                  security_settings_state='unverified',
                    protection_observation=diag.empty_protection_observation(),
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
                    protection_observation=diag.empty_protection_observation(),
                    **{key: key == 'modules_reimported' for key in smoke.STAGE_FLAGS})
        smoke.validate_stage2(data)
        data['diagnostics'].update(category='compile_error', origin='native_log',
                                   module='SessionModule', line=7)
        with self.assertRaises(ValueError): smoke.validate_stage2(data)

    def test_protection_observation_requires_matching_finite_marker(self):
        expected = {'stage': 'bootstrap', 'property_type': 'UnsafeOperationProtectionDescription', 'warning_type': 'Boolean'}
        self.marker(error_marker(observed_protection_type=expected['property_type'], observed_warning_type='Boolean'))
        self.assertEqual(diag.collect_protection_observation(self.root, 'bootstrap', MANIFEST), expected)
        for key, value in (('run_id', 'stale'), ('hook', 'managed'), ('status', []),
                           ('error', 1), ('observed_protection_type', 'PRIVATE'),
                           ('observed_warning_type', False), ('observed_warning_type', [])):
            with self.subTest(key=key, value=value):
                marker = error_marker(observed_protection_type=expected['property_type'], observed_warning_type='Boolean')
                marker[key] = value
                self.marker(marker)
                self.assertEqual(diag.collect_protection_observation(self.root, 'bootstrap', MANIFEST), diag.empty_protection_observation())

    def test_only_allowlisted_actual_type_shapes_are_reported(self):
        for property_type, warning_type in (('Boolean', 'not_observed'), ('Undefined', 'not_observed'),
                                            ('other', 'not_observed'), ('UnsafeOperationProtectionDescription', 'Undefined'),
                                            ('UnsafeOperationProtectionDescription', 'other'),
                                            ('UnsafeOperationProtectionDescription', 'not_observed')):
            self.marker(error_marker(observed_protection_type=property_type, observed_warning_type=warning_type))
            value = diag.collect_protection_observation(self.root, 'bootstrap', MANIFEST)
            self.assertEqual(value, dict(stage='bootstrap', property_type=property_type, warning_type=warning_type))
        self.marker(error_marker(observed_protection_type='Boolean', observed_warning_type='Boolean'))
        self.assertEqual(diag.collect_protection_observation(self.root, 'bootstrap', MANIFEST), diag.empty_protection_observation())

    def test_malformed_protection_marker_never_exports_a_type(self):
        path = self.root / 'bootstrap-session.json'
        for raw in ('[' * 1500, '{"x":NaN}', '{"x":1,"x":2}', '[]', 'null'):
            path.write_text(raw, encoding='utf-8')
            self.assertEqual(diag.collect_protection_observation(self.root, 'bootstrap', MANIFEST), diag.empty_protection_observation())

    def test_host_rejects_invalid_observation_on_otherwise_valid_failed_report(self):
        for edit in (lambda d: d.update(extra='PRIVATE'), lambda d: d.update(stage=[]),
                     lambda d: d.update(property_type='PRIVATE'), lambda d: d.update(warning_type=0),
                     lambda d: d.update(property_type='Boolean'), lambda d: d.update(stage=None),
                     lambda d: d.update(stage='verify')):
            data = bootstrap_report()['stage2']
            data.update(status='failed', failed_stage='bootstrap', failure_kind='process_failed',
                        actual_version=None, version_source='not_measured', simple_output_sha256=None,
                        security_settings_state='unverified',
                        **{key: key == 'modules_reimported' for key in smoke.STAGE_FLAGS})
            data['protection_observation']['stage'] = 'bootstrap'
            smoke.validate_stage2(data)
            edit(data['protection_observation'])
            with self.assertRaises(ValueError): smoke.validate_stage2(data)

    def test_success_requires_observed_supported_named_shape(self):
        for observation in (diag.empty_protection_observation(),
                            dict(stage='bootstrap', property_type='UnsafeOperationProtectionDescription', warning_type='Boolean'),
                            dict(stage='verify', property_type='other', warning_type='not_observed')):
            data = bootstrap_report()['stage2']
            smoke.validate_stage2(data)
            data['protection_observation'] = observation
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

    def test_nonzero_type_guard_reports_observation_but_never_security_success(self):
        def fail(stage, _command, _directory):
            if stage == 'bootstrap':
                marker = self.marker('bootstrap', 'session')
                marker.update(status='error', error='PRIVATE type guard', observed_protection_type='Boolean',
                              observed_warning_type='not_observed')
                (self.evidence / 'bootstrap-session.json').write_text(json.dumps(marker), encoding='utf-8')
                raise self.module.StageError('process_failed', exit_code=1)
        self.native_hook = fail
        report = self.module.run()
        self.assert_failed(report, 'bootstrap', 'process_failed')
        self.assertEqual(report['protection_observation'], dict(stage='bootstrap', property_type='Boolean', warning_type='not_observed'))
        self.assertFalse(report['bootstrap_verified'])
        self.assertEqual(report['security_settings_state'], 'unverified')
        self.assertIsNone(report['actual_version'])
        self.assertNotIn('PRIVATE', json.dumps(report))
        smoke.validate_stage2(report)

    def test_fresh_mismatched_type_observation_does_not_reuse_bootstrap_success(self):
        def fail(stage, _command, _directory):
            if stage == 'verify':
                marker = self.marker('verify', 'session')
                marker.update(status='error', error='PRIVATE type guard', observed_protection_type='Undefined',
                              observed_warning_type='not_observed')
                (self.evidence / 'verify-session.json').write_text(json.dumps(marker), encoding='utf-8')
                raise self.module.StageError('process_failed', exit_code=1)
        self.native_hook = fail
        report = self.module.run()
        self.assert_failed(report, 'verify', 'process_failed')
        self.assertTrue(report['bootstrap_verified'])
        self.assertFalse(report['named_user_verified'])
        self.assertEqual(report['protection_observation'], dict(stage='verify', property_type='Undefined', warning_type='not_observed'))
        smoke.validate_stage2(report)

    def test_stale_session_evidence_never_supplies_new_type_observation(self):
        self.failures['bootstrap'] = 'stale_evidence'
        with mock.patch.object(self.module, 'collect_protection_observation', side_effect=AssertionError('must not read stale marker')):
            report = self.module.run()
        self.assert_failed(report, 'bootstrap', 'stale_evidence')
        self.assertEqual(report['protection_observation'], diag.empty_protection_observation())
        smoke.validate_stage2(report)
        report['protection_observation'] = dict(stage='bootstrap', property_type='Boolean', warning_type='not_observed')
        with self.assertRaises(ValueError): smoke.validate_stage2(report)

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
