"""Owned register contract; fixtures are authored XML, not native evidence."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.register_backend import RegisterDraft, RegisterKey, RegisterScanRequest, RegisterSetDraft
from yadinassi.sqlite_registers import RegisterView
from sqlite_catalog_fixture import configuration_files


def register_files(*, catalogs=True):
    files=configuration_files();config=files['Configuration.xml']
    if not catalogs:
        config=config.replace(b'<Catalog>Categories</Catalog><Catalog>Products</Catalog>',b'');files={}
    files['Configuration.xml']=config.replace(b'</ChildObjects>',b'<InformationRegister>Prices</InformationRegister></ChildObjects>')
    prefix=config.split(b'<Configuration ')[0].decode()
    def field(kind,name,typexml):
        return f'<{kind} uuid="{uuid4()}"><Properties><Name>{name}</Name><Type>{typexml}</Type></Properties></{kind}>'
    text='<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>30</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'
    number='<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>12</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>'
    children=field('Dimension','Item',text)+field('Dimension','Region',text)+field('Resource','Price',number)+field('Attribute','Enabled','<v8:Type>xs:boolean</v8:Type>')
    files['InformationRegisters/Prices.xml']=(prefix+f'<InformationRegister uuid="{uuid4()}"><Properties><Name>Prices</Name><InformationRegisterPeriodicity>Nonperiodical</InformationRegisterPeriodicity><WriteMode>Independent</WriteMode></Properties><ChildObjects>{children}</ChildObjects></InformationRegister></MetaDataObject>').encode()
    return files


class RegisterXMLTests(unittest.TestCase):
    def test_register_only_profile_and_inventory(self):
        result=import_configuration(register_files(catalogs=False))
        self.assertFalse(result.activation_issues);self.assertEqual(result.catalogs,())
        schema,=result.information_registers
        self.assertEqual(tuple(f.name for f in schema.fields),('Item','Region','Price','Enabled'))
    def test_periodic_and_recorder_fail_closed(self):
        for old,new in ((b'Nonperiodical',b'Second'),(b'Independent',b'RecorderSubordinate')):
            files=register_files();files['InformationRegisters/Prices.xml']=files['InformationRegisters/Prices.xml'].replace(old,new)
            with self.subTest(new=new),self.assertRaises(ValueError): import_configuration(files)
    def test_unknown_behavior_and_module_are_inactive(self):
        files=register_files();files['InformationRegisters/Prices.xml']=files['InformationRegisters/Prices.xml'].replace(b'<WriteMode>',b'<CustomBehavior>true</CustomBehavior><WriteMode>')
        self.assertTrue(import_configuration(files).activation_issues)
        files=register_files();files['InformationRegisters/Prices/Ext/RecordSetModule.bsl']=b'Procedure BeforeWrite() EndProcedure'
        self.assertTrue(import_configuration(files).activation_issues)
    def test_casefold_duplicate_field_and_empty_dimension_rejected(self):
        files=register_files();files['InformationRegisters/Prices.xml']=files['InformationRegisters/Prices.xml'].replace(b'<Name>Region</Name>',b'<Name>ITEM</Name>')
        with self.assertRaises(ValueError): import_configuration(files)
        files=register_files();files['InformationRegisters/Prices.xml']=files['InformationRegisters/Prices.xml'].replace(b'<Dimension ',b'<Attribute ').replace(b'</Dimension>',b'</Attribute>')
        with self.assertRaises(ValueError): import_configuration(files)
    def test_unqualified_register_semantics_rejected(self):
        for tag in ('WriteMode','InformationRegisterPeriodicity'):
            import re
            files=register_files();files['InformationRegisters/Prices.xml']=re.sub(f'<{tag}>.*?</{tag}>'.encode(),b'',files['InformationRegisters/Prices.xml'])
            with self.subTest(tag=tag),self.assertRaises(ValueError): import_configuration(files)


class InformationRegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'app.sqlite'
        self.imported=import_configuration(register_files());self.schema=self.imported.information_registers[0]
        self.context=SQLiteDBContext.create(self.path,self.imported)
        self.lines=[];self.vm=Interpreter(database_context=self.context,output=self.lines.append)
    def tearDown(self): self.context.close();self.temp.cleanup()
    def execute(self,code): self.lines.clear();self.vm.execute(code);return self.lines[:]
    def seed(self):
        self.execute('R=InformationRegisters.Prices.CreateRecordManager();R.Item="A";R.Region="North";R.Price=12.50;R.Enabled=True;R.Write();')
    def key(self,item='A',region='North'): return RegisterKey(self.context.backend.database_id,self.schema.identity,(item,region))
    def draft(self,item='A',region='North',price='12.50'): return RegisterDraft(self.key(item,region),(Decimal(price),True))
    def sql(self,query,args=()):
        with closing(sqlite3.connect(self.path)) as c,c: return c.execute(query,args).fetchall()
    def test_record_roundtrip_update_get_and_delete(self):
        self.seed()
        self.assertEqual(self.execute('Message(R.Selected());R.Price=15;R.Write();S=InformationRegisters.Prices.Get(New Structure("Item,Region","A","North"));Message(S.Price);R.Delete();Message(R.Selected());R.Read();Message(R.Price);'),['Да','15','Нет','0'])
    def test_russian_aliases_and_metadata_types(self):
        self.assertEqual(self.execute('Р=РегистрыСведений.Prices.СоздатьМенеджерЗаписи();Р.Item="Б";Р.Region="В";Р.Price=4;Р.Записать();Р.Прочитать();Сообщить(Р.Выбран());Сообщить(Метаданные.РегистрыСведений.Prices.ПолноеИмя());Сообщить(ТипЗнч(Р)=Тип("РегистрСведенийМенеджерЗаписи.Prices"));'),['Да','РегистрСведений.Prices','Да'])
    def test_select_detached_filter_and_reopen(self):
        self.seed();self.execute('S=InformationRegisters.Prices.Select(New Structure("Region","North"));R.Price=22;R.Write();')
        self.assertEqual(self.execute('Message(S.Next());Message(S.Price);Message(S.Next());'),['Да','12,5','Нет'])
        self.context.close();self.context=SQLiteDBContext(self.path);self.vm=Interpreter(database_context=self.context,output=self.lines.append)
        self.assertEqual(self.execute('Message(InformationRegisters.Prices.Get(New Structure("Item,Region","A","North")).Price);'),['22'])
    def test_read_missing_preserves_key_and_clears_values(self):
        self.assertEqual(self.execute('R=InformationRegisters.Prices.CreateRecordManager();R.Item="missing";R.Price=33;R.Read();Message(R.Item);Message(R.Price);Message(R.Selected());'),['missing','0','Нет'])
    def test_duplicate_requires_explicit_read(self):
        self.seed()
        with self.assertRaises(BSLRuntimeError): self.execute('Q=InformationRegisters.Prices.CreateRecordManager();Q.Item="A";Q.Region="North";Q.Write();')
        self.assertEqual(self.execute('Q.Read();Q.Price=99;Q.Write();Message(Q.Price);'),['99'])
    def test_selected_key_immutable_until_clear(self):
        self.seed()
        with self.assertRaises(BSLRuntimeError): self.execute('R.Item="B";')
        self.execute('R.Clear();R.Item="B";R.Region="North";R.Write();')
        self.assertEqual(len(self.sql('SELECT * FROM information_register_record')),2)
    def test_stale_revision_and_delete_reinsert_aba(self):
        self.seed();v=self.context.backend.begin_register_read()
        try:old=v.read_record(self.key())
        finally:v.close()
        self.execute('R.Delete();R.Write();')
        tx=self.context.backend.begin_register_write(uuid4())
        try:
            with self.assertRaises(BackendError): tx.write(self.draft(),old.revision)
        finally:tx.close()
    def test_recordset_filtered_replace_preserves_outside(self):
        self.seed();self.execute('R.Clear();R.Item="B";R.Region="South";R.Price=8;R.Write();')
        self.assertEqual(self.execute('S=InformationRegisters.Prices.CreateRecordSet();S.Filter.Region.Set("North");X=S.Add();X.Item="C";X.Price=44;S.Write();S.Read();Message(S.Count());Message(S.Get(0).Item);Message(TypeOf(S)=Type("InformationRegisterRecordSet.Prices"));'),['1','C','Да'])
        self.assertEqual(self.execute('For Each X In S Do Message(X.Item); EndDo;'),['C'])
        with self.assertRaises(BSLRuntimeError):self.execute('S[0]=Undefined;')
        self.assertEqual(len(self.sql('SELECT * FROM information_register_record')),2)
    def test_recordset_empty_replace_deletes_scope(self):
        self.seed();self.execute('S=InformationRegisters.Prices.CreateRecordSet();S.Filter.Region.Set("North");S.Write();')
        self.assertEqual(self.sql('SELECT * FROM information_register_record'),[])
    def test_unfiltered_replace_requires_read(self):
        self.seed();self.execute('S=InformationRegisters.Prices.CreateRecordSet();')
        with self.assertRaises(BSLRuntimeError):self.execute('S.Write();')
        self.execute('S.Read();S.Clear();S.Write();')
        self.assertEqual(self.sql('SELECT * FROM information_register_record'),[])
    def test_recordset_append_and_duplicate_atomic(self):
        self.seed();self.execute('S=InformationRegisters.Prices.CreateRecordSet();X=S.Add();X.Item="B";X.Region="South";X.Price=7;S.Write(False);')
        self.execute('S.Clear();X=S.Add();X.Item="C";X.Region="South";X=S.Add();X.Item="A";X.Region="North";')
        with self.assertRaises(BSLRuntimeError):self.execute('S.Write(False);')
        self.assertEqual(len(self.sql('SELECT * FROM information_register_record')),2)
    def test_recordset_scope_mismatch_rolls_back(self):
        self.seed();self.execute('S=InformationRegisters.Prices.CreateRecordSet();S.Filter.Region.Set("North");X=S.Add();X.Item="B";X.Region="South";')
        with self.assertRaises(BSLRuntimeError):self.execute('S.Write();')
        self.assertEqual(len(self.sql('SELECT * FROM information_register_record')),1)
    def test_recordset_read_stale_conflict(self):
        self.seed();self.execute('S=InformationRegisters.Prices.CreateRecordSet();S.Filter.Region.Set("North");S.Read();R.Price=66;R.Write();')
        with self.assertRaises(BSLRuntimeError):self.execute('S.Write();')
        self.assertEqual(self.execute('S.Read();Message(S[0].Price);'),['66'])
    def test_recordset_rows_detach_and_filter_change_guard(self):
        self.execute('S=InformationRegisters.Prices.CreateRecordSet();X=S.Add();')
        with self.assertRaises(BSLRuntimeError):self.execute('S.Filter.Region.Set("North");')
        self.execute('S.Clear();')
        with self.assertRaises(BSLRuntimeError):self.execute('X.Price=3;')
        self.execute('S.Filter.Region.Set("North");')
    def test_read_only_can_read_but_not_write(self):
        self.seed();self.context.close();self.context._backend=__import__('yadinassi.sqlite_catalog',fromlist=['SQLiteCatalogBackend']).SQLiteCatalogBackend(self.path,read_only=True);self.vm=Interpreter(database_context=self.context,output=self.lines.append)
        self.assertEqual(self.execute('R=InformationRegisters.Prices.CreateRecordManager();R.Item="A";R.Region="North";R.Read();Message(R.Price);'),['12,5'])
        with self.assertRaises(BSLRuntimeError):self.execute('R.Write();')
    def test_scan_page_tokens_and_complete_rows(self):
        self.seed();self.execute('R.Clear();R.Item="B";R.Region="North";R.Write();')
        v=self.context.backend.begin_register_read()
        try:
            first=v.scan_register(self.schema.identity,RegisterScanRequest(1))
            self.assertEqual(len(first.rows),1);self.assertIsNotNone(first.continuation)
            last=v.scan_register(self.schema.identity,RegisterScanRequest(1,first.continuation))
            self.assertEqual(len(last.rows),1);self.assertIsNone(last.continuation)
            with self.assertRaises(BackendError):v.scan_register(self.schema.identity,RegisterScanRequest(1,first.continuation))
        finally:v.close()
    def test_uncertain_record_receipt_recovery_freezes_buffer(self):
        self.execute('R=InformationRegisters.Prices.CreateRecordManager();R.Item="A";R.Region="North";R.Price=3;')
        original=RegisterView.commit
        def lost(view):original(view);raise OSError('lost acknowledgement')
        with patch.object(RegisterView,'commit',lost),self.assertRaises(BSLRuntimeError):self.execute('R.Write();')
        with self.assertRaises(BSLRuntimeError):self.execute('R.Price=4;')
        self.assertEqual(self.execute('R.Write();Message(R.Selected());Message(R.Price);'),['Да','3'])
        self.assertEqual(len(self.sql('SELECT * FROM information_register_record')),1)
    def test_uncertain_set_receipt_recovery(self):
        self.execute('S=InformationRegisters.Prices.CreateRecordSet();S.Filter.Region.Set("North");X=S.Add();X.Item="A";X.Price=5;')
        original=RegisterView.commit
        def lost(view):original(view);raise OSError('lost acknowledgement')
        with patch.object(RegisterView,'commit',lost),self.assertRaises(BSLRuntimeError):self.execute('S.Write();')
        with self.assertRaises(BSLRuntimeError):self.execute('S.Clear();')
        self.execute('S.Write();S.Read();')
        self.assertEqual(self.execute('Message(S.Count());Message(S[0].Price);'),['1','5'])
    def test_recordset_duplicate_dimension_keys_are_rejected(self):
        self.execute('S=InformationRegisters.Prices.CreateRecordSet();S.Filter.Region.Set("North");X=S.Add();X.Item="A";X=S.Add();X.Item="A";')
        with self.assertRaises(BSLRuntimeError):self.execute('S.Write();')
        self.assertEqual(self.sql('SELECT * FROM information_register_record'),[])
    def test_dimension_types_and_scalar_qualifiers(self):
        self.execute('R=InformationRegisters.Prices.CreateRecordManager();')
        for code in ('R.Item=1;','R.Price="bad";','R.Enabled=1;'):
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError):self.execute(code)
        self.assertEqual(self.execute('R.Item="'+('x'*40)+'";R.Price=1.236;Message(StrLen(R.Item));Message(R.Price);'),['30','1,24'])
    def test_numeric_dimension_signed_zero_has_one_identity(self):
        from yadinassi.catalog_backend import FieldSchema
        files=register_files();config=import_configuration(files)
        schema=config.information_registers[0]
        dimension=replace(schema.dimensions[0],kind='number',qualifiers=(12,2,'Any'))
        schema=replace(schema,dimensions=(dimension,schema.dimensions[1]))
        config=replace(config,information_registers=(schema,))
        path=Path(self.temp.name)/'numeric.sqlite';context=SQLiteDBContext.create(path,config)
        try:
            b=context.backend
            key=lambda n:RegisterKey(b.database_id,schema.identity,(Decimal(n),'North'))
            tx=b.begin_register_write(uuid4());tx.write(RegisterDraft(key('-0'),(Decimal(1),True)));tx.commit()
            view=b.begin_register_read()
            try:
                self.assertIsNotNone(view.read_record(key('0.00')))
                self.assertEqual(len(view.select_records(schema.identity,((dimension.identity,Decimal('0')),))),1)
                self.assertEqual(len(view.select_records(schema.identity,((dimension.identity,Decimal('-0.00')),))),1)
            finally:view.close()
            tx=b.begin_register_write(uuid4())
            try:
                with self.assertRaises(BackendError):tx.write(RegisterDraft(key('0'),(Decimal(2),True)))
            finally:tx.close()
        finally:context.close()

    def test_corrupt_unselected_record_is_detected(self):
        self.seed();self.sql("UPDATE information_register_record SET values_json='[]'")
        with self.assertRaises(BSLRuntimeError): self.execute('S=InformationRegisters.Prices.Select(New Structure("Region","absent"));')
    def test_native_dynamic_codecs_remain_closed(self):
        self.execute('R=InformationRegisters.Prices.CreateRecordManager();')
        for code in ('Message(ValueToStringInternal(R));','T=New TypeDescription("InformationRegisterRecordManager.Prices");'):
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError):self.execute(code)
