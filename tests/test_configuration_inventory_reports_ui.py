"""Readonly report transport does not acquire the document root capability."""
from datetime import datetime
from decimal import Decimal
import unittest
from unittest.mock import patch
from test_configuration_inventory_app import InventoryApplicationTests as _Setup
from yadinassi.ui.local_app import LocalTransportError


class InventoryReportUITests(unittest.TestCase):
    setUp=_Setup.setUp
    rpc=_Setup.rpc
    open=_Setup.open
    event=_Setup.event
    choose=_Setup.choose
    prepare=_Setup.prepare
    cards=_Setup.cards

    def report(self,name='StockBalance',**bounds):
        return self.rpc('report',report=name,at=bounds.get('at','2026-11-12T00:00:00') if name=='StockBalance' else None,
            start=bounds.get('start'),end=bounds.get('end'))

    def test_manifest_reports_are_not_form_or_write_capabilities(self):
        state=self.app._state()
        self.assertEqual({r['view'] for r in state['reports']},{'Movements','Balance','Turnovers'})
        self.assertIsNone(state['report']);self.assertEqual(len(state['entries']),4)
        self.assertTrue(all(set(r)=={'id','title','view'} for r in state['reports']))

    def test_posted_balance_preserves_decimal_and_reference_labels(self):
        sid=self.prepare();self.event(sid,control='PostButton')
        result=self.report()['state']['report']
        self.assertEqual(len(result['rows']),1)
        row=dict(zip((c['name'] for c in result['columns']),result['rows'][0]))
        self.assertEqual(row['QuantityBalance'],{'type':'Number','value':'10.000'})
        self.assertEqual(row['Product'],{'type':'Catalog','text':'Product'})
        self.assertEqual(row['Warehouse'],{'type':'Catalog','text':'Warehouse'})
        self.assertNotIn(str(self.broker.objects[sid].object._key.record_id),str(result))

    def test_movements_and_turnovers_share_public_typed_shape(self):
        sid=self.prepare();self.event(sid,control='PostButton')
        result=self.report('StockMovements')['state']['report']
        row=dict(zip((c['name'] for c in result['columns']),result['rows'][0]))
        self.assertEqual(row['RecordType'],{'type':'String','value':'Receipt'})
        self.assertEqual(row['Recorder']['type'],'Document');self.assertIn('Receipt-1',row['Recorder']['text'])
        result=self.report('StockTurnovers',start='2026-11-11T00:00:00',end='2026-11-11T23:59:59')['state']['report']
        row=dict(zip((c['name'] for c in result['columns']),result['rows'][0]))
        self.assertEqual(row['QuantityReceipt']['value'],'10.000');self.assertEqual(row['QuantityExpense']['value'],'0.000')

    def test_report_ignores_unsaved_form_changes_and_never_executes_bsl(self):
        self.prepare()
        with patch('yadinassi.runtime.Interpreter.execute',side_effect=AssertionError('report must not run BSL')):
            result=self.report()['state']['report']
        self.assertEqual(result['rows'],[]);self.assertEqual(self.cards(),())

    def test_form_dispatch_clears_old_report_then_undo_returns_empty(self):
        sid=self.prepare();self.event(sid,control='PostButton');self.report()
        self.assertIsNotNone(self.app.report)
        self.event(sid,control='UndoPostingButton');self.assertIsNone(self.app.report)
        self.assertEqual(self.report()['state']['report']['rows'],[])

    def test_pending_receipt_blocks_report_without_resolution(self):
        sid=self.open('Document.Receipt.Form.Card');owned=self.broker.objects[sid]
        owned.pending_commit=True
        try:
            with patch.object(owned.operations,'resolve',side_effect=AssertionError('no recovery')):
                result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.report','params':{
                    'report':'StockBalance','at':'2026-11-12T00:00:00','start':None,'end':None}})['result']
            self.assertEqual(result['error'],'report_busy');self.assertIsNone(result['state']['report'])
        finally:owned.pending_commit=False

    def test_invalid_date_or_unknown_report_is_bounded_refusal(self):
        for name,at in [('StockBalance','2026-02-30T00:00:00'),('SELECT *','2026-11-12T00:00:00')]:
            result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.report','params':{
                'report':name,'at':at,'start':None,'end':None}})['result']
            self.assertEqual(result['error'],'report_unavailable');self.assertFalse(self.app.uncertain)
            self.assertIsNone(result['state']['report'])

    def test_report_overflow_beside_large_catalog_refuses_without_lock(self):
        projection={'report':'StockBalance','view':'Balance','at':'2026-11-12T00:00:00','start':None,'end':None,
            'columns':[{'name':'Product','type':'Catalog'},{'name':'Warehouse','type':'Catalog'},
                {'name':'AmountBalance','type':'Number'},{'name':'QuantityBalance','type':'Number'}],
            'rows':[[{'type':'Catalog','text':'x'*1152},{'type':'Catalog','text':'z'*1152},
                {'type':'Number','value':'0'},{'type':'Number','value':'0'}] for _ in range(20)]}
        catalog={'entry':self.app.names['catalog.products.form.card'],'version':1,
            'rows':[{'key':'record-'+str(i+1),'code':str(i),'description':'y'*900,'deletionMark':False} for i in range(100)]}
        for method in ('report','catalog'):
            self.app.catalog=catalog
            self.app.report=None if method=='report' else projection
            with patch.object(self.broker,'_report',return_value=projection), patch.object(self.broker,'_records',return_value=catalog):
                params={k:projection[k] for k in ('report','at','start','end')} if method=='report' else {'entry':catalog['entry']}
                result=self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
            self.assertEqual(result['error'],'report_unavailable')
            self.assertIsNone(result['state']['report']);self.assertIsNone(self.app.report)
            self.assertFalse(self.app.uncertain);self.assertEqual(result['state']['catalog'],catalog)

    def test_changed_report_columns_lock_transport_instead_of_forging_projection(self):
        forged={'report':'StockBalance','view':'Balance','at':'2026-11-12T00:00:00','start':None,'end':None,
            'columns':[{'name':'Injected','type':'String'}],'rows':[[{'type':'String','value':'false report'}]]}
        with patch.object(self.broker,'_report',return_value=forged), self.assertRaises(LocalTransportError):
            self.report()
        self.assertTrue(self.app.uncertain);self.assertIsNone(self.app.report)

    def test_report_cannot_use_form_session_channel(self):
        sid=self.open('Document.Receipt.Form.Card')
        with self.assertRaises(ValueError):self.broker.exchange({'operation':'report','session':sid,'payload':{
            'report':'StockMovements','at':None,'start':None,'end':None}})


del _Setup
