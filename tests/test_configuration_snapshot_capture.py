"""Read-only retained form snapshots do not rotate saved-list capabilities."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import test_configuration_catalog_forms as fixture
from yadinassi.ui.form_app import PROTOCOL as FORM_PROTOCOL


class SnapshotCaptureTests(unittest.TestCase):
    setup_app = fixture.ConfigurationCatalogFormIntegrationTests.setup_app
    rpc = fixture.ConfigurationCatalogFormIntegrationTests.rpc
    entry = fixture.ConfigurationCatalogFormIntegrationTests.entry
    create = fixture.ConfigurationCatalogFormIntegrationTests.create
    event = fixture.ConfigurationCatalogFormIntegrationTests.event
    change = fixture.ConfigurationCatalogFormIntegrationTests.change
    save = fixture.ConfigurationCatalogFormIntegrationTests.save
    fill = fixture.ConfigurationCatalogFormIntegrationTests.fill
    data = fixture.ConfigurationCatalogFormIntegrationTests.data

    def prepared(self,files=None):
        broker,app=self.setup_app(files)
        self.rpc(app,'catalog',entry=self.entry(app))
        sid=self.create(app);self.fill(app,sid);self.save(app,sid)
        return broker,app,sid

    def snapshot(self,app,sid,**params):
        return self.rpc(app,'form',session=sid,request={
            'jsonrpc':'2.0','id':17,'method':'form.snapshot','params':params})

    def test_repeated_snapshots_keep_exact_page_and_opaque_record_grants(self):
        broker,app,sid=self.prepared()
        before=deepcopy(app.catalog);records=dict(broker.records)
        revision=app.sessions[sid][0].session.revision
        with patch.object(broker,'_records',wraps=broker._records) as captures:
            for _ in range(3):
                result=self.snapshot(app,sid)
                self.assertIsNone(result['error']);self.assertEqual(result['form']['id'],17)
                self.assertEqual(result['state']['catalog'],before)
            self.assertEqual(captures.call_count,0)
        self.assertEqual(broker.records,records)
        self.assertEqual(app.sessions[sid][0].session.revision,revision)
        reopened=self.rpc(app,'openRecord',entry=self.entry(app),record=before['rows'][0]['key'],request='still-current')
        self.assertIsNone(reopened['error'])

    def test_write_event_still_reconciles_and_rotates_projection(self):
        broker,app,sid=self.prepared();self.change(app,sid,'Description','Changed')
        before=deepcopy(app.catalog)
        with patch.object(broker,'_records',wraps=broker._records) as captures:
            result=self.save(app,sid)
            self.assertEqual(captures.call_count,1)
        self.assertEqual(result['state']['catalog']['rows'][0]['description'],'Changed')
        self.assertGreater(result['state']['catalog']['version'],before['version'])

    def test_write_then_client_exception_still_reconciles_without_replaying_write(self):
        files=fixture.catalog_form_sources();path='Catalogs/Products/Forms/Card/Ext/Form/Module.bsl'
        files[path]=files[path].replace(b' SaveAtServer();',b' SaveAtServer();\n Raise "after durable write";')
        broker,app=self.setup_app(files);self.rpc(app,'catalog',entry=self.entry(app))
        sid=self.create(app);self.fill(app,sid,description='Durable')
        with patch.object(broker,'_records',wraps=broker._records) as captures, \
             patch.object(broker.objects[sid].context.backend,'begin_write',wraps=broker.objects[sid].context.backend.begin_write) as writes:
            result=self.save(app,sid)
            self.assertEqual(captures.call_count,1);self.assertEqual(writes.call_count,1)
        self.assertEqual(result['form']['result']['error'],'event_failed')
        self.assertEqual(result['state']['catalog']['rows'][0]['description'],'Durable')
        self.assertFalse(app.uncertain)

    def test_blocked_close_snapshot_is_not_misclassified_as_readonly_request(self):
        broker,app,sid=self.prepared();owned=broker.objects[sid]
        owned.pending_refresh=True
        try:
            with patch.object(broker,'_records',wraps=broker._records) as captures:
                result=self.event(app,sid,'close')
                self.assertEqual(result['error'],'save_recovery_required')
                self.assertEqual(captures.call_count,1)
        finally:owned.pending_refresh=False

    def test_hello_and_snapshot_error_remain_conservative(self):
        broker,app,sid=self.prepared();controller=app.sessions[sid][0]
        with patch.object(broker,'_records',wraps=broker._records) as captures:
            self.rpc(app,'form',session=sid,request={'jsonrpc':'2.0','id':1,'method':'form.hello','params':{'protocol':FORM_PROTOCOL}})
            self.assertEqual(captures.call_count,1)
        exchange=controller.exchange
        def failure(request):
            result=exchange(request);result['result']['error']='event_failed';return result
        with patch.object(controller,'exchange',side_effect=failure),patch.object(broker,'_records',wraps=broker._records) as captures:
            self.snapshot(app,sid);self.assertEqual(captures.call_count,1)

    def test_unexpected_revision_change_falls_back_to_capture(self):
        broker,app,sid=self.prepared();controller=app.sessions[sid][0];exchange=controller.exchange
        def advanced(request):
            result=exchange(request);controller.session.revision+=1;return result
        with patch.object(controller,'exchange',side_effect=advanced),patch.object(broker,'_records',wraps=broker._records) as captures:
            self.snapshot(app,sid);self.assertEqual(captures.call_count,1)

    def test_pending_form_lifecycle_keeps_conservative_capture(self):
        broker,app,sid=self.prepared();app.pending.append((self.entry(app,'Categories'),{},None))
        before=len(app.sessions)
        with patch.object(broker,'_records',wraps=broker._records) as captures:
            self.snapshot(app,sid);self.assertEqual(captures.call_count,1)
        self.assertEqual(len(app.sessions),before+1)

    def test_snapshot_is_only_memory_not_a_bypass_of_explicit_source_checked_capture(self):
        broker,app,sid=self.prepared();before=deepcopy(app.catalog)
        with patch.object(broker.record_context.backend,'export_configuration',return_value={}):
            result=self.snapshot(app,sid)
            self.assertIsNone(result['error']);self.assertEqual(result['state']['catalog'],before)
            capture=self.rpc(app,'catalog',entry=self.entry(app))
            self.assertEqual(capture['error'],'catalog_unavailable')
            self.assertIsNone(capture['state']['catalog'])

    def test_snapshot_does_not_grant_save_when_the_object_source_has_changed(self):
        broker,app,sid=self.prepared();self.change(app,sid,'Description','Must not persist')
        owned=broker.objects[sid]
        with patch.object(owned.context.backend,'export_configuration',return_value={}), \
             patch.object(owned.context.backend,'begin_write',wraps=owned.context.backend.begin_write) as writes:
            self.assertIsNone(self.snapshot(app,sid)['error'])
            result=self.save(app,sid)
            self.assertEqual(writes.call_count,0)
            self.assertTrue(owned._stale)
            self.assertTrue(app.uncertain)
            self.assertEqual(result['form']['result']['error'],'outcome_unknown')
        self.assertEqual(result['state']['catalog']['rows'][0]['description'],'Product one')

    def test_malformed_snapshot_is_validated_instead_of_serving_cached_state(self):
        broker,app,sid=self.prepared()
        with patch.object(broker,'_records',wraps=broker._records) as captures:
            with self.assertRaises(ValueError):self.snapshot(app,sid,ignored=True)
            self.assertEqual(captures.call_count,0)
