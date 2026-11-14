"""Recorder navigation consumes server-owned capabilities, never display labels."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from test_main_demo_configuration import source, ROOT
from test_main_demo_runtime import SEED
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.inventory_application_reports import InventoryReports
from yadinassi.runtime import Interpreter
from yadinassi.ui.configuration_app import ConfigurationBroker, ConfigurationController, ConfigurationHandler, load_application, PROTOCOL
from yadinassi.ui.protocol import encode_line, decode_line
from yadinassi.ui.local_app import LocalTransportError
from yadinassi.ui.report_protocol import validate_projection

REPORT = {'report':'StockMovements','at':None,'start':None,'end':None}


class RecorderNavigationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)/'demo.sqlite'
        self.configuration = import_main_demo_configuration(source(), profile=PROFILE)
        with SQLiteDBContext.create_main_demo(self.path, self.configuration) as context:
            vm = Interpreter(database_context=context)
            try:
                vm.execute(SEED + '''
D=Documents.Receipt.CreateDocument();D.Number="r1";D.Date=Date(2024,1,1);D.Warehouse=Склад.Ссылка;
L=D.Lines.Add();L.Product=Карточка.Ссылка;L.Quantity=5;L.Amount=10;L.Unit=Enums.Units.Piece;D.Write(DocumentWriteMode.Posting);
D=Documents.Issue.CreateDocument();D.Number="i1";D.Date=Date(2024,1,2);D.Warehouse=Склад.Ссылка;
L=D.Lines.Add();L.Product=Карточка.Ссылка;L.Quantity=1;L.Amount=2;L.Unit=Enums.Units.Piece;D.Write(DocumentWriteMode.Posting);
''')
            finally: vm.close()
        self.forms = load_application(ROOT/'examples/demo', main_demo_application=True)
        self.broker = ConfigurationBroker(self.forms, self.path, main_demo_application=True)
        self.addCleanup(self.broker.close)
        self.operations = []
        def exchange(raw):
            request = decode_line(raw); self.operations.append(request['operation'])
            result = self.broker.exchange({k:request[k] for k in ('operation','session','payload')})
            return encode_line({'id':request['id'],'session':request['session'],'result':result,'error':None})
        self.app = ConfigurationController(self.forms, exchange, main_demo_application=True)
        self.addCleanup(self.app.close)
        self.assertIsNone(self.rpc('hello', protocol=PROTOCOL)['error'])

    def rpc(self, method, **params):
        return self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']

    def links(self):
        result = self.rpc('report', **REPORT)
        self.assertIsNone(result['error'])
        return [cell['recorder'] for row in self.app.report['rows'] for cell in row if 'recorder' in cell]

    def saved(self):
        with SQLiteDBContext(self.path) as context:
            result = InventoryReports(context,self.configuration).read('StockMovements')
            return result.rows

    def test_handler_explicitly_admits_new_recorder_method(self):
        self.assertIn('application.openRecorder',ConfigurationHandler.methods)

    def test_both_recorders_open_separate_existing_document_forms_without_writes(self):
        before = self.saved(); names = set()
        for index, link in enumerate(self.links()):
            # A successful open retires all sibling grants, so read a fresh snapshot.
            link = self.links()[index]
            result = self.rpc('openRecorder', recorder=link, request='open'+str(index))
            self.assertIsNone(result['error'])
            controller, entry = self.app.sessions[result['session']]
            names.add(self.app.definitions[entry].document_schema.name)
            self.assertIsNotNone(result['form'])
            self.assertIsNone(self.app.catalog)
        self.assertEqual(names, {'Receipt','Issue'})
        self.assertEqual(self.saved(),before)

    def test_repeated_intent_reuses_session_without_replaying_create(self):
        link = self.links()[0]
        first = self.rpc('openRecorder',recorder=link,request='same')
        count = self.operations.count('create')
        again = self.rpc('openRecorder',recorder=link,request='same')
        self.assertEqual(again['session'],first['session']);self.assertIsNone(again['error'])
        self.assertEqual(self.operations.count('create'),count)
        self.assertEqual(self.rpc('openRecorder',recorder=link,request='new')['error'],'invalid_record')

    def test_rotated_or_tampered_tokens_are_rejected_without_create(self):
        old = self.links()[0]; new = self.links()[0]; self.assertNotEqual(old,new)
        count = self.operations.count('create')
        for token in [old,'recorder-'+'0'*32,'r1','record-1']:
            self.assertEqual(self.rpc('openRecorder',recorder=token,request='bad'+token)['error'],'invalid_record')
        self.assertEqual(self.operations.count('create'),count)

    def test_cross_broker_token_and_consumed_broker_grant_are_rejected(self):
        link = self.links()[0]
        other = ConfigurationBroker(self.forms,self.path,main_demo_application=True)
        self.addCleanup(other.close)
        other.exchange({'operation':'hello','session':'','payload':{'source':self.forms.source_sha256}})
        self.assertEqual(other.exchange({'operation':'recorder','session':'','payload':{'recorder':link}}),{'error':'invalid_record'})
        grant = self.broker.exchange({'operation':'recorder','session':'','payload':{'recorder':link}})
        self.assertIn('record',grant)
        self.assertEqual(self.broker.exchange({'operation':'recorder','session':'','payload':{'recorder':link}}),{'error':'invalid_record'})

    def test_pending_modal_and_uncertain_state_do_not_consume_link(self):
        link=self.links()[0]; before=list(self.operations)
        self.app.owner_dialogs['fake']=SimpleNamespace(state='open')
        try:self.assertEqual(self.rpc('openRecorder',recorder=link,request='modal')['error'],'report_busy')
        finally:self.app.owner_dialogs.clear()
        self.assertEqual(self.operations,before)
        self.app.uncertain=True
        try:self.assertEqual(self.rpc('openRecorder',recorder=link,request='unknown')['error'],'outcome_unknown')
        finally:self.app.uncertain=False
        self.assertEqual(self.operations,before)
        self.assertIsNone(self.rpc('openRecorder',recorder=link,request='safe')['error'])

    def test_lost_broker_reply_locks_without_replaying_resolution_or_creation(self):
        link=self.links()[0]; transport=self.app.transport
        def lost(raw):
            result=transport(raw)
            if decode_line(raw)['operation']=='recorder': raise OSError('simulated reply loss')
            return result
        self.app.transport=lost
        with self.assertRaises(LocalTransportError):
            self.rpc('openRecorder',recorder=link,request='lost')
        count=self.operations.count('recorder')
        self.assertEqual(self.rpc('openRecorder',recorder=link,request='lost')['error'],'outcome_unknown')
        self.assertEqual(self.operations.count('recorder'),count)
        self.assertNotIn('create',self.operations)
        self.assertEqual(self.broker._recorder_grants,{})

    def test_lost_renderer_reply_is_reconciled_by_snapshot_without_second_create(self):
        link=self.links()[0]
        completed=self.rpc('openRecorder',recorder=link,request='delivered-on-server')
        before=list(self.operations) # Simulate browser discarding the successful response.
        state=self.rpc('snapshot')['state']
        self.assertEqual(self.operations,before)
        self.assertEqual([session['id'] for session in state['sessions']],[completed['session']])
        self.assertIsNone(state['report'])

    def test_projection_optional_recorder_field_is_closed_to_movements_column(self):
        self.links(); projection=deepcopy(self.app.report)
        validate_projection(projection,self.configuration,REPORT)
        for row in projection['rows']:
            for cell in row:cell.pop('recorder',None)
        validate_projection(projection,self.configuration,REPORT) # Old presentation-only projections remain valid.
        for index,column in enumerate(projection['columns']):
            if column['type']=='Catalog':
                projection['rows'][0][index]['recorder']='recorder-'+'a'*32
                break
        with self.assertRaises(ValueError):validate_projection(projection,self.configuration,REPORT)

    def test_other_broker_action_and_close_retire_grants(self):
        link=self.links()[0]
        self.broker.exchange({'operation':'reportReset','session':'','payload':{}})
        self.assertEqual(self.broker.exchange({'operation':'recorder','session':'','payload':{'recorder':link}}),{'error':'invalid_record'})
        self.links();self.broker.close();self.assertEqual(self.broker._recorder_grants,{})


class NonMainRecorderNavigationTests(unittest.TestCase):
    def setUp(self):
        from test_configuration_inventory_app import InventoryApplicationTests
        InventoryApplicationTests.setUp(self)

    def rpc(self,method,**params):
        return self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']

    def test_generic_inventory_does_not_acquire_recorder_capability(self):
        with self.assertRaises(ValueError):
            self.rpc('openRecorder',recorder='recorder-'+'a'*32,request='x')
        self.assertEqual(self.broker.exchange({'operation':'recorder','session':'','payload':{'recorder':'recorder-'+'a'*32}}),{'error':'invalid_record'})
        self.assertFalse(self.app.sessions)
