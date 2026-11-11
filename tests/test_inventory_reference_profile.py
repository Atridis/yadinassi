"""Closed authored storage/host guards; NOT native reference parity evidence."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from uuid import UUID

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.accumulation_movements import validate_schema
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_accumulation import import_accumulation_configuration, PROFILE as SCALAR
from yadinassi.configuration_accumulation_references import (PROFILE, canonical,
    import_inventory_configuration)
from yadinassi.configuration_profile_import import prepare_files, create_prepared
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_accumulation_movements import schema_data
from test_configuration_accumulation import wrap, field, document, value_type

ROOT = Path(__file__).resolve().parents[1]
REG = 'AccumulationRegisters/Stock.xml'
DOC = 'Documents/Receipt.xml'
MODULE = 'Documents/Receipt/Ext/ObjectModule.bsl'


def ref_field(category, identity, name, target):
    return field(category, identity, name, 'reference').replace('CatalogRef.Products', 'CatalogRef.' + target)


def source():
    files = {'Configuration.xml': wrap('Configuration', 1000, '<Name>Inventory</Name>',
        '<Catalog>Products</Catalog><Catalog>Warehouses</Catalog><Document>Receipt</Document>'
        '<Document>Issue</Document><AccumulationRegister>Stock</AccumulationRegister>')}
    for name, identity in (('Products', 1010), ('Warehouses', 1020)):
        files['Catalogs/' + name + '.xml'] = wrap('Catalog', identity,
            '<Name>' + name + '</Name><CodeType>String</CodeType><CodeLength>9</CodeLength>'
            '<CodeAllowedLength>Variable</CodeAllowedLength><DescriptionLength>80</DescriptionLength>'
            '<CheckUnique>true</CheckUnique><Hierarchical>false</Hierarchical><Autonumbering>false</Autonumbering>')
    for name, identity, base in (('Receipt', 1030, 1100), ('Issue', 1040, 1200)):
        raw = document(name, identity, base).replace(b'AccumulationRegister.Rows', b'AccumulationRegister.Stock')
        children = ref_field('Attribute', identity+1, 'Warehouse', 'Warehouses')
        children += (f'<TabularSection uuid="{UUID(int=identity+2)}"><Properties><Name>Lines</Name></Properties><ChildObjects>'
            + ref_field('Attribute', identity+3, 'Product', 'Products')
            + field('Attribute', identity+4, 'Quantity') + field('Attribute', identity+5, 'Amount')
            + '</ChildObjects></TabularSection>')
        files['Documents/'+name+'.xml'] = raw.replace(b'<ChildObjects></ChildObjects>', ('<ChildObjects>'+children+'</ChildObjects>').encode())
        direction = 'Receipt' if name == 'Receipt' else 'Expense'
        files['Documents/'+name+'/Ext/ObjectModule.bsl'] = ('''
Procedure Posting(Cancel, PostingMode)
    RegisterRecords.Stock.Clear();
    RegisterRecords.Stock.Write = True;
    For Each Line In Lines Do
        R = RegisterRecords.Stock.Add();
        R.Period = Date; R.RecordType = AccumulationRecordType.%s;
        R.Product = Line.Product; R.Warehouse = Warehouse;
        R.Quantity = Line.Quantity; R.Amount = Line.Amount; R.Note = "posted";
    EndDo;
EndProcedure
''' % direction).encode()
    files[REG] = wrap('AccumulationRegister', 1050,
        '<Name>Stock</Name><RegisterType>Balance</RegisterType><EnableTotalsSplitting>false</EnableTotalsSplitting>',
        ref_field('Dimension', 1051, 'Product', 'Products') + ref_field('Dimension', 1052, 'Warehouse', 'Warehouses')
        + field('Resource', 1053, 'Quantity') + field('Resource', 1054, 'Amount') + field('Attribute', 1055, 'Note', 'string'))
    return files


def imported(files=None):
    return import_inventory_configuration(source() if files is None else files, inventory_runtime=PROFILE)


class InventorySourceTests(unittest.TestCase):
    def test_closed_grant(self):
        with self.assertRaises(ValueError): import_inventory_configuration(source())
        self.assertEqual(canonical(imported()), imported())
    def test_scalar_source_does_not_accept_inventory(self):
        with self.assertRaises(ValueError): import_accumulation_configuration(source(), accumulation_runtime=SCALAR)
    def test_source_and_value_profile_are_distinct(self):
        config = imported(); self.assertEqual(config.profile, PROFILE)
        self.assertEqual(config.registers[0].value_profile, 'catalog_reference_v1')
        self.assertEqual(len(config.catalogs), 2)
        self.assertEqual(config.documents[0].fields[0].target_catalog_id, config.catalogs[1].identity)
    def test_scalar_schema_rejects_reference_fields(self):
        with self.assertRaises(BackendError): validate_schema(replace(imported().registers[0], value_profile='scalar_v1'))
    def test_reference_schema_serialization_preserves_target(self):
        data = schema_data(imported().registers[0])
        self.assertEqual(data[0], 'accumulation_reference_v1')
        self.assertEqual(data[5][0][-1], str(imported().catalogs[0].identity))
    def test_forged_target_canonical_refused(self):
        c = imported(); r = c.registers[0]
        r = replace(r, dimensions=(replace(r.dimensions[0],target_catalog_id=UUID(int=99)), *r.dimensions[1:]))
        with self.assertRaises(ValueError): canonical(replace(c,registers=(r,)))
    def test_missing_target_refused(self):
        files = source(); files[REG] = files[REG].replace(b'CatalogRef.Products', b'CatalogRef.Unknown')
        with self.assertRaises(ValueError): imported(files)
    def test_enum_target_not_granted(self):
        files = source(); files[REG] = files[REG].replace(b'CatalogRef.Products', b'EnumRef.Products')
        with self.assertRaises(ValueError): imported(files)
    def test_numeric_resource_required(self):
        files = source(); files[REG] = files[REG].replace(value_type('number').encode(), value_type('reference').encode(), 1)
        with self.assertRaises(ValueError): imported(files)
    def test_no_catalog_modules_or_forms(self):
        for path in ('Catalogs/Products/Ext/ObjectModule.bsl', 'Forms/Order.xml'):
            files = source(); files[path] = b''
            with self.subTest(path=path), self.assertRaises(ValueError): imported(files)
    def test_no_catalog_sections(self):
        files = source(); path = 'Catalogs/Products.xml'
        files[path] = files[path].replace(b'<ChildObjects>', b'<ChildObjects><TabularSection/>')
        with self.assertRaises(ValueError): imported(files)
    def test_profile_report_and_precise_catalog_count(self):
        p = prepare_files(source(), profile=PROFILE)
        self.assertEqual((p.format_version,p.report()['catalogs'],p.report()['documents'],p.report()['registers']), (15,2,2,1))


class InventoryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'inventory.sqlite'
        self.config = imported()
        self.context = SQLiteDBContext.create_inventory(self.path,self.config); self.addCleanup(self.context.close)
        self.backend = self.context.backend
        self.vm = Interpreter(database_context=self.context,output=lambda text:None); self.addCleanup(self.vm.close)
    def sql(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute(sql,args).fetchall()
    def seed(self):
        self.vm.execute('P=Catalogs.Products.CreateItem(); P.Code="1"; P.Description="Product"; P.Write();'
                        'W=Catalogs.Warehouses.CreateItem(); W.Code="1"; W.Description="Warehouse"; W.Write();')
    def document(self, name='Receipt', number='1', quantity=10):
        self.vm.execute(f'D=Documents.{name}.CreateDocument(); D.Number="{number}"; D.Date=Date(2024,1,1);'
                        f'D.Warehouse=W.Ref; L=D.Lines.Add(); L.Product=P.Ref; L.Quantity={quantity}; L.Amount=25;'
                        'D.Write(DocumentWriteMode.Posting);')
        return self.vm.execute('D')
    def rows(self,obj):
        return self.backend.read_accumulation(self.config.registers[0].identity,obj._key).rows
    def query(self,text):
        self.vm.execute('Q=New Query("'+text.replace('"','""')+'"); Q.SetParameter("At",Date(2024,1,2));')
        return self.vm.execute('Q.Execute().Unload()')
    def test_distinct_format_and_reopen(self):
        self.assertEqual((self.backend.format_version,self.backend.storage_version),(15,7))
        with closing(SQLiteCatalogBackend(self.path)) as backend:
            self.assertEqual(backend.accumulation_configuration,self.config)
    def test_fresh_prepared_creation(self):
        with closing(create_prepared(Path(self.temp.name)/'other.sqlite',prepare_files(source(),profile=PROFILE))) as context:
            self.assertEqual(context.backend.format_version,15)
    def test_marker_cannot_downgrade_to_scalar(self):
        self.sql('PRAGMA user_version=14')
        with self.assertRaises(BackendError): SQLiteCatalogBackend(self.path)
    def test_source_tamper_even_same_generation(self):
        self.sql("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'",('0'*64,))
        with self.assertRaises(BackendError): self.backend.begin_read()
    def test_reference_schema_tag_tamper(self):
        self.sql("UPDATE accumulation_register_schema SET definition=replace(definition,'accumulation_reference_v1','accumulation_scalar_v1')")
        with self.assertRaises(BackendError): self.backend.begin_read()
    def test_catalog_source_projection_tamper(self):
        raw = json.loads(self.sql('SELECT definition FROM catalog_schema ORDER BY identity')[0][0]); raw[3] = 81
        self.sql('UPDATE catalog_schema SET definition=? WHERE identity=?',(json.dumps(raw,separators=(',',':')),raw[0]))
        with self.assertRaises(BackendError): SQLiteCatalogBackend(self.path)
    def test_receipt_issue_reference_rows(self):
        self.seed(); receipt=self.document(); issue=self.document('Issue','2',3)
        self.assertEqual(self.rows(receipt)[0].dimensions[0].record_id,self.vm.execute('P')._key.record_id)
        self.assertEqual(self.rows(issue)[0].resources[0],Decimal(3))
        self.assertTrue(self.backend.read_document_posted(receipt._key))
    def test_reference_defaults_are_typed_empty(self):
        self.vm.execute('D=Documents.Receipt.CreateDocument(); L=D.Lines.Add(); R=D.RegisterRecords.Stock.Add();')
        self.assertTrue(self.vm.execute('D.Warehouse').is_empty())
        self.assertTrue(self.vm.execute('L.Product').is_empty())
        self.assertTrue(self.vm.execute('R.Product').is_empty())
    def test_wrong_catalog_host_guard(self):
        self.seed(); self.vm.execute('D=Documents.Receipt.CreateDocument();')
        with self.assertRaises(BSLRuntimeError): self.vm.execute('D.Warehouse=P.Ref;')
    def test_reference_join_balance(self):
        self.seed(); self.document(); self.document('Issue','2',3)
        table=self.query('SELECT P.Description AS Product, B.QuantityBalance AS Quantity FROM '
            'AccumulationRegister.Stock.Balance(&At) AS B INNER JOIN Catalog.Products AS P ON B.Product=P.Ref')
        self.assertEqual(len(table.rows),1); self.assertEqual(table.get_index(Decimal(0)).get_member('Quantity'),Decimal(7))
    def test_rename_does_not_change_group(self):
        self.seed(); self.document(); self.vm.execute('P.Description="Renamed"; P.Write();')
        table=self.query('SELECT B.QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&At) AS B')
        self.assertEqual(len(table.rows),1); self.assertEqual(table.get_index(Decimal(0)).get_member('Quantity'),Decimal(10))
    def test_unpost_removes_only_own_partition(self):
        self.seed(); receipt=self.document(); issue=self.document('Issue','2',3)
        self.vm.execute('D.Write(DocumentWriteMode.UndoPosting);')
        self.assertEqual(self.rows(issue),()); self.assertEqual(len(self.rows(receipt)),1)
    def test_orphan_movement_detected(self):
        self.seed(); obj=self.document()
        table=self.backend._layout.table_name(self.config.catalogs[0].identity)
        self.sql('DELETE FROM "'+table+'"')
        with self.assertRaises(BackendError): self.rows(obj)
    def test_orphan_document_detected(self):
        self.seed(); self.document()
        self.vm.execute('D.Ref.GetObject(); D.Ref.GetObject();')
        table=self.backend._layout.table_name(self.config.catalogs[1].identity)
        self.sql('DELETE FROM "'+table+'"')
        with self.assertRaises(BSLRuntimeError): self.vm.execute('D.Ref.GetObject()')
    def test_outer_transaction_catalog_and_post_rollback(self):
        self.vm.execute('BeginTransaction();'
            'P=Catalogs.Products.CreateItem(); P.Code="1"; P.Description="Product"; P.Write();'
            'W=Catalogs.Warehouses.CreateItem(); W.Code="1"; W.Description="Warehouse"; W.Write();'
            'D=Documents.Receipt.CreateDocument(); D.Number="1"; D.Date=Date(2024,1,1);'
            'D.Warehouse=W.Ref; L=D.Lines.Add(); L.Product=P.Ref; L.Quantity=10; L.Amount=25;'
            'D.Write(DocumentWriteMode.Posting); RollbackTransaction();')
        obj=self.vm.execute('D')
        self.assertEqual(self.rows(obj),())
        for table in ('document_record','accumulation_movement','unit_of_work_receipt'):
            self.assertEqual(self.sql('SELECT COUNT(*) FROM '+table),[(0,)])
    def test_no_migration_admission(self):
        from yadinassi.sqlite_migration_plan import prepare
        with self.assertRaises(BackendError): prepare(self.path,maintenance=True)
