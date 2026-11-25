"""Owned app.execute routes local Val common routines to ordinary SQLite."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration_runtime_fixture import module_files
from test_runtime_context_bindings import BODY
from test_configuration_enumerations import enum_files
from yadinassi import Interpreter
from yadinassi.configuration.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported


class DirectConfigurationSQLiteTests(unittest.TestCase):
    def make(self, common_body, *, with_enums=False):
        module='Function Check() Export\n'+common_body+'\nEndFunction'
        files=enum_files() if with_enums else module_files([('Tools',module,{})])
        if with_enums:files['CommonModules/Tools/Ext/Module.bsl']=module.encode()
        config = import_configuration(files,module_runtime=MODULE_RUNTIME)
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        context = SQLiteDBContext.create(Path(temp.name)/'app.sqlite',config)
        self.addCleanup(context.close)
        seed = Interpreter(database_context=context)
        try: seed.execute('C=Catalogs.Categories.CreateItem();C.Code="01";C.Write();')
        finally: seed.close()
        app = ConfigurationApplication(config,database_context=context)
        self.addCleanup(lambda: app.close(force=True))
        app.start()
        return app,context

    def test_client_module_has_query_temp_manager_and_catalog_buffers(self):
        app, context = self.make(BODY)
        with patch.object(context.backend,'begin_write',side_effect=AssertionError('durable write')):
            self.assertTrue(app.execute('Tools.Check()'))
            self.assertTrue(app.execute('Tools.Check()'))
        self.assertIsNone(context.backend._active)
        with self.assertRaises(PythonDirectUnsupported):
            app.interpreter.execute('Tools.Check()')

    def test_query_handle_cannot_leave_the_command(self):
        app, context = self.make('Return New Запрос;')
        with self.assertRaises(BoundaryViolation):
            app.execute('Tools.Check()')
        self.assertIsNone(context.backend._active)

    def test_catalog_buffer_cannot_write_through_scoped_client_route(self):
        app, context = self.make('P=Catalogs.Products.CreateItem();P.Code="07";P.Write();Return True;')
        with patch.object(context.backend,'begin_write',side_effect=AssertionError('unexpected write')), \
             self.assertRaisesRegex(BoundaryViolation,'database method not connected: Write'):
            app.execute('Tools.Check()')
        self.assertIsNone(context.backend._active)

    def test_query_factory_requires_the_actual_common_module_owner(self):
        app, context = self.make('Q=New Query;Return True;')
        owner = app._modules['tools','client'].interpreter
        parent_factory = app.interpreter.types['query']
        with patch.dict(owner.types,query=parent_factory), \
             self.assertRaisesRegex(BoundaryViolation,'requires owning binding'):
            app.execute('Tools.Check()')
        self.assertIsNone(context.backend._active)

    def test_catalog_type_and_enumeration_type_keep_their_owners(self):
        app, _ = self.make(
            'R=Catalogs.Categories.EmptyRef();'
            'Return TypeOf(R)=Type("CatalogRef.Categories") And '
            'TypeOf(Enums.Status.Active)=Type("EnumRef.Status");',
            with_enums=True)
        self.assertTrue(app.execute('Tools.Check()'))
