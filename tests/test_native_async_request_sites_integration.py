"""Execute exact generated reader operations with controlled first/later faults.
Offline VM only: controlled JSON tokens, exceptions and stages are not native or
Async evidence. No generated-source rewriting or runtime changes are used.
"""
from decimal import Decimal
import unittest

from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.structures import BSLStructure
import test_native_async_request_reader as reader_fixture

SOURCE_LABEL = 'offline-managed-form-module'
FAULT_DESCRIPTION = 'PRIVATE CONTROLLED REQUEST FAILURE'


class SiteReader(reader_fixture.ControlledReader):
    def __init__(self, tokens, expected_path, fault, iteration):
        super().__init__(tokens, expected_path)
        self.site_fault, self.iteration = fault, iteration

    def read(self):
        if self.position == 2 * self.iteration - 2:
            if self.site_fault == 'read_error':
                raise ValueError(FAULT_DESCRIPTION)
            if self.site_fault == 'read_false':
                self.position += 1
                return False
        return super().read()

    def get_member(self, name):
        if self.position == 2 * self.iteration - 1:
            if name == 'CurrentValueType':
                if self.site_fault == 'token_error':
                    raise ValueError(FAULT_DESCRIPTION)
                if self.site_fault == 'token_mismatch':
                    return 'String'
            if name == 'CurrentValue' and self.site_fault == 'current_error':
                raise ValueError(FAULT_DESCRIPTION)
        return super().get_member(name)


class SiteTokenNames(reader_fixture.TokenNames):
    def __init__(self, fault, iteration):
        self.fault, self.iteration = fault, iteration
        self.key_calls = 0

    def get_member(self, name):
        if name == 'PropertyName':
            self.key_calls += 1
            if self.fault == 'call_error' and self.key_calls == self.iteration:
                raise ValueError(FAULT_DESCRIPTION)
        return super().get_member(name)


class SiteStructure(BSLStructure):
    def __init__(self, fault, iteration):
        super().__init__()
        self.fault, self.iteration = fault, iteration
        self.property_calls = 0

    def property(self, name, output=None):
        self.property_calls += 1
        if self.property_calls == self.iteration:
            if self.fault == 'property_error':
                raise ValueError(FAULT_DESCRIPTION)
            if self.fault == 'property_true':
                return True
        return super().property(name, output)


def exercise_site(site_fault, case_id=0, iteration=1, *, outer=False):
    module = reader_fixture.suite.async_client_module(case_id).decode('utf-8-sig')
    start = module.index('&AtClient\nProcedure AsyncExpectToken')
    end = module.index('&НаКлиенте\nПроцедура АсинхЗаписатьВход')
    exact_slice = module[start:end]
    reader = SiteReader(reader_fixture.stream_tokens(reader_fixture.canonical()),
                        '/tmp/offline/request.json', site_fault, iteration)
    output = []
    vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
    vm.register_type('JSONReader', lambda: reader)
    vm.register_type('Structure', lambda: SiteStructure(site_fault, iteration))
    vm.execute('Var JSONValueType, LaunchParameter;')
    vm.variables['jsonvaluetype'] = SiteTokenNames(site_fault, iteration)
    vm.variables['launchparameter'] = '/tmp/offline/request.json'
    if site_fault == 'key_assignment_error':
        normal_set_variable = vm.set_variable
        def set_variable(name, value):
            if name.casefold() == 'key' and reader.position == 2 * iteration - 1:
                raise ValueError(FAULT_DESCRIPTION)
            return normal_set_variable(name, value)
        vm.set_variable = set_variable
    vm.execute(exact_slice, source=SOURCE_LABEL)
    if outer:
        start = module.index('&НаКлиенте\nПроцедура ПриОткрытии')
        end = module.index('КонецПроцедуры', start) + len('КонецПроцедуры')
        vm.execute(module[start:end], source=SOURCE_LABEL)
        vm.execute('Cancel = False; ПриОткрытии(Cancel);')
    else:
        vm.execute('Stage = "request"; Caught = False; '
                   'Try Result = AsyncReadRequest(Stage); Except '
                   'Saved = ErrorInfo(); Caught = True; EndTry;', source=SOURCE_LABEL)
    return vm, reader, output, module


# Frozen independent operation inventory; the labels are not runtime-derived.
FAULTS = (
    ('read_error', 'read'), ('read_false', 'read'),
    ('token_error', 'token'), ('token_mismatch', 'token'),
    ('current_error', 'current'), ('key_assignment_error', 'current'),
    ('property_error', 'property'), ('property_true', 'property'),
)


class GeneratedRequestSiteIntegrationTests(unittest.TestCase):
    def test_success_retains_strict_reader_and_has_no_diagnostic_output(self):
        for case_id in range(8):
            vm, reader, output, module = exercise_site(None, case_id)
            self.assertFalse(vm.execute('Caught'))
            self.assertEqual(vm.execute('Stage'), 'request_paths')
            self.assertEqual(vm.execute('Result.Count()'), Decimal(5))
            self.assertEqual(reader.read_calls, 13)
            self.assertTrue(reader.closed)
            self.assertEqual(output, [])
            self.assertNotIn('AsyncRequestKeySite', module)
            self.assertNotIn('ASYNC-SITE-CALIBRATION', module)

    def test_all_four_operations_and_all_five_iterations_for_all_eight_cases(self):
        for case_id in range(8):
            for iteration in range(1, 6):
                bucket = 'first' if iteration == 1 else 'later'
                for fault, operation in FAULTS:
                    with self.subTest(case=case_id, iteration=iteration, fault=fault):
                        vm, reader, output, _ = exercise_site(fault, case_id, iteration)
                        self.assertTrue(vm.execute('Caught'))
                        self.assertEqual(vm.execute('Stage'), f'request_key_{operation}_{bucket}')
                        self.assertNotIn('result', vm.variables)
                        self.assertFalse(reader.closed)
                        self.assertEqual(output, [])

    def test_argument_evaluation_failure_stays_at_call_and_precedes_read(self):
        for case_id in range(8):
            for iteration in range(1, 6):
                with self.subTest(case=case_id, iteration=iteration):
                    vm, reader, output, _ = exercise_site('call_error', case_id, iteration)
                    self.assertTrue(vm.execute('Caught'))
                    self.assertEqual(vm.execute('Stage'), 'request_key_call')
                    self.assertEqual(reader.position, 2 * iteration - 2)
                    self.assertEqual(reader.read_calls, 2 * iteration - 1)
                    self.assertNotIn('result', vm.variables)
                    self.assertEqual(output, [])


if __name__ == '__main__':
    unittest.main()
