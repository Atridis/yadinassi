"""Owned SQLite catalog section runtime; these are not native 1C parity tests."""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.errors import BSLRuntimeError
from yadinassi.sqlite_catalog import _View
from catalog_sections_fixture import configuration_files_with_sections


class CatalogTabularRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'application.sqlite'
        self.files = configuration_files_with_sections()
        self.context = SQLiteDBContext.create(self.path, import_configuration(self.files))
        self.addCleanup(lambda: self.context.close())
        self.lines = []
        self.vm = Interpreter(output=self.lines.append, database_context=self.context)

    def execute(self, code):
        self.lines.clear()
        self.vm.execute(code)
        return list(self.lines)

    def new_row(self):
        self.vm.execute('O=Catalogs.Products.CreateItem(); O.Code="10"; R=O.Lines.Add();')
        return self.vm.execute('O'), self.vm.execute('O.Lines'), self.vm.execute('R')

    def test_new_defaults_are_typed_and_both_sections_are_empty(self):
        self.assertEqual(self.execute('''O=Catalogs.Products.CreateItem();
Message(O.IsNew()); Message(O.Lines.Count()); Message(O.Notes.Count());
R=O.Lines.Add(); Message(R.Text=""); Message(R.Amount=0); Message(R.Active=False);
Message(R.Stamp=Date(1,1,1)); Message(R.Category.IsEmpty());
Message(TypeOf(R.Text)=Type("String")); Message(TypeOf(R.Amount)=Type("Number"));
Message(TypeOf(R.Active)=Type("Boolean")); Message(TypeOf(R.Stamp)=Type("Date"));
Message(TypeOf(R.Category)=Type("CatalogRef.Categories"));'''),
                         ['Да', '0', '0'] + ['Да'] * 10)

    def test_write_reopen_preserves_order_values_and_other_section(self):
        self.execute('''C=Catalogs.Categories.CreateItem(); C.Code="C"; C.Description="Category"; C.Write();
O=Catalogs.Products.CreateItem(); O.Code="10"; O.Text="owner";
R=O.Lines.Add(); R.Text="first"; R.Amount=12.50; R.Active=True;
R.Stamp=Date(2024,2,29,12,34,56); R.Category=C.Ref;
R=O.Lines.Add(); R.Text="second"; R.Amount=-2.25;
N=O.Notes.Add(); N.Text="note"; O.Write();''')
        self.context.close()
        self.context = SQLiteDBContext(self.path)
        self.vm = Interpreter(output=self.lines.append, database_context=self.context)
        self.assertEqual(self.execute('''O=Catalogs.Products.FindByCode("10").GetObject();
Message(O.IsNew()); Message(O.Text); Message(O.Lines.Count());
Message(O.Lines[0].Text); Message(O.Lines[1].Text);
Message(O.Lines[0].Amount=12.50); Message(O.Lines[0].Active);
Message(XMLString(O.Lines[0].Stamp)); Message(O.Lines[0].Category.Description);
Message(O.Notes[0].Text);'''),
                         ['Нет', 'owner', '2', 'first', 'second', 'Да', 'Да',
                          '2024-02-29T12:34:56', 'Category', 'note'])
        self.assertEqual(self.context.backend.export_configuration(), self.files)

    def test_russian_aliases_and_zero_based_get(self):
        self.assertEqual(self.execute('''O=Справочники.Products.СоздатьЭлемент();
R=O.Lines.Добавить(); R.Text="one"; R=O.Lines.Add(); R.Text="two";
Message(O.Lines.Количество()); Message(O.Lines.Получить(0).Text);
Message(O.Lines.Get(1).Text); O.Lines.Удалить(0);
Message(O.Lines[0].Text); O.Lines.Очистить(); Message(O.Lines.Count());'''),
                         ['2', 'one', 'two', 'two', '0'])

    def test_delete_owned_row_and_clear_invalidate_old_handles(self):
        self.assertEqual(self.execute('''O=Catalogs.Products.CreateItem();
A=O.Lines.Add(); B=O.Lines.Add(); B.Text="keep"; O.Lines.Delete(A);
Try A.Text="dead"; Except Message("deleted"); EndTry;
Message(O.Lines[0].Text); O.Lines.Clear();
Try B.Text="dead"; Except Message("cleared"); EndTry;
Message(O.Lines.Count());'''), ['deleted', 'keep', 'cleared', '0'])

    def test_foreign_rows_and_replacement_are_rejected_without_mutation(self):
        self.assertEqual(self.execute('''O=Catalogs.Products.CreateItem(); P=Catalogs.Products.CreateItem();
A=O.Lines.Add(); A.Text="keep"; B=P.Lines.Add(); N=O.Notes.Add();
Try O.Lines.Delete(B); Except Message("foreign"); EndTry;
Try O.Lines.Delete(N); Except Message("other section"); EndTry;
Try O.Lines=P.Lines; Except Message("readonly section"); EndTry;
Try O.Lines[0]=B; Except Message("readonly slot"); EndTry;
Message(O.Lines.Count()); Message(O.Lines[0].Text);'''),
                         ['foreign', 'other section', 'readonly section', 'readonly slot', '1', 'keep'])

    def test_indices_require_finite_exact_decimal_integer_in_bounds(self):
        unused, section, row = self.new_row()
        self.assertIs(section.get_index(Decimal(0)), row)
        for value in (True, False, 0, 0.0, '0', None, Decimal('-1'),
                      Decimal('0.5'), Decimal('1'), Decimal('NaN'), Decimal('Infinity')):
            for operation in (section.get_index, section.get_method('Get'),
                              section.get_method('Delete')):
                with self.subTest(value=repr(value), operation=operation), self.assertRaises(Exception):
                    operation(value)
        self.assertEqual(self.vm.execute('O.Lines.Count()'), Decimal(1))

    def test_row_field_type_validation_preserves_existing_values(self):
        unused, unused_section, row = self.new_row()
        row.set_member('Text', 'keep')
        row.set_member('Amount', Decimal('1.25'))
        for name, value in [('Text', Decimal(1)), ('Amount', True), ('Amount', 1),
                            ('Amount', Decimal('NaN')), ('Amount', Decimal('Infinity')),
                            ('Active', Decimal(1)), ('Stamp', '2024-01-01'),
                            ('Category', None), ('Missing', 'bad')]:
            with self.subTest(name=name, value=repr(value)), self.assertRaises(Exception):
                row.set_member(name, value)
        self.assertEqual(row.get_member('Text'), 'keep')
        self.assertEqual(row.get_member('Amount'), Decimal('1.25'))

    def test_catalog_references_reject_other_target_and_snapshot(self):
        unused, unused_section, row = self.new_row()
        other_vm = Interpreter(database_context=self.context)
        foreign = other_vm.execute('Catalogs.Categories.EmptyRef()')
        wrong_target = self.vm.execute('Catalogs.Products.EmptyRef()')
        for ref in (foreign, wrong_target):
            with self.subTest(reference=ref), self.assertRaises(Exception):
                row.set_member('Category', ref)
        own = self.vm.execute('Catalogs.Categories.EmptyRef()')
        row.set_member('Category', own)
        self.assertEqual(row.get_member('Category'), own)

    def test_detached_buffers_do_not_write_implicitly(self):
        self.assertEqual(self.execute('''O=Catalogs.Products.CreateItem(); O.Code="10";
R=O.Lines.Add(); R.Text="saved"; O.Write();
A=O.Ref.GetObject(); B=O.Ref.GetObject(); A.Lines[0].Text="dirty"; A.Notes.Add();
Message(B.Lines[0].Text); Message(B.Notes.Count());
Message(O.Ref.GetObject().Lines[0].Text); A=Undefined;
Message(O.Ref.GetObject().Lines[0].Text);'''), ['saved', '0', 'saved', 'saved'])

    def test_stale_write_preserves_dirty_rows_and_committed_owner(self):
        self.assertEqual(self.execute('''O=Catalogs.Products.CreateItem(); O.Code="10";
R=O.Lines.Add(); R.Text="original"; O.Write(); A=O.Ref.GetObject(); B=O.Ref.GetObject();
A.Description="winner"; A.Lines[0].Text="current"; A.Write();
B.Description="loser"; B.Lines[0].Text="dirty"; B.Notes.Add();
Try B.Write(); Except Message("conflict"); EndTry;
Message(B.Description); Message(B.Lines[0].Text); Message(B.Notes.Count());
P=O.Ref.GetObject(); Message(P.Description); Message(P.Lines[0].Text); Message(P.Notes.Count());'''),
                         ['conflict', 'loser', 'dirty', '1', 'winner', 'current', '0'])

    def test_failed_duplicate_create_preserves_sections_and_can_retry(self):
        self.assertEqual(self.execute('''P=Catalogs.Products.CreateItem(); P.Code="10"; P.Write();
O=Catalogs.Products.CreateItem(); O.Code="10"; R=O.Lines.Add(); R.Text="dirty";
Try O.Write(); Except Message("rejected"); EndTry;
Message(O.IsNew()); Message(O.Ref.IsEmpty()); Message(O.Lines[0].Text);
O.Code="20"; O.Write(); Message(O.IsNew());
Message(Catalogs.Products.FindByCode("20").GetObject().Lines[0].Text);'''),
                         ['rejected', 'Да', 'Да', 'dirty', 'Нет', 'dirty'])

    def test_deletion_mark_and_owner_only_update_preserve_sections(self):
        self.assertEqual(self.execute('''O=Catalogs.Products.CreateItem(); O.Code="10";
R=O.Lines.Add(); R.Text="line"; R=O.Notes.Add(); R.Text="note"; O.Write();
P=O.Ref.GetObject(); P.DeletionMark=True; P.Description="marked"; P.Write();
P=O.Ref.GetObject(); Message(P.DeletionMark); Message(P.Description);
Message(P.Lines[0].Text); Message(P.Notes[0].Text);
P.Lines.Clear(); P.Write(); P=O.Ref.GetObject();
Message(P.Lines.Count()); Message(P.Notes[0].Text);'''),
                         ['Да', 'marked', 'line', 'note', '0', 'note'])

    def test_iteration_allows_field_edits_and_bounds_structural_mutations(self):
        self.assertEqual(self.execute('''O=Catalogs.Products.CreateItem(); O.Lines.Add(); O.Lines.Add();
For Each R In O.Lines Do R.Text="edited"; EndDo;
Message(O.Lines[0].Text); Message(O.Lines[1].Text);'''), ['edited', 'edited'])
        # Either a stable snapshot or fail-fast iteration is admitted, never an
        # unbounded iterator that visits rows appended during its own traversal.
        section = self.vm.execute('O.Lines')
        iterator = iter(section)
        next(iterator)
        self.vm.execute('O.Lines.Add();')
        try:
            remaining = [next(iterator) for unused in range(2)]
        except (StopIteration, ValueError, RuntimeError, BackendError):
            pass
        else:
            self.fail('iteration visited rows appended after iteration started: %r' % remaining)

    def test_row_limit_is_shared_across_sections_and_delete_frees_capacity(self):
        self.vm.execute('''O=Catalogs.Products.CreateItem();
For I=1 To 999 Do O.Lines.Add(); EndDo; O.Notes.Add();''')
        with self.assertRaises(Exception):
            self.vm.execute('O.Notes.Add();')
        with self.assertRaises(Exception):
            self.vm.execute('O.Lines.Add();')
        self.assertEqual(self.execute('''O.Lines.Delete(0); O.Notes.Add();
Message(O.Lines.Count()); Message(O.Notes.Count());'''), ['998', '2'])

    def test_uncertain_commit_freezes_nested_intent_and_resolves_without_recommit(self):
        obj, section, row = self.new_row()
        row.set_member('Text', 'original')
        self.vm.execute('N=O.Notes.Add(); N.Text="note";')
        commit = _View.commit

        def lose_response(tx):
            commit(tx)
            raise BackendError('uncertain_commit')

        with patch.object(_View, 'commit', lose_response), self.assertRaises(BackendError):
            obj.write()
        self.assertTrue(obj.is_new())
        self.assertTrue(obj.get_member('Ref').is_empty())
        pending = obj._pending_write
        self.assertIsNotNone(pending)
        draft = pending[0]
        self.assertIsInstance(draft.tabular_sections, tuple)
        self.assertTrue(all(isinstance(part.rows, tuple) for part in draft.tabular_sections))
        stored_row = draft.tabular_sections[0].rows[0]
        self.assertIsInstance(stored_row.values, tuple)
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            stored_row.values = ()
        for code in ('R.Text="changed";', 'O.Lines.Add();', 'O.Lines.Delete(0);',
                     'O.Lines.Clear();', 'O.Notes.Add();', 'N.Text="changed";',
                     'O.Description="changed";'):
            with self.subTest(code=code), self.assertRaisesRegex(BSLRuntimeError, 'uncertain_commit'):
                self.vm.execute(code)
        self.assertEqual(obj._pending_write, pending)
        with patch.object(_View, 'commit', side_effect=AssertionError('must not recommit')):
            obj.write()
        self.assertFalse(obj.is_new())
        self.assertEqual(self.execute('''P=Catalogs.Products.FindByCode("10").GetObject();
Message(P.Lines.Count()); Message(P.Lines[0].Text); Message(P.Notes.Count()); Message(P.Notes[0].Text);'''),
                         ['1', 'original', '1', 'note'])
        row.set_member('Text', 'next')
        obj.write()
        self.assertEqual(self.vm.execute('O.Ref.GetObject().Lines[0].Text'), 'next')

    def test_direct_reference_and_selection_parts_require_getobject(self):
        self.vm.execute('''O=Catalogs.Products.CreateItem(); O.Code="10"; O.Lines.Add(); O.Write();
S=Catalogs.Products.Select(); S.Next();''')
        for expression in ('O.Ref.Lines', 'S.Lines'):
            with self.subTest(expression=expression), self.assertRaises(Exception):
                self.vm.execute(expression)
        self.assertEqual(self.vm.execute('S.GetObject().Lines.Count()'), Decimal(1))

    def test_dynamic_types_codecs_and_unclaimed_row_identity_are_unsupported(self):
        self.new_row()
        for expression in ('TypeOf(O.Lines)', 'TypeOf(R)', 'ValueToStringInternal(O.Lines)',
                           'ValueToStringInternal(R)', 'R.RowNumber', 'R.UUID',
                           'R.UniqueIdentifier()', 'O.Lines.Copy()', 'O.Lines.Load(New Array)'):
            with self.subTest(expression=expression), self.assertRaises(Exception):
                self.vm.execute(expression)

        obj = self.vm.execute('O')
        section = self.vm.execute('O.Lines')
        caps = replace(self.context.backend.capabilities(), catalog_tabular_sections=False)
        with patch.object(self.context.backend, 'capabilities', return_value=caps):
            for action in (obj.write, section.get_method('Add')):
                with self.subTest(action=action), self.assertRaisesRegex(BackendError, 'unsupported'):
                    action()

    def test_row_string_index_reads_and_writes_typed_fields(self):
        self.assertEqual(self.execute('''O=Catalogs.Products.CreateItem(); R=O.Lines.Add();
R["Text"]="indexed"; R["Amount"]=3.50;
Message(R["text"]); Message(R.Amount=3.50);
Try R[0]="bad"; Except Message("nonstring"); EndTry;
Try R["Missing"]="bad"; Except Message("unknown"); EndTry;
Message(R.Text);'''), ['indexed', 'Да', 'nonstring', 'unknown', 'indexed'])

    def test_buffer_limit_refuses_add_and_assignment_atomically(self):
        obj, section, row = self.new_row()
        row.set_member('Text', 'keep')
        self.vm.execute('N=O.Notes.Add(); N.Text="note";')
        size = obj._section_buffer_bytes()
        with patch('yadinassi.catalog_sections._MAX_BUFFER_BYTES', size):
            for code in ('O.Lines.Add();', 'O.Notes.Add();',
                         'R.Text="longer";', 'N.Text="longer";'):
                with self.subTest(code=code), self.assertRaisesRegex(BSLRuntimeError, 'buffer limit'):
                    self.vm.execute(code)
                self.assertEqual(obj._section_buffer_bytes(), size)
            self.assertEqual(self.execute('''Message(O.Lines.Count()); Message(O.Notes.Count());
Message(R.Text); Message(N.Text);'''), ['1', '1', 'keep', 'note'])
            self.vm.execute('O.Lines.Clear(); O.Lines.Add();')
            self.assertLessEqual(obj._section_buffer_bytes(), size)

    def test_invalid_numeric_precision_keeps_buffer_without_partial_write(self):
        obj, section, row = self.new_row()
        row.set_member('Amount', Decimal('1.234'))
        self.vm.execute('O.Description="pending"; N=O.Notes.Add(); N.Text="note";')
        with self.assertRaises(Exception):
            obj.write()
        self.assertTrue(obj.is_new())
        self.assertEqual(row.get_member('Amount'), Decimal('1.234'))
        self.assertEqual(self.vm.execute('O.Notes[0].Text'), 'note')
        self.assertTrue(self.vm.execute('Catalogs.Products.FindByCode("10").IsEmpty()'))
        view = self.context.backend.begin_read()
        try:
            self.assertIsNone(view.read_catalog(obj._key))
        finally:
            view.close()
        row.set_member('Amount', Decimal('1.23'))
        obj.write()
        self.assertEqual(self.vm.execute('O.Ref.GetObject().Lines[0].Amount'), Decimal('1.23'))
        self.assertEqual(self.vm.execute('O.Ref.GetObject().Notes[0].Text'), 'note')

    def test_internal_row_uuid_survives_delete_shift_and_database_reopen(self):
        obj, section, row = self.new_row()
        self.vm.execute('R.Text="first"; R=O.Lines.Add(); R.Text="second"; O.Write();')
        view = self.context.backend.begin_read()
        try:
            before = view.read_catalog(obj._key).tabular_sections[0].rows
        finally:
            view.close()
        self.vm.execute('O.Lines.Delete(0); O.Write();')
        key = obj._key
        self.context.close()
        self.context = SQLiteDBContext(self.path)
        view = self.context.backend.begin_read()
        try:
            after = view.read_catalog(key).tabular_sections[0].rows
        finally:
            view.close()
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].identity, before[1].identity)
        self.assertNotEqual(after[0].identity, before[0].identity)
        self.assertEqual(after[0].values[0], 'second')

    def test_ui_default_context_guard_remains_closed(self):
        with self.assertRaises(BackendError):
            self.context.require_active()
        self.context.require_active(tabular_sections=True)


if __name__ == '__main__':
    unittest.main()
