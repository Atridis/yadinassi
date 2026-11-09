"""Typed-table snapshot extension: bounded local policy, not native evidence."""
from decimal import Decimal, Inexact, Rounded, localcontext
from itertools import combinations
import unittest
from unittest import mock
from uuid import UUID

from yadinassi import value_storage as storage
from yadinassi import value_storage_table as hooks
from yadinassi.catalog_types import BSLCatalogType
from yadinassi.dates import date
from yadinassi.queries import BSLQuery, BSLQueryResult, _Column
from yadinassi.structures import BSLStructure
from yadinassi.type_descriptions import BSLTypeDescription, _query_nullable_description
from yadinassi.type_qualifiers import (BSLAllowedLength, BSLAllowedSign, BSLBinaryDataQualifiers,
                                      BSLDateFractions, BSLDateQualifiers, BSLNumberQualifiers,
                                      BSLStringQualifiers)
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.value_tables import BSLCollectionIndex, BSLValueTable
from yadinassi.values import BSLArray, BSLType, NULL
import test_catalog_queries as fixtures

D = Decimal
_OMITTED = object()


def table_with(description=None, values=(D(1),), *, title='', width=D(0)):
    table = BSLValueTable()
    table.columns.add('Item', description, title, width)
    for value in values:
        table.add().set(D(0), value)
    return table


def numeric(digits=8, fraction=2, sign=BSLAllowedSign.ANY):
    return BSLTypeDescription('Number', BSLNumberQualifiers(D(digits), D(fraction), sign))


def query_table():
    columns = (_Column('Label', 'label', 'string', (12,)),
               _Column('Amount', 'amount', 'number', (12, 2, 'Any')),
               _Column('Flag', 'flag', 'boolean', ()),
               _Column('Stamp', 'stamp', 'datetime', ()))
    return BSLQueryResult(columns, (('one', D('12.50'), True, date('20240229')),
                                    (NULL, NULL, NULL, NULL))).unload()


def rows(table):
    return [tuple(row.cells[column] for column in table.columns.items) for row in table.rows]


def extended_root(table):
    # A nondefault title forces the extended frame even for untyped columns.
    table.columns.items[0].title = 'Schema'
    return storage.capture(table)._root


def replace_schema(root, payload=_OMITTED, **changes):
    column = list(root[1][0])
    if payload is not _OMITTED:
        column[1] = payload
    for field, value in changes.items():
        column[{'name': 0, 'title': 2, 'width': 3}[field]] = value
    return (root[0], (tuple(column), *root[1][1:]), root[2], root[3])


class TypedTableRoundtripTests(unittest.TestCase):
    def test_number_qualifiers_and_decimal_representation_are_preserved(self):
        description = numeric(sign=BSLAllowedSign.NONNEGATIVE)
        source = table_with(description, (D('12.30'), D('0.00')), title='Amount', width=D(18))
        result = storage.BSLValueStorage(source).get()
        column = result.columns.items[0]
        self.assertEqual(column.value_type, description)
        self.assertEqual((column.title, column.width), ('Amount', D(18)))
        self.assertEqual(result.rows[0].get(D(0)).as_tuple(), D('12.30').as_tuple())
        self.assertIsNot(column.value_type, description)
        self.assertIsNot(column.value_type.number_qualifiers, description.number_qualifiers)
        result.rows[0].set(D(0), D('1.236'))
        self.assertEqual(result.rows[0].get(D(0)), D('1.24'))
        result.rows[0].set(D(0), D(-1))
        self.assertEqual(result.rows[0].get(D(0)), D(0))

    def test_string_fixed_length_and_utf16_qualifiers_remain_active(self):
        description = BSLTypeDescription('String', None,
            BSLStringQualifiers(D(4), BSLAllowedLength.FIXED))
        source = table_with(description, ('𐐀x',))
        result = storage.BSLValueStorage(source).get()
        self.assertEqual(result.rows[0].get(D(0)), '𐐀x ')
        result.rows[0].set(D(0), 'abcde')
        self.assertEqual(result.rows[0].get(D(0)), 'abcd')
        self.assertEqual(result.columns.items[0].value_type, description)

    def test_all_date_qualifiers_roundtrip_without_coercing_again(self):
        for fraction in (BSLDateFractions.DATE_TIME, BSLDateFractions.DATE, BSLDateFractions.TIME):
            description = BSLTypeDescription('Date', None, None, BSLDateQualifiers(fraction))
            source = table_with(description, (date('20240229123456'),))
            with self.subTest(fraction=fraction):
                result = storage.BSLValueStorage(source).get()
                self.assertEqual(rows(result), rows(source))
                self.assertEqual(result.columns.items[0].value_type, description)

    def test_boolean_null_and_union_with_undefined_default(self):
        for spelling, values in (('Boolean', (True, False)), ('Null', (NULL,)),
                                 ('Number,String', (D(3), 'abc'))):
            description = BSLTypeDescription(spelling)
            source = table_with(description, values)
            if len(description.types) > 1:
                source.add()
            with self.subTest(spelling=spelling):
                result = storage.BSLValueStorage(source).get()
                self.assertEqual(rows(result), rows(source))
                self.assertEqual(result.columns.items[0].value_type, description)

    def test_all_ordinary_scalar_union_subsets_keep_existing_qualifiers(self):
        kinds = (BSLType.BOOLEAN, BSLType.STRING, BSLType.DATE, BSLType.NUMBER)
        examples = {BSLType.BOOLEAN: True, BSLType.STRING: 'ab',
                    BSLType.DATE: date('20240229123456'), BSLType.NUMBER: D('1.25')}
        for count in range(1, len(kinds) + 1):
            for chosen in combinations(kinds, count):
                types = BSLArray(); types.items = list(chosen)
                description = BSLTypeDescription(types,
                    BSLNumberQualifiers(D(8), D(2)) if BSLType.NUMBER in chosen else None,
                    BSLStringQualifiers(D(4), BSLAllowedLength.FIXED) if BSLType.STRING in chosen else None,
                    BSLDateQualifiers(BSLDateFractions.DATE) if BSLType.DATE in chosen else None)
                source = table_with(description, tuple(examples[kind] for kind in chosen))
                if count > 1: source.add()
                with self.subTest(types=chosen):
                    restored = storage.BSLValueStorage(source).get()
                    self.assertEqual(rows(restored), rows(source))
                    self.assertEqual(restored.columns.items[0].value_type, description)

    def test_empty_typed_schema_and_maximum_width(self):
        source = table_with(numeric(), (), title='Колонка𐐀', width=D(2 ** 32 - 1))
        result = storage.BSLValueStorage(source).get()
        self.assertEqual(rows(result), [])
        column = result.columns.items[0]
        self.assertEqual((column.title, column.width), ('Колонка𐐀', D(2 ** 32 - 1)))
        self.assertEqual(column.value_type, source.columns.items[0].value_type)

    def test_untyped_metadata_keeps_nested_values_uncoerced(self):
        nested = table_with(numeric(), (D('4.50'),), title='Inner')
        source = table_with(None, (nested,), title='Outer', width=D(20))
        result = storage.BSLValueStorage(source).get()
        self.assertEqual(result.rows[0].get(D(0)).rows[0].get(D(0)), D('4.50'))
        self.assertEqual(result.rows[0].get(D(0)).columns.items[0].title, 'Inner')
        self.assertIsNot(result.rows[0].get(D(0)), nested)

    def test_repeated_get_rebuilds_every_owner_and_descriptor(self):
        source = table_with(numeric(), (D(1),), title='Original')
        source.indexes.add('Item')
        saved = storage.BSLValueStorage(source)
        source.columns.items[0].set_member('Title', 'Source changed')
        source.rows[0].set(D(0), D(2))
        one, two = saved.get(), saved.get()
        one.columns.items[0].set_member('Title', 'First changed')
        one.rows[0].set(D(0), D(3))
        self.assertEqual((two.columns.items[0].title, two.rows[0].get(D(0))), ('Original', D(1)))
        for result in (one, two):
            column, row, index = result.columns.items[0], result.rows[0], result.indexes.items[0]
            self.assertIs(column.table, result)
            self.assertIs(row.owner(), result)
            self.assertEqual(tuple(row.cells), (column,))
            self.assertIs(index.table, result)
            self.assertIs(index.columns[0], column)
            self.assertEqual(set(index._keys), {row})
        self.assertIsNot(one.columns.items[0].value_type, two.columns.items[0].value_type)

    def test_shared_typed_child_is_copied_per_occurrence(self):
        child = table_with(numeric(), (D(2),))
        outer = BSLArray(); outer.items = [child, child]
        one, two = storage.BSLValueStorage(outer).get().items
        one.rows[0].set(D(0), D(7))
        self.assertEqual(two.rows[0].get(D(0)), D(2))
        self.assertIsNot(one.columns.items[0].value_type, two.columns.items[0].value_type)

    def test_schema_payload_is_only_immutable_primitives_and_tuples(self):
        source = table_with(numeric(), (), title='Meta', width=D(5))
        source.indexes.add('Item')
        node = storage.capture(source)._root
        def check(value):
            if type(value) is tuple:
                for item in value:
                    check(item)
            else:
                self.assertTrue(any(type(value) is kind for kind in (str, int, bool)))
        check(node)
        object.__setattr__(source.columns.items[0].value_type.number_qualifiers, 'digits', D(1))
        self.assertEqual(storage.restore(storage.Snapshot(node)).columns.items[0].value_type.number_qualifiers.digits, D(8))

    def test_ambient_decimal_context_does_not_change_schema_or_cells(self):
        source = table_with(numeric(12, 2), (D('1234567890.12'),), width=D(1234567890))
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = context.traps[Rounded] = True
            before = dict(context.flags)
            result = storage.BSLValueStorage(source).get()
            self.assertEqual(rows(result), rows(source))
            self.assertEqual(result.columns.items[0].width, D(1234567890))
            self.assertEqual(dict(context.flags), before)


class TypedIndexSnapshotTests(unittest.TestCase):
    def test_ordered_empty_repeated_and_composite_definitions_roundtrip(self):
        source = table_with(numeric(), (D(1), D(2)))
        source.columns.add('Label', BSLTypeDescription('String'))
        source.rows[0].set(D(1), 'a'); source.rows[1].set(D(1), 'b')
        for definition in ('Label,Item', None, 'Item,Item', 'Item'):
            source.indexes.add(definition)
        source.columns.move('Label', D(-1))
        source.columns.get_index('Item').set_member('Name', 'Amount')
        result = storage.BSLValueStorage(source).get()
        self.assertEqual([tuple(index) for index in result.indexes.items],
                         [('Label', 'Amount'), (), ('Amount', 'Amount'), ('Amount',)])
        self.assertEqual([tuple(index.columns) for index in result.indexes.items],
                         [(result.columns.items[0], result.columns.items[1]), (),
                          (result.columns.items[1], result.columns.items[1]), (result.columns.items[1],)])

    def test_rebuilt_buckets_serve_lookup_and_subsequent_mutation(self):
        source = table_with(numeric(), (D(1), D(2), D(1)))
        source.indexes.add('Item')
        result = storage.BSLValueStorage(source).get()
        matches = result.find_rows(BSLStructure('Item', D(1))).items
        self.assertEqual(matches, [result.rows[0], result.rows[2]])
        result.rows[0].set(D(0), D(3))
        self.assertEqual(result.find_rows(BSLStructure('Item', D(1))).items, [result.rows[2]])
        result.add().set(D(0), D(1))
        self.assertEqual(len(result.find_rows(BSLStructure('Item', D(1))).items), 2)

    def test_cached_keys_buckets_units_are_never_read_or_copied(self):
        class Hostile:
            def __iter__(self): raise AssertionError('cache iteration')
            def __eq__(self, other): raise AssertionError('cache comparison')
        source = table_with(numeric(), (D(1),)); index = source.indexes.add('Item')
        index._keys = index._buckets = index._units = Hostile()
        result = storage.BSLValueStorage(source).get()
        self.assertIs(result.find(D(1), 'Item'), result.rows[0])
        self.assertEqual(result.indexes.items[0]._units, 1)

    def test_indexed_nested_collections_get_fresh_identity_tokens(self):
        child = table_with(numeric(), (D(1),))
        source = table_with(None, (child,)); source.indexes.add('Item')
        result = storage.BSLValueStorage(source).get()
        restored_child = result.rows[0].get(D(0))
        self.assertIs(result.find(restored_child, 'Item'), result.rows[0])
        self.assertIsNone(result.find(child, 'Item'))

    def test_invalid_index_owners_flags_containers_and_duplicates_fail(self):
        for change in ('owner', 'deleted', 'cleared', 'duplicate', 'columns', 'foreign', 'subclass'):
            table = table_with(numeric()); index = table.indexes.add('Item')
            if change == 'owner': index.table = table_with()
            elif change == 'deleted': index._deleted = True
            elif change == 'cleared': index._cleared = True
            elif change == 'duplicate': table.indexes.items.append(index)
            elif change == 'columns': index.columns = tuple(index.columns)
            elif change == 'foreign': index.columns = [table_with().columns.items[0]]
            else:
                class Derived(BSLCollectionIndex): pass
                table.indexes.items[0] = Derived(table, index.columns)
            with self.subTest(change=change), self.assertRaises(storage.SnapshotError):
                storage.capture(table)

    def test_forged_index_positions_and_framing_fail_before_decode(self):
        root = extended_root(table_with(numeric()))
        for definitions in ([()], ([],), ((True,),), ((D(0),),), ((-1,),), ((1,),), ((object(),),)):
            calls = []
            with self.subTest(definitions=str(type(definitions))), self.assertRaises(hooks.TableSnapshotError):
                hooks.restore_table((*root[:3], definitions), decode=calls.append,
                                    reserve=lambda n: None, charge_text=lambda s: None)
            self.assertEqual(calls, [])

    def test_invalid_index_key_magnitude_fails_during_capture(self):
        source = table_with(None, (D(1),)); source.indexes.add('Item')
        source.rows[0].cells[source.columns.items[0]] = D('1e4097')
        with self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_index_rebuild_failure_never_returns_partial_table(self):
        snapshot = storage.capture(table_with(numeric()))
        root = snapshot._root
        root = (*root[:3], ((0,),))
        with mock.patch('yadinassi.value_tables.BSLCollectionIndexes._add_columns',
                        side_effect=ValueError('runtime budget')):
            with self.assertRaises(storage.SnapshotError): storage.restore(storage.Snapshot(root))


class TypedTableAdmissionTests(unittest.TestCase):
    def test_wrong_scalar_type_and_unqualified_payload_are_not_coerced(self):
        for description, bad in ((numeric(), '1'), (numeric(), D('1.234')),
                                 (numeric(sign=BSLAllowedSign.NONNEGATIVE), D(-1)),
                                 (BSLTypeDescription('String', None, BSLStringQualifiers(D(2))), 'long'),
                                 (BSLTypeDescription('Boolean'), D(1)),
                                 (BSLTypeDescription('Number'), NULL),
                                 (BSLTypeDescription('Date', None, None, BSLDateQualifiers(BSLDateFractions.DATE)),
                                  date('20240229123456'))):
            source = table_with(description, ())
            row = source.add(); row.cells[source.columns.items[0]] = bad
            with self.subTest(bad=repr(bad)), self.assertRaises(storage.SnapshotError):
                storage.capture(source)

    def test_uuid_descriptor_and_reference_descriptor_remain_excluded(self):
        reference_type = BSLCatalogType(UUID(int=1), 'Items', object())
        for kinds in ((BSLType.UUID,), (reference_type,), (BSLType.ARRAY,)):
            source = table_with(None, ())
            object.__setattr__(source.columns.items[0].value_type, 'types', kinds)
            with self.subTest(kinds=kinds), self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_uuid_value_not_accepted_in_scalar_typed_column(self):
        source = table_with(numeric())
        source.rows[0].cells[source.columns.items[0]] = BSLUUID('00000000-0000-0000-0000-000000000001')
        with self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_noncanonical_types_and_qualifier_combinations_fail(self):
        for change in ('duplicate', 'order', 'mixed_null', 'absent_number', 'binary', 'fraction', 'fixed_zero'):
            source = table_with(None, ())
            desc = source.columns.items[0].value_type
            if change == 'duplicate': object.__setattr__(desc, 'types', (BSLType.NUMBER, BSLType.NUMBER))
            elif change == 'order': object.__setattr__(desc, 'types', (BSLType.NUMBER, BSLType.STRING))
            elif change == 'mixed_null': object.__setattr__(desc, 'types', (BSLType.NULL, BSLType.NUMBER))
            elif change == 'absent_number': object.__setattr__(desc, 'number_qualifiers', BSLNumberQualifiers(D(2)))
            elif change == 'binary': object.__setattr__(desc, 'binary_data_qualifiers', BSLBinaryDataQualifiers(D(2)))
            elif change == 'fraction': object.__setattr__(desc.number_qualifiers, 'fraction_digits', D(1))
            else: object.__setattr__(desc.string_qualifiers, 'allowed_length', BSLAllowedLength.FIXED)
            with self.subTest(change=change), self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_hostile_metadata_objects_never_supply_hooks(self):
        class Meta(type):
            def __eq__(self, other): raise AssertionError('metaclass equality')
        class Hostile(metaclass=Meta):
            def __eq__(self, other): raise AssertionError('equality')
            def __hash__(self): raise AssertionError('hash')
            def __str__(self): raise AssertionError('str')
            def __int__(self): raise AssertionError('int')
        for change in ('types', 'qualifier', 'count', 'enum', 'title', 'width', 'marker'):
            source = table_with(None, ()); column = source.columns.items[0]; desc = column.value_type
            if change == 'types': object.__setattr__(desc, 'types', (Hostile(),))
            elif change == 'qualifier': object.__setattr__(desc, 'date_qualifiers', Hostile())
            elif change == 'count': object.__setattr__(desc.number_qualifiers, 'digits', Hostile())
            elif change == 'enum': object.__setattr__(desc.number_qualifiers, 'allowed_sign', Hostile())
            elif change == 'marker': object.__setattr__(desc, '_query_scalar', Hostile())
            else: setattr(column, change, Hostile())
            with self.subTest(change=change), self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_descriptor_and_qualifier_subclasses_are_not_admitted(self):
        class Description(BSLTypeDescription): pass
        class Qualifier(BSLNumberQualifiers): pass
        for value in (Description('Number'), Qualifier(D(2))):
            source = table_with(None, ())
            if type(value) is Description: source.columns.items[0].value_type = value
            else: object.__setattr__(source.columns.items[0].value_type, 'number_qualifiers', value)
            with self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_noncanonical_decimal_metadata_is_not_normalized(self):
        for value in (D('-0'), D('0.0'), D('1E+1'), D('1.5'), D('-1'), D('NaN'), D('Infinity'), True):
            for field in ('width', 'digits', 'length'):
                source = table_with(None, ()); column = source.columns.items[0]
                if field == 'width': column.width = value
                elif field == 'digits': object.__setattr__(column.value_type.number_qualifiers, field, value)
                else: object.__setattr__(column.value_type.string_qualifiers, field, value)
                with self.subTest(field=field, value=value), self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_huge_coefficient_metadata_rejected_before_tuple_expansion(self):
        source = table_with(None, ())
        object.__setattr__(source.columns.items[0].value_type.number_qualifiers,
                           'digits', D('1' + '0' * 20000 + 'e-20000'))
        with self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_missing_metadata_fields_are_snapshot_errors(self):
        for field in ('types', 'number_qualifiers', 'string_qualifiers', 'date_qualifiers', 'binary_data_qualifiers'):
            source = table_with(None, ())
            object.__delattr__(source.columns.items[0].value_type, field)
            with self.subTest(field=field), self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_instance_adjustment_hook_is_not_called(self):
        source = table_with(numeric())
        object.__setattr__(source.columns.items[0].value_type, 'adjust_value',
                           lambda *args: (_ for _ in ()).throw(AssertionError('host hook')))
        result = storage.BSLValueStorage(source).get()
        self.assertEqual(result.rows[0].get(D(0)), D(1))

    def test_malformed_descriptor_payloads_fail_before_decode(self):
        root = extended_root(table_with(numeric()))
        good = root[1][0][1]
        malformed = [None, list(good), (*good, 0), (list(good[0]), *good[1:]),
                     ((3, 3), *good[1:]), ((3, 1), *good[1:]), ((4, 3), *good[1:]),
                     ((True,), *good[1:]), ((999,), *good[1:]),
                     (good[0], (8, 9, 0), *good[2:]), (good[0], (8, 2, True), *good[2:]),
                     (good[0], good[1], (0, 1), *good[3:]),
                     (good[0], good[1], (1000001, 0), *good[3:]),
                     (*good[:3], 3, good[4]), (*good[:4], 1),
                     ((1, 3), (0, 0, 0), (0, 0), 0, True)]
        for payload in malformed:
            calls = []
            with self.subTest(payload=repr(payload)), self.assertRaises(hooks.TableSnapshotError):
                hooks.restore_table(replace_schema(root, payload), decode=calls.append,
                                    reserve=lambda n: None, charge_text=lambda s: None)
            self.assertEqual(calls, [])

    def test_forged_title_width_name_and_schema_container_fail(self):
        root = extended_root(table_with(numeric()))
        variants = [replace_schema(root, title=object()), replace_schema(root, width=True),
                    replace_schema(root, width=D(1)), replace_schema(root, width=-1),
                    replace_schema(root, width=2 ** 32), replace_schema(root, name='bad name'),
                    (root[0], (list(root[1][0]),), root[2], root[3])]
        for forged in variants:
            with self.assertRaises(storage.SnapshotError): storage.restore(storage.Snapshot(forged))

    def test_forged_cell_is_not_coerced_during_restore(self):
        root = extended_root(table_with(numeric()))
        for node in (('string', '1'), ('number', D('1.234')), ('null',), ('undefined',)):
            forged = (root[0], root[1], ((node,),), root[3])
            with self.subTest(node=node), self.assertRaises(storage.SnapshotError):
                storage.restore(storage.Snapshot(forged))


class NullableQuerySnapshotTests(unittest.TestCase):
    def test_query_unload_roundtrip_retains_all_scalar_nullable_metadata(self):
        source = query_table()
        restored = storage.BSLValueStorage(source).get()
        self.assertEqual(rows(restored), rows(source))
        for original, column in zip(source.columns.items, restored.columns.items):
            self.assertEqual(column.value_type, original.value_type)
            self.assertEqual(column.value_type._query_scalar, original.value_type._query_scalar)
            self.assertIsNot(column.value_type._query_scalar, original.value_type._query_scalar)
        self.assertEqual(restored.columns.items[1].value_type.types, (BSLType.NULL, BSLType.NUMBER))
        self.assertEqual(restored.columns.items[0].value_type.types, (BSLType.STRING, BSLType.NULL))

    def test_nullable_runtime_restrictions_are_preserved_after_get(self):
        source = query_table(); restored = storage.BSLValueStorage(source).get()
        for table in (source, restored):
            with self.assertRaises(ValueError): table.add()
            with self.assertRaises(ValueError): table.rows[0].set(D(1), NULL)
            with self.assertRaises(ValueError): table.rows[0].set(D(1), None)
            with self.assertRaises(ValueError): table.rows[0].set(D(1), '7')
            table.rows[0].set(D(1), D('9.25'))
            self.assertEqual(table.rows[0].get(D(1)), D('9.25'))

    def test_nullable_null_indexes_rebuild_and_each_get_is_independent(self):
        source = query_table(); source.indexes.add('Amount,Label')
        saved = storage.BSLValueStorage(source)
        one, two = saved.get(), saved.get()
        self.assertEqual(one.find_rows(BSLStructure('Amount,Label', NULL, NULL)).items, [one.rows[1]])
        one.rows[0].set(D(1), D(3))
        self.assertEqual(two.rows[0].get(D(1)), D('12.50'))
        self.assertIsNot(one.columns.items[1].value_type._query_scalar, two.columns.items[1].value_type._query_scalar)

    def test_empty_query_table_preserves_nullable_schema(self):
        source = query_table(); source.clear()
        result = storage.BSLValueStorage(source).get()
        self.assertEqual(rows(result), [])
        self.assertIsNotNone(result.columns.items[0].value_type._query_scalar)
        with self.assertRaises(ValueError): result.add()

    def test_inconsistent_or_recursive_nullable_marker_fails_closed(self):
        for change in ('self', 'nested', 'types', 'qualifiers', 'ordinary_marker', 'undefined_cell'):
            source = query_table(); desc = source.columns.items[1].value_type
            if change == 'self': object.__setattr__(desc, '_query_scalar', desc)
            elif change == 'nested': object.__setattr__(desc, '_query_scalar', _query_nullable_description(numeric()))
            elif change == 'types': object.__setattr__(desc, 'types', (BSLType.NUMBER, BSLType.NULL))
            elif change == 'qualifiers': object.__setattr__(desc, 'number_qualifiers', BSLNumberQualifiers(D(2)))
            elif change == 'ordinary_marker': object.__setattr__(desc._query_scalar, 'types', ())
            else: source.rows[0].cells[source.columns.items[1]] = None
            with self.subTest(change=change), self.assertRaises(storage.SnapshotError): storage.capture(source)


class TypedTableBudgetTests(unittest.TestCase):
    def test_metadata_nodes_share_parent_budget_in_both_directions(self):
        source = table_with(numeric(), (), title='Schema')
        snapshot = storage.capture(source)
        capture = storage._Capture(source); capture.take(source)
        count = capture.nodes
        self.assertGreater(count, 3)
        with mock.patch.object(storage, 'MAX_NODES', count):
            storage.capture(source); storage.restore(snapshot)
        with mock.patch.object(storage, 'MAX_NODES', count - 1):
            with self.assertRaises(storage.SnapshotError): storage.capture(source)
            with self.assertRaises(storage.SnapshotError): storage.restore(snapshot)

    def test_titles_and_cells_share_utf16_text_budget(self):
        source = table_with(numeric(), (), title='𐐀' * 499998)
        # Four units in Item, 999996 in the title.
        snapshot = storage.capture(source)
        self.assertEqual(storage.restore(snapshot).columns.items[0].title, source.columns.items[0].title)
        source.columns.items[0].title += 'a'
        with self.assertRaises(storage.SnapshotError): storage.capture(source)
        forged = replace_schema(snapshot._root, title=source.columns.items[0].title)
        with self.assertRaises(storage.SnapshotError): storage.restore(storage.Snapshot(forged))

    def test_title_local_limit_one_at_and_one_over(self):
        source = table_with(None, (), title='𐐀' * 5)
        with mock.patch.object(hooks, 'MAX_TITLE_UNITS', 10):
            snapshot = storage.capture(source); storage.restore(snapshot)
            source.columns.items[0].title += 'a'
            with self.assertRaises(storage.SnapshotError): storage.capture(source)
            with self.assertRaises(storage.SnapshotError):
                storage.restore(storage.Snapshot(replace_schema(snapshot._root, title=source.columns.items[0].title)))

    def test_index_count_limit_one_at_and_one_over(self):
        source = table_with(numeric(), ())
        for _ in range(hooks.MAX_INDEXES): source.indexes.add()
        snapshot = storage.capture(source)
        self.assertEqual(len(storage.restore(snapshot).indexes.items), hooks.MAX_INDEXES)
        source.indexes.add()
        with self.assertRaises(storage.SnapshotError): storage.capture(source)
        with self.assertRaises(storage.SnapshotError):
            storage.restore(storage.Snapshot((*snapshot._root[:3], snapshot._root[3] + ((),))))

    def test_index_column_limit_one_at_and_one_over(self):
        source = table_with(numeric(), ())
        source.indexes.add(','.join(['Item'] * hooks.MAX_INDEX_COLUMNS))
        snapshot = storage.capture(source)
        self.assertEqual(len(storage.restore(snapshot).indexes.items[0].columns), hooks.MAX_INDEX_COLUMNS)
        source.indexes.items[0].columns.append(source.columns.items[0])
        with self.assertRaises(storage.SnapshotError): storage.capture(source)
        with self.assertRaises(storage.SnapshotError):
            storage.restore(storage.Snapshot((*snapshot._root[:3], ((0,) * (hooks.MAX_INDEX_COLUMNS + 1),))))

    def test_index_cell_work_limit_before_rebuild_or_cell_traversal(self):
        source = table_with(numeric(), (D(1), D(2)))
        source.indexes.add('Item,Item')
        with mock.patch.object(hooks, 'MAX_INDEX_CELLS', 4):
            snapshot = storage.capture(source); storage.restore(snapshot)
        with mock.patch.object(hooks, 'MAX_INDEX_CELLS', 3):
            with mock.patch.object(storage._Capture, 'take') as capture:
                # Direct hook verifies no cell encoder callback is reached.
                with self.assertRaises(hooks.TableSnapshotError):
                    hooks.take_table(source, encode=capture, reserve=lambda n: None, charge_text=lambda s: None)
                capture.assert_not_called()
            with self.assertRaises(storage.SnapshotError): storage.restore(snapshot)

    def test_repeated_index_content_is_bounded_without_copying_caches(self):
        source = table_with(None, ('a' * 100,)); source.indexes.add('Item,Item')
        with mock.patch.object(hooks, '_MAX_INDEX_UNITS', 199):
            with self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_qualifier_maxima_and_malformed_one_over(self):
        for description in (numeric(4096, 4096), BSLTypeDescription('String', None, BSLStringQualifiers(D(1000000)))):
            source = table_with(description, ())
            self.assertEqual(storage.BSLValueStorage(source).get().columns.items[0].value_type, description)
        source = table_with(numeric(), ())
        object.__setattr__(source.columns.items[0].value_type.number_qualifiers, 'digits', D(4097))
        with self.assertRaises(storage.SnapshotError): storage.capture(source)

    def test_nested_typed_tables_do_not_reset_node_text_or_cycle_budgets(self):
        child = table_with(numeric(), (), title='child')
        parent = table_with(None, (child,), title='parent')
        snapshot = storage.capture(parent)
        with mock.patch.object(storage, 'MAX_TEXT_UNITS', 18):
            # Names (8) plus titles (11) exceed this shared budget.
            with self.assertRaises(storage.SnapshotError): storage.capture(parent)
            with self.assertRaises(storage.SnapshotError): storage.restore(snapshot)
        parent.rows[0].set(D(0), parent)
        with self.assertRaises(storage.SnapshotError): storage.capture(parent)


class QueryPipelineValueStorageTests(unittest.TestCase):
    setUp = fixtures.CatalogQueryTests.setUp
    tearDown = fixtures.CatalogQueryTests.tearDown

    def test_query_unload_storage_get_filter_and_aggregation_pipeline(self):
        query = BSLQuery(self.vm._catalogs,
            'SELECT P.Code AS Item,P.Amount*2 AS Gross,C.Description AS Caption '
            'FROM Catalog.Products AS P LEFT JOIN Catalog.Categories AS C '
            'ON P.Category=C.Ref AND P.Amount>20 ORDER BY P.Code')
        table = query.execute().unload()
        table.columns.get_index('Gross').set_member('Title', 'Gross amount')
        table.indexes.add('Item')
        self.vm.variables['report'] = table
        self.vm.execute('Saved=New ValueStorage(Report); Copy=Saved.Get(); '
                        'Message(Copy.Find("1", "Item").Gross); Message(Copy.Total("Gross"));')
        self.assertEqual(self.output, ['20', '120'])
        result = self.vm.variables['copy']
        self.assertIs(result.rows[0].get_member('Caption'), NULL)
        self.assertEqual(result.rows[2].get_member('Caption'), 'target')
        self.assertEqual(result.columns.get_index('Gross').title, 'Gross amount')
        self.assertEqual(result.columns.get_index('Gross').value_type,
                         table.columns.get_index('Gross').value_type)


if __name__ == '__main__':
    unittest.main()
