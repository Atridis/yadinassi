"""Actual generated synchronous-reader/ErrorInfo classifier integration.
Offline VM only. VM source labels and error-frame shapes are NOT native evidence.
No source-line rewriting, no native/Async claim, and no repository/runtime edits.
"""
import unittest
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.structures import BSLStructure
import test_native_async_request_reader as reader_fixture

SOURCE_LABEL = 'offline-managed-form-module'
FAULT_DESCRIPTION = 'PRIVATE CONTROLLED REQUEST FAILURE'


class SiteReader(reader_fixture.ControlledReader):
    def __init__(self, tokens, expected_path, site_fault):
        super().__init__(tokens, expected_path)
        self.site_fault = site_fault

    def read(self):
        if self.position == 0:
            if self.site_fault == 'read_error':
                raise ValueError(FAULT_DESCRIPTION)
            if self.site_fault == 'read_false':
                self.position += 1
                return False
        return super().read()

    def get_member(self, name):
        if self.position == 1:
            if name == 'CurrentValueType':
                if self.site_fault == 'token_error':
                    raise ValueError(FAULT_DESCRIPTION)
                if self.site_fault == 'token_mismatch':
                    return 'String'
            if name == 'CurrentValue' and self.site_fault == 'current_error':
                raise ValueError(FAULT_DESCRIPTION)
        return super().get_member(name)


class SiteTokenNames(reader_fixture.TokenNames):
    def __init__(self, fault):
        self.fault = fault

    def get_member(self, name):
        if name == 'PropertyName' and self.fault == 'call_error':
            raise ValueError(FAULT_DESCRIPTION)
        return super().get_member(name)


class SiteStructure(BSLStructure):
    def __init__(self, fault):
        super().__init__()
        self.fault = fault

    def property(self, name, output=None):
        if self.fault == 'property_error':
            raise ValueError(FAULT_DESCRIPTION)
        if self.fault == 'property_true':
            return True
        return super().property(name, output)


def exercise_site(site_fault, case_id=0):
    module = reader_fixture.suite.async_client_module(case_id).decode('utf-8-sig')
    start = module.index('&AtClient\nProcedure AsyncExpectToken')
    end = module.index('&НаКлиенте\nПроцедура АсинхЗаписатьВход')
    exact_slice = module[start:end]
    # Keep exact generated line locations for both real reader exceptions and
    # the deliberate same-module calibration exception inside the classifier.
    padded_source = '\n' * module[:start].count('\n') + exact_slice
    reader = SiteReader(reader_fixture.stream_tokens(reader_fixture.canonical()),
                        '/tmp/offline/request.json', site_fault)
    output = []
    vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
    vm.register_type('JSONReader', lambda: reader)
    if site_fault in ('property_error', 'property_true'):
        vm.register_type('Structure', lambda: SiteStructure(site_fault))
    vm.execute('Var JSONValueType, LaunchParameter;')
    vm.variables['jsonvaluetype'] = SiteTokenNames(site_fault)
    vm.variables['launchparameter'] = '/tmp/offline/request.json'
    if site_fault == 'key_assignment_error':
        normal_set_variable = vm.set_variable
        def set_variable(name, value):
            if name.casefold() == 'key':
                raise ValueError(FAULT_DESCRIPTION)
            return normal_set_variable(name, value)
        vm.set_variable = set_variable
    vm.execute(padded_source, source=SOURCE_LABEL)
    vm.execute('Stage = "request"; Site = "not_called"; Caught = False; '
               'Try Result = AsyncReadRequest(Stage); Except '
               'Saved = ErrorInfo(); Caught = True; Site = AsyncRequestKeySite(Saved); '
               'EndTry;', source=SOURCE_LABEL)
    return vm, reader, output, module


class GeneratedRequestSiteIntegrationTests(unittest.TestCase):
    def test_success_does_not_invoke_failure_classifier(self):
        vm, reader, output, _ = exercise_site(None)
        self.assertFalse(vm.execute('Caught'))
        self.assertEqual(vm.execute('Site'), 'not_called')
        self.assertTrue(reader.closed)
        self.assertEqual(output, [])

    def test_all_five_generated_sites_with_real_local_errorinfo(self):
        cases = (
            ('call_error', 'request_key_call', 183),
            ('read_error', 'request_key_read', 168),
            ('read_false', 'request_key_read', 168),
            ('token_error', 'request_key_token', 169),
            ('token_mismatch', 'request_key_token', 169),
            ('current_error', 'request_key_current', 184),
            ('key_assignment_error', 'request_key_current', 184),
            ('property_error', 'request_key_property', 185),
            ('property_true', 'request_key_property', 185),
        )
        for case_id in range(8):
            for fault, expected, line in cases:
                with self.subTest(case_id=case_id, fault=fault):
                    vm, _, output, module = exercise_site(fault, case_id)
                    self.assertTrue(vm.execute('Caught'))
                    self.assertEqual(vm.execute('Stage'), 'request_key')
                    self.assertEqual(vm.execute('Site'), expected)
                    # The calibration's nested catch must not replace Saved.
                    self.assertEqual(vm.execute('Saved.ModuleName'), SOURCE_LABEL)
                    self.assertEqual(vm.execute('Saved.LineNumber'), line)
                    self.assertEqual(vm.execute('Saved.InitialString'), module.splitlines()[line - 1])
                    self.assertNotEqual(vm.execute('Saved.Description'), 'ASYNC-SITE-CALIBRATION')
                    self.assertNotIn('result', vm.variables)
                    self.assertEqual(output, [])


if __name__ == '__main__':
    unittest.main()
