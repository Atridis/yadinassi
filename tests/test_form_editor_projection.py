"""Trusted scalar editor metadata does not widen value/storage admission."""
from decimal import Decimal
import unittest

from yadinassi.dates import BSLDate, date, MAX_TICKS
from yadinassi.form_model import BSLFormAttribute
from yadinassi.form_replication import ReplicatedFormServer, _decode_form_scalar
from yadinassi.form_tables import FormTableColumn, FormTableSchema
from yadinassi.invocation import InvocationBinding, _encode_scalar
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
    BSLDateQualifiers, BSLAllowedSign, BSLAllowedLength, BSLDateFractions)
from yadinassi.ui.form_app import FormController, PROTOCOL
from yadinassi.ui.form_package import ClientPackage
from yadinassi.ui.protocol import encode_value


def description(kind, *, number=None, string=None, parts=None):
    return BSLTypeDescription(kind, number, string,
        None if parts is None else BSLDateQualifiers(parts))


HANDLERS = (InvocationBinding('Changed', 1, ('Element',), False),)
CLIENT = '''&AtClient
Procedure Changed(Element)
    Changes = Changes + 1;
EndProcedure
'''
SERVER = '''&AtServer
Procedure Create(Cancel, StandardProcessing)
    F = Items.Add("WhenField", Type("FormField")); F.DataPath = "When";
    F.SetAction("OnChange", "Changed");
    F = Items.Add("DayField", Type("FormField")); F.DataPath = "Day";
    F.SetAction("OnChange", "Changed");
    F = Items.Add("TimeField", Type("FormField")); F.DataPath = "Clock";
    F.SetAction("OnChange", "Changed");
    F = Items.Add("CodeField", Type("FormField")); F.DataPath = "Code";
    F.SetAction("OnChange", "Changed");
    F = Items.Add("AmountField", Type("FormField")); F.DataPath = "Amount";
    F.SetAction("OnChange", "Changed");
    T = Items.Add("Grid", Type("FormTable")); T.DataPath = "Lines";
    T.SetAction("OnChange", "Changed");
    R = Lines.Add(); R.When = Date(2024, 2, 29, 12, 30, 45);
EndProcedure
'''


def pair():
    kinds = {
        'When': description('Date'),
        'Day': description('Date', parts=BSLDateFractions.DATE),
        'Clock': description('Date', parts=BSLDateFractions.TIME),
        'Code': description('String', string=BSLStringQualifiers(Decimal(5), BSLAllowedLength.FIXED)),
        'Amount': description('Number', number=BSLNumberQualifiers(Decimal(5), Decimal(2), BSLAllowedSign.NONNEGATIVE)),
        'Changes': description('Number'),
    }
    schema = FormTableSchema('Lines', tuple(FormTableColumn(name, kinds[name])
        for name in ('When', 'Day', 'Clock', 'Code', 'Amount')))
    server = ReplicatedFormServer(SERVER, {}, handlers=HANDLERS,
        attributes=tuple(BSLFormAttribute(name, kind) for name, kind in kinds.items()),
        tables=(schema,), bindings={'OnCreateAtServer': 'Create'})
    controller = FormController(ClientPackage(CLIENT, HANDLERS, ()), server.exchange)
    controller.exchange({'jsonrpc':'2.0','id':1,'method':'form.hello','params':{'protocol':PROTOCOL}})
    return controller, server


def change(controller, control, value, **extra):
    return controller.exchange({'jsonrpc':'2.0','id':2,'method':'form.event','params':{
        'event':'cell' if extra else 'change','revision':controller.session.revision,
        'control':control,'value':encode_value(value),**extra}})['result']


class EditorDescriptionTests(unittest.TestCase):
    def test_unqualified_number_has_closed_descriptor(self):
        self.assertEqual(FormController._editor_description(description('Number')),
            {'kind':'number','digits':0,'scale':0,'nonnegative':False})

    def test_qualified_number_preserves_exact_counts_and_sign(self):
        kind = description('Number', number=BSLNumberQualifiers(Decimal(12), Decimal(4), BSLAllowedSign.NONNEGATIVE))
        self.assertEqual(FormController._editor_description(kind),
            {'kind':'number','digits':12,'scale':4,'nonnegative':True})

    def test_fixed_string_uses_utf16_length_metadata(self):
        kind = description('String', string=BSLStringQualifiers(Decimal(5), BSLAllowedLength.FIXED))
        self.assertEqual(FormController._editor_description(kind),{'kind':'string','length':5,'fixed':True})

    def test_unqualified_string_is_not_claimed_fixed(self):
        self.assertEqual(FormController._editor_description(description('String')),
            {'kind':'string','length':0,'fixed':False})

    def test_date_parts_are_closed_literals(self):
        for parts, expected in ((BSLDateFractions.DATE_TIME,'dateTime'), (BSLDateFractions.DATE,'date'), (BSLDateFractions.TIME,'time')):
            with self.subTest(parts=parts):
                self.assertEqual(FormController._editor_description(description('Date',parts=parts)),
                    {'kind':'date','parts':expected})

    def test_boolean_and_unknown_descriptors_have_no_editor(self):
        self.assertIsNone(FormController._editor_description(description('Boolean')))
        self.assertIsNone(FormController._editor_description(object()))

    def test_result_is_detached_from_immutable_descriptor(self):
        kind = description('Date'); projected = FormController._editor_description(kind)
        projected['parts']='time'
        self.assertEqual(FormController._editor_description(kind)['parts'],'dateTime')

    def test_generic_invocation_still_rejects_empty_date(self):
        with self.assertRaises(Exception): _encode_scalar(BSLDate(0))
        self.assertEqual(_decode_form_scalar({'type':'Date','ticks':'0'}),BSLDate(0))

    def test_scalar_max_and_fractional_envelope_is_unchanged(self):
        for ticks in (MAX_TICKS,1):
            with self.subTest(ticks=ticks):
                with self.assertRaises(Exception): _decode_form_scalar({'type':'Date','ticks':str(ticks)})


class EditorProjectionFlowTests(unittest.TestCase):
    def setUp(self): self.controller, self.server = pair()

    def item(self, name): return next(i for i in self.controller._snapshot()['items'] if i['name']==name)

    def test_fields_project_their_exact_runtime_qualifiers(self):
        self.assertEqual(self.item('DayField')['editor'],{'kind':'date','parts':'date'})
        self.assertEqual(self.item('TimeField')['editor'],{'kind':'date','parts':'time'})
        self.assertEqual(self.item('AmountField')['editor']['scale'],2)
        self.assertEqual(self.item('CodeField')['editor']['length'],5)

    def test_table_columns_project_metadata_without_changing_value_packets(self):
        grid=self.item('Grid');columns={c['name']:c for c in grid['columns']}
        self.assertEqual(columns['Clock']['editor'],{'kind':'date','parts':'time'})
        self.assertEqual(columns['Code']['editor'],{'kind':'string','length':5,'fixed':True})
        self.assertEqual(set(grid['rows'][0]['values'][0]),{'type','ticks'})

    def test_date_change_uses_the_ordinary_onchange_once(self):
        value=date(Decimal(2024),Decimal(2),Decimal(29),Decimal(12),Decimal(30),Decimal(45))
        self.assertIsNone(change(self.controller,'WhenField',value)['error'])
        self.assertEqual(self.item('WhenField')['value'],encode_value(value))
        self.assertEqual(dict(self.controller.session.snapshot().attributes)['Changes'],Decimal(1))

    def test_empty_date_is_an_exact_typed_value(self):
        self.assertIsNone(change(self.controller,'WhenField',BSLDate(0))['error'])
        self.assertEqual(self.item('WhenField')['value'],{'type':'Date','ticks':'0'})

    def test_server_remains_authoritative_for_date_parts(self):
        value=date(Decimal(2024),Decimal(2),Decimal(29),Decimal(12),Decimal(30),Decimal(45))
        self.assertIsNone(change(self.controller,'DayField',value)['error'])
        self.assertIsNone(change(self.controller,'TimeField',value)['error'])
        day=86400*10000
        self.assertEqual(self.item('DayField')['value']['ticks'],str(value.ticks//day*day))
        self.assertEqual(self.item('TimeField')['value']['ticks'],str(value.ticks%day))

    def test_server_normalization_of_number_and_fixed_string_is_not_replaced(self):
        self.assertIsNone(change(self.controller,'AmountField',Decimal('1.235'))['error'])
        self.assertIsNone(change(self.controller,'CodeField','AB')['error'])
        self.assertEqual(self.item('AmountField')['value'],{'type':'Number','value':'1.24'})
        self.assertEqual(self.item('CodeField')['value'],{'type':'String','value':'AB   '})

    def test_date_table_cell_changes_exact_row_without_retargeting(self):
        value=date(Decimal(2025),Decimal(1),Decimal(2),Decimal(3),Decimal(4),Decimal(5))
        self.assertIsNone(change(self.controller,'Grid',value,row=1,column='When')['error'])
        self.assertEqual(self.item('Grid')['rows'][0]['values'][0],encode_value(value))
        self.assertEqual(dict(self.controller.session.snapshot().attributes)['Changes'],Decimal(1))

    def test_editor_metadata_cannot_be_supplied_by_browser_event(self):
        before=self.controller.session.snapshot()
        with self.assertRaises(ValueError):
            self.controller.exchange({'jsonrpc':'2.0','id':2,'method':'form.event','params':{
                'event':'change','revision':self.controller.session.revision,'control':'WhenField',
                'value':{'type':'Date','ticks':'0'},'editor':{'kind':'date','parts':'time'}}})
        self.assertEqual(before,self.controller.session.snapshot())
