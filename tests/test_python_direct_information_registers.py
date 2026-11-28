"""Ordinary BSL reaches existing register operations under its exact owner."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from test_information_registers import register_files
from yadinassi import Interpreter
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


class DirectInformationRegisterTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'owned.sqlite'
        self.db = SQLiteDBContext.create(self.path, import_configuration(register_files()))
        self.addCleanup(self.db.close)
        self.vm = self.interpreter()

    def interpreter(self, **kwargs):
        owner = Interpreter(database_context=self.db, **kwargs)
        self.addCleanup(owner.close)
        return owner

    def test_two_namespace_aliases_and_prepared_read_with_native_structure(self):
        self.vm.execute('R=РегистрыСведений["Prices"].СоздатьМенеджерЗаписи();'
                        'R.Item="A";R.Region="North";R.Price=23;R.Записать();')
        prepared = self.vm.prepare('InformationRegisters.Prices.Get(New Structure("Region,Item","North","A")).Price')
        self.assertEqual(self.vm.execute_prepared(prepared), Decimal(23))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name='information_register_receipt'").fetchone())

    def test_foreign_namespace_and_children_do_not_gain_same_database_authority(self):
        self.vm.execute('Namespace=InformationRegisters;Manager=Namespace.Prices;'
                        'RecordManager=Manager.CreateRecordManager();'
                        'Set=Manager.CreateRecordSet();Filter=Set.Filter;Field=Filter.Region;'
                        'Row=Set.Add();Selection=Manager.Select();')
        other = self.interpreter()
        expressions = {'namespace': 'Foreign.Prices', 'manager': 'Foreign.Select()',
                       'recordmanager': 'Foreign.Price', 'set': 'Foreign.Count()',
                       'filter': 'Foreign.Region', 'field': 'Foreign.Use',
                       'row': 'Foreign.Price', 'selection': 'Foreign.Next()'}
        for name, expression in expressions.items():
            with self.subTest(receiver=name):
                other.variables['foreign'] = self.vm.variables[name]
                with self.assertRaises(BoundaryViolation):
                    other.execute(expression)

    def test_manager_retarget_during_argument_evaluation_cannot_write(self):
        foreign = self.interpreter()
        foreign.execute('R=InformationRegisters.Prices.CreateRecordManager();')
        replacements = []
        def output(_):
            manager._manager = foreign.variables['r']._manager
            replacements.append(True)

        vm = self.interpreter(output=output)
        vm.execute('R=InformationRegisters.Prices.CreateRecordManager();R.Price=7;')
        manager = vm.variables['r']
        original = manager._manager
        try:
            with patch.object(self.db.backend, 'begin_register_write',
                              side_effect=AssertionError('unexpected write')), self.assertRaises(BoundaryViolation):
                vm.execute('Function Decision() Message("effect"); Return 1; EndFunction '
                           'R.Price=Decision();')
        finally:
            manager._manager = original
        self.assertEqual(replacements, [True])
        self.assertEqual(manager.get_member('Price'), Decimal(7))
