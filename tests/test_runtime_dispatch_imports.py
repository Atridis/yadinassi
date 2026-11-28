"""Ordinary calls use their lazy direct service module, not source dispatch."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
import unittest

from yadinassi import BSLError, Interpreter


_SERVICE = 'yadinassi.execution.direct.python_direct_services'
_SOURCE_ONLY = frozenset((
    'yadinassi.execution.direct.python_direct_source',
    'yadinassi.db.metadata.source_constant_managers',
    'yadinassi.db.query.source_constant_queries',
    'yadinassi.db.catalog.source_catalog_runtime',
    'yadinassi.db.document.source_document_runtime',
    'yadinassi.db.document.source_document_sections',
))


class DispatchImportTests(unittest.TestCase):
    def _isolated(self, method):
        # The helper is runnable by exact name but not discovered as another test.
        target = f'tests.test_runtime_dispatch_imports.DispatchImportTests.{method}'
        optimization = ['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []
        child = subprocess.run([sys.executable, '-B', *optimization, '-m', 'unittest', target],
                               cwd=Path(__file__).resolve().parents[1], capture_output=True,
                               text=True, timeout=60)
        self.assertEqual(child.returncode, 0, child.stdout + child.stderr)

    def test_cold_and_warm_calls_preserve_output_and_types(self):
        self._isolated('_cold_and_warm')

    def _cold_and_warm(self):
        initialized = []
        def trace(frame, event, _):
            if (event == 'call' and frame.f_code.co_name == '<module>'
                    and frame.f_globals.get('__name__') == _SERVICE):
                initialized.append(_SERVICE)

        self.addCleanup(sys.setprofile, sys.getprofile())
        sys.setprofile(trace)
        expected = [str(i) for i in range(1, 21)]
        loaded = None
        for warm in (False, True):
            output = []
            with closing(Interpreter(output=output.append)) as vm:
                self.assertEqual(_SERVICE in sys.modules, warm)
                vm.execute('For i = 1 To 20 Do Message(String(i)); EndDo;')
                if not warm:
                    loaded = sys.modules[_SERVICE]
                self.assertIs(sys.modules[_SERVICE], loaded)
                self.assertEqual(initialized, [_SERVICE])
                self.assertIs(type(vm.variables['i']), Decimal)
                self.assertEqual(output, expected)
                self.assertFalse(_SOURCE_ONLY & sys.modules.keys())

    def test_preargument_procedure_refusal_does_not_load(self):
        before, effects = _SOURCE_ONLY & sys.modules.keys(), []
        with closing(Interpreter(allow_extensions=True)) as vm:
            vm.register_function('Touch', lambda: effects.append('argument') or 1)
            vm.register_function('ProcedureOnly', lambda value: effects.append('procedure'),
                                 returns_value=False)
            with self.assertRaisesRegex(BSLError, 'Процедура не возвращает значение'):
                vm.execute('x = ProcedureOnly(Touch());')
            self.assertEqual(effects, [])
            self.assertNotIn('x', vm.variables)
            self.assertEqual(_SOURCE_ONLY & sys.modules.keys(), before)

    def test_failed_argument_does_not_load(self):
        before, output = _SOURCE_ONLY & sys.modules.keys(), []
        with closing(Interpreter(output=output.append)) as vm:
            with self.assertRaisesRegex(BSLError, 'Деление на ноль'):
                vm.execute('Message(1 / 0);')
            self.assertEqual(output, [])
            self.assertEqual(_SOURCE_ONLY & sys.modules.keys(), before)
            vm.execute('Message("next");')
            self.assertEqual(output, ['next'])

    def test_import_failure_is_not_cached(self):
        self._isolated('_import_retry')

    def _import_retry(self):
        class FirstImportFailure:
            def find_spec(self, fullname, path=None, target=None):
                if fullname == _SERVICE:
                    raise ImportError('synthetic unavailable direct service dependency')

        output = []
        with closing(Interpreter(output=output.append)) as vm:
            self.assertNotIn(_SERVICE, sys.modules)
            blocked = FirstImportFailure()
            sys.meta_path.insert(0, blocked)
            try:
                with self.assertRaisesRegex(ImportError, 'synthetic unavailable direct service'):
                    vm.execute('Message("cold");')
                self.assertEqual(output, [])
                self.assertNotIn(_SERVICE, sys.modules)
            finally:
                sys.meta_path.remove(blocked)
            vm.execute('Message("cold");')
            self.assertIn(_SERVICE, sys.modules)
            self.assertEqual(output, ['cold'])


if __name__ == "__main__":
    unittest.main()
