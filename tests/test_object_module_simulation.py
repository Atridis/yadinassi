"""Pure local simulation tests; not native evidence or automatic-event tests."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone, tzinfo
from decimal import Decimal, DefaultContext, Inexact, ROUND_DOWN, getcontext, localcontext
from hashlib import sha256
import io
import socket
import sqlite3
import subprocess
import unittest
from unittest.mock import patch
from uuid import UUID

from yadinassi import object_module_analysis as analysis
from yadinassi import object_module_simulation as sim
from yadinassi.catalog_backend import CatalogSchema, FieldSchema, TabularSectionSchema
from yadinassi.configuration_xml import import_configuration
from sqlite_catalog_fixture import configuration_files


CATALOG = CatalogSchema(UUID(int=3), 'Products', 8, 64, (
    FieldSchema(UUID(int=4), 'Amount', 'number', (12, 2, 'Any')),
    FieldSchema(UUID(int=5), 'Active', 'boolean'),
    FieldSchema(UUID(int=6), 'Stamp', 'datetime', ('DateTime',)),
))
STAMP = datetime(2026, 11, 4, 1, 2, 3)
SNAPSHOT = sim.ScalarSnapshot('A', 'Original', (sim.NumberValue('2.50'), False, STAMP))


def source(body='', helpers=''):
    return ('Procedure BeforeWrite(Cancel)\n' + body + '\nEndProcedure\n' + helpers).encode()


def binding(raw, **changes):
    return replace(analysis.ObjectModuleBinding(UUID(int=1), UUID(int=2), 1,
                   CATALOG, sha256(raw).hexdigest()), **changes)


class Hostile:
    def trip(self, *args, **kwargs):
        raise AssertionError('host hook called')
    __bool__ = __len__ = __iter__ = __hash__ = __eq__ = __str__ = __repr__ = trip
    __int__ = __float__ = __add__ = __radd__ = __getattr__ = trip


class HostileText(str):
    __len__ = __str__ = __eq__ = __hash__ = Hostile.trip


class HostileTuple(tuple):
    __len__ = __iter__ = __getitem__ = Hostile.trip


class HostileDecimal(Decimal):
    as_tuple = is_finite = __str__ = __add__ = Hostile.trip


class HostileDate(datetime):
    def __getattribute__(self, name):
        raise AssertionError('date subclass inspected')


class HostileTimezone(tzinfo):
    utcoffset = dst = tzname = Hostile.trip


class ObjectModuleSimulationTests(unittest.TestCase):
    def run_body(self, body='', helpers='', *, snapshot=SNAPSHOT, cancel=False, catalog=CATALOG):
        raw = source(body, helpers)
        return sim.simulate_object_module(raw, binding(raw, catalog=catalog), snapshot, cancel=cancel)

    def reject(self, body='', helpers='', *, code=None, **kwargs):
        with self.assertRaises(sim.ObjectModuleSimulationError) as caught:
            self.run_body(body, helpers, **kwargs)
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_empty_event_returns_new_snapshot_and_local_profile(self):
        result = self.run_body()
        self.assertIsNot(result.snapshot, SNAPSHOT)
        self.assertEqual(result.snapshot.code, 'A')
        self.assertEqual(result.snapshot.values, (sim.NumberValue('2.5'), False, STAMP))
        self.assertIs(result.cancel, False)
        self.assertEqual(result.profile, 'catalog-before-write-pure-simulation-v1')
        self.assertIs(result.native_parity, False)

    def test_russian_aliases(self):
        raw = 'Процедура ПередЗаписью(Отказ)\nЭтотОбъект.Наименование="Новый"; Отказ=Истина;\nКонецПроцедуры'.encode()
        result = sim.simulate_object_module(raw, binding(raw), SNAPSHOT)
        self.assertEqual(result.snapshot.description, 'Новый')
        self.assertIs(result.cancel, True)

    def test_arithmetic_and_remainder(self):
        result = self.run_body('Amount = (Amount + 1.5) * 3 / 2 - 1; Amount = Amount % 3;')
        self.assertEqual(result.snapshot.values[0], sim.NumberValue('2'))

    def test_unary_and_numeric_comparisons(self):
        self.assertTrue(self.run_body('Amount = -(-Amount); Cancel = +Amount >= 2.5 AND Amount <= 3 AND Amount > 0 AND Amount <> 0;').cancel)

    def test_nonempty_or_malformed_tabular_metadata_is_rejected_before_copy(self):
        raw = source()
        section = TabularSectionSchema(UUID(int=7), 'Rows', ())
        for sections in ((section,), None, [], HostileTuple(())):
            with self.subTest(section_type=type(sections)):
                catalog = replace(CATALOG, tabular_sections=sections)
                with self.assertRaises(sim.ObjectModuleSimulationError) as caught:
                    sim.simulate_object_module(raw, binding(raw, catalog=catalog), SNAPSHOT)
                self.assertEqual(caught.exception.code, 'invalid_input')

    def test_string_concat_and_codepoint_order(self):
        result = self.run_body('Description = "A" + "b"; Cancel = Description = "Ab" AND "A" < "a";')
        self.assertEqual(result.snapshot.description, 'Ab')
        self.assertTrue(result.cancel)

    def test_if_elsif_else(self):
        for amount, expected in (('0', 'zero'), ('2.5', 'other'), ('5', 'large')):
            with self.subTest(amount=amount):
                snapshot = replace(SNAPSHOT, values=(sim.NumberValue(amount), False, STAMP))
                result = self.run_body('If Amount = 0 Then Description="zero"; ElsIf Amount>3 Then Description="large"; Else Description="other"; EndIf;', snapshot=snapshot)
                self.assertEqual(result.snapshot.description, expected)

    def test_conditional_and_boolean_short_circuit(self):
        result = self.run_body('Amount=?(True, 4, 1/0); Cancel=False AND 1/0=0; Cancel=True OR 1/0=0;')
        self.assertEqual(result.snapshot.values[0], sim.NumberValue('4'))
        self.assertTrue(result.cancel)

    def test_nonselected_runtime_error_is_not_evaluated(self):
        result = self.run_body('If False Then Amount=1/0; EndIf; Description="ok";')
        self.assertEqual(result.snapshot.description, 'ok')

    def test_nonselected_host_call_still_rejected(self):
        self.reject('If False Then ThisObject.Write(); EndIf;', code='source_rejected')

    def test_event_return_stops_remaining_statements(self):
        result = self.run_body('Description="first"; Return; Description="last"; Amount=1/0;')
        self.assertEqual(result.snapshot.description, 'first')

    def test_nested_return_stops_current_helper_only(self):
        result = self.run_body('_om_A(); Description=Description+"Y";',
            'Procedure _om_A()\nIf True Then Description="X"; Return; EndIf; Description="bad";\nEndProcedure')
        self.assertEqual(result.snapshot.description, 'XY')

    def test_helper_reference_changes_cancel(self):
        result = self.run_body('_om_A(Cancel);', 'Procedure _om_A(Stop)\nStop=True;\nEndProcedure')
        self.assertTrue(result.cancel)

    def test_repeated_argument_preserves_aliasing(self):
        result = self.run_body('Var X; X=1; _om_A(X,X); Amount=X;',
            'Procedure _om_A(A,B)\nA=2; B=B+3;\nEndProcedure')
        self.assertEqual(result.snapshot.values[0], sim.NumberValue('5'))

    def test_forwarded_reference_preserves_alias(self):
        result = self.run_body('_om_A(Cancel);',
            'Procedure _om_A(A)\n_om_B(A,A);\nEndProcedure\nProcedure _om_B(B,C)\nB=True; C=NOT C;\nEndProcedure')
        self.assertFalse(result.cancel)

    def test_val_parameter_is_a_separate_cell(self):
        result = self.run_body('Var X; X=1; _om_A(X,X); Amount=X;',
            'Procedure _om_A(A,Val B)\nA=2; B=7;\nEndProcedure')
        self.assertEqual(result.snapshot.values[0], sim.NumberValue('2'))

    def test_val_cancel_name_does_not_constrain_local_cell(self):
        result = self.run_body('_om_A(Cancel);',
            'Procedure _om_A(Val Cancel)\nCancel=12; Amount=Cancel;\nEndProcedure')
        self.assertFalse(result.cancel)
        self.assertEqual(result.snapshot.values[0], sim.NumberValue('12'))

    def test_repeated_helpers_use_fresh_local_cells(self):
        result = self.run_body('_om_A(); _om_A();',
            'Procedure _om_A()\nVar X; X=1; X=X+1; Amount=Amount+X;\nEndProcedure')
        self.assertEqual(result.snapshot.values[0], sim.NumberValue('6.5'))

    def test_uninitialized_and_field_reference_reject(self):
        self.reject('Var X; _om_A(X);', 'Procedure _om_A(X)\nX=1;\nEndProcedure', code='source_rejected')
        self.reject('_om_A(Amount);', 'Procedure _om_A(X)\nX=1;\nEndProcedure', code='source_rejected')

    def test_cancel_does_not_stop_or_restore_fields(self):
        result = self.run_body('Cancel=True; Description="changed"; Amount=9;')
        self.assertTrue(result.cancel)
        self.assertEqual(result.snapshot.description, 'changed')
        self.assertEqual(result.snapshot.values[0], sim.NumberValue('9'))

    def test_cancel_can_be_cleared_later(self):
        self.assertFalse(self.run_body('Cancel=True; Cancel=False;', cancel=True).cancel)

    def test_cancel_nonboolean_is_rejected_immediately(self):
        self.reject('Cancel=1; Cancel=False;', code='type_mismatch')

    def test_cancel_reference_alias_remains_boolean_only(self):
        self.reject('_om_A(Cancel);', 'Procedure _om_A(A)\nA=1; A=False;\nEndProcedure', code='type_mismatch')

    def test_input_cancel_requires_exact_bool(self):
        for value in (0, 1, None, 'false', Hostile()):
            self.reject(cancel=value, code='invalid_input')

    def test_all_boolean_contexts_are_strict(self):
        for body in ('If 1 Then Cancel=True; EndIf;', 'Cancel=NOT 1;', 'Cancel=1 AND True;',
                     'Cancel=False OR 1;', 'Amount=?(1,2,3);'):
            with self.subTest(body=body): self.reject(body, code='type_mismatch')

    def test_mixed_types_never_coerce(self):
        for body in ('Amount=True+1;', 'Description="x"+1;', 'Cancel=True=1;',
                     'Cancel=Undefined=False;', 'Cancel=Stamp<Stamp;', 'Cancel=False<True;'):
            with self.subTest(body=body): self.reject(body, code='type_mismatch')

    def test_undefined_local_is_distinct_from_uninitialized(self):
        self.assertTrue(self.run_body('Var X; X=Undefined; Cancel=X=Undefined;').cancel)

    def test_undefined_cannot_be_a_stored_field(self):
        for field in ('Code', 'Description', 'Amount', 'Active', 'Stamp'):
            with self.subTest(field=field): self.reject(field+'=Undefined;')

    def test_number_input_is_bounded_text_not_decimal(self):
        for value in (Decimal('1'), HostileDecimal('1'), 1, 1.0, True, Hostile()):
            snapshot = replace(SNAPSHOT, values=(value, False, STAMP))
            self.reject(snapshot=snapshot, code='invalid_input')

    def test_number_text_length_checked_before_decimal_constructor(self):
        for text in ('9'*61, '0.'+'0'*100000):
            with patch.object(sim, 'Decimal', side_effect=AssertionError('Decimal constructed')):
                self.reject(snapshot=replace(SNAPSHOT, values=(sim.NumberValue(text), False, STAMP)), code='invalid_input')

    def test_number_text_exact_type_and_ascii_grammar(self):
        for value in (Hostile(), HostileText('1'), '', '+1', '01', '1e2', 'NaN', 'sNaN',
                      'Infinity', ' 1', '1 ', '1_0', '١', '.5', '1.'):
            self.reject(snapshot=replace(SNAPSHOT, values=(sim.NumberValue(value), False, STAMP)), code='invalid_input')

    def test_number_wrapper_subclass_rejected(self):
        class Child(sim.NumberValue): pass
        self.reject(snapshot=replace(SNAPSHOT, values=(Child('1'), False, STAMP)), code='invalid_input')

    def test_number_wrapper_incomplete_instance_rejected(self):
        value = object.__new__(sim.NumberValue)
        self.reject(snapshot=replace(SNAPSHOT, values=(value, False, STAMP)), code='invalid_input')

    def test_number_canonicalization_and_negative_zero(self):
        for raw, expected in (('1.2300', '1.23'), ('-0.00', '0'), ('-12.50', '-12.5')):
            result = self.run_body(snapshot=replace(SNAPSHOT, values=(sim.NumberValue(raw), False, STAMP)))
            self.assertEqual(result.snapshot.values[0], sim.NumberValue(expected))

    def test_exact_division_is_supported(self):
        self.assertEqual(self.run_body('Var X; X=1/8; Amount=X*8;').snapshot.values[0], sim.NumberValue('1'))

    def test_inexact_division_is_not_silently_rounded(self):
        self.reject('Var X; X=1/3;', code='numeric_limit')

    def test_division_and_remainder_by_zero(self):
        for expression in ('1/0', '1%0'):
            self.reject('Amount='+expression+';', code='division_by_zero')

    def test_remainder_sign_is_explicit_decimal_policy(self):
        self.assertEqual(self.run_body('Amount=-5%3;').snapshot.values[0], sim.NumberValue('-2'))

    def test_intermediate_digit_growth_is_bounded(self):
        self.reject('Var X; X='+('9'*38)+'; X=X*X;', code='numeric_limit')

    def test_intermediate_scale_growth_is_bounded(self):
        self.reject('Var X; X=0.000000000000000001; X=X*X;', code='numeric_limit')

    def test_small_scientific_ir_number_is_admitted(self):
        result = self.run_body('Var X; X=0.0000001; Cancel=X>0;')
        self.assertTrue(result.cancel)

    def test_field_number_precision_and_scale_have_no_rounding(self):
        for value in ('10000000000', '0.001', '-10000000000'):
            self.reject('Amount='+value+';', code='field_limit')
        self.assertEqual(self.run_body('Amount=9999999999.99;').snapshot.values[0], sim.NumberValue('9999999999.99'))

    def test_input_number_storage_qualifiers_are_checked(self):
        for text in ('10000000000', '0.001'):
            self.reject(snapshot=replace(SNAPSHOT, values=(sim.NumberValue(text), False, STAMP)), code='field_limit')

    def test_ambient_decimal_context_is_ignored_and_restored(self):
        with localcontext() as external:
            external.prec = 1
            external.rounding = ROUND_DOWN
            external.Emax = 1
            external.Emin = -1
            external.traps[Inexact] = False
            external.flags[Inexact] = True
            before = (external.prec, external.rounding, external.Emax, external.Emin,
                      dict(external.traps), dict(external.flags))
            result = self.run_body('Amount=1.25+2.5;')
            self.assertEqual(result.snapshot.values[0], sim.NumberValue('3.75'))
            self.assertIs(getcontext(), external)
            self.assertEqual(before, (external.prec, external.rounding, external.Emax,
                external.Emin, dict(external.traps), dict(external.flags)))

    def test_mutated_default_context_does_not_change_result(self):
        saved = DefaultContext.copy()
        try:
            DefaultContext.prec = 1
            DefaultContext.rounding = ROUND_DOWN
            DefaultContext.Emin = -1
            DefaultContext.Emax = 1
            DefaultContext.traps[Inexact] = False
            self.assertEqual(self.run_body('Amount=1.25+2.5;').snapshot.values[0], sim.NumberValue('3.75'))
            self.reject('Var X; X=1/3;', code='numeric_limit')
        finally:
            for name in ('prec', 'rounding', 'Emin', 'Emax', 'capitals', 'clamp'):
                setattr(DefaultContext, name, getattr(saved, name))
            DefaultContext.traps = saved.traps.copy()
            DefaultContext.flags = saved.flags.copy()

    def test_error_does_not_change_ambient_decimal_context(self):
        with localcontext() as external:
            external.clear_flags()
            flags = dict(external.flags)
            self.reject('Var X; X=1/3;', code='numeric_limit')
            self.assertIs(getcontext(), external)
            self.assertEqual(dict(external.flags), flags)

    def test_date_copy_and_equality_without_host_conversion(self):
        result = self.run_body('Var X; X=Stamp; Stamp=X; Cancel=Stamp=X;')
        self.assertTrue(result.cancel)
        self.assertEqual(result.snapshot.values[2], STAMP)
        self.assertIsNot(result.snapshot.values[2], STAMP)

    def test_datetime_boundaries(self):
        for stamp in (datetime.min, datetime.max.replace(microsecond=0)):
            result = self.run_body(snapshot=replace(SNAPSHOT, values=(sim.NumberValue('1'), True, stamp)))
            self.assertEqual(result.snapshot.values[2], stamp)

    def test_aware_fractional_fold_and_subclass_dates_reject(self):
        for stamp in (STAMP.replace(tzinfo=timezone.utc), STAMP.replace(tzinfo=HostileTimezone()),
                      STAMP.replace(microsecond=1), STAMP.replace(fold=1),
                      HostileDate(2026, 1, 1), Hostile()):
            self.reject(snapshot=replace(SNAPSHOT, values=(sim.NumberValue('1'), False, stamp)), code='type_mismatch')

    def test_datetime_pickle_byte_states_are_revalidated(self):
        # Python's datetime bytes constructor checks the ten-byte shape/month,
        # but its state loader assigns calendar/time components without normal
        # range validation. These are exact datetime objects, not subclasses.
        states = (
            [7, 234, 1, 0, 0, 0, 0, 0, 0, 0],   # Day zero.
            [7, 234, 2, 30, 0, 0, 0, 0, 0, 0],  # Invalid day in month.
            [7, 234, 1, 1, 24, 0, 0, 0, 0, 0],  # Hour 24.
            [7, 234, 1, 1, 0, 60, 0, 0, 0, 0],  # Minute 60.
            [7, 234, 1, 1, 0, 0, 60, 0, 0, 0],  # Second 60.
            [0, 0, 1, 1, 0, 0, 0, 0, 0, 0],    # Year zero.
        )
        for state in states:
            with self.subTest(state=state):
                stamp = datetime(bytes(state))
                self.assertIs(type(stamp), datetime)
                self.reject(snapshot=replace(SNAPSHOT, values=(sim.NumberValue('1'), False, stamp)), code='type_mismatch')

    def test_date_arithmetic_is_not_supported(self):
        self.reject('Stamp=Stamp+1;', code='type_mismatch')

    def test_field_string_lengths_are_exact(self):
        self.assertEqual(self.run_body('Code="12345678";').snapshot.code, '12345678')
        self.reject('Code="123456789";', code='field_limit')
        self.reject('Description="'+'x'*65+'";', code='field_limit')

    def test_string_concatenation_checks_before_allocation(self):
        self.reject('Var X; X="'+'x'*600+'"; X=X+X;', code='resource_limit')

    def test_string_multiplication_is_never_supported(self):
        self.reject('Var X; X="x"*1000;', code='type_mismatch')

    def test_surrogate_and_string_subclass_inputs_rejected(self):
        for text in ('\ud800', HostileText('safe'), Hostile()):
            self.reject(snapshot=replace(SNAPSHOT, description=text), code='field_limit')

    def test_snapshot_exact_type_and_shape(self):
        class Child(sim.ScalarSnapshot): pass
        for value in ({}, Hostile(), Child('A','B',()), object.__new__(sim.ScalarSnapshot)):
            self.reject(snapshot=value, code='invalid_input')

    def test_snapshot_values_tuple_exactness_and_arity(self):
        for values in ([], (), SNAPSHOT.values+(False,), HostileTuple(SNAPSHOT.values), Hostile()):
            self.reject(snapshot=replace(SNAPSHOT, values=values), code='invalid_input')

    def test_boolean_field_rejects_host_and_numeric_values(self):
        for value in (0, 1, Decimal('1'), Hostile()):
            self.reject(snapshot=replace(SNAPSHOT, values=(sim.NumberValue('1'), value, STAMP)), code='type_mismatch')

    def test_input_unchanged_on_success_and_cancel(self):
        result = self.run_body('Amount=7; Description="new"; Cancel=True;')
        self.assertEqual(SNAPSHOT, sim.ScalarSnapshot('A', 'Original', (sim.NumberValue('2.50'), False, STAMP)))
        self.assertNotEqual(result.snapshot, SNAPSHOT)

    def test_input_unchanged_after_partial_scratch_failure(self):
        self.reject('Description="changed"; Amount=7; Amount=1/0;', code='division_by_zero')
        self.assertEqual(SNAPSHOT.description, 'Original')
        self.assertEqual(SNAPSHOT.values[0].text, '2.50')

    def test_output_is_immutable_and_not_a_capability(self):
        result = self.run_body()
        for target, name, value in ((result, 'cancel', True), (result.snapshot, 'code', 'B'),
                                    (result.snapshot.values[0], 'text', '9')):
            with self.assertRaises(FrozenInstanceError): setattr(target, name, value)

    def test_repeat_execution_is_deterministic_and_detached(self):
        first = self.run_body('Amount=Amount+1;')
        second = self.run_body('Amount=Amount+1;')
        self.assertEqual(first, second)
        self.assertIsNot(first.snapshot, second.snapshot)

    def test_source_exact_bytes_and_length(self):
        for raw in ('text', b'', bytearray(source()), b'x'*(sim.MAX_SOURCE_BYTES+1), Hostile()):
            with self.assertRaises(sim.ObjectModuleSimulationError):
                sim.simulate_object_module(raw, binding(source()), SNAPSHOT)

    def test_external_ir_and_analysis_cannot_be_supplied(self):
        raw = source()
        for supplied in (analysis.analyze_object_module(raw, binding(raw)), analysis.IRNode('return')):
            with self.assertRaises(sim.ObjectModuleSimulationError) as caught:
                sim.simulate_object_module(supplied, binding(raw), SNAPSHOT)
            self.assertEqual(caught.exception.code, 'invalid_input')

    def test_every_call_performs_fresh_analysis(self):
        with patch.object(sim, 'analyze_object_module', wraps=analysis.analyze_object_module) as analyzer:
            self.run_body(); self.run_body()
            self.assertEqual(analyzer.call_count, 2)

    def test_analyzer_profile_drift_fails_closed(self):
        raw = source()
        result = analysis.analyze_object_module(raw, binding(raw))
        for changed in (replace(result, profile='future-profile'), replace(result, native_parity=True)):
            with patch.object(sim, 'analyze_object_module', return_value=changed):
                self.reject(code='invalid_ir')

    def test_hash_mismatch_rejects(self):
        raw = source('Cancel=True;')
        with self.assertRaises(sim.ObjectModuleSimulationError) as caught:
            sim.simulate_object_module(raw, binding(raw, source_sha256='0'*64), SNAPSHOT)
        self.assertEqual(caught.exception.code, 'source_rejected')

    def test_binding_is_detached_before_analyzer(self):
        raw = source()
        original = binding(raw)
        with patch.object(sim, 'analyze_object_module', wraps=analysis.analyze_object_module) as analyzer:
            sim.simulate_object_module(raw, original, SNAPSHOT)
        copied = analyzer.call_args.args[1]
        self.assertEqual(copied, original)
        self.assertIsNot(copied, original)
        self.assertIsNot(copied.catalog, original.catalog)
        self.assertIsNot(copied.catalog.fields[0], original.catalog.fields[0])

    def test_binding_exact_type_and_missing_fields(self):
        for value in (Hostile(), {}, object.__new__(analysis.ObjectModuleBinding)):
            with self.assertRaises(sim.ObjectModuleSimulationError):
                sim.simulate_object_module(source(), value, SNAPSHOT)

    def test_forged_uuid_payload_is_not_invoked(self):
        identity = object.__new__(UUID)
        object.__setattr__(identity, 'int', Hostile())
        raw = source()
        with self.assertRaises(sim.ObjectModuleSimulationError):
            sim.simulate_object_module(raw, binding(raw, database_id=identity), SNAPSHOT)

    def test_hostile_metadata_leaves_reject_before_analyzer(self):
        cases = [dict(configuration_generation=Hostile()), dict(source_sha256=Hostile()),
                 dict(catalog=replace(CATALOG, name=HostileText('Products'))),
                 dict(catalog=replace(CATALOG, fields=HostileTuple(CATALOG.fields))),
                 dict(catalog=replace(CATALOG, fields=(replace(CATALOG.fields[0], qualifiers=(Hostile(),)),)))]
        raw = source()
        for changes in cases:
            with patch.object(sim, 'analyze_object_module', side_effect=AssertionError('analyzed')):
                with self.assertRaises(sim.ObjectModuleSimulationError):
                    sim.simulate_object_module(raw, binding(raw, **changes), SNAPSHOT)

    def test_oversized_metadata_tuple_rejects_before_iteration(self):
        raw = source()
        with self.assertRaises(sim.ObjectModuleSimulationError):
            sim.simulate_object_module(raw, binding(raw, catalog=replace(CATALOG, fields=(Hostile(),)*65)), SNAPSHOT)

    def test_field_and_metadata_profile_restrictions_survive(self):
        raw = source()
        catalog = replace(CATALOG, fields=(FieldSchema(UUID(int=8), 'Other', 'string', (10,)),))
        with self.assertRaises(sim.ObjectModuleSimulationError) as caught:
            sim.simulate_object_module(raw, binding(raw, catalog=catalog), sim.ScalarSnapshot('A','B',('x',)))
        self.assertEqual(caught.exception.code, 'source_rejected')

    def test_empty_catalog_and_zero_description_capacity(self):
        catalog = replace(CATALOG, fields=(), description_length=0)
        result = self.run_body(snapshot=sim.ScalarSnapshot('','',()), catalog=catalog)
        self.assertEqual(result.snapshot, sim.ScalarSnapshot('','',()))

    def test_maximum_field_count(self):
        fields = tuple(FieldSchema(UUID(int=100+i), 'F'+str(i), 'boolean') for i in range(64))
        catalog = replace(CATALOG, fields=fields)
        result = self.run_body('F63=True;', snapshot=sim.ScalarSnapshot('A','B',(False,)*64), catalog=catalog)
        self.assertEqual(result.snapshot.values, (False,)*63+(True,))

    def test_fuel_exhaustion_returns_no_partial_result(self):
        with patch.object(sim, 'MAX_STEPS', 8):
            self.reject('Description="changed"; Amount=1+2+3+4;', code='resource_limit')
        self.assertEqual(SNAPSHOT.description, 'Original')

    def test_scalar_byte_budget_is_independent(self):
        with patch.object(sim, 'MAX_VALUE_BYTES', 10):
            self.reject(code='resource_limit')

    def test_runtime_call_depth_is_independent(self):
        with patch.object(sim, 'MAX_CALL_DEPTH', 1):
            self.reject('_om_A();', 'Procedure _om_A()\nEndProcedure', code='resource_limit')

    def test_runtime_expression_depth_is_independent(self):
        with patch.object(sim, 'MAX_EXPRESSION_DEPTH', 1):
            self.reject('Amount=1+(2+3);', code='resource_limit')

    def test_runtime_block_depth_is_independent(self):
        with patch.object(sim, 'MAX_BLOCK_DEPTH', 0):
            self.reject('If True Then Amount=1; EndIf;', code='resource_limit')

    def test_static_cycle_expansion_and_source_budgets_survive(self):
        self.reject('_om_A();', 'Procedure _om_A()\n_om_A();\nEndProcedure', code='source_rejected')
        self.reject('Cancel=False;\n'*600, code='source_rejected')

    def test_user_interrupts_and_programming_errors_are_not_cancel(self):
        for error in (KeyboardInterrupt, SystemExit, AssertionError):
            with patch.object(sim, 'analyze_object_module', side_effect=error):
                with self.assertRaises(error): self.run_body()

    def test_recursion_exhaustion_is_a_failure_category(self):
        with patch.object(sim, 'analyze_object_module', side_effect=RecursionError):
            self.reject(code='resource_limit')

    def test_diagnostics_do_not_echo_inputs_or_source(self):
        error = self.reject('Description="private-value"; Amount=1/0;')
        self.assertNotIn('private-value', str(error))
        self.assertNotIn('Catalogs/', str(error))
        self.assertNotIn('Products', str(error))

    def test_no_runtime_database_network_process_or_file_calls(self):
        with patch('yadinassi.runtime.Interpreter.execute', side_effect=AssertionError('execute')), \
             patch('yadinassi.runtime.Interpreter.execute_program', side_effect=AssertionError('program')), \
             patch('sqlite3.connect', side_effect=AssertionError('database')), \
             patch('socket.socket', side_effect=AssertionError('network')), \
             patch('subprocess.Popen', side_effect=AssertionError('process')), \
             patch('builtins.open', side_effect=AssertionError('file')), \
             patch('io.open', side_effect=AssertionError('file')):
            self.assertTrue(self.run_body('Amount=Amount+1; Cancel=True;').cancel)

    def test_existing_activation_issue_is_unchanged(self):
        files = configuration_files()
        raw = source('Cancel=True;')
        files['Catalogs/Products/Ext/ObjectModule.bsl'] = raw
        before = import_configuration(files)
        sim.simulate_object_module(raw, binding(raw), SNAPSHOT)
        self.assertEqual(before, import_configuration(files))
        self.assertIn('module execution unsupported:Catalogs/Products/Ext/ObjectModule.bsl', before.activation_issues)


if __name__ == '__main__':
    unittest.main()
