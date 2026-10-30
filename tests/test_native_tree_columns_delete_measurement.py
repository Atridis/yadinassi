"""Actual DL14 BSL under distinct synthetic lifetimes; none is a native oracle."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.value_trees import BSLValueTreeColumnCollection as Columns, BSLValueTreeColumn as Column
from yadinassi.values import HostFunction
from scripts import native_1c_tree_columns_delete_contract as wire

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'integrational_tests/measurements/tree_columns_delete.bsl').read_text(encoding='utf-8')


def emit():
    output=[];Interpreter(output.append,native_target=LINUX_8_3_27_1508).execute(SOURCE)
    return ('\n'.join(output)+'\n').encode('ascii')


@contextmanager
def model(mode):
    method=Columns.get_method;member=Column.get_member
    def selected(receiver,name):
        if name.casefold() not in ('delete','удалить'):return method(receiver,name)
        if mode=='missing':raise ValueError('Метод не найден')
        def action(*args):
            if len(args)!=1:raise TypeError('Неверное количество параметров')
            column=receiver.resolve(args[0])
            if mode=='noop':return
            last=len(receiver.items)==1
            if last and mode=='clear':
                receiver.clear();return
            receiver.items.remove(column)
            for row in receiver.table._all_rows:del row.cells[column]
            column._deleted=True
            if mode=='renamed':column.name='X';column.title='Q';column.width=Decimal(8)
            if last and mode=='partial':raise ValueError('Метод не найден original-action-private')
        return HostFunction(name,action,returns_value=mode=='expression')
    def value(receiver,name):
        if mode in ('retained','renamed') and receiver._deleted:
            if name.casefold() in ('name','имя'):return receiver.name
            if name.casefold() in ('title','заголовок'):return receiver.title
            if name.casefold() in ('width','ширина'):return receiver.width
        return member(receiver,name)
    with patch.object(Columns,'get_method',selected),patch.object(Column,'get_member',value):yield


class DeleteMeasurementTests(unittest.TestCase):
    def test_current_guard_is_recorded_not_removed(self):
        records=wire.require_available(emit());self.assertEqual(len(records),14)
        for i in (2,3):
            self.assertEqual(records[i]['status'],'O')
            self.assertEqual(records[i]['snapshots'][0],records[i]['snapshots'][1])
        self.assertEqual(emit(),emit())

    def test_both_aliases_and_exact_fixed_arguments(self):
        calls=[];method=Columns.get_method
        def selected(receiver,name):
            if name.casefold() not in ('delete','удалить'):return method(receiver,name)
            def action(*args):calls.append((name,len(args),args));raise ValueError('synthetic stop')
            return HostFunction(name,action)
        with patch.object(Columns,'get_method',selected):raw=emit()
        records=wire.validate_output(raw);self.assertEqual(len(calls),14)
        self.assertEqual([x[0] for x in calls[:2]],['Delete','Удалить'])
        self.assertEqual([x[1] for x in calls],[1,1,1,1,1,1,1,0,2,1,1,1,1,1])
        self.assertTrue(all(r['status']=='O' for r in records))

    def test_lifetimes_and_retained_metadata_are_independent_observations(self):
        outputs={}
        for mode in ('preserve','clear','retained','renamed'):
            with model(mode):outputs[mode]=wire.require_available(emit())
        preserved=outputs['preserve'][2]['snapshots'][1];cleared=outputs['clear'][2]['snapshots'][1]
        self.assertEqual(len(preserved['nodes']),3);self.assertEqual(len(cleared['nodes']),0)
        self.assertEqual(outputs['retained'][2]['snapshots'][1]['queries'][15:18],(('W','a'),('W','d'),('N',9)))
        self.assertEqual(outputs['renamed'][2]['snapshots'][1]['queries'][15:18],(('W','f'),('W','e'),('N',8)))
        self.assertEqual(len(outputs['preserve'][13]['snapshots'][1]['nodes']),5)
        self.assertEqual(preserved['queries'][15:18],(('E',None),)*3)
        self.assertEqual(cleared['queries'][15:18],(('W','n'),('W','n'),('N',0)))
        # Held child Add distinguishes preserved child storage from root forwarding.
        self.assertNotEqual(outputs['preserve'][11]['snapshots'][1],outputs['clear'][11]['snapshots'][1])

    def test_expression_partial_action_and_followup_failures_do_not_imply_rollback(self):
        with model('expression'):records=wire.require_available(emit())
        self.assertEqual(records[9]['status'],'S');self.assertEqual(records[9]['expression'],'U_')
        with model('partial'):records=wire.require_available(emit())
        self.assertEqual(records[2]['status'],'M');self.assertNotEqual(records[2]['snapshots'][0],records[2]['snapshots'][1])
        with model('preserve'):records=wire.require_available(emit())
        self.assertEqual(records[10]['status'],'S');self.assertEqual(records[10]['follow_status'],'O')
        self.assertEqual(records[13]['phase'],5);self.assertEqual(records[13]['follow_status'],'S')

    def test_missing_noop_and_bad_setup_do_not_pass_positive_gate(self):
        for mode in ('missing','noop'):
            with model(mode):raw=emit()
            wire.validate_output(raw)
            with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)
        raw=emit();bad=raw.replace(b'WdN9',b'WdN8')
        self.assertNotEqual(raw,bad)
        with self.assertRaises(wire.AvailabilityError):wire.require_available(bad)

    def test_unsupported_retained_scalar_fails_observer_without_raw_diagnostics(self):
        original=Column.get_member
        def value(receiver,name):
            if receiver._deleted and name.casefold()=='title':return object()
            return original(receiver,name)
        with patch.object(Column,'get_member',value):raw=emit()
        with self.assertRaises(wire.ObservationError):wire.validate_output(raw)
        self.assertNotIn(b'object at',raw)


if __name__=='__main__':unittest.main()
