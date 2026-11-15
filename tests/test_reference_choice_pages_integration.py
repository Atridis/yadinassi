"""Real storage and HTTP boundary for bounded reference paging, not native parity."""
from contextlib import closing
from unittest.mock import patch
import unittest
import test_configuration_inventory_app as base
import test_configuration_record_pages as pages
from yadinassi.database_context import SQLiteDBContext


class ReferencePagesIntegrationTests(unittest.TestCase):
    setUp=base.InventoryApplicationTests.setUp
    rpc=base.InventoryApplicationTests.rpc
    open=base.InventoryApplicationTests.open
    event=base.InventoryApplicationTests.event
    choose=base.InventoryApplicationTests.choose
    prepare=base.InventoryApplicationTests.prepare
    seed=pages.ConfigurationRecordPagesTests.seed

    def reference(self,sid,action):
        return self.rpc('reference',session=sid,revision=self.app.sessions[sid][0].session.revision,action=action)

    def begin(self,sid):
        return self.reference(sid,dict(action='begin',control='WarehouseInput',row=None,column=None))['state']['choice']

    def test_real_http_page_apply_save_and_reopen(self):
        from http.client import HTTPConnection
        from threading import Thread
        from yadinassi.ui.configuration_app import ConfigurationHandler
        from yadinassi.ui.local_app import LocalUIServer
        from yadinassi.ui.protocol import encode_line,decode_line
        sid=self.prepare();self.seed(32)
        server=LocalUIServer(self.app,handler=ConfigurationHandler)
        thread=Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
        try:
            def action(value):
                connection=HTTPConnection(*server.server_address,timeout=10)
                try:
                    packet={'jsonrpc':'2.0','id':1,'method':'application.reference','params':{
                        'session':sid,'revision':self.app.sessions[sid][0].session.revision,'action':value}}
                    connection.request('POST','/rpc',encode_line(packet),{'Origin':server.origin,
                        'Content-Type':'application/x-ndjson','X-Yadinassi-Session':server.token})
                    response=connection.getresponse();raw=response.read();self.assertEqual(response.status,200)
                    result=decode_line(raw)['result'];self.assertIsNone(result['error'],result);return result
                finally:connection.close()
            first=action(dict(action='begin',control='WarehouseInput',row=None,column=None))['state']['choice']
            self.assertEqual(first['navigation']['total'],33)
            second=action(dict(action='page',ticket=first['ticket'],cursor=first['navigation']['next']))['state']['choice']
            self.assertEqual(second['navigation']['page'],2);self.assertEqual(second['rows'][0]['code'],'X0031')
            action(dict(action='apply',ticket=second['ticket'],choice=second['rows'][0]['choice']))
        finally:server.shutdown();server.server_close();thread.join(10)
        self.event(sid,control='WriteButton');self.assertEqual(self.app.posting_states[sid]['state'],'saved')
        self.event(sid,'close')
        entry=self.app.names['document.receipt.form.card'];rows=self.rpc('catalog',entry=entry)['state']['catalog']['rows']
        reopened=self.open('Document.Receipt.Form.Card',request='reopen-pages',record=rows[0]['key'])
        self.assertEqual(self.broker.objects[reopened].object.get_member('Warehouse').get_member('Code'),'X0031')

    def test_full_budget_refusal_exact_filter_recovery_and_search(self):
        sid=self.prepare();self.seed(32)
        with patch('yadinassi.reference_choice_pages.MAX_ROWS',32):
            first=self.begin(sid);self.assertEqual(first['error'],'snapshot_limit');self.assertIsNone(first['navigation']);self.assertEqual(first['rows'],[])
            filtered=self.reference(sid,dict(action='filter',ticket=first['ticket'],code='X0031'))['state']['choice']
            self.assertEqual(filtered['navigation']['total'],1)
            searched=self.reference(sid,dict(action='search',ticket=first['ticket'],query='warehouse'))['state']['choice']
            self.assertEqual(searched['error'],'snapshot_limit');self.assertIsNone(searched['navigation'])
        found=self.reference(sid,dict(action='search',ticket=first['ticket'],query='X WAREHOUSE 3'))['state']['choice']
        self.assertEqual(found['navigation']['total'],3)
        self.reference(sid,dict(action='cancel',ticket=first['ticket']))

    def test_external_deletion_mark_before_apply_is_refused(self):
        import sqlite3
        from yadinassi.sqlite_catalog import quote_identifier
        from yadinassi.sqlite_query_indexes import register_query_collations
        sid=self.prepare();self.seed(32);first=self.begin(sid)
        found=self.reference(sid,dict(action='search',ticket=first['ticket'],query='X0031'))['state']['choice']
        with closing(SQLiteDBContext(self.path)) as context:
            schema=next(s for s in self.config.catalogs if s.name=='Warehouses');table=quote_identifier(context.backend._layout.table_name(schema.identity))
        with closing(sqlite3.connect(self.path)) as writer, writer:
            register_query_collations(writer);writer.execute('UPDATE '+table+' SET deletion_mark=1 WHERE code=?',('X0031',))
        result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.reference','params':{
            'session':sid,'revision':self.app.sessions[sid][0].session.revision,
            'action':dict(action='apply',ticket=found['ticket'],choice=found['rows'][0]['choice'])}})['result']
        self.assertEqual(result['error'],'reference_refused');self.assertFalse(self.app.uncertain)
        self.assertNotEqual(self.broker.objects[sid].object.get_member('Warehouse').get_member('Code'),'X0031')
