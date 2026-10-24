"""Offline replay of eight accepted native observations, not a native run.

Bodies are exact UTF-8 copies of ASYNC_CASE_SOURCES at the pinned commit.
Only transport/capture and the root are replaced. This finite Linux observation
set is not a universal scheduler specification.
"""
import hashlib
import json
from pathlib import Path
import unittest

from yadinassi import Interpreter
from yadinassi.error_info import BSLErrorCategory, BSLErrorInfo
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.type_values import type_of
from yadinassi.values import BSLType

FIXTURE = Path(__file__).parent / 'fixtures' / 'async_native_linux_8_3_27_1508.json'
FIXTURE_SHA256 = '5f4361f2aeaf96e49b4802ba93daa3fbaaf0a40dbc0213726f30f88cd42ae8ec'
OBSERVATIONS = json.loads(FIXTURE.read_text(encoding='utf-8'))
DECLARATIONS = '''Перем АсинхЛистЗначение, АсинхВнутреннее,
    АсинхЗначениеУмолчания, АсинхСбой;
'''
ROOT = '''
&НаКлиенте
Асинх Процедура ReplayRoot()
    АсинхСобытие(0);
    Тест = АсинхТестПробы();
    АсинхУдержать(Тест);
    Завершение = Ждать Тест;
    АсинхСобытие(3);
    АсинхСобытие(4);
КонецПроцедуры
ReplayRoot();
'''


class Capture:
    """Non-scheduling equivalents of the native capture procedures."""
    def __init__(self):
        self.trace, self.values, self.errors, self.retained = [], [], [], []

    def begin(self, count):
        self.values = [dict(slot=i, type='skipped', value=None)
                       for i in range(int(count))]
        self.event(1)

    def event(self, code):
        self.trace.append(int(code))

    def retain(self, value):
        if type_of(value) is BSLType.PROMISE:
            self.retained.append(value)

    def save(self, slot, value):
        kind = type_of(value)
        names = {BSLType.PROMISE: 'Promise', BSLType.NUMBER: 'Number',
                 BSLType.UNDEFINED: 'Undefined', BSLType.NULL: 'Null'}
        if kind not in names:
            raise AssertionError(f'Unexpected captured type: {kind!r}')
        if kind is BSLType.NUMBER:
            if value != int(value):
                raise AssertionError('Fixture expects exact integer numbers')
            payload = int(value)
        else:
            payload = None
        self.values[int(slot)] = dict(slot=int(slot), type=names[kind], value=payload)

    def save_error(self, slot, phase, error):
        if type(error) is not BSLErrorInfo:
            raise AssertionError('Expected structured ErrorInfo')
        self.values[int(slot)] = dict(slot=int(slot), type='ErrorReference',
                                     value=len(self.errors))
        self.errors.append(dict(
            phase=int(phase), description=error.get_member('Description'),
            code=error.get_member('Code'),
            additional=error.get_member('AdditionalInformation'),
            configuration_error=error.is_error_of_category(
                BSLErrorCategory.CONFIGURATION_ERROR),
            cause_type=type_of(error.get_member('Cause')).name,
        ))

    def install(self, vm):
        for name, callback in (
            ('АсинхНачатьТест', self.begin), ('АсинхСобытие', self.event),
            ('АсинхУдержать', self.retain), ('АсинхСохранить', self.save),
            ('АсинхСохранитьОшибку', self.save_error),
        ):
            vm.register_function(name, callback, returns_value=False)


def expected_error(observation):
    # Public evidence exports exact synthetic classes. Private descriptor hashes
    # include native source locations: provenance only, not wrapper assertions
    # or evidence of ErrorInfo object identity.
    exact = {'exact synthetic ASYNC-REJECT': 'ASYNC-REJECT',
             'exact synthetic ASYNC-CODE': 'ASYNC-CODE',
             'exact synthetic ASYNC-DETAIL': 'ASYNC-DETAIL'}
    assert observation['category'] == 'ConfigurationError membership'
    assert observation['cause'] == 'Undefined'
    return dict(phase=observation['phase'],
                description=exact[observation['description']],
                code=exact[observation['code']],
                additional=exact[observation['additional']],
                configuration_error=True, cause_type='UNDEFINED')


class NativeAsyncObservationTests(unittest.TestCase):
    def test_fixture_integrity_and_scope(self):
        # JSON container newlines may change on checkout; source newlines are
        # escaped inside JSON and their decoded UTF-8 bytes stay exact.
        fixture_text = FIXTURE.read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(fixture_text.encode('utf-8')).hexdigest(),
                         FIXTURE_SHA256)
        provenance = OBSERVATIONS['provenance']
        self.assertEqual(provenance['commit'], '5eaa21bb292498a45886f746fb54cc730140ac12')
        self.assertEqual(provenance['run_id'], 39964367396)
        self.assertEqual([case['case'] for case in OBSERVATIONS['cases']], list(range(8)))
        for case in OBSERVATIONS['cases']:
            with self.subTest(case=case['case']):
                self.assertEqual(hashlib.sha256(case['source'].encode('utf-8')).hexdigest(),
                                 case['source_body_sha256'])
                self.assertEqual(len(case['native_module_sha256']), 64)

    def test_exact_eight_native_observations(self):
        for case in OBSERVATIONS['cases']:
            with self.subTest(case=case['case']):
                vm = Interpreter(output=lambda message: None,
                                 native_target=LINUX_8_3_27_1508)
                capture = Capture()
                capture.install(vm)
                vm.execute(DECLARATIONS + case['source'] + ROOT)
                vm.run_until_idle()
                self.assertEqual(capture.trace, case['trace'])
                self.assertEqual(capture.values, case['values'])
                self.assertEqual(capture.errors, [expected_error(e) for e in case['errors']])
                self.assertFalse(vm.pending_promises)
                self.assertFalse(vm.variables['асинхсбой'])
                self.assertTrue(capture.retained)
                self.assertTrue(all(p.state != 'pending' for p in capture.retained))


if __name__ == '__main__':
    unittest.main()
