"""Host primitive contracts only; no native UI or public BSL API assertions."""
from dataclasses import FrozenInstanceError
from decimal import Decimal, InvalidOperation, localcontext
import gc
import unittest
from unittest.mock import patch
import weakref

from yadinassi.dates import BSLDate, MAX_TICKS, TICKS_PER_SECOND
from yadinassi.form_value_input import (ScalarInputSpec, ValueListSelection,
    MAX_CHOICES, MAX_SELECTION_BYTES)
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
    BSLDateQualifiers, BSLAllowedSign, BSLAllowedLength, BSLDateFractions)
from yadinassi.ui.protocol import encode_value, CatalogRef
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, NULL

D = Decimal
TD = BSLTypeDescription


def number(digits=5, scale=2, sign=BSLAllowedSign.ANY):
    return TD('Number', BSLNumberQualifiers(D(digits), D(scale), sign))


def string(length=5, fixed=False):
    return TD('String', None, BSLStringQualifiers(D(length),
        BSLAllowedLength.FIXED if fixed else BSLAllowedLength.VARIABLE))


def date_type(parts):
    return TD('Date', None, None, BSLDateQualifiers(parts))


def choices(*values):
    result = BSLValueList()
    for value in values:
        result.add(value, 'choice')
    return result


class ScalarInputTests(unittest.TestCase):
    def test_all_four_exact_scalar_types_roundtrip(self):
        for kind, value in [('String', 'plain'), ('Number', D('1.2300')),
                            ('Boolean', False), ('Date', BSLDate(TICKS_PER_SECOND))]:
            with self.subTest(kind=kind):
                spec = ScalarInputSpec.capture(TD(kind), value)
                self.assertEqual(spec.public()['value'], encode_value(value))
                self.assertEqual(spec.decode(encode_value(value)), value)

    def test_undefined_initial_uses_only_explicit_single_type_default(self):
        for descriptor, value in [(TD('String'), ''), (TD('Number'), D(0)),
                                  (TD('Boolean'), False), (TD('Date'), BSLDate(0)),
                                  (string(3, True), '   ')]:
            with self.subTest(types=descriptor.types):
                self.assertEqual(ScalarInputSpec.capture(descriptor, None).public()['value'], encode_value(value))

    def test_empty_union_null_and_nonscalar_descriptors_refused(self):
        for descriptor in (TD(), TD('String,Number'), TD('Null'), TD('UUID'), object(), None):
            with self.subTest(descriptor_type=type(descriptor).__name__):
                with self.assertRaises((TypeError, ValueError)):
                    ScalarInputSpec.capture(descriptor, None)

    def test_descriptor_subclass_never_runs_override(self):
        class BadDescriptor(TD):
            def adjust_value(self, *args): raise AssertionError('subclass hook')
        with self.assertRaises(TypeError):
            ScalarInputSpec.capture(BadDescriptor('String'), 'x')

    def test_initial_and_answer_have_exact_types_without_coercion(self):
        for descriptor, initial, invalid in [(TD('Number'), D(0), True),
                                             (TD('Number'), D(0), '1'),
                                             (TD('Boolean'), False, D(1)),
                                             (TD('String'), '', D(1)),
                                             (TD('Date'), BSLDate(0), '20240101')]:
            with self.subTest(types=descriptor.types, invalid_type=type(invalid).__name__):
                with self.assertRaises(TypeError): ScalarInputSpec.capture(descriptor, invalid)
                with self.assertRaises(TypeError): ScalarInputSpec.capture(descriptor, initial).decode(encode_value(invalid))

    def test_undefined_and_null_answers_are_not_cancellation(self):
        spec = ScalarInputSpec.capture(TD('String'), '')
        for value in (None, NULL):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(TypeError): spec.decode(encode_value(value))

    def test_public_nested_packets_are_detached(self):
        spec = ScalarInputSpec.capture(number(), D('1.25'))
        first = spec.public(); first['value']['value'] = '9999'; first['editor']['scale'] = 0
        self.assertEqual(spec.public(), {'value': encode_value(D('1.25')),
            'editor': {'kind': 'number', 'digits': 5, 'scale': 2, 'nonnegative': False}})

    def test_spec_fields_are_immutable(self):
        spec = ScalarInputSpec.capture(TD('String'), 'x')
        with self.assertRaises(FrozenInstanceError): spec._initial = b'changed'
        with self.assertRaises(FrozenInstanceError): spec._descriptor = TD('Number')

    def test_number_scale_rejects_rounding_but_accepts_trailing_zeroes(self):
        spec = ScalarInputSpec.capture(number(), D('1.2300'))
        self.assertEqual(str(spec.decode(encode_value(D('1.2300')))), '1.2300')
        for value in (D('1.234'), D('-1.234')):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): spec.decode(encode_value(value))

    def test_number_magnitude_rejects_clamping(self):
        spec = ScalarInputSpec.capture(number(3, 2), D(0))
        for value in (D('10'), D('-10'), D('1E+100')):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): spec.decode(encode_value(value))
        self.assertEqual(spec.decode(encode_value(D('9.99'))), D('9.99'))

    def test_nonnegative_rejects_negative_not_sign_zero(self):
        spec = ScalarInputSpec.capture(number(sign=BSLAllowedSign.NONNEGATIVE), D('-0.00'))
        self.assertEqual(spec.public()['value']['value'], '-0.00')
        with self.assertRaises(ValueError): spec.decode(encode_value(D('-0.01')))

    def test_unqualified_number_preserves_exponent(self):
        spec = ScalarInputSpec.capture(TD('Number'), D('1E-99'))
        self.assertEqual(str(spec.decode(spec.public()['value'])), '1E-99')

    def test_decimal_context_and_invalid_decode_do_not_leak_flags(self):
        spec = ScalarInputSpec.capture(number(8, 2), D(0))
        with localcontext() as context:
            context.prec = 2; context.clear_flags()
            self.assertEqual(spec.decode(encode_value(D('1234.50'))), D('1234.50'))
            with self.assertRaises(ValueError): spec.decode({'type':'Number', 'value':'bad'})
            self.assertFalse(any(context.flags.values()))
            self.assertTrue(context.traps[InvalidOperation])

    def test_number_resource_limits_and_nonfinite_rejected(self):
        for value in (D('NaN'), D('Infinity'), D('1E+4097'), D('1' * 129)):
            with self.subTest(value=str(value)[:16]):
                with self.assertRaises((TypeError, ValueError)): ScalarInputSpec.capture(TD('Number'), value)

    def test_string_utf16_length_is_not_codepoint_length(self):
        spec = ScalarInputSpec.capture(string(2), '😀')
        self.assertEqual(spec.decode(encode_value('😀')), '😀')
        for value in ('😀x', 'abc'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): spec.decode(encode_value(value))

    def test_fixed_string_only_right_padding_is_admitted(self):
        spec = ScalarInputSpec.capture(string(4, True), 'x')
        self.assertEqual(spec.public()['value']['value'], 'x   ')
        self.assertEqual(spec.decode(encode_value('😀')), '😀  ')
        with self.assertRaises(ValueError): spec.decode(encode_value('abcde'))

    def test_string_wire_budget_surrogate_and_nul_refused(self):
        for value in ('x' * 8193, '😀' * 2049, '\ud800', 'bad\x00text'):
            with self.subTest(length=len(value)):
                with self.assertRaises((TypeError, ValueError)): ScalarInputSpec.capture(TD('String'), value)

    def test_existing_qualifier_limits_still_apply(self):
        for descriptor in (number(129), string(65537)):
            with self.assertRaises(ValueError): ScalarInputSpec.capture(descriptor, None)

    def test_boolean_editor_is_explicit_and_not_number(self):
        spec = ScalarInputSpec.capture(TD('Boolean'), True)
        self.assertEqual(spec.public()['editor'], {'kind':'boolean'})
        with self.assertRaises(ValueError): spec.decode({'type':'Boolean', 'value':1})

    def test_empty_date_and_whole_second_boundary(self):
        spec = ScalarInputSpec.capture(TD('Date'), BSLDate(0))
        self.assertEqual(spec.decode(spec.public()['value']), BSLDate(0))
        self.assertEqual(spec.decode(encode_value(BSLDate(MAX_TICKS-TICKS_PER_SECOND))), BSLDate(MAX_TICKS-TICKS_PER_SECOND))
        for value in (BSLDate(1), BSLDate(MAX_TICKS), BSLDate(0, True)):
            with self.assertRaises(ValueError): ScalarInputSpec.capture(TD('Date'), value)

    def test_date_parts_reject_loss_of_date_or_time(self):
        day = 86400 * TICKS_PER_SECOND
        for parts, good, bad, label in ((BSLDateFractions.DATE, BSLDate(day), BSLDate(day+TICKS_PER_SECOND), 'date'),
                                        (BSLDateFractions.TIME, BSLDate(TICKS_PER_SECOND), BSLDate(day+TICKS_PER_SECOND), 'time')):
            with self.subTest(parts=label):
                spec = ScalarInputSpec.capture(date_type(parts), good)
                self.assertEqual(spec.public()['editor'], {'kind':'date', 'parts':label})
                with self.assertRaises(ValueError): spec.decode(encode_value(bad))

    def test_date_initial_is_an_immutable_image_not_retained_object(self):
        initial = BSLDate(TICKS_PER_SECOND)
        spec = ScalarInputSpec.capture(TD('Date'), initial)
        object.__setattr__(initial, 'ticks', 2*TICKS_PER_SECOND)
        self.assertEqual(spec.public()['value']['ticks'], str(TICKS_PER_SECOND))

    def test_packets_cannot_supply_metadata_or_references(self):
        spec = ScalarInputSpec.capture(TD('String'), '')
        bad = [[], {'type':'String', 'value':'x', 'editor':{}},
               {'type':'CatalogRef', 'catalog':'11111111-1111-1111-1111-111111111111',
                'record':'22222222-2222-2222-2222-222222222222'},
               {'type':'Number', 'value':1}, {'type':'String', 'value':None}]
        for packet in bad:
            with self.subTest(packet=packet):
                with self.assertRaises((TypeError, ValueError)): spec.decode(packet)

    def test_hostile_scalar_and_subclass_hooks_are_not_invoked(self):
        class Meta(type):
            def __eq__(self, other): raise AssertionError('metaclass equality')
        class Bad(metaclass=Meta):
            def __str__(self): raise AssertionError('string hook')
            def __eq__(self, other): raise AssertionError('value equality')
        class BadString(str):
            def __str__(self): raise AssertionError('subclass string')
        for value in (Bad(), BadString('x'), BSLArray(), object()):
            with self.assertRaises(TypeError): ScalarInputSpec.capture(TD('String'), value)
        spec = ScalarInputSpec.capture(TD('String'), '')
        for packet in ({'type':'String', 'value':Bad()},
                       {'type':BadString('String'), 'value':'x'},
                       {BadString('type'):'String', 'value':'x'}):
            with self.assertRaises(ValueError): spec.decode(packet)

    def test_decode_does_not_mutate_caller_packet_or_initial(self):
        spec = ScalarInputSpec.capture(TD('String'), 'first'); packet = encode_value('second')
        self.assertEqual(spec.decode(packet), 'second')
        self.assertEqual(packet, encode_value('second')); self.assertEqual(spec.public()['value'], encode_value('first'))


class ValueListSelectionTests(unittest.TestCase):
    def pending(self, *values):
        source = choices(*(values or ('one', 'two')))
        selection = ValueListSelection.capture(source)
        return source, selection, selection.public()['choices']

    def test_public_choices_use_opaque_tokens_and_detached_scalars(self):
        source, selection, rows = self.pending('x', D('1.25'), True, BSLDate(0))
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(set(row), {'choice','value','presentation'})
            self.assertRegex(row['choice'], '^[0-9a-f]{32}$')
        self.assertEqual(len({r['choice'] for r in rows}), 4)
        rows[0]['value']['value'] = 'changed'; rows[0]['presentation'] = 'changed'; rows.clear()
        self.assertEqual(selection.public()['choices'][0]['value'], encode_value('x'))
        self.assertEqual(source.items[0].value, 'x')

    def test_take_returns_exact_original_item_not_value_or_copy(self):
        source, selection, rows = self.pending()
        original = source.items[1]
        self.assertIs(selection.take(rows[1]['choice']), original)
        self.assertEqual(selection.state, 'consumed')
        original.set_member('Value', 'after callback')
        self.assertEqual(source.items[1].value, 'after callback')

    def test_duplicate_scalar_values_remain_distinct_item_choices(self):
        source, selection, rows = self.pending('same', 'same')
        self.assertNotEqual(rows[0]['choice'], rows[1]['choice'])
        self.assertIs(selection.take(rows[1]['choice']), source.items[1])

    def test_invalid_foreign_or_index_tokens_do_not_consume(self):
        source, selection, rows = self.pending()
        _, other, foreign = self.pending()
        for token in (None, 0, '0', 'x'*32, 'A'*32, 'a'*33, foreign[0]['choice']):
            with self.subTest(token_type=type(token).__name__):
                with self.assertRaises(ValueError): selection.take(token)
                self.assertEqual(selection.state, 'pending')
        self.assertIs(selection.take(rows[0]['choice']), source.items[0]); other.cancel()

    def test_second_take_and_public_after_terminal_cannot_replay(self):
        _, selection, rows = self.pending(); selection.take(rows[0]['choice'])
        for operation in (lambda: selection.take(rows[0]['choice']), lambda: selection.take(rows[1]['choice']), selection.public, selection.cancel):
            with self.assertRaises(ValueError): operation()
        self.assertEqual(selection.state, 'consumed')

    def test_cancel_is_terminal_without_touching_list(self):
        source, selection, rows = self.pending(); before = tuple(source.items)
        selection.cancel(); self.assertEqual(selection.state, 'cancelled')
        self.assertEqual(tuple(source.items), before)
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])
        with self.assertRaises(ValueError): selection.cancel()

    def test_value_mutation_without_revision_increment_is_stale(self):
        source, selection, rows = self.pending(); revision = source._revision
        source.items[0].set_member('Value', 'different')
        self.assertEqual(source._revision, revision)
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])
        self.assertEqual(selection.state, 'stale')

    def test_presentation_and_check_mutations_are_stale(self):
        for member, value in [('Presentation','changed'), ('Check',True)]:
            with self.subTest(member=member):
                source, selection, rows = self.pending(); source.items[1].set_member(member, value)
                with self.assertRaises(ValueError): selection.take(rows[0]['choice'])
                self.assertEqual(selection.state, 'stale')

    def test_unselected_item_mutation_also_invalidates_exact_snapshot(self):
        source, selection, rows = self.pending(); source.items[1].value = 'other'
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])

    def test_remove_then_recreate_same_value_does_not_retarget(self):
        source, selection, rows = self.pending(); source.delete(D(0)); source.insert(D(0), 'one', 'choice')
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])
        self.assertEqual(selection.state, 'stale')

    def test_order_change_cannot_retarget_by_position(self):
        source, selection, rows = self.pending(); source.move(D(0), D(1))
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])

    def test_structural_mutation_then_restoration_still_rejected(self):
        source, selection, rows = self.pending(); source.add('temporary'); source.delete(D(2))
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])

    def test_stale_publication_refuses_before_any_selection(self):
        source, selection, _ = self.pending(); source.fill_checks(True)
        with self.assertRaises(ValueError): selection.public()
        self.assertEqual(selection.state, 'stale')

    def test_identity_and_membership_checked_even_without_revision_drift(self):
        for mutation in ('owner','owner_hook','id','membership','detached','standalone','order'):
            with self.subTest(mutation=mutation):
                source, selection, rows = self.pending(); item = source.items[0]
                if mutation == 'owner':
                    foreign = choices('foreign'); item._owner_ref = weakref.ref(foreign)
                elif mutation == 'owner_hook':
                    def forbidden(): raise AssertionError('owner hook')
                    item._owner_ref = forbidden
                elif mutation == 'id': item._id += 100
                elif mutation == 'membership': source._by_id.clear()
                elif mutation == 'detached': item._detached = True
                elif mutation == 'standalone': item._decoded_standalone = True
                else: source.items.reverse()
                with self.assertRaises(ValueError): selection.take(rows[0]['choice'])
                self.assertEqual(selection.state, 'stale')

    def test_number_representation_and_date_bytes_are_exact_witnesses(self):
        source, selection, rows = self.pending(D('1.0')); source.items[0].value = D('1.00')
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])
        value = BSLDate(TICKS_PER_SECOND); source, selection, rows = self.pending(value)
        object.__setattr__(value, 'ticks', 2*TICKS_PER_SECOND)
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])

    def test_empty_list_can_only_be_cancelled(self):
        source = choices(); selection = ValueListSelection.capture(source)
        self.assertEqual(selection.public(), {'choices':[]})
        with self.assertRaises(ValueError): selection.take('0'*32)
        self.assertEqual(selection.state, 'pending'); selection.cancel()

    def test_item_budget_is_bounded_before_publication(self):
        source = choices(*(['x']*MAX_CHOICES))
        selection = ValueListSelection.capture(source)
        self.assertEqual(len(selection.public()['choices']), MAX_CHOICES)
        source.add('overflow')
        with self.assertRaises(ValueError): ValueListSelection.capture(source)

    def test_total_encoded_budget_includes_tokens_and_json_escaping(self):
        source = choices(*(['x'*1024]*32))
        with self.assertRaises(ValueError): ValueListSelection.capture(source)
        source = choices(*(['"'*500]*32))
        with self.assertRaises(ValueError): ValueListSelection.capture(source)
        source, selection, _ = self.pending('small')
        with patch('yadinassi.form_value_input.MAX_SELECTION_BYTES', 1):
            with self.assertRaises(ValueError): ValueListSelection.capture(source)
        self.assertLess(len(selection._image), MAX_SELECTION_BYTES)

    def test_unsafe_overlong_or_nonstring_presentations_are_refused(self):
        for presentation in ('x'*1025, 'bad\x00text', '\ud800', object()):
            source = choices('x'); source.items[0].presentation = presentation
            with self.assertRaises((TypeError, ValueError)): ValueListSelection.capture(source)

    def test_arbitrary_values_null_and_references_are_not_admitted(self):
        reference = CatalogRef('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222')
        for value in (None, NULL, BSLArray(), reference, object()):
            source = choices('x'); source.items[0].value = value
            with self.assertRaises(TypeError): ValueListSelection.capture(source)

    def test_source_and_item_subclasses_are_rejected_without_hooks(self):
        class BadList(BSLValueList):
            def __iter__(self): raise AssertionError('iteration hook')
        class BadItem(BSLValueListItem):
            def __str__(self): raise AssertionError('presentation hook')
        with self.assertRaises(TypeError): ValueListSelection.capture(BadList())
        source = choices('x'); source.items[0] = BadItem(source, 0, 'x')
        with self.assertRaises(ValueError): ValueListSelection.capture(source)

    def test_duplicate_items_and_nondefault_constraints_are_refused(self):
        source = choices('x'); source.items.append(source.items[0])
        with self.assertRaises(ValueError): ValueListSelection.capture(source)
        source = choices('x'); source.value_type = TD('String')
        with self.assertRaises(ValueError): ValueListSelection.capture(source)

    def test_choice_collision_refuses_without_publishing_partial_selection(self):
        source = choices('one', 'two')
        with patch('yadinassi.form_value_input.token_hex', return_value='a'*32):
            with self.assertRaises(ValueError): ValueListSelection.capture(source)
        self.assertEqual([x.value for x in source.items], ['one','two'])

    def test_capture_interruption_does_not_change_source(self):
        source = choices('x'); item = source.items[0]
        with patch('yadinassi.form_value_input.token_hex', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): ValueListSelection.capture(source)
        self.assertIs(source.items[0], item); self.assertFalse(item._detached)

    def test_recheck_interruption_retires_before_returning_any_item(self):
        _, selection, rows = self.pending()
        with patch('yadinassi.form_value_input._list_witness', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): selection.take(rows[0]['choice'])
        self.assertEqual(selection.state, 'stale'); self.assertIsNone(selection._source)
        with self.assertRaises(ValueError): selection.take(rows[0]['choice'])

    def test_all_terminal_paths_release_heavy_references(self):
        for outcome in ('consumed','cancelled','stale'):
            with self.subTest(outcome=outcome):
                source, selection, rows = self.pending(); source_ref = weakref.ref(source); item_ref = weakref.ref(source.items[0])
                if outcome == 'consumed': selection.take(rows[0]['choice'])
                elif outcome == 'cancelled': selection.cancel()
                else:
                    source.items[0].value = 'changed'
                    with self.assertRaises(ValueError): selection.require_current()
                self.assertEqual(selection.state, outcome)
                self.assertIsNone(selection._source); self.assertEqual(selection._witness, ())
                self.assertEqual(selection._choices, ()); self.assertEqual(selection._image, b'')
                del source; gc.collect()
                self.assertIsNone(source_ref()); self.assertIsNone(item_ref())

    def test_public_state_cannot_be_assigned(self):
        _, selection, _ = self.pending()
        with self.assertRaises(AttributeError): selection.state = 'pending'


if __name__ == '__main__':
    unittest.main()
