"""The diagnostic export uses production preparation, never executes BSL."""
import ast
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter, launcher
from yadinassi.cli_support.cli_emit_python import emit_file, sources

ROOT = Path(__file__).resolve().parents[1]


class EmitPythonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / 'Пример с пробелом.bsl'
        self.out = self.root / 'python'

    def write(self, text):
        self.script.write_text(text, encoding='utf-8-sig')

    def cli(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        return subprocess.run([sys.executable, '-B', '-m', 'yadinassi', *map(str, args)],
                              env=env, cwd=self.root, capture_output=True,
                              encoding='utf-8', timeout=20)

    def test_module_cli_emits_actual_runtime_source_utf8_without_running(self):
        text = 'Function F(Val x) Return x+1;EndFunction Message("НЕ ИСПОЛНЯТЬ");r=F(2);'
        self.write(text)
        result = self.cli('--emit-python', self.out, self.script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('НЕ ИСПОЛНЯТЬ', result.stdout)
        emitted = (self.out / (self.script.stem + '.py')).read_text(encoding='utf-8')
        ast.parse(emitted)
        # Capture the actual standalone CLI compilation, not a second emitter
        # or the library's embedding mode.
        from yadinassi.cli import main
        from yadinassi.execution.direct import python_direct
        actual = python_direct._compile
        plans = []
        def capture(*args, **kwargs):
            plan = actual(*args, **kwargs)
            plans.append(plan.generated_source)
            return plan
        with mock.patch.object(python_direct, '_compile', side_effect=capture), redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.script)]), 0)
        self.assertTrue(emitted.endswith(plans[0] + '\n'))

    def test_callbacks_execution_and_file_writes_are_not_invoked(self):
        marker = self.root / 'must-not-exist.txt'
        self.write('Message("side effect"); w=New TextDocument;w.AddLine("side effect");w.Write("' + marker.as_posix()
                   + '");')
        # Patching normal execution leaves the compiler/admission identities alone.
        with mock.patch.object(Interpreter, 'execute', side_effect=AssertionError('execute')), \
                mock.patch.object(Interpreter, 'execute_program', side_effect=AssertionError('execute_program')), \
                mock.patch.object(Interpreter, 'execute_prepared', side_effect=AssertionError('execute_prepared')), \
                mock.patch.object(Interpreter, '_message', side_effect=AssertionError('callback')), \
                mock.patch('sqlite3.connect', side_effect=AssertionError('database initialized')):
            emit_file(self.script, self.out)
        self.assertFalse(marker.exists())
        self.assertEqual(len(list(self.out.iterdir())), 1)

    def test_real_subprocess_does_not_write_user_file(self):
        marker = self.root / 'marker.txt'
        self.write('w=New TextDocument;w.AddLine("side effect");w.Write("' + marker.as_posix() + '");')
        result = self.cli(self.script, '--emit-python', self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        # Positive control: this source really has a filesystem effect in the
        # ordinary CLI. Export did not merely avoid an already unsupported call.
        ordinary = self.cli(self.script)
        self.assertEqual(ordinary.returncode, 0, ordinary.stderr)
        self.assertTrue(marker.is_file())

    def test_unsupported_fails_without_partial_output_or_fallback(self):
        self.write('Message("before"); X=New UnknownEmitterFixture;')
        result = self.cli(self.script, '--emit-python', self.out)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('UnknownEmitterFixture', result.stderr)
        self.assertNotIn('before', result.stdout)
        self.assertFalse(self.out.exists())

    def test_client_async_emits_a_generator_without_executing(self):
        self.write('Async Function F() Message("async body"); Return Await 1; EndFunction P=F();')
        result = self.cli(self.script, '--emit-python', self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('async body', result.stdout)
        emitted = (self.out / (self.script.stem + '.py')).read_text(encoding='utf-8')
        self.assertTrue(any(isinstance(node, ast.Yield) for node in ast.walk(ast.parse(emitted))))

    def test_syntax_failure_and_missing_input(self):
        self.write('If ???')
        result = self.cli(self.script, '--emit-python', self.out)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.out.exists())
        result = self.cli(self.root / 'missing.bsl', '--emit-python', self.out)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.out.exists())

    def test_no_clobber_case_insensitive(self):
        self.write('r=1;')
        self.out.mkdir()
        existing = self.out / (self.script.stem.upper() + '.PY')
        existing.write_text('keep', encoding='utf8')
        with self.assertRaises(FileExistsError):
            emit_file(self.script, self.out)
        self.assertEqual(existing.read_text(), 'keep')
        self.assertEqual(len(list(self.out.iterdir())), 1)

    def test_second_export_does_not_overwrite(self):
        self.write('r=1;')
        outputs = emit_file(self.script, self.out)
        original = outputs[0].read_bytes()
        self.write('r=2;')
        with self.assertRaises(FileExistsError):
            emit_file(self.script, self.out)
        self.assertEqual(outputs[0].read_bytes(), original)

    def test_late_server_collision_does_not_create_main_file(self):
        self.write('&AtServer\nFunction F() Return 7;EndFunction\nr=F();')
        self.out.mkdir()
        collision = self.out / (self.script.stem + '.SERVER.PY')
        collision.write_text('keep')
        with self.assertRaises(FileExistsError):
            emit_file(self.script, self.out)
        self.assertEqual(list(self.out.iterdir()), [collision])
        self.assertEqual(collision.read_text(), 'keep')

    @unittest.skipIf(os.name == 'nt', 'symlink creation may require Windows privilege')
    def test_dangling_output_symlink_is_not_followed(self):
        self.write('r=1;')
        self.out.mkdir()
        link = self.out / (self.script.stem + '.py')
        target = self.root / 'absent'
        link.symlink_to(target)
        with self.assertRaises(FileExistsError):
            emit_file(self.script, self.out)
        self.assertTrue(link.is_symlink())
        self.assertFalse(target.exists())

    def test_windows_reserved_output_name_rejected_on_every_platform(self):
        source = self.root / 'CON.bsl'
        if os.name == 'nt':
            from yadinassi.cli_support.cli_emit_python import _portable_name
            with self.assertRaises(ValueError):
                _portable_name('CON.py')
        else:
            source.write_text('r=1;')
            with self.assertRaisesRegex(ValueError, 'имя'):
                emit_file(source, self.out)
        self.assertFalse(self.out.exists())

    def test_imports_are_not_read_or_executed_or_crawled(self):
        self.write('// #Import Missing.bsl\nr=1;')
        # Missing import intentionally does not exist. Resolution belongs to execution.
        paths = emit_file(self.script, self.out)
        self.assertEqual(len(paths), 1)
        ast.parse(paths[0].read_text(encoding='utf-8'))

    def test_server_plans_created_by_preparation_are_included(self):
        text = '&AtServer\nFunction F() Return 7;EndFunction\n&AtClient\nVar r;\nr=F();'
        self.write(text)
        paths = emit_file(self.script, self.out)
        vm = Interpreter(execution_backend='python-direct')
        try:
            expected = sources(vm.prepare(text, str(self.script)))
        finally:
            vm.close()
        self.assertIn('.server', expected)
        self.assertEqual({p.name for p in paths},
                         {self.script.stem + suffix + '.py' for suffix in expected})
        for suffix, code in expected.items():
            emitted = (self.out / (self.script.stem + suffix + '.py')).read_text(encoding='utf-8')
            ast.parse(emitted)
            self.assertTrue(emitted.endswith(code + '\n'))

    def test_profile_and_encoding_use_normal_preparation(self):
        self.script.write_text('#If AtClient Then\nr="Я";\n#Else\nr="Сервер";\n#EndIf', encoding='cp1251')
        result = self.cli(self.script, '--encoding', 'cp1251', '--emit-python', self.out,
                          '--preprocessor-profile', 'standalone')
        self.assertEqual(result.returncode, 0, result.stderr)
        ast.parse(next(self.out.iterdir()).read_text(encoding='utf-8'))

    def test_conflicting_modes_rejected_before_database_or_ui_initialization(self):
        self.write('r=1;')
        bad = [('--legacy',), ('--execution-backend', 'interpreter'), ('-c', 'Message(1);'),
               ('--f', str(self.root / 'db.sqlite')), ('--create-db', str(self.root / 'new.sqlite')),
               ('--configuration-source', str(self.root)), ('--ui',)]
        for extra in bad:
            with self.subTest(extra=extra), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                    mock.patch('yadinassi.cli.SQLiteDBContext', side_effect=AssertionError('db')):
                # UI is first to exercise the launcher rather than only argparse.
                argv = [*extra, str(self.script), '--emit-python', str(self.out)]
                with self.assertRaises(SystemExit) as caught:
                    launcher.main(argv)
                self.assertEqual(caught.exception.code, 2)
        self.assertFalse(self.out.exists())
        self.assertFalse((self.root / 'new.sqlite').exists())

    def test_ui_entry_is_not_called(self):
        ui = mock.Mock()
        ui.main.side_effect = AssertionError('UI started')
        with mock.patch.dict(sys.modules, {'yadinassi.ui.database_launch': ui}), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            launcher.main(['--ui', '--emit-python', str(self.out), str(self.script)])
        self.assertEqual(caught.exception.code, 2)
        ui.main.assert_not_called()

    def test_requires_one_real_file_not_command_or_stdin(self):
        for prefix in ([], ['-'], ['-c', 'r=1;']):
            with self.subTest(prefix=prefix):
                result = self.cli(*prefix, '--emit-python', self.out)
                self.assertEqual(result.returncode, 2)
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
