"""Local policy tests for draft table hooks; only case17 is native evidence."""
from decimal import Decimal
import unittest
from unittest import mock

from yadinassi import value_storage_table as table_hook
from yadinassi import value_storage as storage
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.value_tables import BSLValueTable, BSLValueTableColumn
from yadinassi.runtime import Interpreter
from yadinassi.values import BSLArray

D = Decimal


class MiniCodec:
    """Synthetic parent budget/active-path hooks, not a native implementation."""
    def __init__(self, max_nodes=10000):
        self.active = set()
        self.nodes = 0
        self.text = 0
        self.max_nodes = max_nodes

    def reserve(self, count):
        self.nodes += count
        if self.nodes > self.max_nodes: raise ValueError('node budget')

    def charge_text(self, name):
        self.text += len(name) + sum(ord(c) > 0xffff for c in name)

    def take(self, value, depth=0):
        self.reserve(1)
        if depth > 64: raise ValueError('depth budget')
        identity_bearing = type(value) is BSLValueTable or type(value) is BSLArray
        if identity_bearing:
            if id(value) in self.active: raise ValueError('cycle')
            self.active.add(id(value))
        try:
            if type(value) is BSLValueTable:
                return table_hook.take_table(value, encode=lambda x:self.take(x, depth+1),
                                             charge_text=self.charge_text, reserve=self.reserve)
            if type(value) is BSLArray:
                if type(value.items) is not list: raise ValueError('bad array')
                return ('array', tuple(self.take(x, depth+1) for x in value.items))
            if value is None or type(value) is str or type(value) is Decimal or type(value) is bool: return ('scalar', value)
            raise ValueError('unsupported value')
        finally:
            if identity_bearing: self.active.remove(id(value))

    def _restore(self, node, depth=0):
        self.reserve(1)
        if depth > 64: raise ValueError('depth budget')
        if type(node) is not tuple or not node or type(node[0]) is not str: raise ValueError('bad node')
        if node[0] == 'value_table':
            return table_hook.restore_table(node, decode=lambda x:self._restore(x, depth+1),
                                            charge_text=self.charge_text, reserve=self.reserve)
        if len(node) != 2: raise ValueError('bad node')
        if node[0] == 'scalar': return node[1]
        if node[0] == 'array':
            value = BSLArray()
            value.items = [self._restore(x, depth+1) for x in node[1]]
            return value
        raise ValueError('bad node')

    @classmethod
    def restore(cls, node):
        return cls()._restore(node)


def make_table(names=('x',), rows=((D(1),),)):
    table = BSLValueTable()
    for name in names: table.columns.add(name)
    for values in rows:
        row = table.add()
        for i, value in enumerate(values): row.set(D(i), value)
    return table


class TableSnapshotDraftTests(unittest.TestCase):
    def test_native_case17_abca_and_fresh_owner(self):
        source = make_table()
        snapshot = MiniCodec().take(source)
        source.rows[0].set(D(0), D(2))
        first = MiniCodec.restore(snapshot)
        before = first.rows[0].get(D(0))
        first.rows[0].set(D(0), D(3))
        second = MiniCodec.restore(snapshot)
        self.assertEqual((before, source.rows[0].get(D(0)), first.rows[0].get(D(0)),
                          second.rows[0].get(D(0))), (D(1), D(2), D(3), D(1)))
        self.assertIs(first.rows[0].owner(), first)
        self.assertIsNot(first, second)
        self.assertIsNot(first.columns.items[0], source.columns.items[0])

    def test_fresh_rows_columns_and_cell_dict_keys(self):
        source = make_table(); result = MiniCodec.restore(MiniCodec().take(source))
        row = result.rows[0]; col = result.columns.items[0]
        self.assertIs(result.columns.table, result)
        self.assertIs(result.indexes.table, result)
        self.assertIs(row.table, result)
        self.assertEqual(tuple(row.cells), (col,))
        self.assertNotIn(source.columns.items[0], row.cells)

    def test_multiple_rows_columns_are_local_policy(self):
        source = make_table(('a','b'), ((D(1),'z'), (D(2),'y')))
        result = MiniCodec.restore(MiniCodec().take(source))
        self.assertEqual([c.name for c in result.columns.items], ['a','b'])
        self.assertEqual([[r.get(D(i)) for i in range(2)] for r in result.rows],
                         [[D(1),'z'], [D(2),'y']])

    def test_empty_table_local_policy(self):
        result = MiniCodec.restore(MiniCodec().take(make_table((), ())))
        self.assertEqual((result.columns.items, result.rows, result.indexes.items), ([],[],[]))

    def test_nested_array_restored_independently(self):
        a = BSLArray(); a.items.append(D(1)); source = make_table(rows=((a,),))
        node = MiniCodec().take(source); a.items[0] = D(2)
        one, two = MiniCodec.restore(node), MiniCodec.restore(node)
        one.rows[0].get(D(0)).items[0] = D(3)
        self.assertEqual(two.rows[0].get(D(0)).items, [D(1)])
        self.assertEqual(a.items, [D(2)])

    def test_nested_table_reuses_parent_budgets_and_restores(self):
        inner = make_table(); outer = make_table(rows=((inner,),))
        codec = MiniCodec(); node = codec.take(outer)
        result = MiniCodec.restore(node).rows[0].get(D(0))
        self.assertEqual(result.rows[0].get(D(0)), D(1))
        self.assertGreaterEqual(codec.nodes, 6)

    def test_shared_child_is_copied_per_occurrence_and_cycle_rejected(self):
        a = BSLArray(); a.items.append(D(1))
        table = make_table(('a','b'), ((a,a),))
        result = MiniCodec.restore(MiniCodec().take(table))
        left, right = result.rows[0].get(D(0)), result.rows[0].get(D(1))
        self.assertIsNot(left, right)
        left.items[0] = D(3)
        self.assertEqual(right.items, [D(1)])
        cyclic = make_table(); cyclic.rows[0].set(D(0), cyclic)
        with self.assertRaises(ValueError): MiniCodec().take(cyclic)

    def test_indexed_table_is_rejected(self):
        table = make_table(); table.indexes.add('x')
        with self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)
        self.assertEqual(table.rows[0].get(D(0)), D(1))

    def test_typed_and_nondefault_column_metadata_rejected(self):
        for change in ('type','title','width'):
            table = make_table(); column = table.columns.items[0]
            if change == 'type': column.value_type = BSLTypeDescription('Number')
            elif change == 'title': column.title = 'Title'
            else: column.width = D(3)
            with self.subTest(change=change), self.assertRaises(table_hook.TableSnapshotError):
                MiniCodec().take(table)

    def test_noncanonical_zero_metadata_rejected(self):
        for width in (D('-0'), D('0.0'), D('NaN')):
            table = make_table(); table.columns.items[0].width = width
            with self.subTest(width=str(width)), self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

    def test_restore_metadata_charges_shared_budget_before_decode(self):
        node = ('value_table', ('x',), ((('scalar', D(1)),),))
        codec = MiniCodec(max_nodes=2)
        with self.assertRaises(ValueError): codec._restore(node)
        self.assertEqual(codec.nodes, 3)

    def test_bad_descriptor_and_hostile_metadata_rejected_without_hooks(self):
        class Hostile:
            def __eq__(self, other): raise AssertionError('must not compare')
            def __str__(self): raise AssertionError('must not stringify')
        table = make_table(); desc = table.columns.items[0].value_type
        object.__setattr__(desc, 'number_qualifiers', Hostile())
        with self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

    def test_invalid_column_identity_and_owner_rejected(self):
        for change in ('owner','duplicate','deleted'):
            table = make_table(); col = table.columns.items[0]
            if change == 'owner': col.table = make_table()
            elif change == 'duplicate': table.columns.items.append(col)
            else: col._deleted = True
            with self.subTest(change=change), self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

    def test_invalid_row_identity_and_owner_rejected(self):
        for change in ('owner','duplicate','deleted'):
            table = make_table(); row = table.rows[0]
            if change == 'owner': row.table = make_table()
            elif change == 'duplicate': table.rows.append(row)
            else: row._deleted = True
            with self.subTest(change=change), self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

    def test_bad_or_partial_cells_rejected(self):
        for change in ('missing','foreign','nondict'):
            table = make_table(); row = table.rows[0]
            if change == 'missing': row.cells.clear()
            elif change == 'foreign':
                value = row.cells.pop(table.columns.items[0]); row.cells[make_table().columns.items[0]] = value
            else: row.cells = []
            with self.subTest(change=change), self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

    def test_hostile_subclass_key_rejected_without_eq(self):
        class HostileColumn(BSLValueTableColumn):
            def __hash__(self): return 1
            def __eq__(self, other): raise AssertionError('must not compare')
        table = make_table(); col = table.columns.items[0]; row = table.rows[0]
        row.cells = {HostileColumn(table,'x',col.value_type,'',D(0)): D(1)}
        with self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

    def test_invalid_names_and_slice_rejected(self):
        for change in ('empty','invalid','duplicate','slice'):
            table = make_table(('a','b'), ((D(1),D(2)),))
            if change == 'empty': table.columns.items[0].name = ''
            elif change == 'invalid': table.columns.items[0].name = 'not valid'
            elif change == 'duplicate': table.columns.items[1].name = 'A'
            else: table._bounded_slice_read = True
            with self.subTest(change=change), self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

    def test_bounds_checked_before_traversal(self):
        table = make_table(('a','b'), ((D(1),D(2)),))
        calls=[]
        with mock.patch.object(table_hook,'MAX_CELLS',1), self.assertRaises(table_hook.TableSnapshotError):
            table_hook.take_table(table, encode=lambda x:calls.append(x),
                                  reserve=lambda x:None, charge_text=lambda x:None)
        self.assertEqual(calls,[])

    def test_parent_budget_and_failed_decode_do_not_publish(self):
        table = make_table()
        with self.assertRaises(ValueError): MiniCodec(max_nodes=2).take(table)
        node = MiniCodec().take(table)
        with self.assertRaises(ValueError): table_hook.restore_table(node, decode=lambda x: (_ for _ in ()).throw(ValueError('fail')),
                                                         reserve=lambda x:None, charge_text=lambda x:None)
        self.assertEqual(table.rows[0].get(D(0)),D(1))

    def test_malformed_restore_framing_rejected_before_decode(self):
        bad = [None, ('value_table',(), ((('scalar',D(1)),),)),
               ('value_table', ('x',), ((),)), ('value_table', ('x','X'), ()),
               ('value_table', ('x',), [()]), ('wrong', (), ())]
        for node in bad:
            calls=[]
            with self.subTest(node=repr(node)), self.assertRaises(table_hook.TableSnapshotError):
                table_hook.restore_table(node, decode=lambda v:calls.append(v), reserve=lambda n:None, charge_text=lambda n:None)
            self.assertEqual(calls,[])

    def test_hostile_cell_type_has_no_implicit_host_hooks(self):
        class HostileMeta(type):
            def __eq__(self, other): raise AssertionError('must not compare types')
        class Hostile(metaclass=HostileMeta):
            def __str__(self): raise AssertionError('must not stringify')
            def __eq__(self, other): raise AssertionError('must not compare')
        table = make_table(rows=((Hostile(),),))
        with self.assertRaises(ValueError): MiniCodec().take(table)

    def test_utf16_name_limit_counts_supplementary_units(self):
        # _key only permits identifier characters; non-BMP Deseret letters qualify.
        table = make_table(('𐐀'*65,), ((D(1),),))
        with self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

    def test_incomplete_owner_shape_rejected(self):
        table = make_table(); del table.columns
        with self.assertRaises(table_hook.TableSnapshotError): MiniCodec().take(table)

class IntegratedValueStorageTableTests(unittest.TestCase):
    """Expected integration contract, only after the owner wires the hooks."""
    def test_native_case17_storage_constructor_get_isolation(self):
        table = make_table(); saved = storage.BSLValueStorage(table)
        table.rows[0].set(D(0), D(2))
        first = saved.get(); before = first.rows[0].get(D(0)); first.rows[0].set(D(0), D(3))
        second = saved.get()
        self.assertEqual((before, table.rows[0].get(D(0)), first.rows[0].get(D(0)),
                          second.rows[0].get(D(0))), (D(1),D(2),D(3),D(1)))

    def test_nested_table_and_duplicate_children_use_same_graph_policy(self):
        table = make_table(); outer = BSLArray(); outer.items = [table, table]
        saved = storage.capture(outer); restored = storage.restore(saved)
        left, right = restored.items
        self.assertIsNot(left, right)
        left.rows[0].set(D(0), D(3))
        self.assertEqual(right.rows[0].get(D(0)),D(1))
        table.rows[0].set(D(0), outer)
        with self.assertRaises(ValueError): storage.capture(outer)

    def test_capture_and_restore_share_global_node_budget(self):
        table = make_table(); saved = storage.capture(table)
        with mock.patch.object(storage, 'MAX_NODES', 3):
            with self.assertRaises(ValueError): storage.capture(table)
            with self.assertRaises(ValueError): storage.restore(saved)

    def test_forged_snapshot_rejected_at_restore(self):
        invalid = storage.Snapshot(('value_table', ('x',), ((),)))
        with self.assertRaises(ValueError): storage.restore(invalid)


class RealTableBoundaryTests(unittest.TestCase):
    """Real local one-at/one-over limits; not native platform maxima."""
    @staticmethod
    def table_with_shape(columns, rows):
        result = BSLValueTable()
        for i in range(columns): result.columns.add('c' + str(i))
        for _ in range(rows): result.add()
        return result

    @staticmethod
    def shape_node(columns, rows):
        names = tuple('c' + str(i) for i in range(columns))
        row = tuple(('undefined',) for _ in names)
        return storage.Snapshot(('value_table', names, tuple(row for _ in range(rows))))

    def test_columns_64_and_65_capture_restore(self):
        at = self.table_with_shape(64, 0)
        self.assertEqual(len(storage.restore(storage.capture(at)).columns.items), 64)
        with self.assertRaises(storage.SnapshotError): storage.capture(self.table_with_shape(65, 0))
        with self.assertRaises(storage.SnapshotError): storage.restore(self.shape_node(65, 0))

    def test_rows_1024_and_1025_capture_restore(self):
        at = self.table_with_shape(1, 1024)
        self.assertEqual(len(storage.restore(storage.capture(at)).rows), 1024)
        with self.assertRaises(storage.SnapshotError): storage.capture(self.table_with_shape(1, 1025))
        with self.assertRaises(storage.SnapshotError): storage.restore(self.shape_node(1, 1025))

    def test_cells_4096_and_4097_capture_restore(self):
        at = self.table_with_shape(16, 256)
        restored = storage.restore(storage.capture(at))
        self.assertEqual(len(restored.columns.items) * len(restored.rows), 4096)
        with self.assertRaises(storage.SnapshotError): storage.capture(self.table_with_shape(17, 241))
        with self.assertRaises(storage.SnapshotError): storage.restore(self.shape_node(17, 241))

    def test_name_128_and_129_utf16_units_capture_restore(self):
        at = '𐐀' * 64
        over = at + 'a'
        table = make_table((at,), ((D(1),),))
        self.assertEqual(storage.restore(storage.capture(table)).columns.items[0].name, at)
        with self.assertRaises(storage.SnapshotError): storage.capture(make_table((over,), ((D(1),),)))
        forged = storage.Snapshot(('value_table', (over,), ((('number', D(1)),),)))
        with self.assertRaises(storage.SnapshotError): storage.restore(forged)

    def test_total_text_1000000_and_1000001_units_capture_restore(self):
        at = 'z' * 999999  # plus the single UTF-16 unit of column name x
        table = make_table(rows=((at,),))
        self.assertEqual(len(storage.restore(storage.capture(table)).rows[0].get(D(0))), 999999)
        over = 'z' * 1000000
        with self.assertRaises(storage.SnapshotError): storage.capture(make_table(rows=((over,),)))
        forged = storage.Snapshot(('value_table', ('x',), ((('string', over),),)))
        with self.assertRaises(storage.SnapshotError): storage.restore(forged)

    def test_depth_64_and_65_capture_restore(self):
        def chain(count):
            value = None
            for _ in range(count):
                parent = BSLArray(); parent.items = [value]; value = parent
            return value
        def node(count):
            value = ('undefined',)
            for _ in range(count): value = ('array', (value,))
            return storage.Snapshot(('value_table', ('x',), ((value,),)))
        # Root table is depth 0 and terminal scalar is depth 1 + array count.
        self.assertIs(type(storage.restore(storage.capture(make_table(rows=((chain(63),),))))), BSLValueTable)
        self.assertIs(type(storage.restore(node(63))), BSLValueTable)
        with self.assertRaises(storage.SnapshotError): storage.capture(make_table(rows=((chain(64),),)))
        with self.assertRaises(storage.SnapshotError): storage.restore(node(64))

    def test_missing_table_fields_are_catchable_in_bsl(self):
        fixtures=[]
        table = make_table(); del table.columns; fixtures.append(table)
        table = make_table(); del table.columns.items[0].name; fixtures.append(table)
        table = make_table(); del table.rows[0].cells; fixtures.append(table)
        table = make_table(); del table.indexes.table; fixtures.append(table)
        vm=Interpreter()
        for value in fixtures:
            vm.variables['broken'] = value
            vm.execute('Caught = False; Try V = New ValueStorage(Broken); Except Caught = True; EndTry;')
            self.assertIs(vm.variables['caught'], True)


if __name__ == '__main__': unittest.main()
