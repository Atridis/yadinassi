"""Ordinary BSL and explicit Python extension modes share the same compiler."""
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.types.values import HostFunction


class InterpreterExtensionPolicyTests(unittest.TestCase):
    def interpreter(self, **options):
        vm = Interpreter(**options)
        self.addCleanup(vm.close)
        return vm

    def test_plain_by_default_and_public_registrations_are_explicit(self):
        vm = self.interpreter()
        self.assertIs(vm.allow_extensions, False)
        self.assertEqual(vm.execute('A=New Array;A.Add(StrLen("abc"));A[0]'), 3)
        with self.assertRaisesRegex(ValueError, 'allow_extensions=True'):
            vm.register_function('PythonFunction', lambda: 1)
        with self.assertRaisesRegex(ValueError, 'allow_extensions=True'):
            vm.register_type('PythonType', object)
        with self.assertRaises(AttributeError):
            vm.allow_extensions = True

    def test_native_operations_are_lean_unless_extensions_enabled(self):
        source = 'Function F(Val A,Val B) A[0]=B;Return A[0]+B;EndFunction X=New Array;X.Add(0);F(X,3)'
        for enabled in (False, True):
            vm = self.interpreter(allow_extensions=enabled)
            plan = vm.prepare(source)
            self.assertEqual('_context._check()' in plan._plan.generated_source, enabled)
            self.assertEqual(vm.execute_prepared(plan), 6)

    def test_filled_service_registry_and_callable_values_cannot_bypass_opt_in(self):
        calls = []
        vm = self.interpreter()
        host = HostFunction('PythonFunction', lambda: calls.append('extension'))
        vm.functions['pythonfunction'] = host
        self.assertEqual(vm.execute('1+2'), 3)
        with self.assertRaisesRegex(BoundaryViolation, 'allow_extensions=True'):
            vm.execute('PythonFunction()')
        del vm.functions['pythonfunction']
        vm.variables['pythonfunction'] = host
        with self.assertRaisesRegex(BoundaryViolation, 'allow_extensions=True'):
            vm.execute('PythonFunction()')
        self.assertEqual(calls, [])

    def test_a_builtin_swapped_by_output_callback_is_not_called(self):
        calls = []

        def output(_):
            vm.functions['strlen'].function = lambda value: calls.append(value)

        vm = self.interpreter(output=output)
        with self.assertRaisesRegex(BoundaryViolation, 'allow_extensions=True'):
            vm.execute('Message("swap");StrLen("data")')
        self.assertEqual(calls, [])

    def test_opt_in_callback_and_imported_child_inherit_extensions(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        (path / 'Side.bsl').write_text(
            'Function Run(Val X) Export Return Increment(X);EndFunction',
            encoding='utf-8',
        )
        vm = self.interpreter(allow_extensions=True)
        vm.register_function('Increment', lambda value: value + 1)
        vm.register_type('PythonType', object)
        self.assertIn('pythontype', vm.types)
        self.assertEqual(vm.execute('// #Import Side.bsl\nSide.Run(7)', str(path/'Main.bsl')), 8)
        self.assertIs(vm.imports['side'].interpreter.allow_extensions, True)

    def test_prepared_contract_does_not_cross_modes(self):
        plain = self.interpreter()
        extended = self.interpreter(allow_extensions=True)
        for source_vm, target_vm in ((plain, extended), (extended, plain)):
            with self.assertRaises(PythonDirectUnsupported):
                target_vm.execute_prepared(source_vm.prepare('1+2'))

    def test_python_embedding_does_not_opt_into_context_free_import_links(self):
        vm = self.interpreter()
        plan = vm.prepare('// #Import Side.bsl\nSide.F(5)')
        self.assertNotIn('link_import_call', plan._plan.generated_source)


    def test_no_database_does_not_prevent_ordinary_bsl_side_transition(self):
        vm = self.interpreter()
        source = ('&AtServer\nFunction S(Val X) Return X+1;EndFunction\n'
                  '&AtClient\nFunction F() Return S(40);EndFunction\nF()')
        self.assertIsNone(vm.database_context)
        self.assertEqual(vm.execute(source), 41)
        self.assertEqual(vm.execution_context, 'client')

    def test_database_context_is_explicit_and_independent_of_extensions(self):
        from yadinassi.db.database_context import SQLiteDBContext
        from yadinassi.db.sqlite.sqlite_migration_plan import prepare, apply
        from test_sqlite_catalog_hierarchy import configuration

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / 'owned.sqlite'
        SQLiteDBContext.create(database, configuration(mixed=True)).close()
        apply(database, prepare(database, maintenance=True), maintenance=True)
        context = SQLiteDBContext(database)
        self.addCleanup(context.close)
        vm = self.interpreter(database_context=context)
        self.assertIs(vm.allow_extensions, False)
        vm.execute('C=Catalogs.Products.CreateItem();C.Code="plain";'
                   'BeginTransaction();C.Write();CommitTransaction();')
        self.assertEqual(vm.execute('Catalogs.Products.FindByCode("plain").Code'), 'plain')
