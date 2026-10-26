"""Exercise the separate packaged FindRows program through every CLI transport."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import smoke_test
from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]


class TreeFindRowsBuildSmokeTests(unittest.TestCase):
    def test_shared_program_is_exact_and_preserves_original_type_program_boundary(self):
        source, expected = smoke_test.tree_findrows_smoke_program()
        output = []
        Interpreter(output.append).execute(source)
        self.assertEqual('\n'.join(output) + '\n', expected)
        self.assertEqual(output, ['14523', '2', '2', 'changed', '2', '0',
                                  'undefined flag rejected', 'unknown column rejected'])
        type_source, type_expected = smoke_test.type_smoke_program()
        self.assertNotIn('FindRows', type_source)
        self.assertTrue(type_expected.endswith('Да\nДа\nДерево значений\n'))

    def test_exact_program_across_command_aliases_bom_file_stdin_and_console(self):
        source, expected = smoke_test.tree_findrows_smoke_program()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Поиск.bsl'
            path.write_text(source, encoding='utf-8-sig')
            cases = [([flag, source], None) for flag in ('-c', '-с', '--command')]
            cases += [([str(path)], None), (['-'], source), ([], source + '/exit\n')]
            for args, stdin in cases:
                with self.subTest(args=args[:1]):
                    result = subprocess.run([sys.executable, '-m', 'yadinassi', *args],
                                            input=stdin, capture_output=True, encoding='utf-8',
                                            cwd=ROOT, timeout=30)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))


if __name__ == '__main__':
    unittest.main()
