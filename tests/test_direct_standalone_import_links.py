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

    def sqlite_database(self):
        from yadinassi.db.database_context import SQLiteDBContext
        from yadinassi.db.sqlite.sqlite_migration_plan import prepare, apply
        from test_sqlite_catalog_hierarchy import configuration

        database = self.main.with_name('db.sqlite')
        SQLiteDBContext.create(database, configuration(mixed=True)).close()
        apply(database, prepare(database, maintenance=True), maintenance=True)
        return database

    def test_cli_database_keeps_transaction_boundary_but_links_pure_export(self):
        database = self.sqlite_database()
        self.main.write_text(
            '// #Import Side.bsl\n'
            'BeginTransaction();'
            'A=New Array; A.Add(1);'
            'For I=1 To 4 Do A[0]=Side.Inc(A[0]); EndDo;'
            'R=A[0];For I=1 To 4 Do R=Side.Inc(R); EndDo;'
            'C=Catalogs.Products.CreateItem();C.Code=String(R);C.Write();'
            'CommitTransaction();Message(Catalogs.Products.FindByCode("9").Code);',
            encoding='utf-8',
        )
        seen = []
        original = ImportBoundary.link_import_call

        def link(boundary, path, **kwargs):
            self.assertIsNotNone(boundary._direct_transaction_owner)
            function = original(boundary, path, **kwargs)
            self.assertIsNotNone(function)
            seen.append(path)
            return function

        with patch.object(ImportBoundary, 'link_import_call', link), redirect_stdout(StringIO()) as output:
            status = main(['--f', str(database), str(self.main)])
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue().strip(), '9')
        self.assertEqual(seen, [('side', 'inc')])
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(main(['--f', str(database), '-c',
                                   'Message(Catalogs.Products.FindByCode("9").Code);']), 0)
        self.assertEqual(output.getvalue().strip(), '9')

    def test_cli_client_server_crossing_keeps_working_with_or_without_database(self):
        self.main.write_text(
            '&AtServer\nFunction ServerName()\n'
            '#If Server And Not Client Then\n Return "server";\n'
            '#Else\n Return "wrong";\n#EndIf\nEndFunction\n'
            '&AtClient\nProcedure Run()\n'
            'For I=1 To 2 Do Message(ServerName());EndDo;\n'
            'EndProcedure\nRun();',
            encoding='utf-8',
        )
        database = self.sqlite_database()
        for options in ([], ['--f', str(database)]):
            with self.subTest(options=options), redirect_stdout(StringIO()) as output:
                self.assertEqual(main([*options, str(self.main)]), 0)
                self.assertEqual(output.getvalue().splitlines(), ['server', 'server'])

    def test_cli_database_and_embedded_database_use_different_generated_checks(self):
        from yadinassi.db.database_context import SQLiteDBContext
        from yadinassi.execution.direct import python_direct

        database = self.sqlite_database()
        source = 'Function F(Val A) A[0]=1;Return A[0];EndFunction X=New Array;X.Add(0);Message(F(X));'
        generated = []
        original = python_direct._compile

        def compile(vm, *args, **kwargs):
            plan = original(vm, *args, **kwargs)
            generated.append(plan.generated_source)
            return plan

        with patch.object(python_direct, '_compile', compile), redirect_stdout(StringIO()):
            self.assertEqual(main(['-c', source]), 0)
            self.assertEqual(main(['--f', str(database), '-c', source]), 0)
            with SQLiteDBContext(database) as context:
                vm = Interpreter(database_context=context)
                try:
                    vm.execute(source)
                finally:
                    vm.close()
        self.assertEqual(len(generated), 3)
        self.assertEqual(['_context._check()' in plan for plan in generated], [False, False, True])

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
