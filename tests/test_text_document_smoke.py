"""Use the exact packaged TextDocument program through all ordinary CLI routes."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import smoke_test
from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]


class TextDocumentSmokeTests(unittest.TestCase):
    def test_program_covers_core_and_closed_file_api(self):
        source, expected = smoke_test.text_document_smoke_program()
        messages = []
        Interpreter(messages.append).execute(source)
        self.assertEqual('\n'.join(messages) + '\n', expected)
        for name in ('SetText', 'GetText', 'LineCount', 'GetLine', 'AddLine',
                     'ВставитьСтроку', 'ReplaceLine', 'УдалитьСтроку', 'Очистить'):
            self.assertIn('.' + name + '(', source)
        self.assertEqual(messages[-2:], ['line-boundary', 'file-api-closed'])

    def test_all_cli_transports_preserve_output_and_never_create_write_target(self):
        source, expected = smoke_test.text_document_smoke_program()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'ТекстовыйДокумент.bsl'
            path.write_text(source, encoding='utf-8-sig')
            # -m resolves the checked-out package from ROOT; the inert target
            # name is never interpreted as a path by the in-memory object.
            for args, stdin in (([str(path)], None), (['-c', source], None),
                                (['-с', source], None), (['--command', source], None),
                                (['-'], source), ([], source + '/exit\n')):
                with self.subTest(args=args[:1]):
                    result = subprocess.run([sys.executable, '-m', 'yadinassi', *args],
                                            input=stdin, capture_output=True, encoding='utf-8',
                                            cwd=ROOT, timeout=30)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, expected, ''))
            self.assertFalse((ROOT / 'must-not-write').exists())


if __name__ == '__main__': unittest.main()
