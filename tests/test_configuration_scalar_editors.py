"""Real separate-process scalar form edits and independently read typed storage."""
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import unittest

import test_configuration_reference_app as reference_tests
from yadinassi.catalogs import BSLCatalogs
from yadinassi.configuration_reference_profile import import_reference_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.dates import BSLDate, date
from yadinassi.document_backend import DocumentSelection
from yadinassi.documents import BSLDocuments
from yadinassi.metadata import BSLMetadata, BSLCatalogMetadataCollection
from yadinassi.ui.configuration_app import ConfigurationProcess, ConfigurationController, PROTOCOL, load_application
from yadinassi.ui.protocol import encode_value

ROOT = Path(__file__).resolve().parents[1]/'examples/configuration-scalar-editors'
def sources(): return {p.relative_to(ROOT).as_posix():p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}


class ScalarEditorProfileTests(unittest.TestCase):
    def test_example_uses_existing_datetime_storage_admission_only(self):
        files=sources();imported=import_reference_configuration(files)
        order=imported.documents[0]
        delivery=next(field for field in order.tabular_sections[0].fields if field.name=='DeliveryDate')
        self.assertEqual(delivery.kind,'datetime')
        for parts in (b'Date',b'Time'):
            changed=dict(files)
            changed['Documents/Orders.xml']=files['Documents/Orders.xml'].replace(
                b'<v8:DateFractions>DateTime</v8:DateFractions>',b'<v8:DateFractions>'+parts+b'</v8:DateFractions>')
            with self.subTest(parts=parts):
                with self.assertRaises(ValueError): import_reference_configuration(changed)


class ScalarEditorOwnedProcessTests(unittest.TestCase):
    setup_application=reference_tests.ReferenceApplicationTests.setup_application
    rpc=reference_tests.ReferenceApplicationTests.rpc
    open=reference_tests.ReferenceApplicationTests.open
    event=reference_tests.ReferenceApplicationTests.event

    def setUp(self): self.setup_application(sources())

    def item(self,sid,name): return next(i for i in self.app.sessions[sid][0]._snapshot()['items'] if i['name']==name)

    def product(self):
        sid=self.open('Catalog.Products.Form.Card')
        self.event(sid,'change',control='CodeInput',value=encode_value('P2'))
        self.event(sid,'change',control='DescriptionInput',value=encode_value('Scalar editor product'))
        return sid

    def test_catalog_datetime_persists_exactly_without_timezone_conversion(self):
        sid=self.product();value=date(Decimal(2024),Decimal(2),Decimal(29),Decimal(23),Decimal(45),Decimal(17))
        projected=self.item(sid,'AvailableDateInput')
        self.assertEqual(projected['editor'],{'kind':'date','parts':'dateTime'})
        self.assertIs(type(projected['controlId']),int)
        self.event(sid,'change',control='AvailableDateInput',value=encode_value(value))
        self.event(sid,'command',control='SaveButton')
        with closing(SQLiteDBContext(self.path)) as context:
            manager=BSLCatalogs(BSLCatalogMetadataCollection(context),context).get_index('Products')
            item=manager._get_object(manager.find_by_code('P2'))
            self.assertEqual(item.get_member('AvailableDate'),value)

    def test_document_header_line_and_empty_date_survive_restart(self):
        sid=self.open('Document.Orders.Form.Card')
        stamp=date(Decimal(2025),Decimal(3),Decimal(30),Decimal(1),Decimal(59),Decimal(59))
        delivery=date(Decimal(2025),Decimal(10),Decimal(26),Decimal(2),Decimal(30),Decimal(0))
        self.event(sid,'change',control='DateInput',value=encode_value(stamp))
        self.event(sid,'command',control='NewLineButton')
        grid=self.item(sid,'LinesTable');row=grid['rows'][0]['id']
        column=next(c for c in grid['columns'] if c['name']=='DeliveryDate')
        self.assertEqual(column['editor'],{'kind':'date','parts':'dateTime'})
        self.event(sid,'cell',control='LinesTable',row=row,column='DeliveryDate',value=encode_value(delivery))
        self.event(sid,'cell',control='LinesTable',row=row,column='Quantity',value=encode_value(Decimal('3.25')))
        self.event(sid,'command',control='NewLineButton')
        empty_row=self.item(sid,'LinesTable')['rows'][1]['id']
        self.event(sid,'cell',control='LinesTable',row=empty_row,column='DeliveryDate',value=encode_value(BSLDate(0)))
        self.event(sid,'command',control='WriteButton')
        for opened in list(self.app.sessions): self.event(opened,'close')
        self.rpc('close');self.app.close();self.process.close()
        with closing(SQLiteDBContext(self.path)) as context:
            metadata=BSLMetadata(context);catalogs=BSLCatalogs(metadata._catalogs,context)
            manager=BSLDocuments(metadata._documents,context,catalogs).get_index('Orders')
            view=manager._view()
            try:
                card=view.select_documents(manager._schema.identity,DocumentSelection())[0]
                stored=view.read_document(card.key)
            finally:view.close()
            self.assertEqual(stored.date,datetime(2025,3,30,1,59,59))
            schema=manager._schema.tabular_sections[0];index=next(i for i,f in enumerate(schema.fields) if f.name=='DeliveryDate')
            self.assertEqual(stored.tabular_sections[0].rows[0].values[index],datetime(2025,10,26,2,30))
            self.assertEqual(stored.tabular_sections[0].rows[1].values[index],datetime(1,1,1))
        self.process=ConfigurationProcess(self.root,self.path,reference_application=True);self.addCleanup(self.process.close)
        self.app=ConfigurationController(load_application(self.root,reference_application=True),self.process.exchange,reference_application=True)
        self.addCleanup(self.app.close);self.rpc('hello',protocol=PROTOCOL)
        entry=self.app.names['document.orders.form.card']
        listed=self.rpc('catalog',entry=entry)['state']['catalog']['rows']
        sid=self.rpc('openRecord',entry=entry,request='reopened',record=listed[0]['key'])['session']
        self.assertEqual(self.item(sid,'DateInput')['value'],encode_value(stamp))
        grid=self.item(sid,'LinesTable');index=next(i for i,c in enumerate(grid['columns']) if c['name']=='DeliveryDate')
        self.assertEqual(grid['rows'][0]['values'][index],encode_value(delivery))
        self.assertEqual(grid['rows'][1]['values'][index],{'type':'Date','ticks':'0'})

    def test_existing_bsl_number_normalization_is_still_authoritative(self):
        sid=self.product()
        self.event(sid,'change',control='PriceInput',value=encode_value(Decimal('12.345')))
        self.assertEqual(self.item(sid,'PriceInput')['value'],{'type':'Number','value':'12.35'})
        self.event(sid,'command',control='SaveButton')
        with closing(SQLiteDBContext(self.path)) as context:
            manager=BSLCatalogs(BSLCatalogMetadataCollection(context),context).get_index('Products')
            self.assertEqual(manager._get_object(manager.find_by_code('P2')).get_member('Price'),Decimal('12.35'))
