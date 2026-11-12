"""Real owned SQLite report snapshots; no browser/native acquisition."""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.accumulation_movements import AccumulationDirection
from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey, TabularRow, TabularSectionRows
from yadinassi.configuration_inventory_application import import_inventory_application, PROFILE, validated_core
from yadinassi.database_context import SQLiteDBContext
from yadinassi.database_transactions import admission, execution
from yadinassi.document_backend import DocumentDraft, DocumentKey
from yadinassi.inventory_application_reports import InventoryReports, UNAVAILABLE
from yadinassi.inventory_host_operations import InventoryRootOperations
from yadinassi.sqlite_accumulation_movements import AccumulationMovementPort
from yadinassi.sqlite_catalog import _View
from yadinassi.sqlite_query_indexes import register_query_collations
from inventory_application_fixture import ROOT, source

DATE = datetime(2024, 1, 1, 12)
AT = DATE + timedelta(days=1)
REPORTS = 'yadinassi.inventory_application_reports.'


class InventoryReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.files = source()
        self.config = import_inventory_application(self.files, inventory_runtime=PROFILE)
        self.path = Path(self.temp.name) / 'reports.sqlite'
        self.context = SQLiteDBContext.create_inventory_application(self.path, self.config)
        self.addCleanup(self.context.close)
        self.backend = self.context.backend
        self.service = InventoryReports(self.context, self.config)
        self.host = None
        self.catalogs = {s.name: s for s in self.config.catalogs}
        self.documents = {s.name: s for s in self.config.documents}
        self.product = self.warehouse = None
        self.serial = 0

    def catalog(self, name, code, description):
        key = CatalogKey(self.backend.database_id, self.catalogs[name].identity, uuid4())
        with closing(self.backend.begin_write(uuid4())) as owner:
            owner.create(CatalogDraft(key, code, description, False, (), ()))
            owner.commit()
        return key

    def post(self, quantity='10', amount='100', *, name='Receipt', date=DATE,
             product=None, warehouse=None, command='Post', lines=1):
        if self.product is None:
            self.product = self.catalog('Products', 'P1', 'Product')
            self.warehouse = self.catalog('Warehouses', 'W1', 'Warehouse')
        if self.host is None:
            self.host = InventoryRootOperations(self.context, self.config)
            self.addCleanup(self.host.close)
        schema = self.documents[name]
        self.serial += 1
        draft = DocumentDraft(DocumentKey(self.backend.database_id, schema.identity, uuid4()),
            str(self.serial), date, False, (warehouse or self.warehouse,),
            (TabularSectionRows(schema.tabular_sections[0].identity,
                tuple(TabularRow(uuid4(), (product or self.product, Decimal(quantity), Decimal(amount)))
                      for _ in range(lines))),), False)
        receipt = self.host.execute(uuid4(), draft, None, form='Document.' + name + '.Form.Card', command=command)
        self.assertEqual(receipt.state, 'committed')
        return draft

    def read(self, name='StockMovements', **kwargs):
        return self.service.read(name, **kwargs)

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.path)) as c:
            register_query_collations(c)
            result = c.execute(statement, args).fetchall()
            c.commit()
            return result

    def refused(self, callback, code=None):
        with self.assertRaises(BackendError) as caught:
            callback()
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        self.assertIsNone(self.backend._active)

    def named(self, result):
        return [dict(zip((c.name for c in result.columns), row)) for row in result.rows]

    def test_empty_all_three_views_are_typed(self):
        for name, args in [('StockMovements', {}), ('StockBalance', {'at': AT}),
                           ('StockTurnovers', {'start': DATE, 'end': AT})]:
            with self.subTest(name=name):
                r = self.read(name, **args)
                self.assertEqual((r.rows, r.labels), ((), ()))
                self.assertTrue(r.columns)
                self.assertEqual((r.database_id, r.configuration_generation, r.source_digest),
                    (self.backend.database_id, 1, self.config.source_digest))

    def test_raw_rows_retain_exact_types_and_original_direction(self):
        draft = self.post()
        r = self.read(); row = self.named(r)[0]
        self.assertEqual(row['Recorder'], draft.key)
        self.assertIs(type(row['Recorder']), DocumentKey)
        self.assertIs(type(row['Product']), CatalogKey)
        self.assertIs(type(row['Period']), datetime)
        self.assertIs(type(row['Quantity']), Decimal)
        self.assertEqual(row['LineNumber'], Decimal(1))
        self.assertIs(row['RecordType'], AccumulationDirection.RECEIPT)
        self.assertIs(row['Active'], True)

    def test_balance_exclusive_boundary(self):
        self.post()
        self.assertEqual(self.read('StockBalance', at=DATE).rows, ())
        self.assertEqual(self.named(self.read('StockBalance', at=DATE+timedelta(seconds=1)))[0]['QuantityBalance'], Decimal(10))

    def test_turnovers_includes_both_endpoints(self):
        self.post(date=DATE); self.post('2', '20', date=AT)
        row = self.named(self.read('StockTurnovers', start=DATE, end=AT))[0]
        self.assertEqual(row['QuantityTurnover'], Decimal(12))
        self.assertEqual(row['QuantityReceipt'], Decimal(12))
        self.assertEqual(row['QuantityExpense'], Decimal(0))

    def test_receipt_and_expense_are_separate_positive_vectors(self):
        self.post(); self.post('3', '30', name='Issue', date=DATE+timedelta(seconds=1))
        row = self.named(self.read('StockTurnovers', start=DATE, end=AT))[0]
        self.assertEqual((row['QuantityTurnover'], row['QuantityReceipt'], row['QuantityExpense']),
                         (Decimal(7), Decimal(10), Decimal(3)))

    def test_zero_balance_omitted_but_nonzero_turnovers_retained(self):
        self.post(); self.post(name='Issue', date=DATE+timedelta(seconds=1))
        self.assertEqual(self.read('StockBalance', at=AT).rows, ())
        self.assertEqual(self.named(self.read('StockTurnovers', start=DATE, end=AT))[0]['QuantityTurnover'], Decimal(0))

    def test_all_zero_turnover_group_is_refused(self):
        self.post('0', '0')
        self.refused(lambda: self.read('StockTurnovers', start=DATE, end=AT), 'unsupported')

    def test_duplicate_occurrences_are_not_deduplicated(self):
        self.post(lines=2)
        self.assertEqual(len(self.read().rows), 2)
        self.assertEqual(self.named(self.read('StockBalance', at=AT))[0]['QuantityBalance'], Decimal(20))

    def test_write_without_post_has_no_movements(self):
        self.post(command='Write')
        self.assertEqual(self.read().rows, ())

    def test_undo_posting_removes_rows_on_next_snapshot(self):
        draft = self.post(); old = self.read()
        with closing(self.backend.begin_document_read()) as v:
            revision = v.read_document(draft.key).revision
        self.host.execute(uuid4(), draft, revision, form='Document.Receipt.Form.Card', command='UndoPosting')
        self.assertEqual(self.read().rows, ())
        self.assertEqual(len(old.rows), 1)

    def test_raw_order_is_period_recorder_line_not_insertion(self):
        self.post(date=AT); self.post(date=DATE, lines=2)
        rows = self.read().rows
        self.assertEqual(rows, tuple(sorted(rows, key=lambda r:(r[0],r[1].document_id.int,r[1].record_id.int,r[2]))))
        self.assertEqual(rows[0][0], DATE)

    def test_totals_order_is_deterministic_typed_dimension_identity(self):
        self.post()
        product = self.catalog('Products', 'P2', 'Another')
        self.post(product=product)
        r = self.read('StockBalance', at=AT)
        index = next(i for i,c in enumerate(r.columns) if c.name=='Product')
        self.assertEqual([row[index].record_id.int for row in r.rows], sorted([self.product.record_id.int, product.record_id.int]))
        self.assertEqual(r, self.read('StockBalance', at=AT))

    def test_sums_ignore_ambient_decimal_precision_and_preserve_scale(self):
        self.post('1.125', '10.05'); self.post('2.125', '20.05')
        with localcontext() as c:
            c.prec = 2; c.clear_flags()
            row = self.named(self.read('StockBalance', at=AT))[0]
            self.assertEqual(row['QuantityBalance'].as_tuple(), Decimal('3.250').as_tuple())
            self.assertEqual(row['AmountBalance'], Decimal('30.10'))
            self.assertFalse(any(c.flags.values()))

    def test_result_columns_rows_and_labels_are_frozen(self):
        self.post(); r = self.read()
        self.assertIs(type(r.rows), tuple); self.assertIs(type(r.rows[0]), tuple)
        with self.assertRaises(FrozenInstanceError): r.report = 'other'
        with self.assertRaises(FrozenInstanceError): r.columns[0].name = 'other'
        with self.assertRaises(TypeError): r.rows[0][0] = AT
        with self.assertRaises(TypeError): r.labels[0] = ()

    def test_labels_include_exact_reference_and_recorder_keys(self):
        draft = self.post(); r = self.read(); labels = dict(r.labels)
        self.assertEqual(labels[self.product], 'Product')
        self.assertEqual(labels[self.warehouse], 'Warehouse')
        self.assertEqual(labels[draft.key], 'Receipt 1 (2024-01-01 12:00:00)')

    def test_repeated_references_have_one_label_lookup(self):
        self.post(lines=2)
        original = _View.read_catalog
        with patch.object(_View, 'read_catalog', autospec=True, side_effect=original) as lookup:
            r = self.read()
        self.assertEqual(lookup.call_count, 2)
        self.assertEqual(len(r.labels), 3)

    def test_deleted_catalog_label_is_unavailable(self):
        self.post()
        with closing(self.backend.begin_read()) as v: card = v.read_catalog(self.product)
        with closing(self.backend.begin_write(uuid4())) as v:
            v.update(CatalogDraft(card.key, card.code, card.description, True, card.values, card.tabular_sections), card.revision)
            v.commit()
        self.assertEqual(dict(self.read().labels)[self.product], UNAVAILABLE)

    def test_deleted_recorder_label_is_unavailable(self):
        draft = self.post()
        self.sql('UPDATE document_record SET deletion_mark=1 WHERE document_id=? AND record_id=?',
                 (str(draft.key.document_id), str(draft.key.record_id)))
        self.assertEqual(dict(self.read().labels)[draft.key], UNAVAILABLE)

    def test_empty_reference_label_is_unavailable(self):
        self.post()
        empty = CatalogKey(self.backend.database_id, self.product.catalog_id, UUID(int=0))
        self.post(product=empty)
        self.assertEqual(dict(self.read().labels)[empty], UNAVAILABLE)

    def test_missing_nonempty_reference_is_integrity_failure_not_placeholder(self):
        self.post()
        from yadinassi.sqlite_catalog_layout import quote_identifier
        table = quote_identifier(self.backend._layout.table_name(self.product.catalog_id))
        self.sql('DELETE FROM '+table+' WHERE record_id=?', (str(self.product.record_id),))
        self.refused(self.read, 'integrity')

    def test_one_lease_for_admission_movements_and_labels(self):
        self.post(); original = self.backend.begin_read
        with patch.object(self.backend, 'begin_read', wraps=original) as begin, \
             patch.object(self.backend, 'export_configuration', side_effect=AssertionError('second connection')), \
             patch.object(self.backend, 'begin_document_read', side_effect=AssertionError('second lease')):
            self.read()
        self.assertEqual(begin.call_count, 1)
        self.assertIsNone(self.backend._active)

    def test_labels_and_movements_share_real_sqlite_read_snapshot(self):
        self.post(); original = AccumulationMovementPort.scan
        from yadinassi.sqlite_catalog_layout import quote_identifier
        table = quote_identifier(self.backend._layout.table_name(self.product.catalog_id))
        def scan(port, identity):
            rows = original(port, identity)
            with closing(sqlite3.connect(self.path, timeout=0)) as other:
                other.execute('UPDATE '+table+' SET description=? WHERE record_id=?', ('Changed',str(self.product.record_id)))
                with self.assertRaises(sqlite3.OperationalError): other.commit()
                other.rollback()
            return rows
        with patch.object(AccumulationMovementPort, 'scan', autospec=True, side_effect=scan):
            self.assertEqual(dict(self.read().labels)[self.product], 'Product')
        self.sql('UPDATE '+table+' SET description=? WHERE record_id=?', ('Changed',str(self.product.record_id)))
        self.assertEqual(dict(self.read().labels)[self.product], 'Changed')

    def test_no_writes_receipts_or_handlers_during_report(self):
        self.post(); before = self.path.read_bytes()
        with patch.object(self.backend,'begin_write',side_effect=AssertionError('write')), \
             patch.object(self.backend,'begin_unit_of_work',side_effect=AssertionError('journal')), \
             patch.object(self.backend,'resolve_unit_of_work',side_effect=AssertionError('resolve')):
            self.read(); self.read('StockBalance', at=AT)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNone(getattr(self.backend,'_bsl_transaction',None))

    def test_invalid_names_never_open_lease(self):
        with patch.object(self.backend,'begin_read',side_effect=AssertionError('read')):
            for name in ['stockmovements', 'SELECT *', '', 'Stock', uuid4(), object()]:
                with self.subTest(name=type(name).__name__): self.refused(lambda:self.read(name))

    def test_period_contract_rejects_unknown_or_missing_options(self):
        for name,args in [('StockMovements',{'at':DATE}),('StockBalance',{}),
                          ('StockBalance',{'at':AT,'start':DATE}),('StockTurnovers',{'start':DATE}),
                          ('StockTurnovers',{'start':AT,'end':DATE}),('StockTurnovers',{'at':AT,'start':DATE,'end':AT})]:
            with self.subTest(name=name,args=args): self.refused(lambda:self.read(name,**args),'invalid_input')

    def test_dates_require_exact_naive_second_resolution_without_fold(self):
        class DateSubclass(datetime): pass
        for at in [DATE.isoformat(), DateSubclass(2024,1,1), DATE.replace(microsecond=1),
                   DATE.replace(tzinfo=timezone.utc), DATE.replace(fold=1)]:
            with self.subTest(kind=type(at).__name__): self.refused(lambda:self.read('StockBalance',at=at),'invalid_input')

    def test_forged_full_configuration_is_refused(self):
        self.refused(lambda:InventoryReports(self.context,replace(self.config,source_digest='0'*64)),'unsupported')

    def test_same_generation_source_bytes_and_hash_tamper_refused(self):
        path='Documents/Receipt/Ext/ObjectModule.bsl'; raw=self.files[path]+b'\n// changed\n'
        self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',(raw,sha256(raw).hexdigest(),path))
        self.refused(self.read)

    def test_bad_source_hash_is_refused(self):
        self.sql("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'",('0'*64,))
        self.refused(self.read)

    def test_source_kind_tamper_is_refused(self):
        self.sql("UPDATE configuration_file SET kind='module' WHERE path='Configuration.xml'")
        self.refused(self.read)

    def test_profile_marker_downgrade_is_refused(self):
        self.sql("UPDATE inventory_profile SET profile='accumulation-reference-v1'")
        self.refused(self.read)

    def test_register_schema_tamper_is_refused(self):
        self.sql("UPDATE accumulation_register_schema SET definition=replace(definition,'Quantity','Changed')")
        self.refused(self.read)

    def test_catalog_schema_tamper_is_refused(self):
        self.sql("UPDATE catalog_schema SET name='Changed' WHERE identity=?",(str(self.config.catalogs[0].identity),))
        self.refused(self.read)

    def test_generation_change_is_refused(self):
        self.sql('UPDATE database_info SET generation=2')
        self.refused(self.read)

    def test_database_uuid_change_is_refused(self):
        self.sql('UPDATE database_info SET database_uuid=?',(str(uuid4()),))
        self.refused(self.read)

    def test_backend_substitution_is_refused(self):
        other=SQLiteDBContext.create_inventory_application(Path(self.temp.name)/'other.sqlite',self.config)
        self.addCleanup(other.close)
        with patch.object(self.context,'_backend',other.backend): self.refused(self.read,'unsupported')

    def test_raw_core15_has_no_report_grant(self):
        with closing(SQLiteDBContext.create_inventory(Path(self.temp.name)/'core.sqlite',validated_core(self.config))) as c:
            self.refused(lambda:InventoryReports(c,self.config),'unsupported')

    def test_format14_and_13_have_no_report_grant(self):
        from yadinassi.configuration_accumulation import import_accumulation_configuration, PROFILE as P14
        from test_sqlite_accumulation_profile import accumulation_source
        from yadinassi.configuration_posting import import_posting_configuration, PROFILE as P13
        from test_configuration_posting import source as posting_source
        configs=[(SQLiteDBContext.create_accumulation,import_accumulation_configuration(accumulation_source(),accumulation_runtime=P14)),
                 (SQLiteDBContext.create_posting,import_posting_configuration(posting_source(),posting_runtime=P13))]
        for i,(create,config) in enumerate(configs):
            with self.subTest(profile=config.profile),closing(create(Path(self.temp.name)/('other'+str(i)+'.sqlite'),config)) as c:
                self.refused(lambda:InventoryReports(c,self.config),'unsupported')

    def test_busy_owner_is_not_borrowed(self):
        with closing(self.backend.begin_read()) as owner:
            with self.assertRaisesRegex(BackendError,'busy'): self.read()
            self.assertIs(self.backend._active,owner)

    def test_closed_backend_refused(self):
        self.context.close(); self.refused(self.read,'closed')

    def test_client_and_server_execution_cannot_read_through_host_service(self):
        with execution(self.backend):
            self.refused(self.read,'unsupported')
        with admission(False):
            self.refused(self.read,'unsupported')
        self.assertEqual(self.read().rows,())

    def test_registered_foreign_or_unknown_owner_not_cleared(self):
        owner=object()
        with patch.object(self.backend,'_bsl_transaction',owner,create=True):
            self.refused(self.read,'unsupported')
            self.assertIs(self.backend._bsl_transaction,owner)

    def test_input_budgets_apply_even_to_excluded_rows(self):
        self.post(lines=2)
        for constant,value in [('MAX_INPUT_ROWS',1),('MAX_INPUT_CELLS',1),('MAX_TEXT',1)]:
            with self.subTest(constant=constant),patch(REPORTS+constant,value):
                self.refused(lambda:self.read('StockBalance',at=datetime(2020,1,1)),'unsupported')

    def test_output_row_and_cell_limits_refuse_instead_of_truncating(self):
        self.post(lines=2)
        for constant,value in [('MAX_ROWS',1),('MAX_CELLS',1)]:
            with self.subTest(constant=constant),patch(REPORTS+constant,value): self.refused(self.read,'unsupported')

    def test_label_limits_refuse_instead_of_truncating(self):
        self.post()
        for constant,value in [('MAX_LABELS',1),('MAX_LABEL_LENGTH',1)]:
            with self.subTest(constant=constant),patch(REPORTS+constant,value): self.refused(self.read,'unsupported')

    def test_interruption_releases_lease_without_partial_result(self):
        with patch.object(AccumulationMovementPort,'scan',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.read()
        self.assertIsNone(self.backend._active)
        self.assertEqual(self.read().rows,())

    def test_sql_error_is_closed_category_and_releases_lease(self):
        with patch.object(AccumulationMovementPort,'scan',side_effect=sqlite3.DatabaseError('private details')):
            self.refused(self.read,'storage_error')
        self.assertEqual(self.read().rows,())

    def test_cleanup_failure_does_not_publish_result(self):
        original=_View.close
        def close(owner):
            original(owner)
            raise KeyboardInterrupt()
        with patch.object(_View,'close',autospec=True,side_effect=close):
            with self.assertRaises(KeyboardInterrupt): self.read()
        self.assertIsNone(self.backend._active)

    def test_completed_result_survives_backend_close(self):
        self.post(); r=self.read()
        self.host.close(); self.context.close()
        self.assertEqual(dict(r.labels)[self.product],'Product')
        self.assertEqual(self.named(r)[0]['Quantity'],Decimal(10))
