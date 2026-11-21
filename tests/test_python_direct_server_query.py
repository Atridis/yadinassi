"""Ordinary server Query uses the active interpreter's SQLite namespace."""
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import HostFunction
from yadinassi.types.errors import BSLError
import test_catalog_queries as fixtures
from test_runtime_context_bindings import BODY


class DirectServerQueryTests(unittest.TestCase):
    setUp = fixtures.CatalogQueryTests.setUp
    tearDown = fixtures.CatalogQueryTests.tearDown

    def test_bilingual_query_and_temp_manager_across_server_modes(self):
        self.assertFalse(self.vm.allow_extensions)
        for directive in ('AtServer', 'AtServerNoContext', 'AtClientAtServerNoContext'):
            with self.subTest(directive=directive):
                self.vm.execute('&' + directive + '\nFunction Probe()\n' + BODY + '\nEndFunction')
                self.assertTrue(self.vm.execute('Probe()'))
                if directive == 'AtClientAtServerNoContext':
                    self.vm.execute('&AtServer\nFunction CallDual() Return Probe(); EndFunction')
                    self.assertTrue(self.vm.execute('CallDual()'))
                self.assertEqual(self.vm.execution_context, 'client')
                self.assertIsNone(self.context.backend._active)

    def test_imported_server_uses_its_own_binding(self):
        helper = Path(self.temp.name) / 'Gateway.bsl'
        helper.write_text('&AtServerNoContext\nFunction Probe() Export\n' + BODY + '\nEndFunction',
                          encoding='utf-8')
        self.vm.execute('// #Import Gateway.bsl\n', str(helper.with_name('main.bsl')))
        self.assertTrue(self.vm.execute('Gateway.Probe()'))
        self.assertIsNone(self.context.backend._active)

    def test_noncanonical_query_factory_is_never_called_on_server(self):
        self.vm.execute('&AtServer\nFunction Probe() Return New Query; EndFunction')
        called = []
        factory = HostFunction('Query', lambda: called.append('unexpected'))
        with patch.dict(self.vm.types, query=factory), self.assertRaisesRegex(BoundaryViolation,'query constructor'):
            self.vm.execute('Probe()')
        self.assertEqual(called, [])

    def test_query_handle_cannot_cross_to_the_client(self):
        self.vm.execute('&AtServer\nFunction Probe() Return New Query; EndFunction')
        with self.assertRaisesRegex((BSLError, TypeError, ValueError), 'Межконтекстная передача'):
            self.vm.execute('Probe()')
        self.assertEqual(self.vm.execution_context, 'client')


class DirectServerQueryNoDatabaseTests(unittest.TestCase):
    def test_unused_definition_is_allowed_but_query_needs_database(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('&AtServer\nFunction Unused() Return New Запрос; EndFunction')
        self.assertEqual(vm.execute('1+2'), 3)
        with self.assertRaisesRegex(BSLError, 'db required'):
            vm.execute('Unused()')
        self.assertEqual(vm.execution_context, 'client')
