"""Statement controls/pages across the real broker boundary, no browser execution."""
from dataclasses import replace
from copy import deepcopy
from unittest.mock import patch
import unittest
from test_configuration_inventory_app import InventoryApplicationTests as _Setup
from yadinassi.ui.local_app import LocalTransportError
from yadinassi.ui import report_pages
from yadinassi.ui.report_protocol import validate_projection, validate_setup


class StatementControllerTests(unittest.TestCase):
    setUp = _Setup.setUp
    rpc = _Setup.rpc
    open = _Setup.open
    event = _Setup.event
    choose = _Setup.choose
    prepare = _Setup.prepare
    cards = _Setup.cards

    def setup_report(self):
        return self.rpc('reportSetup', report='StockStatement', action='open')['state']['reportSetup']

    def action(self, action, **params):
        setup = self.app.report_setup
        return self.rpc('reportSetup', report=setup['report'], ticket=setup['ticket'], action=action, **params)['state']['reportSetup']

    def read(self, periodicity='None'):
        return self.rpc('report', report='StockStatement', at=None, start='2026-11-01T00:00:00', end='2026-11-30T23:59:59',
                        periodicity=periodicity, setup=self.app.report_setup['ticket'])['state']['report']

    def raw(self, method, **params):
        return self.app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']

    def two_pages(self):
        sid=self.prepare(); self.event(sid,control='PostButton'); self.setup_report()
        first=self.read(); service=self.broker._inventory_reports
        original=service.read
        def double(*args,**kwargs):
            result=original(*args,**kwargs)
            return replace(result,rows=result.rows+result.rows)
        with patch.object(service,'read',side_effect=double),patch.object(report_pages,'PAGE_ROWS',1):
            first=self.read()
        self.assertEqual(first['page']['total'],2)
        return sid, first

    def test_new_declaration_has_explicit_periodicities_and_filter_names_only(self):
        state=self.app._state(); grant=next(r for r in state['reports'] if r['id']=='StockStatement')
        self.assertEqual(grant['periodicities'],['None','Day','Month'])
        self.assertEqual(grant['filters'],[{'id':'Product','title':'Product'},{'id':'Warehouse','title':'Warehouse'}])
        self.assertIsNone(state['reportSetup']); self.assertIsNone(state['report'])

    def test_open_setup_has_no_database_identifiers_and_no_form(self):
        setup=self.setup_report()
        self.assertEqual([f['mode'] for f in setup['filters']],['all','all'])
        self.assertFalse(self.app.sessions); self.assertNotIn(str(self.broker.record_context.backend.database_id),str(setup))
        validate_setup(setup,self.config)

    def test_real_choice_and_typed_filter_match_saved_statement(self):
        sid=self.prepare(); self.event(sid,control='PostButton'); self.setup_report()
        setup=self.action('begin',filter='Product'); choice=setup['choice']
        self.assertEqual(choice['rows'][0]['description'],'Product')
        selected=self.action('apply',choice=choice['ticket'],value=choice['rows'][0]['choice'])
        self.assertEqual(selected['filters'][0],{'id':'Product','mode':'selected','text':'Product'})
        result=self.read();self.assertEqual(len(result['rows']),1)
        self.assertEqual(result['filters'][0]['text'],'Product');self.assertEqual(result['page']['total'],1)

    def test_explicit_empty_excludes_nonempty_and_clear_restores_all(self):
        sid=self.prepare();self.event(sid,control='PostButton');self.setup_report()
        self.action('empty',filter='Product');self.assertEqual(self.read()['page']['total'],0)
        self.action('clear',filter='Product');self.assertEqual(self.read()['page']['total'],1)

    def test_cancel_keeps_committed_filter_and_retires_choice(self):
        self.setup_report();self.action('empty',filter='Warehouse'); old=deepcopy(self.app.report_setup)
        setup=self.action('begin',filter='Product');self.action('cancel',choice=setup['choice']['ticket'])
        self.assertEqual(self.app.report_setup['filters'],old['filters']);self.assertEqual(self.app.report_setup['ticket'],old['ticket'])

    def test_real_exact_code_search_never_exposes_persistent_reference(self):
        self.setup_report();setup=self.action('begin',filter='Product')
        chosen=self.action('filter',choice=setup['choice']['ticket'],code='P1')['choice']
        self.assertEqual([r['code'] for r in chosen['rows']],['P1'])
        self.assertTrue(all(set(r)=={'choice','code','description'} for r in chosen['rows']))
        self.assertNotEqual(chosen['ticket'],setup['choice']['ticket'])

    def test_statement_read_while_choice_open_refuses_without_lock(self):
        self.setup_report();self.action('begin',filter='Product');setup=self.app.report_setup
        result=self.raw('report',report='StockStatement',at=None,start='2026-11-01T00:00:00',end='2026-11-30T23:59:59',periodicity='Day',setup=setup['ticket'])
        self.assertEqual(result['error'],'report_unavailable');self.assertFalse(self.app.uncertain)

    def test_stale_setup_cannot_retarget_after_selection_change(self):
        old=self.setup_report();self.action('empty',filter='Product')
        result=self.raw('report',report='StockStatement',at=None,start='2026-11-01T00:00:00',end='2026-11-30T23:59:59',periodicity='None',setup=old['ticket'])
        self.assertEqual(result['error'],'report_unavailable');self.assertIsNone(result['state']['report'])

    def test_pages_do_not_requery_or_resolve_receipts(self):
        _,first=self.two_pages(); page=first['page']
        with patch.object(self.broker._inventory_reports,'read',side_effect=AssertionError('new query')):
            result=self.rpc('reportPage',snapshot=page['snapshot'],cursor=page['next'])['state']['report']
        self.assertEqual(result['page']['offset'],1);self.assertEqual(result['page']['previous'],page['cursor'])
        self.assertEqual(result['rows'],first['rows'])

    def test_page_navigation_is_idempotent_and_previous_exact(self):
        _,first=self.two_pages(); page=first['page']
        second=self.rpc('reportPage',snapshot=page['snapshot'],cursor=page['next'])['state']['report']
        repeated=self.rpc('reportPage',snapshot=page['snapshot'],cursor=page['next'])['state']['report']
        self.assertEqual(second,repeated)
        back=self.rpc('reportPage',snapshot=page['snapshot'],cursor=page['cursor'])['state']['report']
        self.assertEqual(back,first)

    def test_new_setup_retires_old_pages(self):
        _,first=self.two_pages(); self.setup_report()
        result=self.raw('reportPage',snapshot=first['page']['snapshot'],cursor=first['page']['next'])
        self.assertEqual(result['error'],'report_unavailable');self.assertFalse(self.app.uncertain)

    def test_filter_selection_retires_old_pages(self):
        _,first=self.two_pages(); self.action('empty',filter='Warehouse')
        result=self.raw('reportPage',snapshot=first['page']['snapshot'],cursor=first['page']['next'])
        self.assertEqual(result['error'],'report_unavailable')

    def test_form_event_retires_setup_and_pages(self):
        sid,first=self.two_pages();self.event(sid,'change',control='NumberInput',value='Edited')
        self.assertIsNone(self.app.report);self.assertIsNone(self.app.report_setup)
        result=self.raw('reportPage',snapshot=first['page']['snapshot'],cursor=first['page']['next'])
        self.assertEqual(result['error'],'report_unavailable')

    def test_catalog_navigation_retires_statement_not_form_state(self):
        _,first=self.two_pages();self.rpc('catalog',entry=self.app.names['catalog.products.form.card'])
        self.assertIsNone(self.app.report);self.assertIsNone(self.app.report_setup)
        self.assertEqual(len(self.app.sessions),1)

    def test_pending_commit_blocks_setup_and_page_without_read(self):
        sid,first=self.two_pages();owned=self.broker.objects[sid];owned.pending_commit=True
        try:
            with patch.object(self.broker._inventory_reports,'choice_snapshot',side_effect=AssertionError('read')):
                result=self.raw('reportSetup',report='StockStatement',action='open')
            self.assertEqual(result['error'],'report_busy')
            result=self.raw('reportPage',snapshot=first['page']['snapshot'],cursor=first['page']['next'])
            # The refused new setup already retired the old displayed page.
            # Its stale cursor is unavailable, independently of the busy owner.
            self.assertEqual(result['error'],'report_unavailable')
        finally:owned.pending_commit=False

    def test_page_header_forgery_locks_transport_without_installing_result(self):
        _,first=self.two_pages();forged=deepcopy(first);forged['page']['cursor']=first['page']['next'];forged['filters'][0]['text']='forged'
        with patch.object(self.broker,'_report_page',return_value=forged),self.assertRaises(LocalTransportError):
            self.rpc('reportPage',snapshot=first['page']['snapshot'],cursor=first['page']['next'])
        self.assertTrue(self.app.uncertain);self.assertIsNone(self.app.report)

    def test_unknown_filter_shape_refuses_without_unsafe_dispatch(self):
        setup=self.setup_report()
        result=self.raw('reportSetup',report='StockStatement',ticket=setup['ticket'],action='empty',filter='Product',key='forged')
        self.assertEqual(result['error'],'report_unavailable');self.assertFalse(self.app.uncertain)

    def test_statement_projection_rejects_ungranted_periodicity_and_columns(self):
        self.setup_report();valid=self.read()
        request={k:valid[k] for k in ('report','at','start','end','periodicity','setup')}
        for change in (lambda r:r.update(periodicity='Year'),lambda r:r['columns'][0].update(name='Injected')):
            bad=deepcopy(valid);change(bad)
            with self.assertRaises(ValueError):validate_projection(bad,self.config,request)

    def test_new_periodic_report_reuses_exact_same_snapshot_headers_on_reload(self):
        self.setup_report(); result=self.read('Month')
        self.assertEqual(self.rpc('snapshot')['state']['report'],result)
        self.assertEqual(self.rpc('snapshot')['state']['reportSetup'],self.app.report_setup)

    def test_legacy_report_clears_statement_setup_without_changing_old_shape(self):
        self.setup_report();self.read()
        result=self.rpc('report',report='StockMovements',at=None,start=None,end=None)['state']
        self.assertIsNone(result['reportSetup']);self.assertNotIn('page',result['report'])

    def test_real_http_allowlist_delivers_setup_report_and_page(self):
        from http.client import HTTPConnection
        from threading import Thread
        from yadinassi.ui.configuration_app import ConfigurationHandler
        from yadinassi.ui.local_app import LocalUIServer
        from yadinassi.ui.protocol import encode_line, decode_line
        server=LocalUIServer(self.app,handler=ConfigurationHandler)
        thread=Thread(target=server.serve_forever,kwargs={'poll_interval':0.01},daemon=True);thread.start()
        try:
            def call(method,params):
                connection=HTTPConnection(*server.server_address,timeout=10)
                try:
                    connection.request('POST','/rpc',encode_line({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params}),
                        {'Origin':server.origin,'Content-Type':'application/x-ndjson','X-Yadinassi-Session':server.token})
                    response=connection.getresponse();raw=response.read();self.assertEqual(response.status,200)
                    return decode_line(raw)['result']
                finally:connection.close()
            setup=call('reportSetup',{'report':'StockStatement','action':'open'})['state']['reportSetup']
            result=call('report',{'report':'StockStatement','at':None,'start':'2026-11-01T00:00:00','end':'2026-11-30T23:59:59','periodicity':'None','setup':setup['ticket']})
            self.assertIsNone(result['error']);page=result['state']['report']['page']
            result=call('reportPage',{'snapshot':page['snapshot'],'cursor':page['cursor']})
            self.assertIsNone(result['error']);self.assertEqual(result['state']['report']['page'],page)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=10)

    def test_oversized_setup_refuses_whole_projection_without_lock(self):
        from copy import deepcopy
        original=self.setup_report();big=deepcopy(original)
        big['choice']={'filter':'Product','ticket':'choice-'+'a'*32+'-1','code':'','error':None,
            'rows':[{'choice':format(i,'032x'),'code':str(i),'description':'😀'*1024} for i in range(32)]}
        with patch.object(self.broker._report_controls,'action',return_value=big):
            result=self.raw('reportSetup',report='StockStatement',action='open')
        self.assertEqual(result['error'],'report_unavailable');self.assertIsNone(result['state']['reportSetup'])
        self.assertIsNone(self.broker._report_controls.state);self.assertFalse(self.app.uncertain)

    def test_setup_overflow_beside_catalog_retires_choices_without_lock(self):
        original=self.setup_report();big=deepcopy(original)
        big['choice']={'filter':'Product','ticket':'choice-'+'a'*32+'-1','code':'','error':None,
            'rows':[{'choice':format(i,'032x'),'code':str(i),'description':'x'*1024} for i in range(32)]}
        self.app.catalog={'entry':self.app.names['catalog.products.form.card'],'version':1,
            'rows':[{'key':'record-'+str(i+1),'code':str(i),'description':'y'*1024,'deletionMark':False} for i in range(100)]}
        with patch.object(self.broker._report_controls,'action',return_value=big):
            result=self.raw('reportSetup',report='StockStatement',action='open')
        self.assertEqual(result['error'],'report_unavailable');self.assertIsNone(result['state']['reportSetup'])
        self.assertIsNone(self.broker._report_controls.state);self.assertFalse(self.app.uncertain)
        self.app.catalog=None
        stale=self.raw('reportSetup',report='StockStatement',ticket=original['ticket'],action='empty',filter='Product')
        self.assertEqual(stale['error'],'report_unavailable');self.assertFalse(self.app.uncertain)



    def test_choice_navigation_crosses_broker_with_exact_shape(self):
        self.prepare();self.setup_report()
        state=self.action('begin',filter='Product')
        choice=state['choice']
        self.assertEqual(choice['navigation']['total'],1)
        self.assertEqual(choice['navigation']['page'],1)
        previous=choice['ticket']
        state=self.action('search',choice=previous,query='Wid')
        self.assertNotEqual(state['choice']['ticket'],previous)
        self.assertEqual(state['choice']['navigation']['query'],'Wid')
        state=self.action('refresh',choice=state['choice']['ticket'])
        self.assertEqual(state['choice']['navigation']['page'],1)

    def test_choice_navigation_protocol_refuses_forged_totals_and_cursors(self):
        self.prepare();self.setup_report();state=self.action('begin',filter='Product')
        for mutate in (lambda n:n.update(total=8193),lambda n:n.update(page=True),lambda n:n.update(next='bad')):
            bad=deepcopy(state);mutate(bad['choice']['navigation'])
            with self.assertRaises(ValueError):validate_setup(bad,self.broker.posting_configuration)

    def test_choice_snapshot_limit_has_no_fabricated_partial_page(self):
        import yadinassi.inventory_application_reports as reports
        self.prepare();self.setup_report()
        with patch.object(reports,'MAX_CHOICE_SNAPSHOT_ROWS',0):
            state=self.action('begin',filter='Product')
        self.assertEqual(state['choice']['error'],'snapshot_limit')
        self.assertEqual(state['choice']['rows'],[])
        self.assertIsNone(state['choice']['navigation'])


del _Setup
