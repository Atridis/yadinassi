"""Closed regex40 observations: static small inputs, no native golden assertions."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
import native_1c_regex_family_contract as wire
import native_1c_tree_profiles as profiles

SOURCE_PATH = ROOT/'integrational_tests/measurements/regex_family.bsl'
SOURCE = SOURCE_PATH.read_text(encoding='utf-8')


def emit(*, missing=False, source=SOURCE):
    out = []
    vm = Interpreter(out.append)
    if missing:
        vm.register_function('СтрПодобнаПоРегулярномуВыражению', lambda *args: (_ for _ in ()).throw(ValueError('missing')), 'StrLikeByRegularExpression')
    vm.execute(source)
    return ('\n'.join(out)+'\n').encode('ascii')


def synthetic_output(*, unavailable=False, observer=False):
    return wire.CALIBRATION + b''.join(
        f'RF-{index:02d}: ['.encode()+
        (b'observer-error' if observer and index==40 else b'action-error' if unavailable and index==1 else
         b'ok|S40:'+b'0078'*40)+b']\n' for index in range(1,41))


class RegexFamilyMeasurementTests(unittest.TestCase):
    def test_source_pin_and_closed_forty_cases(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(),profiles.REGEX_FAMILY.source_sha256)
        parse(SOURCE)
        self.assertLessEqual(len(SOURCE.encode()),8192)
        self.assertIn('For N=1 To 40 Do RFObserve(N);EndDo;',SOURCE)
        for number in range(1,41):self.assertEqual(SOURCE.count(f'N={number} Then'),1)
        self.assertEqual(SOURCE.count('Сообщить('),5)
        for forbidden in ('ОписаниеОшибки','Вычислить(','GetTempFileName','DeleteFiles','New File','New MemoryStream','http://','file://'):
            self.assertNotIn(forbidden,SOURCE)
        self.assertIn('// !todo',SOURCE)

    def test_rectangular_wire_budget_and_rejections(self):
        raw=synthetic_output()
        self.assertEqual(len(raw),wire.MAX_ENCODED_BYTES)
        self.assertLessEqual(wire.MAX_ENCODED_BYTES,8192)
        self.assertEqual(len(wire.require_available(raw)),40)
        for bad in (raw+b'x',raw[:-1],raw.replace(b'RF-02:',b'RF-01:'),
                    raw.replace(b'S40:',b'S57:',1),raw.replace(b'0078',b'007g',1),
                    raw.replace(b'RF-C1: [S0:]',b'RF-C1: [S1:]')):
            with self.subTest(bad=bad[:20]),self.assertRaises(wire.ObservationError):wire.validate_output(bad)
        with self.assertRaises(wire.AvailabilityError):wire.require_available(synthetic_output(unavailable=True))
        with self.assertRaises(wire.AvailabilityError):wire.require_available(synthetic_output(observer=True))

    def test_local_runtime_observation_is_not_native_evidence(self):
        self.assertEqual(len(wire.require_available(emit())),40)
        with self.assertRaises(wire.AvailabilityError):wire.require_available(emit(missing=True))

    def test_isolated_cold_import_has_its_own_scripts_bootstrap(self):
        code='import sys;sys.path[:0]=sys.argv[1:3];import test_native_regex_family_measurement as m; m.wire.require_available(m.synthetic_output()); print(m.profiles.REGEX_FAMILY.count)'
        command=[sys.executable,'-I']+(['-O'] if sys.flags.optimize else [])
        with tempfile.TemporaryDirectory(prefix='regex-cold-import-') as cwd:
            result=subprocess.run(command+['-c',code,str(ROOT),str(ROOT/'tests')],cwd=cwd,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'42')

if __name__=='__main__':unittest.main()
