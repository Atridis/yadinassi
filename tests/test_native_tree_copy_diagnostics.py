"""Finite synthetic Copy diagnostics, not native evidence."""
import unittest
from scripts import native_1c_tree_copy_diagnostics as d
from scripts import native_1c_tree_copy_contract as c
from test_native_tree_copy_measurement import maximum_output


def diagnose(raw, site='server'):
    return d.observation_diagnostic(raw, site, c.validate_payload, c.ObservationError)


class Diagnostics(unittest.TestCase):
    def test_success_maximum_and_both_sites(self):
        raw = maximum_output()
        self.assertIsNone(diagnose(raw))
        self.assertIsNone(diagnose(raw, 'client'))
        self.assertTrue(set(raw.decode().replace('\n', '')) <= d.MESSAGE_CHARACTERS)
        self.assertIn('/', d.MESSAGE_CHARACTERS)

    def test_all_calibration_codes_and_invalid_codes(self):
        raw = maximum_output()
        for code in d.CALIBRATION_CODES + 'Z':
            value = diagnose(raw.replace(b'TC-C: [-]', f'TC-C: [{code}]'.encode()))
            self.assertEqual(value, {'site':'server', 'case':0, 'category':'calibration',
                                     'calibration':code if code != 'Z' else None})

    def test_all_stages_all_cases(self):
        lines = maximum_output().splitlines(keepends=True)
        for case in range(1, 10):
            for stage in d.OBSERVER_STAGES:
                changed = lines.copy(); changed[case] = f'TC-{case}: [X{stage}]\n'.encode()
                value = diagnose(b''.join(changed))
                self.assertEqual(value['category'], 'observer_' + stage.lower())
                self.assertEqual(value['case'], case)
                d.validate_diagnostic(value)

    def test_global_and_shape_and_payload_failures(self):
        raw = maximum_output()
        for value, category in [(None,'invalid_type'), (bytearray(raw),'invalid_type'),
                                (b'x'*8193,'output_limit'), (raw+b'\r','encoding'),
                                (raw+b'\xff','encoding'), (raw+b'\n','record_count'),
                                (raw.replace(b'TC-1:',b'TC-2:',1),'record_shape'),
                                (raw.replace(b'[S/',b'[X/',1),'payload_contract')]:
            self.assertEqual(diagnose(value)['category'], category)
        for forbidden in ('"', '\\', '\t', '\r', '\x00', 'é'):
            self.assertEqual(diagnose(raw+forbidden.encode())['category'],'encoding')

    def test_validator_rejects_bad_values(self):
        base={'site':'server','case':1,'category':'observer_b','calibration':None}
        for field, value in [('site',None), ('site','other'), ('site',[]), ('case',True),
                             ('case',0),('case',10),('case',None),('category',[]),
                             ('category','private text'), ('calibration','B'),('calibration','I')]:
            item = dict(base); item[field] = value
            with self.subTest(field=field,value=value), self.assertRaises(d.DiagnosticError):
                d.validate_diagnostic(item)
        for item in ([], {}, {**base,'private':'no'}, {**base,'category':'encoding'},
                     {**base,'category':'calibration'}, {**base,'category':'calibration','case':0,'calibration':'-' } ):
            with self.assertRaises(d.DiagnosticError):d.validate_diagnostic(item)

    def test_programmer_error_not_masked(self):
        def broken(payload, case):raise RuntimeError('internal')
        with self.assertRaises(RuntimeError):
            d.observation_diagnostic(maximum_output(),'server',broken,c.ObservationError)


if __name__ == '__main__':unittest.main()
