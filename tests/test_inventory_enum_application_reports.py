"""Closed format16 read-only reports erase enum storage identity at output."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from uuid import UUID, uuid4

from inventory_enum_application_fixture import source
from yadinassi.configuration_inventory_enum_application import import_inventory_application, PROFILE, validated_core
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalog_backend import BackendError
from yadinassi.enum_storage_values import EnumKey
from yadinassi.inventory_application_reports import InventoryReports, _enum_text
from yadinassi.runtime import Interpreter


class InventoryEnumApplicationReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)/'db.sqlite'
        self.config = import_inventory_application(source(), inventory_runtime=PROFILE)
        self.context = SQLiteDBContext.create_inventory_enum_application(self.path,self.config)
        self.addCleanup(self.context.close)
        self.reports = InventoryReports(self.context,self.config)

    def post(self):
        vm=Interpreter(database_context=self.context); self.addCleanup(vm.close)
        vm.execute('D=Documents.Receipt.CreateDocument();D.Number="R1";D.Date=Date(2024,2,10);'
            'D.State=Enums.States.Approved;L=D.Lines.Add();L.Unit=Enums.Units.Piece;'
            'L.Quantity=2;L.Amount=10;D.Write(DocumentWriteMode.Posting);')

    def test_movements_expose_enum_names_as_strings_only(self):
        self.post()
        result=self.reports.read('StockMovements')
        columns={c.name:i for i,c in enumerate(result.columns)}
        self.assertEqual(result.rows[0][columns['Unit']], 'Piece')
        self.assertEqual(result.rows[0][columns['State']], 'Approved')
        self.assertEqual(result.columns[columns['Unit']].kind,'string')
        self.assertFalse(any(type(v) is EnumKey for row in result.rows for v in row))
        self.assertFalse(any(type(k) is EnumKey for k,_ in result.labels))

    def test_aggregates_and_catalog_filter_choices_remain_read_only(self):
        self.post()
        for name, options in (
            ('StockBalance',{'at':datetime(2024,2,11)}),
            ('StockTurnovers',{'start':datetime(2024,2,1),'end':datetime(2024,3,1)}),
            ('StockStatement',{'start':datetime(2024,2,1),'end':datetime(2024,3,1),'periodicity':'None'})):
            result=self.reports.read(name,**options)
            self.assertEqual(len(result.rows),1)
            self.assertFalse(any(type(v) is EnumKey for row in result.rows for v in row))
        self.assertEqual(self.reports.choices('StockStatement','Product').rows,())
        self.assertIsNone(self.context.backend._active)

    def test_core_profile_is_not_report_grant(self):
        with SQLiteDBContext.create_inventory_enum(self.path.with_name('core.sqlite'),validated_core(self.config)) as context:
            with self.assertRaises(BackendError): InventoryReports(context,self.config)

    def test_foreign_and_unknown_enum_keys_fail_before_projection(self):
        enum=self.config.enumerations[0]
        domain=self.context.backend._enum_domain
        for key in (EnumKey(uuid4(),enum.identity,enum.values[0].identity),
                    EnumKey(domain.database_id,enum.identity,uuid4())):
            with self.assertRaises(BackendError): _enum_text(((key,),),self.config,domain)
        empty=EnumKey(domain.database_id,enum.identity,UUID(int=0))
        self.assertEqual(_enum_text(((empty,),),self.config,domain),(('',),))

    def test_foreign_configuration_property_is_never_invoked(self):
        class Foreign:
            @property
            def profile(self):raise AssertionError('foreign hook called')
        backend=self.context.backend;original=backend.accumulation_configuration
        try:
            backend.accumulation_configuration=Foreign()
            with self.assertRaises(BackendError):self.reports._admit()
        finally:backend.accumulation_configuration=original
