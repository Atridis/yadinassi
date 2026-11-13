"""Isolated owned SQLite chooser/setup contracts; no browser or shared fixtures."""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.catalog_backend import (BackendError, CatalogDraft, CatalogComparison,
    CatalogPredicate, CatalogOrder, CatalogScanRequest)
from yadinassi.configuration_inventory_application import canonical
from yadinassi.inventory_application_reports import (InventoryReports, InventoryReportChoice,
    InventoryReportChoices, InventoryReportFilter, UNAVAILABLE)
from yadinassi.sqlite_catalog import _View
from yadinassi.ui.inventory_report_controls import InventoryReportControls
import test_inventory_application_reports as support

CONTROLS='yadinassi.ui.inventory_report_controls.'
START=datetime(2024,1,1)
END=datetime(2024,12,31)


class ControlsFixture:
    catalog=support.InventoryReportTests.catalog
    post=support.InventoryReportTests.post
    sql=support.InventoryReportTests.sql
    refused=support.InventoryReportTests.refused

    def setUp(self):
        support.InventoryReportTests.setUp(self)
        self.controls=InventoryReportControls(self.service,self.config)

    def choices(self, dimension='Product', code=''):
        return self.service.choices('StockStatement',dimension,code)

    def open(self):
        return self.controls.action({'report':'StockStatement','action':'open'})

    def act(self, action, **kwargs):
        state=self.controls.state
        return self.controls.action({'report':state['report'],'ticket':state['ticket'],'action':action,**kwargs})

    def begin(self, name='Product'):
        return self.act('begin',filter=name)

    def apply_first(self):
        choice=self.controls.state['choice']
        return self.act('apply',choice=choice['ticket'],value=choice['rows'][0]['choice'])

    def report(self):
        state=self.controls.state
        values=self.controls.resolve(state['report'],state['ticket'])
        return self.service.read(state['report'],start=START,end=END,periodicity='None',filters=values)


class InventoryReportChoiceTests(ControlsFixture,unittest.TestCase):
    def test_empty_catalog_returns_frozen_bound_snapshot(self):
        result=self.choices();grant=self.config.reports[-1].filters[0]
        self.assertEqual((result.database_id,result.configuration_generation,result.source_digest),
                         (self.backend.database_id,1,self.config.source_digest))
        self.assertEqual((result.report,result.dimension,result.dimension_id,result.catalog_id),
                         ('StockStatement','Product',grant.dimension_id,grant.catalog_id))
        self.assertEqual((result.rows,result.error,result.code),((),None,''))
        with self.assertRaises(FrozenInstanceError):result.report='Other'

    def test_rows_have_exact_original_keys_and_detached_presentations(self):
        key=self.catalog('Products','P1','Widget');result=self.choices()
        self.assertEqual(result.rows,(InventoryReportChoice(key,'P1','Widget'),))
        with self.assertRaises(FrozenInstanceError):result.rows[0].description='Changed'
        self.context.close();self.assertEqual(result.rows[0].key,key)

    def test_exact_code_is_case_sensitive_and_not_prefix(self):
        self.catalog('Products','P1','Upper');self.catalog('Products','p1','Lower');self.catalog('Products','P10','Longer')
        self.assertEqual([r.description for r in self.choices(code='P1').rows],['Upper'])
        self.assertEqual(self.choices(code='P').rows,())

    def test_scan_request_is_closed_typed_and_32_rows(self):
        original=_View.scan_catalog
        with patch.object(_View,'scan_catalog',autospec=True,side_effect=original) as scan:
            self.choices(code='P1')
        request=scan.call_args.args[2]
        self.assertIs(type(request),CatalogScanRequest)
        self.assertEqual(request.page_size,32);self.assertIsNone(request.continuation)
        self.assertEqual(request.order,(CatalogOrder('code'),))
        self.assertEqual(request.predicate,CatalogPredicate('and',(
            CatalogComparison('deletion_mark','eq',False),CatalogComparison('code','eq','P1'))))

    def test_deletion_marked_cards_are_excluded_not_write_capabilities(self):
        key=self.catalog('Products','P1','Deleted')
        with closing(self.backend.begin_read()) as owner:card=owner.read_catalog(key)
        with closing(self.backend.begin_write(uuid4())) as owner:
            owner.update(CatalogDraft(card.key,card.code,card.description,True,card.values,card.tabular_sections),card.revision);owner.commit()
        self.assertEqual(self.choices().rows,());self.assertEqual(self.choices(code='P1').rows,())

    def test_33_matches_refuse_whole_list_and_exact_code_recovers(self):
        for n in range(33):self.catalog('Products','P'+str(n).zfill(2),'Item')
        result=self.choices();self.assertEqual((result.rows,result.error),((),'too_many_matches'))
        exact=self.choices(code='P32');self.assertIsNone(exact.error);self.assertEqual(len(exact.rows),1)

    def test_exactly_32_matches_are_complete_not_truncated(self):
        for n in range(32):self.catalog('Products','P'+str(n).zfill(2),'Item')
        result=self.choices();self.assertEqual(len(result.rows),32);self.assertIsNone(result.error)

    def test_wrong_report_dimension_code_and_subclasses_denied_before_lease(self):
        class Text(str):pass
        with patch.object(self.backend,'begin_read',side_effect=AssertionError('read')):
            for report,dimension,code in [('StockBalance','Product',''),('StockStatement','product',''),
                ('StockStatement','Unknown',''),('StockStatement','Product','x'*9),
                ('StockStatement','Product','\x00'),('StockStatement','Product','\ud800'),
                ('StockStatement','Product',Text('P1')),(object(),'Product','')]:
                with self.subTest(report=type(report).__name__,dimension=dimension):
                    self.refused(lambda:self.service.choices(report,dimension,code))

    def test_one_lease_canonical_source_and_scan_share_owner(self):
        self.catalog('Products','P1','Item');original=self.backend.begin_read
        with patch.object(self.backend,'begin_read',wraps=original) as begin, \
             patch.object(self.backend,'export_configuration',side_effect=AssertionError('source lease')):
            self.choices()
        self.assertEqual(begin.call_count,1);self.assertIsNone(self.backend._active)

    def test_same_generation_source_tamper_denied_before_scan(self):
        path='InventoryApplication.xml';raw=self.files[path]+b'\n'
        self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',(raw,sha256(raw).hexdigest(),path))
        with patch.object(_View,'scan_catalog',side_effect=AssertionError('scan')):self.refused(self.choices)

    def test_same_generation_schema_tamper_denied(self):
        self.sql("UPDATE catalog_schema SET name='Changed' WHERE identity=?",(str(self.catalogs['Products'].identity),))
        self.refused(self.choices)

    def test_busy_closed_and_execution_owners_denied(self):
        from yadinassi.database_transactions import admission,execution
        with closing(self.backend.begin_read()) as owner:
            with self.assertRaises(BackendError):self.choices()
            self.assertIs(self.backend._active,owner)
        with admission(False):self.refused(self.choices,'unsupported')
        with execution(self.backend):self.refused(self.choices,'unsupported')
        self.context.close();self.refused(self.choices,'closed')

    def test_interrupted_scan_releases_without_result(self):
        with patch.object(_View,'scan_catalog',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.choices()
        self.assertIsNone(self.backend._active)

    def test_choices_never_write_or_resolve_receipts(self):
        before=self.path.read_bytes()
        with patch.object(self.backend,'begin_write',side_effect=AssertionError('write')), \
             patch.object(self.backend,'resolve_unit_of_work',side_effect=AssertionError('resolve')):
            self.choices()
        self.assertEqual(self.path.read_bytes(),before)

    def test_scan_payload_wrong_target_duplicates_or_generation_denied(self):
        from yadinassi.catalog_backend import CatalogPage
        key=self.catalog('Products','P1','One')
        with closing(self.backend.begin_read()) as owner:card=owner.read_catalog(key)
        for page in (CatalogPage((card,card),None),CatalogPage((replace(card,key=replace(key,catalog_id=uuid4())),),None),
                     CatalogPage((replace(card,revision=replace(card.revision,configuration_generation=2)),),None),
                     CatalogPage((card,),'bad'),CatalogPage([card],None)):
            with self.subTest(page=page),patch.object(_View,'scan_catalog',return_value=page):self.refused(self.choices,'integrity')

    def test_cleanup_interruption_does_not_publish_choices(self):
        original=_View.close
        def close(owner):
            original(owner);raise KeyboardInterrupt()
        with patch.object(_View,'close',autospec=True,side_effect=close):
            with self.assertRaises(KeyboardInterrupt):self.choices()
        self.assertIsNone(self.backend._active)


class InventoryReportControlTests(ControlsFixture,unittest.TestCase):
    def test_exact_service_and_source_required_not_ducktyped(self):
        class Subclass(InventoryReports):pass
        for service in (object(),object.__new__(Subclass)):
            with self.subTest(kind=type(service).__name__),self.assertRaises(BackendError):
                InventoryReportControls(service,self.config)
        with self.assertRaises(BackendError):InventoryReportControls(self.service,replace(self.config,source_digest='0'*64))

    def test_state_starts_none_open_is_detached_all_and_opaque(self):
        self.assertIsNone(self.controls.state);state=self.open()
        self.assertRegex(state['ticket'],r'^setup-[0-9a-f]{32}-[1-9][0-9]*$')
        self.assertEqual(state['filters'],[{'id':'Product','mode':'all','text':''},{'id':'Warehouse','mode':'all','text':''}])
        state['filters'][0]['mode']='selected';self.assertEqual(self.controls.state['filters'][0]['mode'],'all')
        self.assertNotIn(str(self.backend.database_id),json.dumps(self.controls.state))

    def test_begin_rows_are_tokens_not_catalog_keys(self):
        key=self.catalog('Products','P1','Widget');self.open();choice=self.begin()['choice']
        self.assertEqual(set(choice),{'filter','ticket','code','rows','error','navigation'})
        self.assertRegex(choice['ticket'],r'^choice-[0-9a-f]{32}-[1-9][0-9]*$')
        self.assertRegex(choice['rows'][0]['choice'],r'^[0-9a-f]{32}$')
        self.assertEqual(set(choice['rows'][0]),{'choice','code','description'})
        raw=json.dumps(choice);self.assertNotIn(str(key.record_id),raw);self.assertNotIn(str(key.catalog_id),raw)
        choice['rows'][0]['description']='Changed';self.assertEqual(self.controls.state['choice']['rows'][0]['description'],'Widget')

    def test_apply_returns_exact_key_and_new_setup_ticket(self):
        key=self.catalog('Products','P1','Widget');old=self.open()['ticket'];self.begin();state=self.apply_first()
        self.assertNotEqual(state['ticket'],old);self.assertIsNone(state['choice'])
        values=self.controls.resolve(state['report'],state['ticket'])
        self.assertEqual(len(values),1);self.assertEqual(values[0].key,key)
        self.assertEqual(state['filters'][0],{'id':'Product','mode':'selected','text':'Widget'})

    def test_cancel_keeps_committed_selection_and_setup_ticket(self):
        self.catalog('Products','P1','Widget');self.open();self.begin();committed=self.apply_first()
        choice=self.begin()['choice'];cancelled=self.act('cancel',choice=choice['ticket'])
        self.assertEqual(cancelled['filters'],committed['filters']);self.assertEqual(cancelled['ticket'],committed['ticket'])
        self.assertIsNone(cancelled['choice'])

    def test_empty_is_typed_empty_but_clear_is_omitted(self):
        self.open();empty=self.act('empty',filter='Product')
        values=self.controls.resolve(empty['report'],empty['ticket'])
        self.assertEqual(values[0].key.record_id,UUID(int=0));self.assertEqual(empty['filters'][0]['mode'],'empty')
        self.assertEqual(empty['filters'][0]['text'],'(empty reference)')
        cleared=self.act('clear',filter='Product');self.assertNotEqual(cleared['ticket'],empty['ticket'])
        self.assertEqual(self.controls.resolve(cleared['report'],cleared['ticket']),())

    def test_resolve_refuses_open_chooser(self):
        self.open();state=self.begin()
        with self.assertRaisesRegex(BackendError,'busy'):self.controls.resolve(state['report'],state['ticket'])

    def test_filter_replaces_ticket_and_rejects_old_rows(self):
        self.catalog('Products','P1','One');self.catalog('Products','P2','Two');self.open();old=self.begin()['choice']
        new=self.act('filter',choice=old['ticket'],code='P2')['choice'];self.assertNotEqual(old['ticket'],new['ticket'])
        before=self.controls.state
        with self.assertRaises(BackendError):self.act('apply',choice=old['ticket'],value=old['rows'][0]['choice'])
        self.assertEqual(self.controls.state,before);self.assertEqual(new['rows'][0]['code'],'P2')

    def test_row_from_another_current_chooser_does_not_retarget(self):
        self.catalog('Products','P1','One');self.catalog('Warehouses','W1','Place');self.open();old=self.begin()['choice']
        new=self.begin('Warehouse')['choice'];before=self.controls.state
        with self.assertRaises(BackendError):self.act('apply',choice=new['ticket'],value=old['rows'][0]['choice'])
        self.assertEqual(self.controls.state,before)

    def test_foreign_controls_setup_and_chooser_cannot_be_reused(self):
        self.catalog('Products','P1','One');state=self.open();choice=self.begin()['choice']
        other=InventoryReportControls(self.service,self.config);other.action({'report':'StockStatement','action':'open'})
        with self.assertRaises(BackendError):other.action({'report':'StockStatement','ticket':state['ticket'],
            'action':'apply','choice':choice['ticket'],'value':choice['rows'][0]['choice']})

    def test_new_open_retires_all_old_tickets_and_resets_selections(self):
        self.catalog('Products','P1','One');self.open();self.begin();old=self.apply_first();new=self.open()
        self.assertNotEqual(old['ticket'],new['ticket']);self.assertTrue(all(f['mode']=='all' for f in new['filters']))
        with self.assertRaises(BackendError):self.controls.resolve(old['report'],old['ticket'])

    def test_clear_method_drops_choice_and_keys_without_counter_reset(self):
        self.catalog('Products','P1','One');old=self.open();self.begin();self.controls.clear()
        self.assertIsNone(self.controls.state);self.assertEqual(self.controls._selections,());self.assertIsNone(self.controls._choice)
        new=self.open();self.assertNotEqual(old['ticket'],new['ticket'])
        with self.assertRaises(BackendError):self.controls.resolve(old['report'],old['ticket'])

    def test_invalid_action_shapes_preserve_state_and_do_not_scan(self):
        state=self.open()
        malformed=[{},dict(state),{'report':'StockStatement','action':'open','extra':1},
                   {'report':'StockStatement','ticket':state['ticket'],'action':'empty','filter':'product'},
                   {'report':'StockBalance','action':'open'},
                   {'report':'StockStatement','ticket':'stale','action':'clear','filter':'Product'}]
        with patch.object(InventoryReports,'choice_snapshot',side_effect=AssertionError('scan')):
            for params in malformed:
                with self.subTest(params=params),self.assertRaises(BackendError):self.controls.action(params)
                self.assertEqual(self.controls.state,state)

    def test_failed_scan_retires_old_rows_preserves_committed_selection(self):
        self.catalog('Products','P1','One');self.open();self.begin();saved=self.apply_first();old=self.begin()['choice']
        with patch.object(InventoryReports,'choice_snapshot',side_effect=BackendError('storage_error')):
            with self.assertRaises(BackendError):self.act('filter',choice=old['ticket'],code='P1')
        state=self.controls.state;self.assertIsNone(state['choice']);self.assertEqual(state['filters'],saved['filters'])
        self.assertEqual(state['ticket'],saved['ticket'])
        with self.assertRaises(BackendError):self.act('apply',choice=old['ticket'],value=old['rows'][0]['choice'])

    def test_invalid_apply_does_not_consume_or_change_selection(self):
        self.catalog('Products','P1','One');self.open();state=self.begin()
        with self.assertRaises(BackendError):self.act('apply',choice=state['choice']['ticket'],value='0'*32)
        self.assertEqual(self.controls.state,state)

    def test_duplicate_apply_cannot_repeat_with_old_setup(self):
        self.catalog('Products','P1','One');self.open();state=self.begin();choice=state['choice']
        params={'report':state['report'],'ticket':state['ticket'],'action':'apply','choice':choice['ticket'],'value':choice['rows'][0]['choice']}
        saved=self.controls.action(params)
        with self.assertRaises(BackendError):self.controls.action(params)
        self.assertEqual(self.controls.state,saved)

    def test_noncurrent_report_and_ticket_refused_by_resolve(self):
        state=self.open()
        for report,ticket in [('StockBalance',state['ticket']),('StockStatement','other'),('StockStatement',None)]:
            with self.subTest(report=report),self.assertRaises(BackendError):self.controls.resolve(report,ticket)

    def test_generation_exhaustion_never_reuses_ticket_or_changes_selection(self):
        state=self.open()
        with patch(CONTROLS+'MAX_GENERATION',self.controls._generation):
            with self.assertRaises(BackendError):self.act('empty',filter='Product')
            self.assertEqual(self.controls.state,state)
            with self.assertRaises(BackendError):self.open()
            self.assertEqual(self.controls.state,state)

    def test_duplicate_row_tokens_fail_closed(self):
        self.catalog('Products','P1','One');self.catalog('Products','P2','Two');state=self.open()
        with patch(CONTROLS+'secrets.token_hex',return_value='a'*32):
            with self.assertRaises(BackendError):self.begin()
        self.assertEqual(self.controls.state,state)

    def test_wrong_snapshot_binding_or_target_cannot_be_applied(self):
        self.catalog('Products','P1','One');snapshot=self.service.choice_snapshot('StockStatement','Product');self.open()
        invalid=[replace(snapshot,database_id=uuid4()),replace(snapshot,configuration_generation=2),
                 replace(snapshot,source_digest='0'*64),replace(snapshot,dimension='Warehouse'),
                 replace(snapshot,rows=(replace(snapshot.rows[0],key=replace(snapshot.rows[0].key,catalog_id=uuid4())),)),
                 replace(snapshot,rows=list(snapshot.rows)),replace(snapshot,error='too_many_matches')]
        invalid.append(replace(snapshot,rows=tuple(replace(snapshot.rows[0],key=replace(snapshot.rows[0].key,record_id=UUID(int=i+100)),description='x'*1024) for i in range(4096))))
        for value in invalid:
            with self.subTest(value=value),patch.object(InventoryReports,'choice_snapshot',return_value=value),self.assertRaises(BackendError):self.begin()
            self.assertIsNone(self.controls.state['choice'])

    def test_33_matches_are_paged_and_can_filter_again(self):
        for n in range(33):self.catalog('Products','P'+str(n).zfill(2),'Item')
        self.open();choice=self.begin()['choice'];self.assertEqual(len(choice['rows']),32)
        self.assertIsNone(choice['error']);self.assertEqual(choice['navigation']['total'],33)
        self.assertEqual(choice['navigation']['pages'],2)
        exact=self.act('filter',choice=choice['ticket'],code='P01')['choice']
        self.assertEqual(len(exact['rows']),1);self.assertIsNone(exact['error'])

    def test_display_uses_result_labels_not_new_setup_selection_or_catalog(self):
        self.catalog('Products','P1','Old');self.open();self.begin();self.apply_first();result=self.report()
        self.act('clear',filter='Product')
        shown=self.controls.display(result)
        self.assertEqual(shown,[{'id':'Product','mode':'selected','text':'Old'},{'id':'Warehouse','mode':'all','text':''}])
        shown[0]['text']='Changed';self.assertEqual(self.controls.display(result)[0]['text'],'Old')

    def test_display_empty_all_and_selected_in_source_order(self):
        self.catalog('Warehouses','W1','Warehouse');self.open();self.begin('Warehouse');self.apply_first();self.act('empty',filter='Product')
        self.assertEqual(self.controls.display(self.report()),[
            {'id':'Product','mode':'empty','text':'(empty reference)'},
            {'id':'Warehouse','mode':'selected','text':'Warehouse'}])

    def test_display_deleted_card_uses_actual_unavailable_label(self):
        key=self.catalog('Products','P1','Old');self.open();self.begin();self.apply_first()
        with closing(self.backend.begin_read()) as owner:card=owner.read_catalog(key)
        with closing(self.backend.begin_write(uuid4())) as owner:
            owner.update(CatalogDraft(card.key,card.code,card.description,True,card.values,card.tabular_sections),card.revision);owner.commit()
        self.assertEqual(self.controls.display(self.report())[0]['text'],UNAVAILABLE)

    def test_display_missing_label_or_foreign_binding_denied(self):
        self.catalog('Products','P1','One');self.open();self.begin();self.apply_first();result=self.report()
        for bad in [replace(result,labels=()),replace(result,database_id=uuid4()),
                    replace(result,source_digest='0'*64),replace(result,configuration_generation=True),
                    replace(result,labels=result.labels+result.labels)]:
            with self.subTest(bad=bad),self.assertRaises(BackendError):self.controls.display(bad)

    def test_service_source_binding_change_invalidates_setup_without_retarget(self):
        state=self.open()
        with patch.object(self.service,'_binding',(self.backend.database_id,2)):
            with self.assertRaises(BackendError):self.controls.resolve(state['report'],state['ticket'])
            with self.assertRaises(BackendError):self.act('empty',filter='Product')
        self.assertEqual(self.controls.state,state)

    def test_selected_missing_card_is_revalidated_by_report_read(self):
        key=self.catalog('Products','P1','One');self.open();self.begin();self.apply_first()
        from yadinassi.sqlite_catalog_layout import quote_identifier
        self.sql('DELETE FROM '+quote_identifier(self.backend._layout.table_name(key.catalog_id))+' WHERE record_id=?',(str(key.record_id),))
        self.refused(self.report,'invalid_input')

    def test_no_service_scan_on_all_empty_clear_cancel_or_resolve(self):
        self.open();self.begin();choice=self.controls.state['choice']
        with patch.object(InventoryReports,'choice_snapshot',side_effect=AssertionError('scan')):
            self.act('cancel',choice=choice['ticket']);self.act('empty',filter='Product');self.act('clear',filter='Product')
            state=self.controls.state;self.assertEqual(self.controls.resolve(state['report'],state['ticket']),())

    def test_65_pages_revoke_old_choice_and_cursor_without_rescan(self):
        for n in range(65):self.catalog('Products',f'P{n:02}','Item')
        self.open();first=self.begin()['choice']
        with patch.object(InventoryReports,'choice_snapshot',side_effect=AssertionError('rescan')):
            second=self.act('page',choice=first['ticket'],cursor=first['navigation']['next'])['choice']
            self.assertEqual((second['navigation']['page'],len(second['rows'])),(2,32))
            before=self.controls.state
            with self.assertRaises(BackendError):self.act('page',choice=second['ticket'],cursor=first['navigation']['next'])
            with self.assertRaises(BackendError):self.act('apply',choice=second['ticket'],value=first['rows'][0]['choice'])
            self.assertEqual(self.controls.state,before)
            third=self.act('page',choice=second['ticket'],cursor=second['navigation']['next'])['choice']
            self.assertEqual((third['navigation']['page'],len(third['rows'])),(3,1))

    def test_casefold_search_after_exact_restores_full_snapshot(self):
        self.catalog('Products','P1','First');self.catalog('Products','P2','Straße')
        self.open();first=self.begin()['choice']
        exact=self.act('filter',choice=first['ticket'],code='P1')['choice']
        found=self.act('search',choice=exact['ticket'],query='STRASSE')['choice']
        self.assertEqual(found['code'],'');self.assertEqual([r['code'] for r in found['rows']],['P2'])
        with patch.object(InventoryReports,'choice_snapshot',side_effect=AssertionError('rescan')):
            all_rows=self.act('search',choice=found['ticket'],query='')['choice']
            self.assertEqual(all_rows['navigation']['total'],2)

    def test_refresh_exposes_external_rows_preserving_query(self):
        self.catalog('Products','P1','One');self.open();first=self.begin()['choice']
        searched=self.act('search',choice=first['ticket'],query='P')['choice']
        self.catalog('Products','P2','Two')
        unchanged=self.act('search',choice=searched['ticket'],query='P')['choice']
        self.assertEqual(unchanged['navigation']['total'],1)
        fresh=self.act('refresh',choice=unchanged['ticket'])['choice']
        self.assertEqual((fresh['navigation']['total'],fresh['navigation']['query']),(2,'P'))
        with self.assertRaises(BackendError):self.act('apply',choice=fresh['ticket'],value=unchanged['rows'][0]['choice'])

    def test_snapshot_overflow_exact_recovers_full_search_refuses_partial(self):
        self.catalog('Products','P1','One');self.catalog('Products','P2','Two');self.open()
        with patch('yadinassi.inventory_application_reports.MAX_CHOICE_SNAPSHOT_ROWS',1):
            over=self.begin()['choice']
            self.assertEqual((over['rows'],over['navigation'],over['error']),([],None,'snapshot_limit'))
            exact=self.act('filter',choice=over['ticket'],code='P2')['choice']
            self.assertEqual(exact['navigation']['total'],1)
            full=self.act('search',choice=exact['ticket'],query='P2')['choice']
            self.assertEqual((full['rows'],full['navigation'],full['error']),([],None,'snapshot_limit'))

    def test_new_snapshot_choice_can_be_historical_after_external_deletion_mark(self):
        key=self.catalog('Products','P1','Old');self.open();choice=self.begin()['choice']
        with closing(self.backend.begin_read()) as owner:card=owner.read_catalog(key)
        with closing(self.backend.begin_write(uuid4())) as owner:
            owner.update(CatalogDraft(card.key,card.code,card.description,True,card.values,card.tabular_sections),card.revision);owner.commit()
        self.act('apply',choice=choice['ticket'],value=choice['rows'][0]['choice'])
        self.assertEqual(self.controls.display(self.report())[0]['text'],UNAVAILABLE)
        self.assertEqual(self.begin()['choice']['navigation']['total'],0)
