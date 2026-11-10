"""Bounded built-in property transfer: local policy, not native parity evidence."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter, BSLError
from yadinassi import property_transfer as policy
from yadinassi.catalog_backend import BackendError
from yadinassi.catalogs import BSLCatalogObject
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.dates import date
from yadinassi.documents import BSLDocumentObject
from yadinassi.structures import BSLStructure, BSLFixedStructure, fill_property_values
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers, BSLAllowedLength
from yadinassi.value_tables import BSLValueTable, BSLValueTableRow
from yadinassi.value_trees import BSLValueTree
from yadinassi.values import BSLArray
from catalog_sections_fixture import configuration_files_with_sections
from test_document_configuration_xml import document_files

D = Decimal


def row(kind='table', names=('Text', 'Amount'), values=('old', D(0)), typed=False):
    owner = BSLValueTree() if kind == 'tree' else BSLValueTable()
    for name in names:
        description = None
        if typed:
            description = (BSLTypeDescription('Number', BSLNumberQualifiers(D(8), D(2)))
                           if name == 'Amount' else BSLTypeDescription('String'))
        owner.columns.add(name, description)
    result = owner.rows.add() if kind == 'tree' else owner.add()
    for index, value in enumerate(values): result.set(D(index), value)
    return result


class PropertyTransferRowTests(unittest.TestCase):
    def test_structure_and_fixed_structure_to_both_row_families(self):
        for family in ('table', 'tree'):
            for source in (BSLStructure('TEXT,Amount,Extra', 'new', D(4), True),
                           BSLFixedStructure('TEXT,Amount,Extra', 'new', D(4), True)):
                target = row(family)
                fill_property_values(target, source)
                self.assertEqual((target.get_member('Text'), target.get_member('Amount')), ('new', D(4)))
                self.assertEqual(len(target.cells), 2)

    def test_both_row_families_to_structure_without_adding_properties(self):
        for family in ('table', 'tree'):
            source = row(family, values=('new', D(7)))
            target = BSLStructure('tEXT,Amount,Leave', 'old', D(0), 9)
            fill_property_values(target, source)
            self.assertEqual((target.get('text'), target.get('Amount'), target.get('Leave')), ('new', D(7), 9))
            self.assertEqual([p.key for p in target], ['tEXT', 'Amount', 'Leave'])

    def test_all_table_tree_row_pairs_and_self_copy(self):
        for source_family in ('table', 'tree'):
            for target_family in ('table', 'tree'):
                source = row(source_family, values=('new', D(7)))
                target = row(target_family)
                owner = target.owner()
                fill_property_values(target, source)
                fill_property_values(target, target)
                self.assertIs(target.owner(), owner)
                self.assertEqual(target.get_member('Text'), 'new')
                self.assertEqual(target.get_member('Amount'), D(7))

    def test_shallow_references_aliases_and_cycles_are_not_cloned(self):
        shared = BSLArray(); shared.items = [D(1)]
        source = BSLStructure('Text,Amount', shared, shared)
        for family in ('table', 'tree'):
            target = row(family)
            fill_property_values(target, source)
            self.assertIs(target.get_member('Text'), shared)
            self.assertIs(target.get_member('Amount'), shared)
        target = row()
        source.set('Text', source)
        fill_property_values(target, source)
        self.assertIs(target.get_member('Text'), source)

    def test_typed_table_and_tree_setters_keep_number_and_string_adjustment(self):
        for family in ('table', 'tree'):
            target = row(family, typed=True)
            fill_property_values(target, BSLStructure('Text,Amount', 'new', D('12.345')))
            self.assertEqual(target.get_member('Amount'), D('12.35'))
            target.owner().columns.items[0].value_type = BSLTypeDescription('String', None,
                BSLStringQualifiers(D(3), BSLAllowedLength.FIXED))
            fill_property_values(target, BSLStructure('Text', 'x'))
            self.assertEqual(target.get_member('Text'), 'x  ')

    def test_table_indexes_are_updated_by_existing_setter(self):
        target = row(typed=True)
        table = target.owner(); table.indexes.add('Amount')
        fill_property_values(target, BSLStructure('Amount', D('9.876')))
        self.assertIs(table.find(D('9.88'), 'Amount'), target)
        self.assertIsNone(table.find(D(0), 'Amount'))
        self.assertEqual(table.find_rows(BSLStructure('Amount', D('9.88'))).items, [target])

    def test_existing_row_and_column_identity_and_tree_ancestry_are_preserved(self):
        root = row('tree'); child = root.rows.add()
        before = (child.owner(), child.parent, child.rows, tuple(child.cells))
        fill_property_values(child, BSLStructure('Text,Amount', 'child', D(5)))
        self.assertEqual((child.owner(), child.parent, child.rows, tuple(child.cells)), before)
        self.assertEqual(child.get_member('Text'), 'child')
        self.assertEqual(root.get_member('Text'), 'old')

    def test_tree_owner_properties_are_default_skipped_and_excludable(self):
        source = row('tree', values=('new', D(3))); target = row('tree')
        parent, children = target.parent, target.rows
        fill_property_values(target, source)
        fill_property_values(target, source, None, ' Родитель , Строки ')
        self.assertIs(target.parent, parent); self.assertIs(target.rows, children)
        for name in ('Parent', 'Родитель', 'Rows', 'Строки'):
            with self.assertRaises(ValueError): fill_property_values(target, source, name)

    def test_readonly_tree_parent_can_be_read_but_rows_collection_stays_closed(self):
        source = row('tree')
        target = BSLStructure('Parent,Rows,Text', 1, 2, 'old')
        fill_property_values(target, source)
        self.assertEqual((target.get('Parent'), target.get('Rows')), (None, 2))
        target.set('Parent', 1)
        fill_property_values(target, source, 'Родитель')
        self.assertIsNone(target.get('Parent'))
        with self.assertRaises(ValueError): fill_property_values(target, source, 'Rows')

    def test_deleted_table_and_tree_rows_are_rejected_for_both_roles(self):
        for family in ('table', 'tree'):
            dead = row(family)
            if family == 'table': dead.table.delete(dead)
            else: dead.collection.delete(dead)
            for target, source in ((dead, BSLStructure()), (BSLStructure(), dead)):
                with self.assertRaises(ValueError): fill_property_values(target, source)

    def test_readonly_slice_source_remains_readable_but_target_is_rejected(self):
        source = row(values=('snapshot', D(1)))
        source.table._bounded_slice_read = True
        target = BSLStructure('Text,Amount')
        fill_property_values(target, source)
        self.assertEqual(target.get('Text'), 'snapshot')
        with self.assertRaises(ValueError): fill_property_values(source, target)

    def test_fixed_target_new_profile_is_rejected_without_mutation(self):
        target = BSLFixedStructure('Text', 'old')
        with self.assertRaises(ValueError): fill_property_values(target, row())
        self.assertEqual(target.get('Text'), 'old')
        # Existing structure-only fixed-target behavior is intentionally intact.
        fill_property_values(target, BSLStructure('Text', 'new'))
        self.assertEqual(target.get('Text'), 'old')

    def test_typed_setter_failure_is_non_atomic_in_target_schema_order(self):
        target = row(typed=True)
        source = BSLStructure('Amount,Text', BSLArray(), 'first')
        with self.assertRaises(ValueError): fill_property_values(target, source)
        self.assertEqual(target.get_member('Text'), 'first')
        self.assertEqual(target.get_member('Amount'), D(0))

    def test_include_order_controls_which_prior_writes_survive_setter_failure(self):
        for include, expected in (('Amount,Text', 'old'), ('Text,Amount', 'first')):
            target = row(typed=True)
            with self.assertRaises(ValueError):
                fill_property_values(target, BSLStructure('Text,Amount', 'first', BSLArray()), include)
            self.assertEqual(target.get_member('Text'), expected)

    def test_ordinary_columns_do_not_acquire_unrelated_standard_aliases(self):
        source = row(names=('Дата',), values=('source',))
        target = row(names=('Date',), values=('old',))
        fill_property_values(target, source)
        self.assertEqual(target.get_member('Date'), 'old')


class PropertyTransferSelectionTests(unittest.TestCase):
    def test_include_and_exclude_accept_surrounding_ascii_spaces(self):
        source = BSLStructure('Text,Amount', 'new', D(8))
        target = row()
        fill_property_values(target, source, ' Amount , Text ')
        self.assertEqual((target.get_member('Text'), target.get_member('Amount')), ('new', D(8)))
        target = row()
        fill_property_values(target, source, None, ' Amount ')
        self.assertEqual((target.get_member('Text'), target.get_member('Amount')), ('new', D(0)))

    def test_include_precedence_ignores_exclude_completely(self):
        class Hostile:
            def __str__(self): raise AssertionError('ignored argument')
        for excluded in ('Text', 'Missing', ',bad,', Hostile()):
            target = row()
            fill_property_values(target, BSLStructure('Text', 'new'), 'Text', excluded)
            self.assertEqual(target.get_member('Text'), 'new')

    def test_missing_include_or_exclude_in_either_endpoint_fails_before_writes(self):
        for include, excluded in (('Text,Missing', None), ('Text,Amount', None),
                                  (None, 'Missing'), (None, 'Amount')):
            target = row()
            source = BSLStructure('Text,OnlySource', 'new', 1)
            with self.assertRaises(ValueError): fill_property_values(target, source, include, excluded)
            self.assertEqual(target.get_member('Text'), 'old')
        target = row(names=('Text',), values=('old',))
        with self.assertRaises(ValueError):
            fill_property_values(target, BSLStructure('Text,OnlySource', 'new', 1), None, 'OnlySource')
        self.assertEqual(target.get_member('Text'), 'old')

    def test_empty_tokens_unicode_whitespace_and_quoted_names_are_rejected(self):
        for names in ('', ' ', ',Text', 'Text,', 'Text,,Amount', '\tText', 'Text\n', '\u00a0Text', '"Text"'):
            for include, excluded in ((names, None), (None, names)):
                target = row()
                with self.subTest(names=repr(names)), self.assertRaises(ValueError):
                    fill_property_values(target, BSLStructure('Text,Amount', 'new', D(1)), include, excluded)
                self.assertEqual(target.get_member('Text'), 'old')

    def test_repeated_valid_include_names_remain_ordered_assignments(self):
        target = row(); calls = []
        original = BSLValueTableRow.set_member
        def set_member(value, name, content):
            calls.append(name); return original(value, name, content)
        with mock.patch.object(BSLValueTableRow, 'set_member', set_member):
            fill_property_values(target, BSLStructure('Text,Amount', 'new', D(1)), 'Text,Amount,text')
        self.assertEqual(calls, ['Text', 'Amount', 'Text'])

    def test_invalid_list_types_and_subclasses_do_not_invoke_hooks(self):
        class Hostile(str):
            def split(self, *args): raise AssertionError('split')
        for value in (D(1), True, BSLArray(), Hostile('Text')):
            for include, excluded in ((value, None), (None, value)):
                with self.assertRaises(TypeError): fill_property_values(row(), BSLStructure('Text'), include, excluded)

    def test_list_count_length_and_schema_name_budgets(self):
        target = row(); source = BSLStructure('Text,Amount', 'new', D(1))
        for constant, limit, include in (('MAX_LIST_NAMES', 1, 'Text,Amount'),
                                         ('MAX_LIST_UNITS', 3, 'Text')):
            with mock.patch.object(policy, constant, limit), self.assertRaises(ValueError):
                fill_property_values(target, source, include)
        with mock.patch.object(policy, 'MAX_FIELDS', 1), self.assertRaises(ValueError):
            fill_property_values(target, source)
        with mock.patch.object(policy, 'MAX_NAME_UNITS', 3), self.assertRaises(ValueError):
            fill_property_values(target, source)
        with mock.patch.object(policy, 'MAX_SCHEMA_UNITS', 19), self.assertRaises(ValueError):
            fill_property_values(target, source)
        self.assertEqual(target.get_member('Text'), 'old')

    def test_real_list_boundary_and_utf16_names(self):
        target = row(names=('𐐀' * 128,), values=(0,))
        source = BSLStructure('𐐀' * 128, 1)
        fill_property_values(target, source)
        self.assertEqual(target.get(D(0)), 1)
        target.table.columns.items[0].name += 'a'
        with self.assertRaises(ValueError): fill_property_values(target, source)


class PropertyTransferHostSafetyTests(unittest.TestCase):
    def test_unsupported_types_and_hostile_metaclasses_are_never_reflected(self):
        class Meta(type):
            def __eq__(self, other): raise AssertionError('class equality')
        class Hostile(metaclass=Meta):
            def __getattribute__(self, name): raise AssertionError('reflection')
            def __iter__(self): raise AssertionError('iteration')
        for value in (Hostile(), None, D(1), True, 'text', BSLArray(), BSLValueTable(), BSLValueTree()):
            for target, source in ((row(), value), (value, row())):
                with self.assertRaises(TypeError): fill_property_values(target, source)

    def test_row_subclasses_and_instance_method_replacements_are_rejected(self):
        class Derived(BSLValueTableRow):
            def get_member(self, name): raise AssertionError('host getter')
        table = BSLValueTable(); table.columns.add('Text')
        hostile = Derived(table)
        with self.assertRaises(TypeError): fill_property_values(row(), hostile)
        target = row()
        target._live = lambda: (_ for _ in ()).throw(AssertionError('host hook'))
        with self.assertRaises(ValueError): fill_property_values(target, BSLStructure('Text', 'new'))

    def test_hostile_structure_internal_mapping_is_rejected_before_iteration(self):
        class Hostile(dict):
            def items(self): raise AssertionError('items')
        source = BSLStructure('Text', 'new'); source._items = Hostile(source._items)
        with self.assertRaises(ValueError): fill_property_values(row(), source)

    def test_malformed_row_owner_columns_cells_and_schema_fail_closed(self):
        for change in ('owner', 'column_owner', 'column_name', 'column_duplicate', 'cells', 'detached', 'descriptor'):
            target = row()
            if change == 'owner': target.table = object()
            elif change == 'column_owner': target.table.columns.items[0].table = BSLValueTable()
            elif change == 'column_name': target.table.columns.items[0].name = object()
            elif change == 'column_duplicate': target.table.columns.items.append(target.table.columns.items[0])
            elif change == 'cells': target.cells.clear()
            elif change == 'detached': target.table.rows.clear()
            else: target.table.columns.items[0].value_type = object()
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                fill_property_values(target, BSLStructure('Text', 'new'))

    def test_target_index_hooks_and_foreign_columns_are_not_called(self):
        for change in ('hook', 'foreign'):
            target = row(); index = target.table.indexes.add('Amount')
            if change == 'hook': index._key = lambda *args: (_ for _ in ()).throw(AssertionError('host index'))
            else: index.columns[:] = [row().table.columns.items[0]]
            with self.assertRaises(ValueError): fill_property_values(target, BSLStructure('Amount', D(2)))

    def test_exact_qualifier_state_is_checked_without_storage_policy(self):
        class Hostile:
            def __int__(self): raise AssertionError('qualifier conversion')
        target = row(typed=True)
        object.__setattr__(target.table.columns.items[1].value_type.number_qualifiers,
                           'digits', Hostile())
        with self.assertRaises(ValueError):
            fill_property_values(target, BSLStructure('Amount', D(2)))
        # Scalar UUID descriptors are not constrained by a snapshot allowlist;
        # the existing ValueTable setter remains responsible for rejecting them.
        target = row()
        target.table.columns.items[0].value_type = BSLTypeDescription('UUID')
        with self.assertRaisesRegex(ValueError, 'UUID'):
            fill_property_values(target, BSLStructure('Text', 'value'))

    def test_missing_fields_are_catchable_in_bsl(self):
        vm = Interpreter(); broken = row(); del broken.table
        vm.variables['broken'] = broken
        vm.execute('Caught=False;Try FillPropertyValues(Broken,New Structure());Except Caught=True;EndTry;')
        self.assertIs(vm.variables['caught'], True)


class PropertyTransferObjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        files = document_files()
        files['Catalogs/Products.xml'] = configuration_files_with_sections()['Catalogs/Products.xml']
        # Authored fixtures refer to CatalogRef.Categories by name, so the
        # importer resolves references within this one combined configuration.
        self.context = SQLiteDBContext.create(Path(self.temp.name) / 'owned.sqlite', import_configuration(files))
        self.addCleanup(self.context.close)
        self.vm = Interpreter(database_context=self.context)
        self.vm.execute('C=Catalogs.Products.CreateItem();D=Documents.Orders.CreateDocument();')
        self.catalog = self.vm.variables['c']; self.document = self.vm.variables['d']

    def test_structure_to_catalog_object_and_reverse_uses_standard_aliases(self):
        source = BSLStructure('Код,Наименование,ПометкаУдаления,Text,Amount', 'C1', 'Name', True, 'custom', D('1.234'))
        fill_property_values(self.catalog, source)
        self.assertEqual(self.catalog.get_member('Code'), 'C1')
        self.assertEqual(self.catalog.get_member('Description'), 'Name')
        self.assertIs(self.catalog.get_member('DeletionMark'), True)
        self.assertEqual(self.catalog.get_member('Amount'), D('1.23'))
        target = BSLStructure('Код,Наименование,Text')
        fill_property_values(target, self.catalog)
        self.assertEqual((target.get('Код'), target.get('Наименование'), target.get('Text')), ('C1', 'Name', 'custom'))

    def test_structure_to_document_uses_aliases_and_preserves_ref_posted_sections(self):
        reference = self.document.get_member('Ref'); section = self.document.get_member('Lines')
        source = BSLStructure('Номер,Дата,ПометкаУдаления,Text,Amount', 'N1', date('20261110'), True, 'text', D(5))
        fill_property_values(self.document, source)
        self.assertEqual(self.document.get_member('Number'), 'N1')
        self.assertEqual(self.document.get_member('Date'), date('20261110'))
        self.assertIs(self.document.get_member('Ref'), reference)
        self.assertIs(self.document.get_member('Posted'), False)
        self.assertIs(self.document.get_member('Lines'), section)

    def test_document_to_document_excludes_date_posted_deletionmark(self):
        target = self.vm.execute('Documents.Orders.CreateDocument()')
        self.document.set_member('Text', 'copied'); self.document.set_member('Amount', D(7))
        self.document.set_member('Date', date('20261110')); self.document.set_member('DeletionMark', True)
        before = target.get_member('Date')
        fill_property_values(target, self.document, None, 'Дата,Проведен,ПометкаУдаления')
        self.assertEqual(target.get_member('Text'), 'copied'); self.assertEqual(target.get_member('Amount'), D(7))
        self.assertEqual(target.get_member('Date'), before); self.assertIs(target.get_member('DeletionMark'), False)
        self.assertTrue(target.is_new()); self.assertTrue(self.document.is_new())

    def test_catalog_document_and_row_object_common_fields_transfer(self):
        self.catalog.set_member('Text', 'copied'); self.catalog.set_member('Amount', D(9))
        fill_property_values(self.document, self.catalog)
        self.assertEqual(self.document.get_member('Text'), 'copied')
        target_row = row('tree', typed=True)
        fill_property_values(target_row, self.document)
        self.assertEqual(target_row.get_member('Amount'), D(9))
        target_row.set_member('Text', 'from row')
        fill_property_values(self.catalog, target_row)
        self.assertEqual(self.catalog.get_member('Text'), 'from row')

    def test_source_and_target_alias_collisions_are_rejected_without_precedence(self):
        for source in (BSLStructure('Code,Код', 'first', 'second'),
                       BSLStructure('Code,Код', 'same', 'same')):
            with self.assertRaises(ValueError): fill_property_values(self.catalog, source)
            self.assertEqual(self.catalog.get_member('Code'), '')
        target = BSLStructure('Code,Код', 'first', 'second')
        with self.assertRaises(ValueError): fill_property_values(target, self.catalog)
        self.assertEqual(target.get('Code'), 'first')

    def test_explicit_aliases_match_opposite_endpoint_spelling(self):
        fill_property_values(self.catalog, BSLStructure('Code', 'A'), 'Код')
        self.assertEqual(self.catalog.get_member('Code'), 'A')
        target = BSLStructure('Код')
        fill_property_values(target, self.catalog, 'Code')
        self.assertEqual(target.get('Код'), 'A')

    def test_readonly_and_whole_sections_are_never_transferred(self):
        other = self.vm.execute('Documents.Orders.CreateDocument()')
        other.get_member('Lines').add().set_member('Flag', True)
        fill_property_values(self.document, other)
        self.assertEqual(self.document.get_member('Lines').count(), D(0))
        for name in ('Ref', 'Ссылка', 'Posted', 'Проведён', 'Lines'):
            with self.assertRaises(ValueError): fill_property_values(self.document, other, name)
        fill_property_values(self.document, other, None, 'Ref,Posted,Lines')

    def test_catalog_tabular_rows_use_typed_setters_and_dirty_bookkeeping(self):
        section = self.catalog.get_member('Lines'); target = section.add()
        section._dirty = False; old_bytes = section._bytes
        fill_property_values(target, BSLStructure('Text,Amount', 'longer caption', D('3.456')))
        self.assertEqual(target.get_member('Amount'), D('3.46'))
        self.assertTrue(section._dirty); self.assertGreater(section._bytes, old_bytes)
        self.assertEqual(section._bytes, sum(item._bytes for item in section._rows))
        self.assertIs(target._section, section)
        self.assertEqual(target.get_member('LineNumber'), D(1))

    def test_document_lines_to_lines_and_structures_keep_line_identity(self):
        section = self.document.get_member('Lines'); source = section.add(); target = section.add()
        source.set_member('Flag', True)
        identity = target._identity
        fill_property_values(target, source)
        self.assertIs(target.get_member('Flag'), True)
        self.assertEqual(target._identity, identity); self.assertEqual(target.get_member('LineNumber'), D(2))
        out = BSLStructure('Flag'); fill_property_values(out, source)
        self.assertIs(out.get('Flag'), True)
        fill_property_values(target, source, None, 'НомерСтроки')
        with self.assertRaises(ValueError): fill_property_values(target, source, 'LineNumber')

    def test_catalog_and_document_tabular_rows_can_cross_by_common_fields(self):
        catalog_row = self.catalog.get_member('Lines').add()
        document_row = self.document.get_member('Lines').add()
        # The schemas deliberately differ; unrelated fields remain unchanged.
        catalog_row.set_member('Active', True)
        fill_property_values(document_row, catalog_row)
        self.assertIs(document_row.get_member('Flag'), False)
        table_row = row(names=('Flag',), values=(True,))
        fill_property_values(document_row, table_row)
        self.assertIs(document_row.get_member('Flag'), True)
        target = BSLStructure('Text,Amount'); fill_property_values(target, catalog_row)
        self.assertEqual((target.get('Text'), target.get('Amount')), ('', D(0)))

    def test_detached_section_rows_and_pending_targets_stay_blocked(self):
        for owner in (self.catalog, self.document):
            section = owner.get_member('Lines'); detached = section.add(); section.delete(detached)
            for target, source in ((detached, BSLStructure()), (BSLStructure(), detached)):
                with self.assertRaises(ValueError): fill_property_values(target, source)
            live = section.add(); owner._pending_write = object()
            with self.assertRaises(BackendError): fill_property_values(owner, BSLStructure('Text', 'blocked'))
            with self.assertRaises(BackendError): fill_property_values(live, BSLStructure())
            # Reads from a pending detached buffer do not alter its write intent.
            out = BSLStructure('Text'); fill_property_values(out, owner)
            self.assertEqual(out.get('Text'), '')
            owner._pending_write = None

    def test_no_database_write_handlers_or_section_replacement_is_called(self):
        self.catalog.set_member('Text', 'local')
        with mock.patch.object(BSLCatalogObject, 'write', side_effect=AssertionError('catalog write')), \
             mock.patch.object(BSLDocumentObject, 'write', side_effect=AssertionError('document write')), \
             mock.patch.object(type(self.context.backend), 'begin_write', side_effect=AssertionError('transaction')), \
             mock.patch.object(type(self.context.backend), 'begin_document_write', side_effect=AssertionError('document transaction')):
            fill_property_values(self.document, self.catalog)
            fill_property_values(self.catalog.get_member('Lines').add(), self.document)
        self.assertTrue(self.catalog.is_new()); self.assertTrue(self.document.is_new())

    def test_object_and_section_setter_errors_preserve_prior_writes(self):
        for target in (self.catalog, self.document, self.catalog.get_member('Lines').add()):
            with self.assertRaises(TypeError):
                fill_property_values(target, BSLStructure('Amount,Text', True, 'earlier'))
            self.assertEqual(target.get_member('Text'), 'earlier')
            self.assertEqual(target.get_member('Amount'), D(0))
        self.assertTrue(self.catalog.get_member('Lines')._dirty)

    def test_standard_readonly_fields_cannot_be_included_via_generic_rows(self):
        source = row(names=('Posted', 'Ref'), values=(True, self.document.get_member('Ref')))
        before = self.document.get_member('Ref')
        fill_property_values(self.document, source)
        self.assertIs(self.document.get_member('Posted'), False)
        self.assertIs(self.document.get_member('Ref'), before)
        for name in ('Posted', 'Проведён', 'Ссылка'):
            with self.assertRaises(ValueError): fill_property_values(self.document, source, name)

    def test_catalog_reference_values_remain_shallow_and_existing_setter_validated(self):
        reference = self.vm.execute('Catalogs.Categories.EmptyRef()')
        fill_property_values(self.catalog, BSLStructure('Category', reference))
        self.assertIs(self.catalog.get_member('Category'), reference)
        with self.assertRaises(TypeError):
            fill_property_values(self.catalog, BSLStructure('Category', self.document.get_member('Ref')))
        self.assertIs(self.catalog.get_member('Category'), reference)

    def test_readonly_source_scalars_and_references_can_fill_writable_properties(self):
        reference = self.document.get_member('Ref')
        target = BSLStructure('Ссылка,Проведён', 1, True)
        fill_property_values(target, self.document)
        self.assertIs(target.get('Ссылка'), reference)
        self.assertIs(target.get('Проведён'), False)
        target.set('Ссылка', 1)
        fill_property_values(target, self.document, 'Ref')
        self.assertIs(target.get('Ссылка'), reference)
        line = self.document.get_member('Lines').add()
        output = row(names=('НомерСтроки',), values=(D(0),))
        fill_property_values(output, line, 'LineNumber')
        self.assertEqual(output.get(D(0)), D(1))

    def test_references_and_managers_are_not_new_endpoints(self):
        for value in (self.catalog.get_member('Ref'), self.document.get_member('Ref'),
                      self.catalog._manager, self.document._manager, self.document.get_member('Lines')):
            with self.assertRaises(TypeError): fill_property_values(BSLStructure(), value)
            with self.assertRaises(TypeError): fill_property_values(value, BSLStructure())


class PropertyTransferInterpreterTests(unittest.TestCase):
    def test_bilingual_calls_omissions_and_identity_dispatch(self):
        vm = Interpreter()
        vm.execute('T=New ValueTable;T.Columns.Add("Text");R=T.Add();S=New Structure("Text","new");'
                   'FillPropertyValues(R,S,,);ЗаполнитьЗначенияСвойств(S,R,Undefined,Undefined);')
        self.assertEqual(vm.variables['r'].get_member('Text'), 'new')
        self.assertIs(vm.functions['fillpropertyvalues'].function, fill_property_values)
        self.assertIs(vm.functions['заполнитьзначениясвойств'].function, fill_property_values)

    def test_arguments_evaluate_once_left_to_right_and_procedure_stays_statement(self):
        vm = Interpreter()
        vm.execute('Var Order;Order="";Function Arg(Val Tag,Val Value) Order=Order+Tag;Return Value;EndFunction;'
                   'T=New ValueTable;T.Columns.Add("Text");R=T.Add();S=New Structure("Text","new");'
                   'FillPropertyValues(Arg("a",R),Arg("b",S),Arg("c","Text"),Arg("d","Missing"));')
        self.assertEqual(vm.variables['order'], 'abcd')
        with self.assertRaises(BSLError): vm.execute('X=FillPropertyValues(R,S);')
        with self.assertRaises(BSLError): vm.execute('FillPropertyValues(,S);')

    def test_legacy_selection_profile_remains_separate(self):
        vm = Interpreter()
        vm.execute('A=New Structure("Text","old");B=New Structure("Text","new");')
        with self.assertRaises(BSLError): vm.execute('FillPropertyValues(A,B,"Text","Missing");')
        self.assertEqual(vm.variables['a'].get('Text'), 'old')
        vm.execute('T=New ValueTable;T.Columns.Add("Text");R=T.Add();FillPropertyValues(R,B,"Text","Missing");')
        self.assertEqual(vm.variables['r'].get_member('Text'), 'new')


if __name__ == '__main__': unittest.main()
