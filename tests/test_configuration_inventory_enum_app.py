"""Host UI integration over explicit enum full-source grant."""
from pathlib import Path
import tempfile
import unittest
from inventory_enum_application_fixture import source
from yadinassi.configuration_inventory_enum_application import import_inventory_application, PROFILE
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.configuration_app import ConfigurationBroker,ConfigurationController,load_application,PROTOCOL
from yadinassi.ui.protocol import decode_line,encode_line
import test_configuration_inventory_app as helpers

class EnumApplicationTests(unittest.TestCase):
    rpc=helpers.InventoryApplicationTests.rpc
    open=helpers.InventoryApplicationTests.open
    event=helpers.InventoryApplicationTests.event
    choose=helpers.InventoryApplicationTests.choose
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'data.sqlite';root=Path(temp.name)/'source';root.mkdir()
        for name,raw in source().items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        config=import_inventory_application(source(),inventory_runtime=PROFILE)
        SQLiteDBContext.create_inventory_enum_application(self.path,config).close()
        forms=load_application(root,inventory_enum_application=True)
        self.broker=ConfigurationBroker(forms,self.path,inventory_enum_application=True);self.addCleanup(self.broker.close)
        def exchange(raw):
            req=decode_line(raw);result=self.broker.exchange({k:req[k] for k in ('operation','session','payload')})
            return encode_line({'id':req['id'],'session':req['session'],'result':result,'error':None})
        self.app=ConfigurationController(forms,exchange,inventory_enum_application=True);self.addCleanup(self.app.close)
        self.rpc('hello',protocol=PROTOCOL)
    def test_catalog_form_projects_enum_and_retires_owner(self):
        sid=self.open('Catalog.Products.Form.Card')
        owned=self.broker.objects[sid]
        from yadinassi.inventory_enum_runtime import binding
        enum=binding(owned._interpreter._metadata)
        value=owned.object.get_member('Unit');self.assertTrue(value.is_empty())
        server=self.broker.sessions[sid][0]
        self.assertTrue(any(type(v).__name__=='FormEnumBinding' for v in server.session.reference_scope.targets.values()))
        self.broker.exchange({'operation':'retire','session':sid,'payload':{}})
        from yadinassi.catalog_backend import BackendError
        with self.assertRaises(BackendError):enum.value_type(value.value_type.metadata_uuid)
    def test_document_form_opens_with_enum_header_and_rows(self):
        sid=self.open('Document.Receipt.Form.Card')
        owned=self.broker.objects[sid]
        self.assertTrue(owned.object.get_member('State').is_empty())
        self.assertTrue(self.broker.sessions[sid][0].session.reference_scope.server)

    def test_list_enum_choose_save_refresh_and_reopen(self):
        entry=self.app.names['catalog.products.form.card']
        self.rpc('catalog',entry=entry)
        self.assertEqual(self.app.catalog['rows'],[])
        sid=self.open('Catalog.Products.Form.Card')
        self.event(sid,'change',control='CodeInput',value='P1')
        self.event(sid,'change',control='DescriptionInput',value='Product')
        self.choose(sid,'UnitInput')
        # Choice mutates the detached form; storage/object changes only on Save.
        self.event(sid,control='SaveButton')
        self.assertFalse(self.broker.objects[sid].object.get_member('Unit').is_empty())
        self.assertEqual(len(self.app.catalog['rows']),1)
        record=self.app.catalog['rows'][0]['key']
        other=self.open('Catalog.Products.Form.Card',request='reopen',record=record)
        value=self.broker.objects[other].object.get_member('Unit')
        self.assertFalse(value.is_empty())
        self.assertEqual(str(value),str(self.broker.objects[sid].object.get_member('Unit')))
        report=self.rpc('report',report='StockBalance',at='2026-11-12T00:00:00',start=None,end=None)['state']['report']
        self.assertEqual(report['rows'],[])

    def test_summary_projection_preserves_schema_bounds(self):
        example=Path(__file__).resolve().parents[1]/"examples/configuration-inventory-enum-application"
        self.assertEqual({p.relative_to(example).as_posix():p.read_bytes() for p in example.rglob("*") if p.is_file()},source())
        from dataclasses import replace
        from yadinassi.ui.catalog_view import CatalogRepository
        from yadinassi.ui.protocol import UIError
        schema=next(d.catalog_schema for d in self.broker.definitions.values() if d.catalog_schema is not None)
        for forged in (replace(schema,code_length=True),replace(schema,description_length=1025),
                       replace(schema,fields=list(schema.fields)),replace(schema,fields=schema.fields*65)):
            with self.assertRaises(UIError):CatalogRepository._summary_fields(forged)

    def test_document_enum_header_rows_post_unpost_reopen_and_reports(self):
        from decimal import Decimal
        for name,code in (('Products','P1'),('Warehouses','W1')):
            sid=self.open('Catalog.'+name+'.Form.Card')
            self.event(sid,'change',control='CodeInput',value=code)
            self.event(sid,'change',control='DescriptionInput',value=name)
            if name=='Products':self.choose(sid,'UnitInput')
            self.event(sid,control='SaveButton')
        entry=self.app.names['document.receipt.form.card'];self.rpc('catalog',entry=entry)
        sid=self.open('Document.Receipt.Form.Card')
        self.event(sid,'change',control='NumberInput',value='R1')
        self.choose(sid,'WarehouseInput');self.choose(sid,'StateInput')
        self.event(sid,control='AddLineButton')
        table=next(i for i in self.app.sessions[sid][0]._snapshot()['items'] if i['kind']=='table')
        row=table['rows'][0]['id']
        self.choose(sid,'LinesTable',row,'Product');self.choose(sid,'LinesTable',row,'Unit')
        self.event(sid,'cell',control='LinesTable',row=row,column='Quantity',value=Decimal(2))
        self.event(sid,'cell',control='LinesTable',row=row,column='Amount',value=Decimal(10))
        self.event(sid,control='WriteButton')
        self.assertEqual(len(self.app.catalog['rows']),1)
        record=self.app.catalog['rows'][0]['key']
        self.event(sid,control='PostButton')
        self.assertTrue(self.broker.objects[sid].object.get_member('Posted'))
        report=self.rpc('report',report='StockMovements',at=None,start=None,end=None)['state']['report']
        self.assertEqual(len(report['rows']),1)
        values=dict(zip((c['name'] for c in report['columns']),report['rows'][0]))
        self.assertEqual(values['Unit'],{'type':'String','value':'Piece'})
        self.assertEqual(values['State'],{'type':'String','value':'Draft'})
        other=self.open('Document.Receipt.Form.Card',request='posted-reopen',record=record)
        self.assertTrue(self.broker.objects[other].object.get_member('Posted'))
        self.assertFalse(self.broker.objects[other].object.get_member('State').is_empty())
        self.event(other,control='UndoPostingButton')
        self.assertFalse(self.broker.objects[other].object.get_member('Posted'))
        report=self.rpc('report',report='StockMovements',at=None,start=None,end=None)['state']['report']
        self.assertEqual(report['rows'],[])
