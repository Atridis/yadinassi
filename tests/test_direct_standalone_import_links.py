"""Standalone CLI links closed BSL exports at their first call only."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.cli import main
from yadinassi.execution.direct.python_direct_imports import ImportBoundary


class StandaloneImportLinksTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name)
        self.main = path / 'Main.bsl'
        self.side = path / 'Side.bsl'
        self.side.write_text('Function Inc(Val X) Export\nReturn X+1;\nEndFunction', encoding='utf-8')
        self.events = []
        self.vm = Interpreter(output=self.events.append)
        self.addCleanup(self.vm.close)
        self.vm._standalone_script = True

    def execute(self, body):
        return self.vm.execute('// #Import Side.bsl\n'+body, str(self.main))

    def test_cli_loop_links_once_and_never_resolves_per_iteration(self):
        self.main.write_text('// #Import Side.bsl\nR=0;For I=1 To 10 Do R=R+Side.Inc(I);EndDo;Message(R);', encoding='utf-8')
        seen = []
        original = ImportBoundary.link_import_call

        def link(boundary, path, **kwargs):
            seen.append(path)
            function = original(boundary, path, **kwargs)
            self.assertIsNotNone(function)
            return function

        with patch.object(ImportBoundary, 'link_import_call', link), \
                patch.object(ImportBoundary, 'resolve_import_call', side_effect=AssertionError('generic import call')), \
                redirect_stdout(StringIO()) as output:
            status = main([str(self.main)])
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue().strip(), '65')
        self.assertEqual(seen, [('side','inc')])

    def test_dead_call_does_not_resolve(self):
        with patch.object(ImportBoundary, 'link_import_call', side_effect=AssertionError('dead call')):
            self.assertEqual(self.execute('If False Then R=Side.Missing();EndIf;42'), 42)

    def test_module_state_reads_keep_their_boundary_and_stay_live(self):
        self.side.write_text('Var X Export;X=1;Function Get() Export Return X;EndFunction', encoding='utf-8')
        self.execute('R=0;For I=1 To 2 Do R=R+Side.Get();Side.X=I+1;EndDo;')
        self.assertEqual(self.vm.variables['r'], 3)

    def test_imported_failure_keeps_callee_source_and_line(self):
        with self.assertRaises(BSLError) as error:
            self.execute('Side.Inc(Undefined)')
        self.assertEqual(error.exception.source, str(self.side))
        self.assertEqual(error.exception.line, 2)

    def test_link_from_inside_local_routine(self):
        self.assertEqual(self.execute('Function F() Return Side.Inc(1);EndFunction F()+F()'), 4)

    def test_prepared_link_belongs_to_one_execution(self):
        source = '// #Import Side.bsl\nR=Side.Inc(1);'
        plan = self.vm.prepare(source, str(self.main))
        seen = []
        original = ImportBoundary.link_import_call

        def link(boundary, path, **kwargs):
            seen.append(path)
            return original(boundary, path, **kwargs)

        with patch.object(ImportBoundary, 'link_import_call', link):
            self.vm.execute_prepared(plan)
            self.vm.execute_prepared(plan)
        self.assertEqual(self.vm.variables['r'], 2)
        self.assertEqual(seen, [('side','inc')]*2)

    def test_byref_and_dynamic_code_keep_ordinary_import_boundaries(self):
        self.side.write_text(
            'Procedure Update(X) Export X=X+1;EndProcedure\n'
            'Function EvalArg(Val X) Export Return Eval("X+1");EndFunction',
            encoding='utf-8',
        )
        self.execute('R=40;Side.Update(R);R=Side.EvalArg(R);')
        self.assertEqual(self.vm.variables['r'], 42)

    def test_non_client_contexts_do_not_link(self):
        from yadinassi.execution.direct.python_direct import make_boundary
        self.execute('42')
        boundary = make_boundary(self.vm)
        boundary.enter()
        try:
            for attr, value in (('_server_side', True), ('module_context', False)):
                with self.subTest(attr=attr), patch.object(boundary, attr, value, create=True), \
                        patch.object(boundary, '_import_target', side_effect=AssertionError('target lookup')):
                    self.assertIsNone(boundary.link_import_call(('side', 'inc'), require_value=True, argument_count=1))
        finally:
            boundary.leave()

    def test_invalid_bindings_report_original_error_before_arguments(self):
        for source in ('Side.Missing(Bug)', 'Side.Inc(Bug, Bug)'):
            errors = []
            for enable in (False, True):
                vm = Interpreter()
                self.addCleanup(vm.close)
                vm._standalone_script = enable
                with self.assertRaises(BSLError) as error:
                    vm.execute('// #Import Side.bsl\n'+source, str(self.main))
                errors.append(str(error.exception))
            self.assertEqual(*errors)
            self.assertNotIn('Bug', errors[0])

    def test_embedding_does_not_enter_standalone_path(self):
        self.vm._standalone_script = False
        with patch.object(ImportBoundary, 'link_import_call', side_effect=AssertionError('linked in embedding')):
            self.assertEqual(self.execute('Side.Inc(1)'), 2)
