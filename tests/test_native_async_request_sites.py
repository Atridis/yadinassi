"""Closed append-only operation labels and the actual private failure handler.
Offline harness checks only; no native execution or semantic cause is inferred.
"""
import re
import unittest

import test_native_async_request_reader as reader_fixture
import test_native_async_request_sites_integration as integration
from test_native_async_fixture import routine

suite = reader_fixture.suite
NEW_LABELS = (
    'request_key_read_first', 'request_key_read_later',
    'request_key_token_first', 'request_key_token_later',
    'request_key_current_first', 'request_key_current_later',
    'request_key_property_first', 'request_key_property_later',
)
END_LABELS = ('request_end_call', 'request_end_read', 'request_end_token',
              'request_end_trailing', 'request_end_close')
LEGACY_CATEGORIES = (
    'not_checked', 'observed_absent', 'observed_invalid', 'unknown',
    'compile_error', 'runtime_error', 'unsupported_api', 'permission_denied',
    'authentication_failed', 'license_unavailable', 'training_restriction',
    'startup_failed', 'conflicting_evidence', 'entry_request', 'entry_witness',
    'entry_initialize', 'entry_entered', 'entry_root', 'entry_request_open',
    'entry_request_object', 'entry_request_key', 'entry_request_value',
    'entry_request_end', 'entry_request_fields', 'entry_request_nonce', 'entry_request_paths',
    'entry_request_key_call', 'entry_request_key_read', 'entry_request_key_token',
    'entry_request_key_current', 'entry_request_key_property',
)


class GeneratedRequestSiteGuardTests(unittest.TestCase):
    def test_append_only_labels_have_fixed_literal_producers_for_all_cases(self):
        self.assertEqual(suite.ASYNC_LOG_CATEGORIES[:31], LEGACY_CATEGORIES)
        self.assertEqual(suite.ASYNC_LOG_CATEGORIES[31:39], tuple('entry_' + label for label in NEW_LABELS))
        for code, label in enumerate(NEW_LABELS, 31):
            self.assertEqual(suite.ASYNC_ENTRY_LOG_MARKERS['ASYNC-ENTRY-FAILURE:' + label], code)
        for case_id in range(8):
            module = suite.async_client_module(case_id).decode('utf-8-sig')
            helper = routine(module, 'AsyncExpectRequestKey')
            reader = routine(module, 'AsyncReadRequest')
            labels = re.findall(r'ЭтапВхода = "(request_key_[a-z_]+)";', helper + reader)
            self.assertEqual(labels, [*NEW_LABELS[:4], 'request_key_call', *NEW_LABELS[4:]])
            self.assertNotIn('AsyncRequestKeySite', module)
            self.assertNotIn('ASYNC-SITE-CALIBRATION', module)
            self.assertNotIn('ErrorInfo()', helper + reader)
            self.assertNotIn('Сообщить(', helper + reader)
            expected = (
                ('read', 'If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;', helper),
                ('token', 'If Reader.CurrentValueType <> Token Then Raise "ASYNC-REQUEST"; EndIf;', helper),
                ('current', 'AsyncRequestKey = Reader.CurrentValue;', reader),
                ('property', 'If Request.Property(AsyncRequestKey) Then Raise "ASYNC-REQUEST"; EndIf;', reader),
            )
            for name, operation, source in expected:
                block = (f'If Index = 1 Then\n'
                         f'    ЭтапВхода = "request_key_{name}_first";\n'
                         f'Else\n'
                         f'    ЭтапВхода = "request_key_{name}_later";\n'
                         f'EndIf;\n{operation}')
                normalized = '\n'.join(line.strip() for line in source.splitlines())
                self.assertIn('\n'.join(line.strip() for line in block.splitlines()), normalized)

    def test_end_labels_append_after_all_unchanged_legacy_categories(self):
        self.assertEqual(suite.ASYNC_LOG_CATEGORIES[:39],
                         LEGACY_CATEGORIES + tuple('entry_' + label for label in NEW_LABELS))
        self.assertEqual(suite.ASYNC_LOG_CATEGORIES[39:],
                         tuple('entry_' + label for label in END_LABELS))
        for code, label in enumerate(END_LABELS, 39):
            self.assertEqual(suite.ASYNC_ENTRY_LOG_MARKERS['ASYNC-ENTRY-FAILURE:' + label], code)
        for case_id in range(8):
            module = suite.async_client_module(case_id).decode('utf-8-sig')
            reader = routine(module, 'AsyncReadRequest')
            self.assertEqual(re.findall(r'ЭтапВхода = "(request_end_[a-z]+)";', reader),
                             list(END_LABELS))
            self.assertTrue(reader.startswith('    Var AsyncRequestKey, AsyncRequestEndToken;\n'))
            self.assertEqual(len(re.findall(r'\bAsyncRequestEndToken\b', module)), 3)
            self.assertEqual(module.count('JSONValueType.ObjectEnd'), 1)
            self.assertNotIn('AsyncExpectRequestEnd', module)
            for label, operation in (
                ('call', 'AsyncRequestEndToken = JSONValueType.ObjectEnd;'),
                ('read', 'If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;'),
                ('token', 'If Reader.CurrentValueType <> AsyncRequestEndToken Then Raise "ASYNC-REQUEST"; EndIf;'),
                ('trailing', 'If Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;'),
                ('close', 'Reader.Close();'),
            ):
                self.assertIn(f'    ЭтапВхода = "request_end_{label}";\n    {operation}', reader)
            for forbidden in ('ErrorInfo()', 'Сообщить(', 'Try', 'Except'):
                self.assertNotIn(forbidden, reader)

    def test_actual_outer_catch_emits_only_exact_finite_label(self):
        for iteration in range(1, 6):
            bucket = 'first' if iteration == 1 else 'later'
            for fault, operation in integration.FAULTS:
                with self.subTest(iteration=iteration, fault=fault):
                    vm, reader, output, _ = integration.exercise_site(fault, iteration=iteration, outer=True)
                    self.assertEqual(output, [f'ASYNC-ENTRY-FAILURE:request_key_{operation}_{bucket}'])
                    self.assertFalse(reader.closed)
                    self.assertNotIn(integration.FAULT_DESCRIPTION, ''.join(output))
        _, _, output, _ = integration.exercise_site('call_error', outer=True)
        self.assertEqual(output, ['ASYNC-ENTRY-FAILURE:request_key_call'])

    def test_actual_outer_catch_emits_only_each_finite_end_label(self):
        for case_id in range(8):
            for fault, operation in integration.END_FAULTS:
                with self.subTest(case=case_id, fault=fault):
                    _, reader, output, _ = integration.exercise_site(fault, case_id, outer=True)
                    self.assertEqual(output, ['ASYNC-ENTRY-FAILURE:request_end_' + operation])
                    self.assertFalse(reader.closed)
                    self.assertNotIn(integration.FAULT_DESCRIPTION, ''.join(output))


if __name__ == '__main__':
    unittest.main()
