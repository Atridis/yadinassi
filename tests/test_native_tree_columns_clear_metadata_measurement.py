"""Actual CD3 BSL with distinguishable reset/retention/error models, no oracle."""
from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.value_trees import BSLValueTreeColumn as Column, BSLValueTreeColumnCollection as Columns
from yadinassi.values import HostFunction
from scripts import native_1c_tree_columns_clear_metadata_contract as wire

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'integrational_tests/measurements/tree_columns_clear_metadata.bsl').read_text(encoding='utf-8')


def emit(target=None):
    output=[];kwargs={} if target is None else {'native_target':target}
    Interpreter(output.append,**kwargs).execute(SOURCE)
    return ('\n'.join(output)+'\n').encode('ascii')


@contextmanager
def model(mode):
    method=Columns.get_method;member=Column.get_member
    def selected(receiver,name):
        if name.casefold() not in ('clear','очистить'):return method(receiver,name)
        if mode=='missing':raise ValueError('Метод не найден')
        def action():
            custom=receiver.items[0].title=='P'
            if custom and mode=='error':raise ValueError('private metadata error')
            retained=[(c,c.title,c.width) for c in receiver.items]
            receiver.clear()
            if mode=='retain':
                for c,title,width in retained:c.title=title;c.width=width
            if custom and mode=='partial':raise ValueError('Метод не найден private-original-action')
        return HostFunction(name,action,returns_value=False)
    def value(receiver,name):
        if mode=='retain' and receiver._deleted:
            if name.casefold() in ('title','заголовок'):return receiver.title
            if name.casefold() in ('width','ширина'):return receiver.width
        return member(receiver,name)
    with patch.object(Columns,'get_method',selected),patch.object(Column,'get_member',value):yield


class MetadataMeasurementTests(unittest.TestCase):
    def test_active_and_retained_before_values_prove_setup(self):
        records=wire.require_available(emit(LINUX_8_3_27_1508));before=records[2]['snapshots'][0]
        self.assertEqual(before['schema'][0][1][1:3],'d9')
        self.assertEqual(before['queries'][16:18],(('W','d'),('N',9)))

    def test_reset_retention_error_and_partial_mutation_are_distinct(self):
        records={}
        for mode in ('reset','retain','error','partial'):
            with model(mode):records[mode]=wire.require_available(emit(LINUX_8_3_27_1508))[2]
        self.assertEqual(records['reset']['snapshots'][1]['queries'][16:18],(('W','n'),('N',0)))
        self.assertEqual(records['retain']['snapshots'][1]['queries'][16:18],(('W','d'),('N',9)))
        self.assertEqual(records['error']['status'],'O');self.assertTrue(records['error']['snapshots'][1]['schema'])
        self.assertEqual(records['partial']['status'],'M');self.assertFalse(records['partial']['snapshots'][1]['schema'])

    def test_missing_and_default_target_guard_cannot_be_available(self):
        with self.assertRaises(wire.AvailabilityError):wire.require_available(emit())
        with model('missing'):raw=emit(LINUX_8_3_27_1508)
        self.assertEqual([r['status'] for r in wire.validate_output(raw)],['M']*3)
        with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)

    def test_repeated_capture_and_unsupported_value_fail_closed(self):
        self.assertEqual(emit(LINUX_8_3_27_1508),emit(LINUX_8_3_27_1508))
        original=Column.get_member
        def value(receiver,name):
            if receiver._deleted and name.casefold()=='title':return object()
            return original(receiver,name)
        with patch.object(Column,'get_member',value):raw=emit(LINUX_8_3_27_1508)
        with self.assertRaises(wire.ObservationError):wire.validate_output(raw)


if __name__=='__main__':unittest.main()
