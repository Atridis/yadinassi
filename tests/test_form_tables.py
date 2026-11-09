"""Host-functional fixed form tables. These are not native parity fixtures."""
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.dates import BSLDate
from yadinassi.form_model import BSLFormAttribute, BSLFormTable
from yadinassi.form_runtime import FormSession
from yadinassi.form_tables import (FormTableColumn, FormTableSchema,
    BSLFormDataCollection, BSLFormDataCollectionItem, validate_table_data)
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import BSLStringQualifiers, BSLAllowedLength
from yadinassi.values import BSLType


def column(name, kind='String', **kwargs):
    return FormTableColumn(name, BSLTypeDescription(kind), **kwargs)


SCHEMA = FormTableSchema('Lines', (column('Label'), column('Quantity', 'Number'),
                                   column('Amount', 'Number', read_only=True)), 'Order lines')
SOURCE = '''
&AtServer
Procedure Create(Cancel, StandardProcessing)
 T = Items.Add("Grid", Type("FormTable")); T.DataPath = "Lines";
 T.SetAction("OnChange", "Changed");
 R = Lines.Add(); R.Label = "first"; R.Quantity = 2; R.Amount = 4;
 C = Commands.Add("Run"); C.Action = "RunCommand";
 B = Items.Add("RunButton", Type("FormButton")); B.CommandName = "Run";
 // extra-create
EndProcedure
&AtClient
Procedure Changed(Element)
 Status = String(Element.CurrentRow);
 Element.CurrentData.Label = "edited";
EndProcedure
&AtClient
Procedure RunCommand(Command)
 Work();
EndProcedure
&AtServer
Procedure Work()
 // work
EndProcedure
'''


def make(*, create='', work='', changed=None, client=None, tables=(SCHEMA,)):
    source = SOURCE.replace('// extra-create', create).replace('// work', work)
    if changed is not None:
        source = source.replace('Status = String(Element.CurrentRow);\n Element.CurrentData.Label = "edited";', changed)
    if client is not None: source = source.replace(' Work();', ' ' + client)
    return FormSession(source, tables=tables,
        attributes=(BSLFormAttribute('Status', BSLTypeDescription('String')),),
        bindings={'OnCreateAtServer': 'Create'})


@contextmanager
def active(session, side='server', module=True):
    """Trusted host access for ownership/budget assertions, not an API bypass."""
    session._busy = True
    session.interpreter._context_stack.append(side)
    session.interpreter._module_context_stack.append(module)
    try: yield
    finally:
        session.interpreter._module_context_stack.pop()
        session.interpreter._context_stack.pop()
        session._busy = False


class FormTableTests(unittest.TestCase):
    def test_full_cell_selection_command_workflow(self):
        session = make(work='R = Lines.Add(); R.Label = "second";')
        first = session.open()
        self.assertEqual(first.tables[0].rows, ((1, ('first', Decimal(2), Decimal(4))),))
        snap = session.dispatch('cell', revision=1, control='Grid', row=1, column='Quantity', value=Decimal('3.125'))
        self.assertEqual(snap.tables[0].rows[0][1], ('edited', Decimal('3.125'), Decimal(4)))
        self.assertEqual(dict(snap.attributes)['Status'], '1')
        self.assertEqual(dict(snap.selections), {'Grid': 1})
        self.assertEqual(len(session.dispatch('command', revision=2, control='RunButton').tables[0].rows), 2)
        self.assertEqual(session.dispatch('close', revision=3).state, 'closed')

    def test_client_trusted_cells_ignore_view_readonly(self):
        session = make(client='R = Lines.Get(0); R.Amount = 10; Items.Grid.CurrentRow = R.GetID();')
        session.open(); snap = session.dispatch('command', revision=1, control='RunButton')
        self.assertEqual(snap.tables[0].rows[0][1][2], Decimal(10))
        self.assertEqual(snap.selections, (('Grid', 1),))

    def test_client_structural_mutations_are_rejected(self):
        for statement in ('Lines.Add();', 'Lines.Delete(Lines.Get(0));', 'Lines.Clear();'):
            with self.subTest(statement=statement):
                session = make(client=statement); session.open()
                with self.assertRaises(Exception): session.dispatch('command', revision=1, control='RunButton')
                self.assertEqual(len(session.snapshot().tables[0].rows), 1)

    def test_server_delete_clear_never_reuses_ids(self):
        session = make(work='Lines.Delete(Lines.Get(0)); R = Lines.Add(); Lines.Clear(); R = Lines.Add();')
        session.open(); old = session.form._tables['lines']._rows[0]
        snap = session.dispatch('command', revision=1, control='RunButton')
        self.assertEqual(snap.tables[0].rows[0][0], 3)
        self.assertTrue(old._removed)
        self.assertEqual(snap.tables[0].allocated, 3)

    def test_foreign_deleted_and_detached_rows_fail_closed(self):
        first = make(); second = make(); first.open(); second.open()
        table = first.form._tables['lines']; own = table._rows[0]
        with active(first):
            with self.assertRaises(ValueError): table.delete(second.form._tables['lines']._rows[0])
            detached_table = BSLFormDataCollection(first.form, SCHEMA, 1)
            with self.assertRaises(ValueError): detached_table.count()
            detached = BSLFormDataCollectionItem(table, 2)
            with self.assertRaises(ValueError): detached.get_id()
            table.delete(own)
            with self.assertRaises(ValueError): own.get_member('Label')
            with self.assertRaises(ValueError): own.set_member('Label', 'wrong')
            with self.assertRaises(ValueError): own.get_id()

    def test_nocontext_rejects_table_and_row(self):
        session = make(); session.open(); table = session.form._tables['lines']; row = table._rows[0]
        with active(session, module=False):
            for callback in (table.count, row.get_id, lambda: session.form.get_member('Lines')):
                with self.assertRaises(ValueError): callback()

    def test_inactive_and_closed_handles_are_unusable(self):
        session = make(); session.open(); table = session.form._tables['lines']; row = table._rows[0]
        with self.assertRaises(ValueError): table.count()
        with self.assertRaises(ValueError): row.get_id()
        session.dispatch('close', revision=1)
        with active(session):
            with self.assertRaises(ValueError): row.get_id()
            with self.assertRaises(ValueError): table.count()

    def test_select_and_clear_have_no_change_handler(self):
        session = make(); session.open()
        snap = session.dispatch('select', revision=1, control='Grid', row=1)
        self.assertEqual(snap.selections, (('Grid', 1),))
        self.assertEqual(dict(snap.attributes)['Status'], '')
        self.assertEqual(session.dispatch('select', revision=2, control='Grid', row=None).selections, (('Grid', None),))

    def test_selection_currentdata_and_currentrow_setters(self):
        session = make(client='Items.Grid.CurrentRow = 1; Status = Items.Grid.CurrentData.Label; Items.Grid.CurrentRow = Undefined;')
        session.open(); snap = session.dispatch('command', revision=1, control='RunButton')
        self.assertEqual(dict(snap.attributes)['Status'], 'first')
        self.assertEqual(snap.selections, (('Grid', None),))
        with active(session):
            grid = session.form.items._values['grid']
            for value in (True, Decimal('1.1'), Decimal(0), Decimal(99)):
                with self.assertRaises(ValueError): grid.set_member('CurrentRow', value)
            with self.assertRaises(ValueError): grid.set_member('CurrentData', None)

    def test_delete_and_clear_remove_selection_without_autoselect(self):
        for work in ('Lines.Delete(Lines.Get(0));', 'Lines.Clear();'):
            session = make(work=work, create='R = Lines.Add();'); session.open()
            session.dispatch('select', revision=1, control='Grid', row=1)
            snap = session.dispatch('command', revision=2, control='RunButton')
            self.assertEqual(snap.selections, (('Grid', None),))

    def test_snapshot_is_frozen_and_detached(self):
        session = make(); old = session.open()
        session.dispatch('cell', revision=1, control='Grid', row=1, column='Label', value='later')
        self.assertEqual(old.tables[0].rows[0][1][0], 'first')
        with self.assertRaises(FrozenInstanceError): old.tables[0].name = 'wrong'
        self.assertEqual(old.tables[0].columns[1], ('Quantity', '', 'Number', False))
        self.assertEqual(old.items[0][1], 'table')
        self.assertEqual(old.item_views, ())

    def test_fixed_schema_validation(self):
        for columns in ((), [], (column('A'), column('a')), tuple(column('C'+str(i)) for i in range(9))):
            with self.assertRaises(ValueError): FormTableSchema('Lines', columns)
        for bad in ('ValueTable', 'String,Number', 'UUID'):
            with self.assertRaises(ValueError): FormTableColumn('A', BSLTypeDescription(bad))
        with self.assertRaises(TypeError): column('A', read_only=1)
        with self.assertRaises(ValueError): column('GetID')
        with self.assertRaises(ValueError): FormTableSchema('bad.name', (column('A'),))

    def test_static_and_dynamic_namespace_collisions(self):
        with self.assertRaises(ValueError): FormSession('', tables=(SCHEMA,), attributes=(BSLFormAttribute('LINES', BSLTypeDescription('String')),))
        with self.assertRaises(ValueError): FormSession('', tables=(SCHEMA, SCHEMA))
        with self.assertRaises(ValueError): FormSession('', tables=(FormTableSchema('Items', (column('A'),)),))
        session = make(create='A = New Array; A.Add(New FormAttribute("LINES", New TypeDescription("String"))); ChangeAttributes(A);')
        with self.assertRaises(Exception): session.open()
        self.assertNotIn('lines', session.form._attributes)

    def test_entire_table_assignment_is_forbidden(self):
        for statement in ('Lines = Undefined;', 'ThisObject.Lines = Undefined;'):
            session = make(client=statement); session.open()
            with self.assertRaises(Exception): session.dispatch('command', revision=1, control='RunButton')
            self.assertEqual(session.snapshot().tables[0].rows[0][0], 1)

    def test_unique_binding_and_table_control_limit(self):
        session = make(create='Other = Items.Add("Other", Type("FormTable")); Other.DataPath = "Lines";')
        with self.assertRaises(Exception): session.open()
        session = make(create='For I = 1 To 4 Do Items.Add("Table" + String(I), Type("FormTable")); EndDo;')
        with self.assertRaises(Exception): session.open()
        self.assertEqual(sum(type(item) is BSLFormTable for item in session.form.items._values.values()), 4)
        with self.assertRaises(ValueError): FormSession('', tables=tuple(FormTableSchema('T'+str(i), (column('A'),)) for i in range(5)))

    def test_table_and_scalar_field_bindings_are_disjoint(self):
        for create in ('F = Items.Add("Bad", Type("FormField")); F.DataPath = "Lines";',
                       'F = Items.Add("Bad", Type("FormTable")); F.DataPath = "Status";',
                       'T.DataPath = "Lines";'):
            session = make(create=create)
            with self.assertRaises(Exception): session.open()

    def test_unavailable_controls_reject_before_mutation(self):
        for property in ('Visible', 'Enabled', 'ReadOnly'):
            value = 'True' if property == 'ReadOnly' else 'False'
            session = make(create='T.'+property+' = '+value+';'); session.open()
            with self.assertRaises(ValueError): session.dispatch('cell', revision=1, control='Grid', row=1, column='Label', value='bad')
            self.assertEqual(session.revision, 1)
            self.assertEqual(session.snapshot().tables[0].rows[0][1][0], 'first')

    def test_readonly_unknown_column_and_wrong_event_control(self):
        session = make(); session.open()
        for kwargs in ({'event':'cell','control':'Grid','row':1,'column':'Amount','value':Decimal(2)},
                       {'event':'cell','control':'Grid','row':1,'column':'Unknown','value':'x'},
                       {'event':'change','control':'Grid','value':'x'},
                       {'event':'select','control':'RunButton','row':1}):
            with self.assertRaises(ValueError): session.dispatch(revision=1, **kwargs)
        self.assertEqual(session.revision, 1)

    def test_invalid_stale_and_deleted_row_ids(self):
        session = make(); session.open()
        for identity in (True, 0, -1, 4097, '1', Decimal(1), 2):
            with self.assertRaises(ValueError): session.dispatch('select', revision=1, control='Grid', row=identity)
        with self.assertRaises(ValueError): session.dispatch('select', revision=0, control='Grid', row=1)
        with self.assertRaises(ValueError): session.dispatch('cell', revision=1, control='Grid', row=None, column='Label', value='x')
        self.assertEqual(session.revision, 1)

    def test_failed_cell_value_does_not_change_selection_or_value(self):
        session = make(); session.open()
        with self.assertRaises(ValueError): session.dispatch('cell', revision=1, control='Grid', row=1, column='Label', value='x' * 8193)
        snap = session.snapshot()
        self.assertEqual(snap.tables[0].rows[0][1][0], 'first')
        self.assertEqual(snap.selections, (('Grid', None),))
        self.assertEqual(snap.revision, 2)

    def test_handler_error_retains_completed_cell_and_selection(self):
        session = make(changed='Element.CurrentData.Label = "known"; Raise "stop";'); session.open()
        with self.assertRaises(Exception): session.dispatch('cell', revision=1, control='Grid', row=1, column='Quantity', value=Decimal(9))
        snap = session.snapshot()
        self.assertEqual(snap.tables[0].rows[0][1][:2], ('known', Decimal(9)))
        self.assertEqual(snap.selections, (('Grid', 1),))
        self.assertEqual(snap.revision, 2)

    def test_replica_install_preserves_handles_and_rejects_recycled_ids(self):
        session = make(); session.open(); table = session.form._tables['lines']; old = table._rows[0]
        table._replace_rows(((1, ('new', Decimal(3), Decimal(6))), (3, ('third', Decimal(0), Decimal(0)))), 3)
        self.assertIs(table._rows[0], old)
        table._replace_rows(((3, ('third', Decimal(0), Decimal(0))),), 3)
        self.assertTrue(old._removed)
        for rows, allocated in ((((1, ('recycled', Decimal(0), Decimal(0))),), 3),
                                (((3, ('third', Decimal(0), Decimal(0))),), 2)):
            with self.assertRaises(ValueError): table._replace_rows(rows, allocated)
        self.assertEqual(table._rows[0]._row_id, 3)

    def test_row_budget_is_checked_before_add(self):
        session = make(); session.open(); table = session.form._tables['lines']
        with active(session):
            for _ in range(31): table.add()
            with self.assertRaises(ValueError): table.add()
        self.assertEqual((len(table._rows), table._allocated), (32, 32))

    def test_lifetime_row_budget_is_not_reset_by_clear(self):
        session = make(); session.open(); table = session.form._tables['lines']
        with patch('yadinassi.form_tables.MAX_TABLE_ALLOCATED', 2), active(session):
            table.clear(); table.add(); table.clear()
            with self.assertRaises(ValueError): table.add()
        self.assertEqual(table._allocated, 2)
        self.assertEqual(table._rows, [])

    def test_aggregate_cells_budget(self):
        tables = tuple(FormTableSchema('T'+str(i), tuple(column('C'+str(j)) for j in range(8))) for i in range(2))
        session = FormSession('', tables=tables)
        first, second = session.form._tables.values()
        with active(session):
            for _ in range(16): first.add(); second.add()
            with self.assertRaises(ValueError): first.add()
        self.assertEqual((len(first._rows), len(second._rows)), (16, 16))
        # A replica installs a fully validated multi-table candidate. Its first
        # table may grow before its second table shrinks; never validate that
        # transient aggregate against the already-validated final budget.
        growing = first._snapshot().rows + tuple((i, ('',) * 8) for i in range(17, 25))
        shrinking = second._snapshot().rows[:8]
        validate_table_data(session.form, {'t0': growing, 't1': shrinking})
        first._replace_rows(growing, 24)
        second._replace_rows(shrinking, 16)
        validate_table_data(session.form)

    def test_serialized_utf8_budget_is_atomic(self):
        session = make(); session.open(); table = session.form._tables['lines']
        with active(session):
            row = table._rows[0]
            row.set_member('Label', 'é' * 3000)
            with patch('yadinassi.form_tables.MAX_TABLE_DATA_BYTES', 100):
                with self.assertRaises(ValueError): row.set_member('Label', 'é' * 50)
            self.assertEqual(row.get_member('Label'), 'é' * 3000)
        with self.assertRaises(ValueError): validate_table_data(session.form, {'missing': ()})

    def test_scalar_and_table_text_share_budget(self):
        session = make(); session.open(); row = session.form._tables['lines']._rows[0]
        with active(session), patch('yadinassi.form_model.MAX_TOTAL_TEXT', 10), patch('yadinassi.form_tables.MAX_TOTAL_TEXT', 10):
            session.form.set_member('Status', 'abcde')
            with self.assertRaises(ValueError): row.set_member('Label', 'abcdef')
            with self.assertRaises(ValueError): session.form.set_member('Status', 'abcdef')
            self.assertEqual(row.get_member('Label'), 'first')

    def test_types_registered_but_internal_serialization_refused(self):
        from yadinassi.type_values import type_of, type_by_name
        from yadinassi.serialization import value_to_string_internal
        session = make(); session.open(); table = session.form._tables['lines']
        for value, kind, english in ((table, BSLType.FORM_DATA_COLLECTION, 'FormDataCollection'),
                                    (table._rows[0], BSLType.FORM_DATA_COLLECTION_ITEM, 'FormDataCollectionItem'),
                                    (session.form.items._values['grid'], BSLType.FORM_TABLE, 'FormTable')):
            self.assertIs(type_of(value), kind)
            self.assertIs(type_by_name(english), kind)
            self.assertIs(type_by_name(kind.value), kind)
            for unsupported in (value, kind):
                with self.assertRaises((TypeError, ValueError)): value_to_string_internal(unsupported)

    def test_no_constructor_or_ordinary_context_codec(self):
        from yadinassi.invocation import _encode_scalar
        session = make(); session.open(); table = session.form._tables['lines']
        for value in (table, table._rows[0], session.form.items._values['grid']):
            with self.assertRaises((TypeError, ValueError)): _encode_scalar(value)
            with self.assertRaises((TypeError, ValueError)): Interpreter._copy_context_packet([value])
        for type_name in ('FormDataCollection', 'FormDataCollectionItem', 'FormTable'):
            with self.assertRaises(Exception): Interpreter().execute('X = New '+type_name+';')

    def test_bad_replica_candidate_is_rejected_atomically(self):
        session = make(); session.open(); table = session.form._tables['lines']; before = table._snapshot()
        bad = (((1, ('bad', Decimal(1), Decimal(1))), (2, ('incomplete',))),
               ((1, ('bad', Decimal(1), Decimal(1))), (1, ('duplicate', Decimal(1), Decimal(1)))),
               ((2, ('wrong', 'not number', Decimal(0))),))
        for rows in bad:
            with self.assertRaises((TypeError, ValueError)): table._replace_rows(rows, 2)
            self.assertEqual(table._snapshot(), before)

    def test_decimal_boolean_date_and_qualified_values(self):
        fixed = BSLTypeDescription('String', None, BSLStringQualifiers(Decimal(3), BSLAllowedLength.FIXED))
        schema = FormTableSchema('Data', (FormTableColumn('Text', fixed), column('Amount','Number'), column('Flag','Boolean'), column('When','Date')))
        session = FormSession('', tables=(schema,)); table = session.form._tables['data']
        with active(session):
            row = table.add(); row.set_member('Text','abcde'); row.set_member('Amount',Decimal('1.23000'))
            row.set_member('Flag',True); row.set_member('When', BSLDate(123456789))
        values = table._snapshot().rows[0][1]
        self.assertEqual(values[0], 'abc')
        self.assertEqual(str(values[1]), '1.23000')
        self.assertIs(values[2], True)
        self.assertEqual(values[3].ticks, 123456789)

    def test_bare_member_iteration_and_index_access(self):
        session = make(work='For Each R In ThisObject.Lines Do R.Quantity = R.Quantity + 1; EndDo; Status = Lines[0].Label;')
        session.open(); snap = session.dispatch('command', revision=1, control='RunButton')
        self.assertEqual(snap.tables[0].rows[0][1][1], Decimal(3))
        self.assertEqual(dict(snap.attributes)['Status'], 'first')
        with active(session):
            for index in (Decimal('-1'), Decimal('0.5'), Decimal(1), True):
                with self.assertRaises(ValueError): session.form._tables['lines'].get(index)

    def test_unbound_and_deleted_table_controls(self):
        session = make(create='Items.Add("Unbound", Type("FormTable"));'); session.open()
        with self.assertRaises(ValueError): session.dispatch('select', revision=1, control='Unbound', row=1)
        with active(session):
            grid = session.form.items._values['grid']; session.form.items.delete(grid)
            with self.assertRaises(ValueError): grid.get_member('CurrentData')
        with self.assertRaises(ValueError): session.dispatch('select', revision=1, control='Grid', row=1)

    def test_getattributes_remains_scalar_only(self):
        session = make(create='A = GetAttributes(); Status = String(A.Count());'); snap = session.open()
        self.assertEqual(dict(snap.attributes)['Status'], '1')
        self.assertEqual(tuple(session.form._attributes), ('status',))
