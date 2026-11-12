"""Integrated main-demo admission; authored interactions are not native evidence."""
from hashlib import sha256
from pathlib import Path
import tempfile
from unittest.mock import patch
import test_main_demo_interactions as authored
from main_demo_interactions_fixture import sources
from test_main_demo_configuration import source, ROOT
from test_main_demo_runtime import SEED
from yadinassi import Interpreter, BSLError
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.form_dialogs import DIALOG_CAPABILITY
from yadinassi.ui.configuration_app import load_application, ConfigurationBroker, ConfigurationController, PROTOCOL
from yadinassi.ui.protocol import encode_line, decode_line


class MainDemoInteractionHostTests(authored.OperationDraftTests):
    def host(self, files=None, **unused):
        full = source()
        for name, raw in sources().items():
            if name != 'Configuration.xml':
                self.assertEqual(full[name], raw)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'main.sqlite'
        self.config = import_main_demo_configuration(full, profile=PROFILE)
        SQLiteDBContext.create_main_demo(self.path, self.config).close()
        before = sha256(self.path.read_bytes()).digest()
        self.expect_unchanged = True
        def unchanged():
            if self.expect_unchanged:
                self.assertEqual(sha256(self.path.read_bytes()).digest(), before)
        self.addCleanup(unchanged)
        forms = load_application(ROOT / 'examples/demo', main_demo_application=True)
        broker = ConfigurationBroker(forms, self.path, main_demo_application=True)
        self.addCleanup(broker.close)
        packets = []
        def exchange(raw):
            request = decode_line(raw); packets.append(request)
            result = broker.exchange({k:request[k] for k in ('operation','session','payload')})
            return encode_line({'id':request['id'],'session':request['session'],'result':result,'error':None})
        app = ConfigurationController(forms, exchange, main_demo_application=True)
        self.addCleanup(app.close)
        self.assertIsNone(self.rpc(app, 'hello', protocol=PROTOCOL, dialogCapability=DIALOG_CAPABILITY)['error'])
        self.broker = broker
        private = app.names['commonform.draftdetails']
        count = len(packets)
        self.assertEqual(app._open(private, {})[2], 'open_failed')
        self.assertEqual(len(packets), count)  # no server allocation before owner admission
        self.assertFalse(broker.sessions)
        return broker, app, packets

    def setup_draft(self):
        app, owner, child = super().setup_draft()
        for sid in (owner, child):
            for controller in (app.sessions[sid][0], self.broker.sessions[sid][0]):
                vm = controller.session.interpreter
                self.assertIsNone(vm.database_context)
                self.assertFalse(vm._transaction_activation_allowed)
        return app, owner, child

    def test_common_form_no_db_query_write_or_foreign_transaction_authority(self):
        app, owner, child = self.setup_draft()
        for controller in (app.sessions[owner][0], self.broker.sessions[owner][0]):
            vm = controller.session.interpreter
            for code in ('BeginTransaction();', 'Q=New Query("SELECT Code FROM Catalog.Склады");Q.Execute();',
                         'Catalogs.Склады.CreateItem().Write();'):
                with self.subTest(code=code), self.assertRaises(BSLError):
                    vm.execute(code)
        with SQLiteDBContext(self.path) as foreign:
            with patch.object(foreign.backend, 'begin_unit_of_work') as begin:
                with self.assertRaises((ValueError, BSLError)):
                    vm = self.broker.application.interpreter_factory(lambda value: None, database_context=foreign)
                    try:
                        vm.execute('BeginTransaction();')
                    finally:
                        vm.close()
                begin.assert_not_called()

    def test_child_completion_cannot_replay_after_owner_close(self):
        app, owner, child = self.setup_draft()
        self.prepare(app, owner, child)
        self.question(app, owner, 'yes')
        self.assertEqual(self.data(app, owner)['appliedcount'], 1)
        self.event(app, owner, event='close')
        self.assertNotIn(owner, app.sessions)
        stale = self.rpc(app, 'form', session=child, request={'jsonrpc':'2.0','id':1,
            'method':'form.event','params':{'event':'command','control':'AcceptButton','revision':1}})
        self.assertEqual(stale['error'], 'retired_session')
        self.assertFalse(app.sessions)
        self.assertIsNone(app.owned_results[child].callback)

    def test_document_post_preserves_source_bound_enum_values(self):
        broker, app, _ = self.host()
        self.expect_unchanged = False
        with SQLiteDBContext(self.path) as context:
            vm = Interpreter(database_context=context)
            try:
                vm.execute(SEED + '''D=Documents.Receipt.CreateDocument();D.Number="interaction1";
D.Date=Date(2026,11,12);D.Warehouse=Склад.Ссылка;D.State=Enums.States.Draft;
L=D.Lines.Add();L.Product=Карточка.Ссылка;L.Quantity=3;L.Amount=123;L.Unit=Enums.Units.Piece;D.Write();''')
            finally:
                vm.close()
        entry = app.names['document.receipt.form.card']
        self.rpc(app, 'catalog', entry=entry)
        record = app.catalog['rows'][0]['key']
        opened = self.rpc(app, 'openRecord', entry=entry, record=record, request='receipt')
        self.assertIsNone(opened['error'], opened)
        sid = opened['session']; owned = broker.objects[sid]
        from yadinassi.inventory_enum_runtime import binding
        domain = binding(owned.operations._interpreter._metadata)
        self.assertIsNotNone(domain)
        self.assertFalse(owned.object.get_member('State').is_empty())
        result = self.event(app, sid, 'PostButton')
        self.assertIsNone(result['error'], result)
        self.assertIsNone(result['form']['result']['error'], result)
        self.assertTrue(owned.object.get_member('Posted'))
        report = self.rpc(app, 'report', report='StockMovements', at=None, start=None, end=None)['state']['report']
        self.assertEqual(len(report['rows']), 1)
        values = dict(zip((c['name'] for c in report['columns']), report['rows'][0]))
        self.assertEqual(values['Unit'], {'type':'String','value':'Piece'})
        self.assertEqual(values['State'], {'type':'String','value':'Draft'})
