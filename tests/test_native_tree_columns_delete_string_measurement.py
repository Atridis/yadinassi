"""Actual DS6 BSL with independently chosen synthetic outcomes, not native answers."""
from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.value_trees import BSLValueTreeColumnCollection as Columns
from yadinassi.values import HostFunction
from scripts import native_1c_tree_columns_delete_string_contract as wire
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'integrational_tests/measurements/tree_columns_delete_string.bsl').read_text(encoding='utf-8')
def emit():
    output=[];Interpreter(output.append,native_target=LINUX_8_3_27_1508).execute(SOURCE)
    return ('\n'.join(output)+'\n').encode('ascii')
@contextmanager
def model(mode):
    method=Columns.get_method
    def selected(receiver,name):
        if name.casefold() not in ('delete','удалить'):return method(receiver,name)
        if mode=='missing':raise ValueError('Метод не найден')
        def action(selector):
            if mode=='noop':return
            if mode=='reject-string' and type(selector) is str:raise TypeError('synthetic selector rejection')
            column=receiver.resolve(selector);receiver.items.remove(column)
            for row in receiver.table._all_rows:del row.cells[column]
            column._deleted=True
            if mode=='partial' and type(selector) is str:raise ValueError('Метод не найден original-private')
        return HostFunction(name,action,returns_value=mode!='procedure')
    with patch.object(Columns,'get_method',selected):yield
class DeleteStringMeasurementTests(unittest.TestCase):
    def test_existing_legacy_capture_is_finite_and_repeatable(self):
        raw=emit();self.assertEqual(raw,emit());self.assertEqual(len(wire.require_available(raw)),6)
    def test_exact_aliases_and_arguments(self):
        calls=[];old=Columns.get_method
        def selected(receiver,name):
            if name.casefold() not in ('delete','удалить'):return old(receiver,name)
            def action(*args):calls.append((name,args));raise TypeError('synthetic stop')
            return HostFunction(name,action)
        with patch.object(Columns,'get_method',selected):records=wire.validate_output(emit())
        self.assertEqual([n for n,a in calls],['Delete','Удалить']*3)
        self.assertEqual([len(a) for n,a in calls],[1]*6)
        self.assertEqual([a[0] for n,a in calls[2:]],['Key']*4)
        self.assertTrue(all(r['status']=='O' for r in records))
    def test_expression_statement_and_partial_mutation_are_independent(self):
        observations={}
        for mode in ('legacy','procedure','reject-string','partial'):
            with model(mode):observations[mode]=wire.require_available(emit())
        self.assertEqual([r['status'] for r in observations['legacy']],['S']*6)
        self.assertEqual([r['status'] for r in observations['procedure']],['S']*4+['O']*2)
        self.assertEqual([r['status'] for r in observations['reject-string']],['S']*2+['O']*4)
        for r in observations['partial'][2:]:
            self.assertEqual(r['status'],'M');self.assertNotEqual(*r['snapshots'])
        self.assertEqual([r['expression'] for r in observations['legacy'][4:]],['U_']*2)
    def test_noop_missing_or_bad_initial_metadata_cannot_be_green(self):
        for mode in ('noop','missing'):
            with model(mode):raw=emit()
            wire.validate_output(raw)
            with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)
        raw=emit();bad=raw.replace(b'WdN9',b'WdN8');self.assertNotEqual(raw,bad)
        with self.assertRaises(wire.AvailabilityError):wire.require_available(bad)
