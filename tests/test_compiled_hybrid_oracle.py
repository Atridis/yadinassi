"""Separate legacy oracle evidence and observed whole-program strict cases.

Clean subprocess assertions are deliberately not compiled coverage. The legacy
hybrid tests keep an explicit interpreter oracle: observer-induced fallback is
not relabelled green.
"""
import json
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
import unittest

from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]


def tagged_value(value):
    """Closed value evidence: never collapse distinct runtime types to strings."""
    kind = type(value)
    if kind is Decimal:
        parts = value.as_tuple()
        return ['decimal', parts.sign, list(parts.digits), parts.exponent]
    if value is None:
        return ['none']
    if kind is bool:
        return ['bool', value]
    if kind is str:
        return ['str', value]
    if kind is int:
        return ['int', value]
    if kind is list:
        return ['list', [tagged_value(item) for item in value]]
    if kind is dict:
        return ['dict', [[tagged_value(key), tagged_value(item)]
                         for key, item in value.items()]]
    raise TypeError('unsupported oracle evidence value')


class HybridOracleEvidenceTests(unittest.TestCase):
    def test_original_hybrid_assertions_in_clean_process_unobserved(self):
        code = '''
import sys, unittest
sys.path[:0] = [sys.argv[1], sys.argv[1] + '/tests']
suite = unittest.defaultTestLoader.loadTestsFromName('test_hybrid_backend')
result = unittest.TextTestRunner().run(suite)
raise SystemExit(not result.wasSuccessful())
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('OK', result.stderr)

    def test_strict_numeric_control_errors_and_effects_match_clean_oracle(self):
        self.assertNotEqual(tagged_value(Decimal('7')), tagged_value('7'))
        self.assertNotEqual(tagged_value(True), tagged_value(1))
        with self.assertRaisesRegex(TypeError, 'unsupported oracle evidence value'):
            tagged_value(object())
        cases = [
            'r=0; Для i=1 По 20 Цикл r=r+i*3-7; КонецЦикла;',
            'r=0; Для i=1 По 10 Цикл i=i+1;r=r+i;КонецЦикла;',
            'n=3;r=0;Для i=1 По n Цикл n=0;r=r+1;КонецЦикла;',
            'Для i=0.5 По 3.7 Цикл r=i;КонецЦикла;',
            'Функция f() Сообщить(7);Возврат 2;КонецФункции Для i=f() По f()+1 Цикл r=i;КонецЦикла;',
            'r=0;Для i=1 По 2 Цикл r=r+1;z=1/0;КонецЦикла;',
        ]
        code = '''
import sys, json
sys.path[:0] = [sys.argv[1], sys.argv[1] + '/tests']
from yadinassi import Interpreter
from test_compiled_hybrid_oracle import tagged_value
rows=[]
for source in json.loads(sys.argv[2]):
    output=[];vm=Interpreter(execution_backend='interpreter',output=output.append)
    error=None
    try:vm.execute(source)
    except Exception as failure:error=[type(failure).__name__,str(failure)]
    rows.append(tagged_value([dict(vm.variables),output,error]))
print(json.dumps(rows))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT), json.dumps(cases)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        reference = json.loads(result.stdout)
        self.assertEqual(len(reference), len(cases))
        for source, expected in zip(cases, reference):
            with self.subTest(source=source):
                output=[]
                vm=Interpreter(execution_backend='compiled-strict',output=output.append)
                error=None
                try:vm.execute(source)
                except Exception as failure:error=[type(failure).__name__,str(failure)]
                actual=tagged_value([dict(vm.variables),output,error])
                self.assertEqual(actual, expected)
                stats=vm.compiled_backend_stats
                self.assertGreater(sum(stats.get(key,0) for key in
                    ('emitted_executions','helper_executions','inline_blocks','inline_fragments')),0)
                for key in ('rejected_units','unsupported_executions','interpreter_fallbacks'):
                    self.assertEqual(stats[key],0)
