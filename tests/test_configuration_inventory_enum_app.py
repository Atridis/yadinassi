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
