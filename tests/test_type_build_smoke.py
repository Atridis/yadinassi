"""Exercise the exact packaged type-smoke program before a binary is built."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import smoke_test
from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]


class TypeBuildSmokeTests(unittest.TestCase):
    def test_shared_program_keeps_unknown_type_failure_and_positive_tree_checks(self):
        source, expected = smoke_test.type_smoke_program()
        messages = []
        Interpreter(output=messages.append).execute(source)
        self.assertEqual('\n'.join(messages) + '\n', expected)
        self.assertEqual(messages.count('неизвестный тип'), 1)
        self.assertEqual(messages[-3:], ['Да', 'Да', 'Дерево значений'])

    def test_supported_tree_cannot_silently_replace_negative_probe(self):
        source, expected = smoke_test.type_smoke_program()
        self.assertEqual(source.count('Type("UnknownTree")'), 1)
        messages = []
        Interpreter(output=messages.append).execute(source.replace('Type("UnknownTree")', 'Type("ValueTree")'))
        self.assertNotEqual('\n'.join(messages) + '\n', expected)
        self.assertNotIn('неизвестный тип', messages)

    def test_exact_shared_program_across_all_build_smoke_transports(self):
        source, expected = smoke_test.type_smoke_program()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Типы.bsl'
            path.write_text(source, encoding='utf-8-sig')
            for args, stdin in (([str(path)], None), (['-c', source], None),
                                (['-'], source), ([], source + '/exit\n')):
                with self.subTest(args=args[:1]):
                    result = subprocess.run([sys.executable, '-m', 'yadinassi', *args],
                                            input=stdin, capture_output=True, encoding='utf-8',
                                            cwd=ROOT, timeout=30)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))

    def test_no_obsolete_tree_diagnostics_in_build_or_console_helpers(self):
        for filename in ('smoke_test.py', 'console_check.py'):
            source = (ROOT / 'scripts' / filename).read_text(encoding='utf-8')
            for name in ('ValueTree', 'ДеревоЗначений'):
                self.assertNotIn('Тип не поддерживается: ' + name, source)


if __name__ == '__main__':
    unittest.main()
