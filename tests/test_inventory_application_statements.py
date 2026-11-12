"""Source-bound statement reports: real owned SQLite, no native/browser run."""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.configuration_inventory_application import (
    PROFILE, InventoryReportFilterGrant, import_inventory_application, canonical, validated_core)
from yadinassi.database_context import SQLiteDBContext
from yadinassi.inventory_application_reports import InventoryReports, InventoryReportFilter, UNAVAILABLE
from yadinassi.sqlite_accumulation_movements import AccumulationMovementPort
from yadinassi.sqlite_catalog import _View
import test_inventory_application_reports as support
from inventory_application_fixture import ROOT, MANIFEST, source

START = datetime(2024, 1, 15, 12)
END = datetime(2024, 3, 20, 12)
REPORTS = 'yadinassi.inventory_application_reports.'


def legacy_source():
    files = source()
    files[MANIFEST] = re.sub(rb'<Report name="StockStatement".*?</Report>', b'', files[MANIFEST])
    return files


def load(files=None):
    return import_inventory_application(source() if files is None else files, inventory_runtime=PROFILE)


class StatementSourceTests(unittest.TestCase):
    def changed(self, old, new):
        files = source(); self.assertIn(old, files[MANIFEST])
        files[MANIFEST] = files[MANIFEST].replace(old, new)
        return files

    def refused(self, files):
        with self.assertRaises(ValueError): load(files)

    def test_old_three_reports_stay_valid_with_no_new_options(self):
        old = load(legacy_source()); new = load()
        self.assertEqual(new.reports[:3], old.reports)
        self.assertEqual([r.view for r in old.reports], ['Movements','Balance','Turnovers'])
        self.assertTrue(all(r.periodicities == r.filters == () for r in old.reports))
        self.assertEqual(validated_core(old), validated_core(new))

    def test_statement_grant_binds_exact_dimension_and_catalog_identity(self):
        config = load(); grant = config.reports[-1]; schema = config.registers[0]
        self.assertEqual((grant.name,grant.view,grant.periodicities),
                         ('StockStatement','BalanceAndTurnovers',('None','Day','Month')))
        self.assertEqual(grant.filters, tuple(InventoryReportFilterGrant(f.name,f.identity,f.target_catalog_id)
                                             for f in schema.dimensions))

    def test_statement_and_options_change_full_digest_not_core_projection(self):
        config = load(); files = self.changed(b'<Periodicity name="Month"/>', b'')
        other = load(files)
        self.assertNotEqual(config.source_digest, other.source_digest)
        self.assertEqual(config.core_projection_digest, other.core_projection_digest)
        self.assertEqual(dict(other.files), files)

    def test_missing_or_duplicate_periodicity_denied(self):
        self.refused(self.changed(b'<Periodicity name="Day"/>', b'<Periodicity name="None"/>'))
        files = source(); files[MANIFEST] = re.sub(rb'<Periodicity name="[^"]+"/>', b'', files[MANIFEST])
        self.refused(files)

    def test_unknown_case_timeout_and_extra_periodicity_fields_denied(self):
        for item in (b'<Periodicity name="day"/>', b'<Periodicity name="Year"/>',
                     b'<Periodicity name="Day" extra="x"/>', b'<Periodicity name="Day">x</Periodicity>'):
            with self.subTest(item=item): self.refused(self.changed(b'<Periodicity name="Day"/>', item))

    def test_periodicity_after_filter_denied(self):
        self.refused(self.changed(b'</Report>', b'<Periodicity name="Day"/></Report>'))

    def test_filter_name_uuid_target_and_shape_are_closed(self):
        for old,new in [(b'dimension="Product"',b'dimension="product"'),
                        (b'dimensionId="277c63d2-4e4b-5746-9237-e74144a8b8d9"',b'dimensionId="00000000-0000-0000-0000-000000000001"'),
                        (b'catalogId="afdf0d36-94e5-5b46-a396-1e0283921f02"',b'catalogId="9ccac98d-93d7-5a53-a195-7bfab9d06bd6"'),
                        (b'dimension="Product"',b'dimension="Product" sql="x"')]:
            with self.subTest(old=old): self.refused(self.changed(old,new))

    def test_duplicate_filter_denied(self):
        files=source(); item=re.search(rb'<Filter dimension="Product"[^>]*/>',files[MANIFEST]).group()
        self.refused(self.changed(item,item+item))

    def test_filter_is_optional_but_cannot_be_invented_by_caller(self):
        files=source();files[MANIFEST]=re.sub(rb'<Filter [^>]*/>',b'',files[MANIFEST])
        self.assertEqual(load(files).reports[-1].filters,())

    def test_unknown_statement_child_and_content_denied(self):
        for child in (b'<Order field="Product"/>',b'<Filter/>',b'unexpected'):
            with self.subTest(child=child): self.refused(self.changed(b'</Report>',child+b'</Report>'))

    def test_legacy_views_cannot_acquire_options(self):
        for view in (b'Movements',b'Balance',b'Turnovers'):
            with self.subTest(view=view):
                self.refused(self.changed(b'view="'+view+b'"/>',b'view="'+view+b'"><Periodicity name="None"/></Report>'))

    def test_canonical_reimport_refuses_forged_options(self):
        config=load(); grant=config.reports[-1]
        for changed in (replace(grant,periodicities=('Year',)),replace(grant,filters=()),
                        replace(grant,filters=(replace(grant.filters[0],catalog_id=uuid4()),))):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                canonical(replace(config,reports=config.reports[:-1]+(changed,)))

    def test_grants_are_immutable_and_exact_type_checked(self):
        config=load();grant=config.reports[-1]
        with self.assertRaises(FrozenInstanceError): grant.filters[0].dimension='Other'
        with self.assertRaises(ValueError): canonical(replace(config,reports=config.reports[:-1]+(replace(grant,periodicities=list(grant.periodicities)),)))

    def test_statement_filter_count_is_bounded(self):
        with patch('yadinassi.configuration_inventory_application.MAX_REPORT_FILTERS',1):
            self.refused(source())


class StatementReportTests(unittest.TestCase):
    setUp = support.InventoryReportTests.setUp
    catalog = support.InventoryReportTests.catalog
    post = support.InventoryReportTests.post
    sql = support.InventoryReportTests.sql
    refused = support.InventoryReportTests.refused
    named = support.InventoryReportTests.named

    def read(self, *, start=START, end=END, periodicity='None', filters=(), **kwargs):
        return self.service.read('StockStatement',start=start,end=end,periodicity=periodicity,filters=filters,**kwargs)

    def selection(self, dimension, key, generation=None):
        field=next(f for f in self.config.registers[0].dimensions if f.name==dimension)
        return InventoryReportFilter(field.identity,key,self.backend.configuration_generation if generation is None else generation)

    def test_empty_none_day_month_have_exact_typed_columns(self):
        for period in ('None','Day','Month'):
            with self.subTest(period=period):
                result=self.read(periodicity=period)
                self.assertEqual((result.rows,result.labels,result.filters),((),(),()))
                self.assertEqual(result.periodicity,period)
                expected=['Product','Warehouse']+([] if period=='None' else ['Period'])
                expected += [r.name+s for s in ('OpeningBalance','Receipt','Expense','ClosingBalance') for r in self.config.registers[0].resources]
                self.assertEqual([c.name for c in result.columns],expected)

    def test_opening_strict_before_and_flow_both_endpoints_inclusive(self):
        self.post('10','100',date=START-timedelta(seconds=1))
        self.post('2','20',date=START);self.post('3','30',name='Issue',date=END)
        self.post('99','990',date=END+timedelta(seconds=1))
        row=self.named(self.read())[0]
        self.assertEqual([row['Quantity'+s] for s in ('OpeningBalance','Receipt','Expense','ClosingBalance')],
                         [Decimal(10),Decimal(2),Decimal(3),Decimal(9)])

    def test_none_has_no_synthetic_period_column(self):
        self.post(date=START)
        result=self.read();self.assertNotIn('Period',[c.name for c in result.columns])
        self.assertEqual(result.boundaries,(START,END))

    def test_day_clips_first_label_and_preserves_sparse_boundary_rows(self):
        self.post(date=START-timedelta(days=1));self.post('2','20',date=START+timedelta(days=2))
        rows=self.named(self.read(periodicity='Day'))
        self.assertEqual([r['Period'] for r in rows],[START,datetime(2024,1,17),datetime(2024,3,20)])
        self.assertEqual([r['QuantityClosingBalance'] for r in rows],[Decimal(10),Decimal(12),Decimal(12)])

    def test_month_boundary_carry_is_sparse_not_daily_gap_fill(self):
        self.post(date=START-timedelta(days=1));self.post('3','30',name='Issue',date=datetime(2024,2,1))
        rows=self.named(self.read(periodicity='Month'))
        self.assertEqual([r['Period'] for r in rows],[START,datetime(2024,2,1),datetime(2024,3,1)])
        self.assertEqual(rows[-1]['QuantityOpeningBalance'],Decimal(7))

    def test_opening_only_appears_at_requested_boundary_buckets(self):
        self.post(date=START-timedelta(days=1))
        rows=self.named(self.read(periodicity='Month'))
        self.assertEqual([r['Period'] for r in rows],[START,datetime(2024,3,1)])
        self.assertTrue(all(r['QuantityReceipt']==r['QuantityExpense']==0 for r in rows))

    def test_zero_vectors_are_omitted_without_poisoning_other_groups(self):
        self.post('0','0',date=START)
        self.assertEqual(self.read().rows,())
        other=self.catalog('Products','P2','Other');self.post('2','20',date=START,product=other)
        self.assertEqual(len(self.read().rows),1)

    def test_repeated_occurrences_keep_exact_decimal_scale_in_hostile_context(self):
        self.post('1.125','10.05',date=START,lines=2)
        with localcontext() as context:
            context.prec=2;context.clear_flags();row=self.named(self.read())[0]
            self.assertEqual(row['QuantityReceipt'].as_tuple(),Decimal('2.250').as_tuple())
            self.assertEqual(row['AmountClosingBalance'].as_tuple(),Decimal('20.10').as_tuple())
            self.assertFalse(any(context.flags.values()))

    def test_reducer_is_reused_without_query_or_handler_execution(self):
        self.post(date=START)
        from yadinassi.accumulation_periods import StatementReducer
        original=StatementReducer.add
        with patch.object(StatementReducer,'add',autospec=True,side_effect=original) as add, \
             patch.object(self.backend,'begin_write',side_effect=AssertionError('write')), \
             patch.object(self.backend,'resolve_unit_of_work',side_effect=AssertionError('resolve')):
            self.read()
        self.assertEqual(add.call_count,1)

    def test_two_catalog_filters_are_and_not_label_matching(self):
        self.post(date=START)
        other=self.catalog('Products','P2','Product');self.post('2','20',date=START,product=other)
        filters=(self.selection('Warehouse',self.warehouse),self.selection('Product',other))
        result=self.read(filters=filters);row=self.named(result)[0]
        self.assertEqual(row['Product'],other);self.assertEqual(row['QuantityReceipt'],Decimal(2))
        self.assertEqual(result.filters,tuple(reversed(filters)))

    def test_explicit_empty_reference_filter_is_not_omitted(self):
        self.post(date=START)
        empty=CatalogKey(self.backend.database_id,self.product.catalog_id,UUID(int=0))
        self.post('2','20',date=START,product=empty)
        filtered=self.read(filters=(self.selection('Product',empty),))
        self.assertEqual(len(self.read().rows),2);self.assertEqual(len(filtered.rows),1)
        self.assertEqual(self.named(filtered)[0]['Product'],empty)
        self.assertEqual(dict(filtered.labels)[empty],UNAVAILABLE)

    def test_nonempty_missing_filter_card_refused_same_lease(self):
        self.post(date=START);missing=replace(self.product,record_id=uuid4())
        self.refused(lambda:self.read(filters=(self.selection('Product',missing),)),'invalid_input')

    def test_soft_deleted_historical_filter_is_readonly_unavailable(self):
        self.post(date=START)
        with closing(self.backend.begin_read()) as owner: card=owner.read_catalog(self.product)
        with closing(self.backend.begin_write(uuid4())) as owner:
            owner.update(CatalogDraft(card.key,card.code,card.description,True,card.values,card.tabular_sections),card.revision);owner.commit()
        before=self.path.read_bytes();result=self.read(filters=(self.selection('Product',self.product),))
        self.assertEqual(len(result.rows),1);self.assertEqual(dict(result.labels)[self.product],UNAVAILABLE)
        self.assertEqual(self.path.read_bytes(),before)

    def test_filter_label_retained_even_when_no_matching_movements(self):
        key=self.catalog('Products','P2','Unused')
        result=self.read(filters=(self.selection('Product',key),))
        self.assertEqual(result.rows,());self.assertEqual(result.labels,((key,'Unused'),))

    def test_filter_wrong_database_target_generation_and_dimension_denied(self):
        self.post();good=self.selection('Product',self.product)
        invalid=[replace(good,key=replace(self.product,database_id=uuid4())),
                 replace(good,key=self.warehouse),replace(good,dimension_id=uuid4()),
                 replace(good,configuration_generation=2),replace(good,configuration_generation=True)]
        with patch.object(self.backend,'begin_read',side_effect=AssertionError('lease')):
            for value in invalid:
                with self.subTest(value=value):self.refused(lambda:self.read(filters=(value,)))

    def test_filter_exact_types_and_duplicate_dimension_denied(self):
        self.post();good=self.selection('Product',self.product)
        class FilterSubclass(InventoryReportFilter): pass
        class KeySubclass(CatalogKey): pass
        invalid=[(good,good),[good],(object(),),(replace(good,key=KeySubclass(*[getattr(self.product,k) for k in ('database_id','catalog_id','record_id')])),),
                 (FilterSubclass(good.dimension_id,good.key,1),),(replace(good,dimension_id=str(good.dimension_id)),),
                 (replace(good,key=replace(self.product,record_id='bad')),)]
        with patch.object(self.backend,'begin_read',side_effect=AssertionError('lease')):
            for values in invalid:
                with self.subTest(kind=type(values).__name__):self.refused(lambda:self.read(filters=values),'invalid_input')

    def test_filter_options_never_call_arbitrary_equality_or_string_hooks(self):
        class Hostile:
            def __eq__(self,other):raise AssertionError('eq')
            def __str__(self):raise AssertionError('str')
        with patch.object(self.backend,'begin_read',side_effect=AssertionError('lease')):
            self.refused(lambda:self.read(periodicity=Hostile()),'invalid_input')
            self.refused(lambda:self.read(filters=(Hostile(),)),'invalid_input')

    def test_source_declared_subset_does_not_grant_other_periods_or_filters(self):
        files=source();files[MANIFEST]=files[MANIFEST].replace(b'<Periodicity name="Month"/>',b'')
        files[MANIFEST]=re.sub(rb'<Filter dimension="Product"[^>]*/>',b'',files[MANIFEST])
        config=load(files)
        with closing(SQLiteDBContext.create_inventory_application(Path(self.temp.name)/'restricted.sqlite',config)) as context:
            service=InventoryReports(context,config)
            with self.assertRaises(BackendError):service.read('StockStatement',start=START,end=END,periodicity='Month')
            field=config.registers[0].dimensions[0]
            with self.assertRaises(BackendError):service.read('StockStatement',start=START,end=END,periodicity='None',
                filters=(InventoryReportFilter(field.identity,CatalogKey(context.backend.database_id,field.target_catalog_id,UUID(int=0)),1),))

    def test_legacy_reports_refuse_statement_options_without_lease(self):
        with patch.object(self.backend,'begin_read',side_effect=AssertionError('lease')):
            for kwargs in ({'periodicity':'None'},{'filters':[ ]},{'filters':(object(),)}):
                with self.subTest(kwargs=kwargs):self.refused(lambda:self.service.read('StockMovements',**kwargs),'invalid_input')

    def test_dates_1900_2099_exact_seconds_and_missing_periodicity(self):
        invalid=[{'start':datetime(1899,12,31)},{'end':datetime(2100,1,1)},
                 {'start':START.replace(microsecond=1)},{'end':END.replace(tzinfo=timezone.utc)},
                 {'start':END,'end':START},{'start':START.replace(fold=1)},
                 {'periodicity':None},{'periodicity':'day'},{'at':START}]
        with patch.object(self.backend,'begin_read',side_effect=AssertionError('lease')):
            for kwargs in invalid:
                with self.subTest(kwargs=kwargs):self.refused(lambda:self.read(**kwargs),'invalid_input')
        self.assertEqual(self.read(start=datetime(1900,1,1),end=datetime(2099,12,31,23,59,59)).rows,())

    def test_prior_1900_rows_contribute_to_opening_not_silently_dropped(self):
        self.post(date=datetime(1899,12,31))
        row=self.named(self.read(start=datetime(1900,1,1)))[0]
        self.assertEqual(row['QuantityOpeningBalance'],Decimal(10))

    def test_unknown_keyword_is_refused_not_ignored(self):
        with patch.object(self.backend,'begin_read',side_effect=AssertionError('lease')):
            with self.assertRaises(TypeError):self.read(sql='SELECT 1')

    def test_every_row_budget_is_charged_before_catalog_and_period_filters(self):
        self.post(date=START,lines=2);other=self.catalog('Products','P2','Unused')
        for constant in ('MAX_INPUT_ROWS','MAX_INPUT_CELLS','MAX_TEXT'):
            with self.subTest(constant=constant),patch(REPORTS+constant,1):
                self.refused(lambda:self.read(start=datetime(2020,1,1),end=datetime(2020,1,2),
                    filters=(self.selection('Product',other),)),'unsupported')

    def test_sparse_boundary_expansion_output_caps_refuse_no_truncation(self):
        self.post(date=START-timedelta(days=1))
        for constant,value in (('MAX_ROWS',1),('MAX_CELLS',1)):
            with self.subTest(constant=constant),patch(REPORTS+constant,value):
                self.refused(lambda:self.read(periodicity='Day'),'unsupported')

    def test_filter_label_caps_also_apply_to_empty_results(self):
        self.post();filters=(self.selection('Product',self.product),self.selection('Warehouse',self.warehouse))
        for constant,value in (('MAX_LABELS',1),('MAX_LABEL_LENGTH',1)):
            with self.subTest(constant=constant),patch(REPORTS+constant,value):
                self.refused(lambda:self.read(start=datetime(2020,1,1),end=datetime(2020,1,2),filters=filters),'unsupported')

    def test_dimension_then_period_sort_is_deterministic(self):
        self.post(date=START);other=self.catalog('Products','P2','Other');self.post(date=END,product=other)
        result=self.read(periodicity='Day');rows=result.rows
        self.assertEqual(rows,tuple(sorted(rows,key=lambda row:(row[0].record_id.int,row[1].record_id.int,row[2]))))
        self.assertEqual(result,self.read(periodicity='Day'))

    def test_one_lease_covers_admission_filter_cards_movements_and_labels(self):
        self.post(date=START);original=self.backend.begin_read;lookup=_View.read_catalog
        with patch.object(self.backend,'begin_read',wraps=original) as begin, \
             patch.object(self.backend,'export_configuration',side_effect=AssertionError('second source lease')), \
             patch.object(self.backend,'begin_document_read',side_effect=AssertionError('second document lease')), \
             patch.object(_View,'read_catalog',autospec=True,side_effect=lookup) as read:
            self.read(filters=(self.selection('Product',self.product),))
        self.assertEqual(begin.call_count,1);self.assertEqual(read.call_count,2)
        self.assertIsNone(self.backend._active)

    def test_same_generation_manifest_bytes_and_digest_tamper_refused(self):
        raw=self.files[MANIFEST].replace(b'<Periodicity name="Month"/>',b'')
        self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',(raw,sha256(raw).hexdigest(),MANIFEST))
        self.refused(self.read)

    def test_same_generation_schema_tamper_refused_before_scan(self):
        self.sql("UPDATE accumulation_register_schema SET definition=replace(definition,'Quantity','Changed')")
        with patch.object(AccumulationMovementPort,'scan',side_effect=AssertionError('scan')):self.refused(self.read)

    def test_statement_result_filters_and_rows_are_detached_frozen(self):
        self.post(date=START);selection=self.selection('Product',self.product);result=self.read(filters=(selection,))
        with self.assertRaises(FrozenInstanceError):result.periodicity='Day'
        with self.assertRaises(FrozenInstanceError):result.filters[0].configuration_generation=2
        self.host.close();self.context.close()
        self.assertEqual(self.named(result)[0]['QuantityClosingBalance'],Decimal(10))
        self.assertEqual(dict(result.labels)[self.product],'Product')

    def test_interrupt_during_reducer_or_filter_lookup_releases_lease(self):
        self.post(date=START)
        from yadinassi.accumulation_periods import StatementReducer
        for target,method in ((StatementReducer,'add'),(_View,'read_catalog')):
            with self.subTest(method=method),patch.object(target,method,side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):self.read(filters=(self.selection('Product',self.product),))
            self.assertIsNone(self.backend._active)

    def test_live_writer_or_execution_never_gains_report_authority(self):
        from yadinassi.database_transactions import execution, admission
        with execution(self.backend):self.refused(self.read,'unsupported')
        with admission(False):self.refused(self.read,'unsupported')
        with closing(self.backend.begin_read()) as owner:
            with self.assertRaises(BackendError):self.read()
            self.assertIs(self.backend._active,owner)
