"""Detached query tables use canonical public methods without database authority."""
from decimal import Decimal
import hashlib
import json
import unittest
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.collections.value_tables import BSLValueTable, BSLValueTableRow
from yadinassi.types.type_descriptions import BSLTypeDescription

class QueryTableTests(unittest.TestCase):
    def table(self):
        table=BSLValueTable();table.columns.add('N',BSLTypeDescription('Number'))
        table.add().set_member('N',Decimal(4));return table

    def test_source_ast_prepared_public_protocol(self):
        from yadinassi.syntax.parser import parse
        source='T[0].N=5;R=T.Count()+T[0].N;C=T.Columns[0].Name;D=T.Columns[0].ValueType.NumberQualifiers.Digits;'
        for route in ('source','ast','prepared'):
            vm=Interpreter();vm.variables['t']=self.table()
            if route=='source':vm.execute(source)
            elif route=='ast':vm.execute_program(parse(source))
            else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(vm.variables['r'],6);self.assertEqual(vm.variables['c'],'N')

    def test_noncanonical_receivers_and_owners_rejected(self):
        class OtherTable(BSLValueTable):pass
        table=OtherTable();table.columns.add('N',BSLTypeDescription('Number'))
        row=table.add();row.set_member('N',Decimal(4))
        self.assertIs(type(row),BSLValueTableRow)
        vm=Interpreter();self.addCleanup(vm.close)
        vm.variables.update(t=table,r=row)
        with self.assertRaises(BoundaryViolation):vm.execute('T.Count();')
        with self.assertRaisesRegex(BoundaryViolation,'noncanonical value table owner'):
            vm.execute('R.N;')

    def test_foreign_row_deleted_row_and_private_attributes(self):
        vm=Interpreter();table=self.table();foreign=self.table().get(Decimal(0))
        vm.variables.update(t=table,r=foreign)
        with self.assertRaises(BSLRuntimeError):vm.execute('T.Delete(R);')
        self.assertEqual(len(table.rows),1)
        row=table.get(Decimal(0));table.delete(row);vm.variables['r']=row
        with self.assertRaises(BSLRuntimeError):vm.execute('R.N=9;')
        with self.assertRaises(BSLRuntimeError):vm.execute('R=T.rows;')

    def test_bounded_slice_restrictions_preserved(self):
        table=self.table();table._bounded_slice_read=True
        vm=Interpreter();vm.variables['t']=table
        self.assertEqual(vm.execute('T.Count()'),1)
        for source in ('T.Add();','T[0].N=8;','T.Columns.Add("Other");','R=T.Indexes;'):
            with self.assertRaises(BSLRuntimeError):vm.execute(source)
        self.assertEqual(table.get(Decimal(0)).get_member('N'),4)

    def test_revocation_after_method_binding_before_write(self):
        vm=Interpreter(allow_extensions=True);table=self.table();vm.variables['t']=table
        vm.register_function('Close',lambda:vm.close() or Decimal(0))
        with self.assertRaises(BoundaryViolation):vm.execute('T.Delete(Close());')
        self.assertEqual(len(table.rows),1)

    def test_original_catalog_query_replay_matches_native24(self):
        from catalog_query_behavior.replay import replay
        rows=replay()
        self.assertEqual(len(rows),24)
        # Accepted native artifact14334693411, run44098520311; exact compact wire.
        wire=(json.dumps(rows,separators=(',',':'))+'\n').encode()
        self.assertEqual(hashlib.sha256(wire).hexdigest(),'2a0a0e7db4025a5babc7ece3edd833feddba7ccffc16027bd6139cc184aa5c84')

    def test_table_cell_does_not_grant_foreign_catalog_authority(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from yadinassi.configuration.configuration_main_demo import PROFILE,import_main_demo_configuration
        from yadinassi.db.database_context import SQLiteDBContext
        from test_main_demo_configuration import source
        with TemporaryDirectory() as folder:
            context=SQLiteDBContext.create_main_demo(Path(folder)/'db.sqlite',import_main_demo_configuration(source(),profile=PROFILE))
            try:
                owner=Interpreter(database_context=context);other=Interpreter(database_context=context)
                try:
                    owner.execute('A=Catalogs.Склады.CreateItem();A.Description="original";')
                    table=BSLValueTable();table.columns.add('Foreign');table.add().set_member('Foreign',owner.variables['a'])
                    other.variables['t']=table
                    with self.assertRaises(BoundaryViolation):other.execute('T[0].Foreign.Description="bad";')
                    self.assertEqual(owner.variables['a'].get_member('Description'),'original')
                finally:owner.close();other.close()
            finally:context.close()
