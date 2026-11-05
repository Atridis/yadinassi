"""Owned SQLite section Query model tests, never native parity evidence."""
from dataclasses import replace
from decimal import Decimal, Inexact, Overflow, Rounded, localcontext
from uuid import UUID, uuid4
import unittest
from unittest.mock import patch

import test_catalog_tabular_runtime as fixtures
from yadinassi.catalog_backend import (
    BackendError, CatalogKey, CatalogScanRequest, CatalogSectionPage,
    CatalogSectionRecord, TabularRow,
)
from yadinassi.queries import BSLQuery, _section_value
from yadinassi.sqlite_catalog import _View


class CatalogSectionQueryTests(unittest.TestCase):
    setUp = fixtures.CatalogTabularRuntimeTests.setUp

    def seed(self):
        self.vm.execute('''C=Catalogs.Categories.CreateItem();C.Code="C";C.Write();
O=Catalogs.Products.CreateItem();O.Code="10";O.Text="owner scalar";
R=O.Lines.Add();R.Text="high";R.Amount=20.10;R.Category=C.Ref;
R=O.Lines.Add();R.Text="low";R.Amount=2.25;
N=O.Notes.Add();N.Text="unrelated";O.Write();
P=Catalogs.Products.CreateItem();P.Code="20";
R=P.Lines.Add();R.Text="other owner";R.Amount=99;P.Write();''')

    def query(self, text='SELECT Text AS Text, Amount FROM Catalog.Products.Lines ORDER BY Amount'):
        return BSLQuery(self.vm._catalogs, text)

    def test_section_query_ignores_hostile_decimal_context(self):
        self.seed()
        manager = self.vm._catalogs.get_index('Products')
        amount = next(f for f in manager._schema.tabular_sections[0].fields if f.name == 'Amount')
        with localcontext() as context:
            context.prec = 6
            context.Emin, context.Emax = -2, 2
            for signal in (Inexact, Overflow, Rounded): context.traps[signal] = True
            before = dict(context.flags)
            self.assertEqual(_section_value(manager, amount, Decimal('1.000')), Decimal('1'))
            result = self.query().execute()
            self.assertEqual(len(result._rows), 3)
            self.assertEqual(dict(context.flags), before)

    def test_section_logical_port_rejects_oversize_utf16_string(self):
        manager = self.vm._catalogs.get_index('Products')
        text = next(f for f in manager._schema.tabular_sections[0].fields if f.name == 'Text')
        with self.assertRaisesRegex(BackendError, 'integrity'):
            _section_value(manager, text, '😀' * 17)

    def test_owner_filter_exact_decimal_order_and_no_owner_flattening(self):
        self.seed()
        with patch.object(_View, 'scan_catalog', side_effect=AssertionError('must scan section')):
            self.vm.execute('''Q=New Query("SELECT L.Text AS Text, L.Amount FROM Catalog.Products.Lines AS L WHERE L.Ref=&Owner AND L.Amount>=&Min ORDER BY L.Amount");
Q.SetParameter("Owner",O.Ref);Q.SetParameter("Min",2.25);
S=Q.Execute().Select();While S.Next() Do Message(S.Text);Message(S.Amount);EndDo;''')
        self.assertEqual(self.lines, ['low', '2,25', 'high', '20,1'])

    def test_owner_reference_and_row_reference_keep_dynamic_identity(self):
        self.seed()
        self.vm.execute('''Q=New Query("ВЫБРАТЬ L.Ссылка КАК Owner, L.Category ИЗ Справочник.Products.Lines КАК L ГДЕ L.Amount>10 И L.Amount<30");
S=Q.Выполнить().Выбрать();S.Следующий();Message(S.Owner=O.Ref);
Message(TypeOf(S.Owner)=Type("CatalogRef.Products"));Message(S.Category=C.Ref);
Try Q.Execute().Unload();Except Message("reference-unload-refused");EndTry;''')
        self.assertEqual(self.lines, ['Да', 'Да', 'Да', 'reference-unload-refused'])

    def test_scalar_unload_detaches_rows_and_uses_section_qualifiers(self):
        self.seed()
        result = self.query().execute()
        table = result.unload()
        self.assertEqual(len(table.rows), 3)
        self.assertEqual(table.columns.items[0].name, 'Text')
        self.assertEqual(table.columns.items[0].value_type.string_qualifiers.length, Decimal(32))
        self.assertEqual(table.columns.items[1].value_type.number_qualifiers.fraction_digits, Decimal(2))
        table.rows[0].set_member('Amount', Decimal(500))
        selection = result.select(); self.assertTrue(selection.next())
        self.assertEqual(selection.get_member('Amount'), Decimal('2.25'))

    def test_unknown_section_owner_only_and_internal_row_fields_refused_before_scan(self):
        with patch.object(_View, 'scan_catalog_section', side_effect=AssertionError('invalid query scanned')):
            for text in (
                'SELECT Text FROM Catalog.Products.Missing',
                'SELECT Code FROM Catalog.Products.Lines',
                'SELECT Description FROM Catalog.Products.Lines',
                'SELECT DeletionMark FROM Catalog.Products.Lines',
                'SELECT LineNumber FROM Catalog.Products.Lines',
                'SELECT НомерСтроки FROM Catalog.Products.Lines',
                'SELECT RowId FROM Catalog.Products.Lines',
                'SELECT L.Ref.Code FROM Catalog.Products.Lines AS L',
                'SELECT X.Text FROM Catalog.Products.Lines AS L',
                'SELECT Text FROM Catalog.Products.Lines WHERE Code="10"',
                'SELECT Text FROM Catalog.Products.Lines ORDER BY Description',
                'SELECT Amount FROM Catalog.Products.Notes',
            ):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    self.query(text).execute()

    def test_empty_section_and_missing_or_wrong_parameters(self):
        result = self.query().execute()
        self.assertFalse(result.select().next())
        query = self.query('SELECT Amount FROM Catalog.Products.Lines WHERE Ref=&Owner AND Amount>=&Min')
        with patch.object(_View, 'scan_catalog_section', side_effect=AssertionError('invalid parameter scanned')):
            with self.assertRaises(ValueError): query.execute()
            query.set_parameter('Owner', self.vm.execute('Catalogs.Categories.EmptyRef()'))
            query.set_parameter('Min', Decimal(0))
            with self.assertRaises(TypeError): query.execute()
            query.set_parameter('Owner', self.vm.execute('Catalogs.Products.EmptyRef()'))
            query.set_parameter('Min', True)
            with self.assertRaises(TypeError): query.execute()

    def test_result_is_detached_old_result_and_new_execution_observe_distinct_snapshots(self):
        self.seed(); query = self.query()
        old = query.execute()
        self.vm.execute('X=O.Ref.GetObject();X.Lines[1].Amount=7.50;X.Write();')
        before = old.select(); before.next()
        after = query.execute().select(); after.next()
        self.assertEqual(before.get_member('Amount'), Decimal('2.25'))
        self.assertEqual(after.get_member('Amount'), Decimal('7.50'))
        view = self.context.backend.begin_read(); view.close()

    def records(self):
        manager = self.vm._catalogs.get_index('Products')
        section = manager._schema.tabular_sections[0]
        view = self.context.backend.begin_read()
        try:
            page = view.scan_catalog_section(manager._schema.identity, section.identity, CatalogScanRequest())
            return page.rows[0], manager, section
        finally:
            view.close()

    def test_top_pagination_keeps_page_size_and_accepts_scoped_row_id_duplicates(self):
        self.seed(); sample, manager, section = self.records()
        # Row UUID is scoped to owner, never globally unique across a result.
        records = tuple(replace(sample, owner=replace(sample.owner, record_id=UUID(int=i+1)))
                        for i in range(1002))
        requests = []
        def scan(view, catalog_id, section_id, request):
            self.assertEqual((catalog_id, section_id), (manager._schema.identity, section.identity))
            requests.append(request)
            return (CatalogSectionPage(records[:1000], 'a'*32) if len(requests) == 1
                    else CatalogSectionPage(records[1000:], None))
        with patch.object(_View, 'scan_catalog_section', scan):
            result = self.query('SELECT TOP 1001 Text FROM Catalog.Products.Lines').execute()
        self.assertEqual(len(result._rows), 1001)
        self.assertEqual([r.page_size for r in requests], [1000, 1000])
        self.assertEqual([r.continuation for r in requests], [None, 'a'*32])

    def test_hostile_pages_refuse_and_release_read_view(self):
        self.seed(); sample, unused_manager, section = self.records()
        pages = (
            object(), CatalogSectionPage([], None),
            CatalogSectionPage((), object()), CatalogSectionPage((), 'x'),
            CatalogSectionPage((), 'a'*32), CatalogSectionPage((object(),), None),
            CatalogSectionPage((replace(sample, section_id=uuid4()),), None),
            CatalogSectionPage((replace(sample, owner=replace(sample.owner, database_id=uuid4())),), None),
            CatalogSectionPage((replace(sample, row=replace(sample.row, identity=UUID(int=0))),), None),
            CatalogSectionPage((replace(sample, row=replace(sample.row, values=('short',))),), None),
            CatalogSectionPage((sample, sample), None),
        )
        for page in pages:
            with self.subTest(page=type(page).__name__), patch.object(_View, 'scan_catalog_section', return_value=page):
                with self.assertRaises(BackendError): self.query().execute()
            view = self.context.backend.begin_read(); view.close()

    def test_backend_refusal_closes_read_view_even_for_top(self):
        with patch.object(_View, 'scan_catalog_section', side_effect=BackendError('unsupported')):
            with self.assertRaises(BackendError):
                self.query('SELECT TOP 1 Text FROM Catalog.Products.Lines').execute()
        view = self.context.backend.begin_read(); view.close()

    def test_unprojected_hostile_scalar_is_validated_before_result(self):
        self.seed(); sample, unused_manager, unused_section = self.records()
        # Only Text is selected; the complete supplied row still requires validation.
        for bad in (True, 1.2, Decimal('NaN'), Decimal('1.001')):
            values = sample.row.values[:1] + (bad,) + sample.row.values[2:]
            record = replace(sample, row=replace(sample.row, values=values))
            with patch.object(_View, 'scan_catalog_section', return_value=CatalogSectionPage((record,), None)):
                with self.subTest(bad=bad), self.assertRaises(BackendError):
                    self.query('SELECT Text FROM Catalog.Products.Lines').execute()
            view = self.context.backend.begin_read(); view.close()

    def test_repeated_continuation_refuses_without_stranding_view(self):
        self.seed(); sample, unused_manager, unused_section = self.records()
        second = replace(sample, row=replace(sample.row, identity=uuid4()))
        with patch.object(_View, 'scan_catalog_section', side_effect=(
                CatalogSectionPage((sample,), 'a'*32), CatalogSectionPage((second,), 'a'*32))):
            with self.assertRaises(BackendError): self.query().execute()
        view = self.context.backend.begin_read(); view.close()

    def test_corrupt_tail_beyond_top_is_not_silently_ignored(self):
        self.seed(); sample, unused_manager, unused_section = self.records()
        records = tuple(replace(sample, owner=replace(sample.owner, record_id=UUID(int=i+1)))
                        for i in range(1001))
        bad = replace(sample, row=replace(sample.row, identity=UUID(int=0)))
        with patch.object(_View, 'scan_catalog_section', side_effect=(
                CatalogSectionPage(records[:1000], 'a'*32),
                CatalogSectionPage((records[1000], bad), None))):
            with self.assertRaises(BackendError):
                self.query('SELECT TOP 1001 Text FROM Catalog.Products.Lines').execute()
        view = self.context.backend.begin_read(); view.close()

    def test_top_and_selective_filter_cannot_reduce_source_preflight_budget(self):
        self.seed()
        with patch('yadinassi.sqlite_catalog._MAX_ROWS', 2):
            with self.assertRaises(BackendError):
                self.query('SELECT TOP 1 Text FROM Catalog.Products.Lines WHERE Amount=99').execute()
        view = self.context.backend.begin_read(); view.close()

    def test_custom_reference_parameters_require_target_and_runtime_snapshot(self):
        from yadinassi import Interpreter
        self.seed()
        query = self.query('SELECT Text FROM Catalog.Products.Lines WHERE Category=&Target')
        other_vm = Interpreter(database_context=self.context)
        wrong_target = self.vm.execute('Catalogs.Products.EmptyRef()')
        other_snapshot = other_vm.execute('Catalogs.Categories.EmptyRef()')
        with patch.object(_View, 'scan_catalog_section', side_effect=AssertionError('invalid ref scanned')):
            for value in (wrong_target, other_snapshot):
                query.set_parameter('Target', value)
                with self.assertRaises(TypeError): query.execute()
        query.set_parameter('Target', self.vm.execute('C.Ref'))
        selection = query.execute().select(); self.assertTrue(selection.next())
        self.assertEqual(selection.get_member('Text'), 'high')
        self.assertFalse(selection.next())

    def test_deletion_mark_and_unsaved_or_cleared_buffers_do_not_rewrite_source(self):
        self.seed()
        query = self.query('SELECT Text FROM Catalog.Products.Lines WHERE Ref=&Owner ORDER BY Amount')
        query.set_parameter('Owner', self.vm.execute('O.Ref'))
        self.vm.execute('''X=O.Ref.GetObject();X.DeletionMark=True;X.Write();
X.Lines.Clear();R=X.Lines.Add();R.Text="unsaved edit";
N=Catalogs.Products.CreateItem();R=N.Lines.Add();R.Text="unsaved owner";''')
        selection = query.execute().select(); texts = []
        while selection.next(): texts.append(selection.get_member('Text'))
        self.assertEqual(texts, ['low', 'high'])
        all_rows = self.query().execute().select(); count = 0
        while all_rows.next(): count += 1
        self.assertEqual(count, 3)
        self.vm.execute('X.Lines.Clear();X.Write();')
        self.assertFalse(query.execute().select().next())
        remaining = self.query().execute().select(); self.assertTrue(remaining.next())
        self.assertEqual(remaining.get_member('Text'), 'other owner')
        self.assertFalse(remaining.next())

    def test_owner_query_keeps_scalar_projection_and_does_not_read_section_tables(self):
        self.seed()
        original = _View.scan_catalog_values
        statements = []
        def scan(view, catalog_id, request, fields):
            view._connection.set_trace_callback(statements.append)
            return original(view, catalog_id, request, fields)
        with patch.object(_View, 'scan_catalog_values', scan), \
                patch.object(_View, 'scan_catalog', side_effect=AssertionError('owner cards materialized')), \
                patch.object(_View, 'scan_catalog_section', side_effect=AssertionError('section source scanned')):
            result = self.query('SELECT Code AS Code FROM Catalog.Products ORDER BY Code').execute()
        self.assertEqual(result._rows, (('10',), ('20',)))
        manager = self.vm._catalogs.get_index('Products')
        for section in manager._schema.tabular_sections:
            table = self.context.backend._section_layout.table_name(manager._schema.identity, section.identity)
            self.assertFalse(any(table in sql for sql in statements))
        self.context.backend.begin_read().close()

    def test_section_source_never_uses_owner_projection(self):
        self.seed()
        with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('owner source scanned')):
            self.assertEqual(len(self.query().execute()._rows), 3)

    def test_section_owner_and_custom_reference_ids_require_exact_uuid_before_comparison(self):
        self.seed(); sample, manager, section = self.records()
        class HostileIdentity:
            def __eq__(self, other): raise AssertionError('untyped identity compared')
            @property
            def int(self): raise AssertionError('untyped identity interpreted')
        bad = HostileIdentity()
        for name in ('database_id', 'catalog_id', 'record_id'):
            record = replace(sample, owner=replace(sample.owner, **{name: bad}))
            with self.subTest(owner=name), patch.object(_View, 'scan_catalog_section', return_value=CatalogSectionPage((record,), None)):
                with self.assertRaisesRegex(BackendError, 'integrity'): self.query().execute()
            self.context.backend.begin_read().close()
        field = next(f for f in section.fields if f.kind == 'catalog_ref')
        for name in ('database_id', 'catalog_id', 'record_id'):
            reference = CatalogKey(self.context.backend.database_id, field.target_catalog_id, UUID(int=0))
            with self.subTest(reference=name), self.assertRaisesRegex(BackendError, 'integrity'):
                _section_value(manager, field, replace(reference, **{name: bad}))
