"""Authored periodic-register contract, not native parity evidence."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.dates import BSLDate, literal_date
from yadinassi.periodic_information_registers import period
from yadinassi.queries import BSLQuery
from yadinassi.register_backend import RegisterKey, RegisterDraft, RegisterScanRequest
from test_information_registers import register_files


def periodic_files(periodicity='Day', catalogs=True):
    files=register_files(catalogs=catalogs)
    files['InformationRegisters/Prices.xml']=files['InformationRegisters/Prices.xml'].replace(
        b'Nonperiodical',periodicity.encode())
    return files


class PeriodicSchemaTests(unittest.TestCase):
    def test_declared_dimensions_and_generated_period(self):
        schema,=import_configuration(periodic_files()).information_registers
        self.assertEqual(schema.periodicity,'Day')
        self.assertEqual([f.name for f in schema.dimensions],['Item','Region'])
        self.assertEqual([f.name for f in schema.key_fields],['Period','Item','Region'])
        self.assertEqual(schema.period_field.identity,schema.period_field.identity)
    def test_calendar_normalization(self):
        source=literal_date('20240229174329')
        expected={'WithinSecond':'20240229174329','Day':'20240229000000',
                  'Month':'20240201000000','Quarter':'20240101000000','Year':'20240101000000'}
        for kind,want in expected.items():
            with self.subTest(kind=kind): self.assertEqual(period(source,kind),literal_date(want))
    def test_fractional_assignment_floors_to_second(self):
        self.assertEqual(period(BSLDate(10009),'WithinSecond'),BSLDate(10000))
    def test_unknown_periodicity_and_recorder_rejected(self):
        for kind in ('Week','Second','RecorderPosition',''):
            with self.subTest(kind=kind),self.assertRaises(ValueError): import_configuration(periodic_files(kind))
    def test_period_field_shadow_rejected(self):
        files=periodic_files();files['InformationRegisters/Prices.xml']=files['InformationRegisters/Prices.xml'].replace(b'<Name>Item</Name>',b'<Name>Period</Name>')
        with self.assertRaises(ValueError): import_configuration(files)
    def test_invalid_period_value_and_boundary(self):
        for value in (None,Decimal(1),'20240101',BSLDate(0,True)):
            with self.subTest(value=type(value).__name__),self.assertRaises((TypeError,ValueError)): period(value,'Day')


class PeriodicRegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'periodic.sqlite'
        self.context=SQLiteDBContext.create(self.path,import_configuration(periodic_files()))
        self.addCleanup(self.context.close)
        self.output=[];self.vm=Interpreter(database_context=self.context,output=self.output.append)
        self.manager=self.vm._information_registers.get_index('Prices')
        self.schema=self.manager._schema
    def execute(self,text): self.vm.execute(text)
    def seed(self):
        self.execute('''For I=1 To 3 Do
 R=InformationRegisters.Prices.CreateRecordManager(); R.Period=Date(2024,1,I,14,20,0);
 R.Item="A"; R.Region="North"; R.Price=I*10; R.Enabled=I<>2; R.Write();
 EndDo;
 R=InformationRegisters.Prices.CreateRecordManager(); R.Period=Date(2024,1,2); R.Item="B";
 R.Region="North";R.Price=7;R.Enabled=True;R.Write();''')
    def query(self,text,when=None):
        q=BSLQuery(self.vm._catalogs,text,self.vm._documents,self.vm._information_registers)
        if when is not None:q.set_parameter('At',when)
        return q
    def test_explicit_v9_and_reopen(self):
        self.assertEqual(self.context.backend.storage_version,9)
        self.seed();self.context.close()
        with SQLiteDBContext(self.path) as ctx:
            self.assertEqual(ctx.backend.storage_version,9)
    def test_nonperiodic_still_v8(self):
        path=Path(self.temp.name)/'old.sqlite'
        ctx=SQLiteDBContext.create(path,import_configuration(register_files()))
        try:self.assertEqual(ctx.backend.storage_version,8)
        finally:ctx.close()
    def test_record_period_is_normalized_and_key_immutable(self):
        self.execute('''R=InformationRegisters.Prices.CreateRecordManager();R.Period=Date(2024,2,29,12,0,0);
 R.Item="A";R.Region="N";R.Price=5;R.Write();Message(R.Period=Date(2024,2,29));''')
        self.assertEqual(self.output,['Да'])
        with self.assertRaises(BSLRuntimeError): self.execute('R.Period=Date(2024,3,1);')
    def test_same_dimension_different_period_and_duplicate_bucket(self):
        self.seed()
        self.assertEqual(self.query('SELECT COUNT(*) AS N FROM InformationRegister.Prices').execute()._rows,((Decimal(4),),))
        with self.assertRaises(BSLRuntimeError):self.execute('''R=InformationRegisters.Prices.CreateRecordManager();R.Period=Date(2024,1,1,23,0,0);R.Item="A";R.Region="North";R.Write();''')
    def test_exact_get_and_missing_defaults(self):
        self.seed();self.execute('''K=New Structure("Item,Region","A","North");
 Message(InformationRegisters.Prices.Get(Date(2024,1,2,10,0,0),K).Price);
 Message(InformationRegisters.Prices.Get(Date(2024,2,1),K).Price);''')
        self.assertEqual(self.output,['20','0'])
    def test_first_last_complete_key(self):
        self.seed();self.execute('''K=New Structure("Item,Region","A","North");
 Message(InformationRegisters.Prices.GetLast(Date(2024,1,2,12,0,0),K).Price);
 Message(InformationRegisters.Prices.GetFirst(Date(2024,1,2,12,0,0),K).Price);''')
        self.assertEqual(self.output,['20','30'])
    def test_slices_return_one_row_per_dimension_key(self):
        self.seed();self.execute('''T=InformationRegisters.Prices.SliceLast(Date(2024,1,2));Message(T.Count());
 For Each R In T Do Message(R.Price);EndDo;''')
        self.assertEqual(self.output,['2','20','7'])
    def test_dimension_filter_before_slice(self):
        self.seed();self.execute('''T=InformationRegisters.Prices.SliceLast(Date(2024,1,3),New Structure("Item","B"));Message(T.Count());Message(T[0].Price);''')
        self.assertEqual(self.output,['1','7'])
    def test_slice_missing_and_first_after_end(self):
        self.seed();self.execute('''Message(InformationRegisters.Prices.SliceLast(Date(2023,1,1)).Count());Message(InformationRegisters.Prices.SliceFirst(Date(2025,1,1)).Count());''')
        self.assertEqual(self.output,['0','0'])
    def test_select_range_inclusive_and_not_truncated(self):
        self.seed();self.execute('''S=InformationRegisters.Prices.Select(Date(2024,1,1),Date(2024,1,2),New Structure("Item","A"));While S.Next() Do Message(S.Price);EndDo;''')
        self.assertEqual(self.output,['10','20'])
    def test_invalid_ranges_and_resource_filters(self):
        for code in ('InformationRegisters.Prices.Select(Date(2024,2,1),Date(2024,1,1));',
                     'InformationRegisters.Prices.SliceLast(Date(2024,1,1),New Structure("Price",10));'):
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError):self.execute(code)
    def test_recordset_period_filter_replaces_one_bucket(self):
        self.seed();self.execute('''S=InformationRegisters.Prices.CreateRecordSet();S.Filter.Period.Set(Date(2024,1,2,12,0,0));
 R=S.Add();R.Item="C";R.Region="North";R.Price=99;S.Write();''')
        self.assertEqual(self.query('SELECT Item,Price FROM InformationRegister.Prices ORDER BY Period').execute()._rows,
                         (('A',Decimal(10)),('C',Decimal(99)),('A',Decimal(30))))
    def test_recordset_snapshot_detects_period_scope_change(self):
        self.seed();self.execute('''S=InformationRegisters.Prices.CreateRecordSet();S.Filter.Period.Set(Date(2024,1,2));S.Read();
 R=InformationRegisters.Prices.CreateRecordManager();R.Period=Date(2024,1,2);R.Item="A";R.Region="North";R.Read();R.Price=100;R.Write();''')
        with self.assertRaises(BSLRuntimeError):self.execute('S.Write();')
    def test_delete_preserves_other_periods(self):
        self.seed();self.execute('''R=InformationRegisters.Prices.CreateRecordManager();R.Period=Date(2024,1,2);R.Item="A";R.Region="North";R.Read();R.Delete();''')
        self.assertEqual(self.query('SELECT COUNT(*) AS N FROM InformationRegister.Prices').execute()._rows,((Decimal(3),),))
    def test_query_period_projection_and_slice(self):
        self.seed();q=self.query('SELECT Item,Period,Price FROM InformationRegister.Prices.SliceLast(&At) ORDER BY Item',literal_date('20240102'))
        self.assertEqual(q.execute()._rows,(('A',literal_date('20240102'),Decimal(20)),('B',literal_date('20240102'),Decimal(7))))
    def test_query_where_is_after_edge(self):
        self.seed();q=self.query('SELECT Item,Price FROM InformationRegister.Prices.SliceLast(&At) WHERE Enabled=TRUE ORDER BY Item',literal_date('20240102'))
        self.assertEqual(q.execute()._rows,(('B',Decimal(7)),))
    def test_query_russian_first_join_group_and_package(self):
        self.seed();q=self.query('ВЫБРАТЬ СУММА(Price) КАК Total ИЗ РегистрСведений.Prices.СрезПервых(&At)',literal_date('20240102'))
        self.assertEqual(q.execute()._rows,((Decimal(27),),))
        q=self.query('SELECT Item,Price INTO T FROM InformationRegister.Prices.SliceLast(&At); SELECT COUNT(*) AS N FROM T',literal_date('20240102'))
        self.assertEqual(q.execute()._rows,((Decimal(2),),))
    def test_query_union_virtual_and_plain(self):
        self.seed();q=self.query('SELECT Price FROM InformationRegister.Prices.SliceLast(&At) UNION ALL SELECT Price FROM InformationRegister.Prices WHERE Item="B"',literal_date('20240102'))
        self.assertEqual(len(q.execute()._rows),3)
    def test_query_invalid_boundary_and_nonperiodic_virtual(self):
        for when in (Decimal(2),BSLDate(1)):
            with self.subTest(when=when),self.assertRaises((TypeError,ValueError)):
                self.query('SELECT Price FROM InformationRegister.Prices.SliceLast(&At)',when).execute()
    def test_storage_rejects_unnormalized_period(self):
        backend=self.context.backend;key=RegisterKey(backend.database_id,self.schema.identity,(datetime(2024,1,1,12),'A','N'))
        tx=backend.begin_register_write(uuid4())
        try:
            with self.assertRaises(BackendError):tx.write(RegisterDraft(key,(Decimal(1),True)))
        finally:tx.rollback();tx.close()
    def test_version_downgrade_is_not_implicit_admission(self):
        self.context.close()
        with closing(sqlite3.connect(self.path)) as c:
            c.execute('PRAGMA user_version=8');c.commit()
        with self.assertRaises(BackendError):SQLiteDBContext(self.path)
    def test_read_only_reads_and_rejects_write(self):
        self.seed();self.context.close();ctx=SQLiteDBContext(self.path);ctx.close()
        from yadinassi.sqlite_catalog import SQLiteCatalogBackend
        ctx._backend=SQLiteCatalogBackend(self.path,read_only=True)
        try:
            vm=Interpreter(database_context=ctx,output=self.output.append)
            vm.execute('Message(InformationRegisters.Prices.SliceLast(Date(2024,1,2)).Count());')
            with self.assertRaises(BSLRuntimeError):vm.execute('R=InformationRegisters.Prices.CreateRecordManager();R.Write();')
        finally:ctx.close()
    def test_query_projection_does_not_hide_corrupt_history(self):
        self.seed()
        with closing(sqlite3.connect(self.path)) as c:
            c.execute("UPDATE information_register_record SET values_json='[]' WHERE key_json=(SELECT MIN(key_json) FROM information_register_record)");c.commit()
        with self.assertRaises(BackendError):self.query('SELECT Price FROM InformationRegister.Prices.SliceLast(&At)',literal_date('20240103')).execute()
    def test_scalar_slice_rejects_fractional_boundary(self):
        with self.assertRaises(ValueError):self.manager.slice_last(BSLDate(1))
    def test_plain_and_periodic_catalog_transaction_snapshot(self):
        self.seed();q=self.query('SELECT A.Item,B.Price FROM InformationRegister.Prices.SliceFirst(&At) AS A INNER JOIN InformationRegister.Prices.SliceLast(&At) AS B ON A.Item=B.Item ORDER BY A.Item',literal_date('20240102'))
        self.assertEqual(q.execute()._rows,(('A',Decimal(20)),('B',Decimal(7))))
