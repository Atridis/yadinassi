"""Competing synthetic boundary/conversion models, not native semantics."""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.value_trees import BSLValueTreeColumnCollection as Columns, BSLValueTreeColumn, BSLValueTreeRow
from yadinassi.values import HostFunction
from scripts import native_1c_tree_columns_move_boundary_contract as wire
from test_native_tree_columns_move_measurement import model as original_model

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'integrational_tests/measurements/tree_columns_move_boundary.bsl').read_text(encoding='utf-8')
HELPERS=SOURCE[:SOURCE.index('Сообщить("CB-C1:')]


def emit():
    out=[];Interpreter(out.append).execute(SOURCE)
    return ('\n'.join(out)+'\n').encode('ascii')


@contextmanager
def model(policy='strict',deleted_first=False):
    original=Columns.get_method
    def get(receiver,name):
        if name.casefold() not in ('move','сдвинуть'):
            return original(receiver,name)
        if policy=='missing':raise ValueError('Метод не найден: '+name)
        def action(column,offset):
            deleted=type(column) is BSLValueTreeColumn and column.table is receiver.table and column._deleted
            if deleted and deleted_first:return
            try:
                if type(offset) is bool:distance=int(offset)
                elif type(offset) is str:distance=int(Decimal(offset))
                elif type(offset) is Decimal:distance=int(offset)
                else:raise ValueError('synthetic offset')
            except (ValueError,InvalidOperation):raise ValueError('synthetic offset') from None
            if deleted:return
            if type(column) is Decimal:index=int(column)
            elif type(column) is BSLValueTreeColumn:
                index=next((i for i,c in enumerate(receiver.items) if c is column),-1)
            else:raise ValueError('synthetic selector')
            if not 0<=index<len(receiver.items):raise ValueError('synthetic selector')
            destination=index+distance
            if policy=='clamp':destination=min(max(destination,0),len(receiver.items)-1)
            elif not 0<=destination<len(receiver.items):raise ValueError('synthetic destination')
            receiver.items.insert(destination,receiver.items.pop(index))
        return HostFunction(name,action,returns_value=False)
    with patch.object(Columns,'get_method',get):yield


class BoundaryObserverTests(unittest.TestCase):
    def probe(self,case):
        vm=Interpreter();vm.execute(HELPERS)
        return wire.validate_payload(vm.execute(f'CBProbe({case})').encode(),case)

    def test_explicit_missing_method_model_has_all17_full_fresh_fixtures_not_availability(self):
        with original_model('missing'):raw=emit()
        records=wire.validate_output(raw)
        self.assertEqual(len(raw),4779)
        self.assertEqual(len(records),17)
        self.assertTrue(all(r['status']=='M' for r in records))
        self.assertTrue(all(len(r['snapshots'][0]['nodes'])==5 for r in records))
        self.assertTrue(all(r['snapshots'][0]==r['snapshots'][1] for r in records))
        with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)

    def test_positive_en_ru_controls_move_existing_columns_and_cells(self):
        with model():en,ru=self.probe(1),self.probe(2)
        self.assertEqual(en,dict(ru,case=1))
        before,after=en['snapshots'];self.assertNotEqual(before['schema'],after['schema'])
        self.assertEqual(tuple(c[0] for c in after['schema']),tuple(before['schema'][i][0] for i in (0,2,1)))
        for old,new in zip(before['nodes'],after['nodes']):
            self.assertEqual(old[:6],new[:6])
            self.assertEqual(new.cells,tuple(old.cells[i] for i in (0,2,1)))
            self.assertEqual(new.cells,new.named_cells)

    def test_destination_boundary_models_are_distinguished_without_assuming_one(self):
        for case in (3,4,5,13):
            with model('strict'):strict=self.probe(case)
            with model('clamp'):clamped=self.probe(case)
            self.assertEqual(strict['status'],'O');self.assertEqual(clamped['status'],'S')
        with model('clamp'):changed=self.probe(3)
        self.assertNotEqual(*changed['snapshots'])

    def test_deleted_selector_conversion_order_is_observable(self):
        for case in (9,10):
            with model(deleted_first=True):early=self.probe(case)
            with model(deleted_first=False):late=self.probe(case)
            self.assertEqual(early['status'],'S');self.assertEqual(late['status'],'O')
            self.assertEqual(early['snapshots'],late['snapshots'])
        with model(deleted_first=True):
            for case in (6,7,8):self.assertEqual(self.probe(case)['status'],'S')

    def test_paired_numeric_string_and_boolean_inputs_reach_models(self):
        with model('clamp'):
            pairs=((4,14),(11,16))
            for a,b in pairs:self.assertEqual(self.probe(a)['snapshots'],self.probe(b)['snapshots'])
            self.assertEqual(self.probe(15)['status'],'O')
            for case in (12,17):
                record=self.probe(case);self.assertEqual(record['status'],'S')
                self.assertEqual(*record['snapshots'])
            wire.require_available(emit())

    def test_partial_errors_and_replacement_identities_are_retained(self):
        with original_model('partial'):first,second=self.probe(1),self.probe(2)
        self.assertEqual(first['status'],'O');self.assertNotEqual(*first['snapshots'])
        self.assertEqual(first['snapshots'][0],second['snapshots'][0])
        with original_model('replacement'):record=self.probe(1)
        self.assertNotEqual(record['snapshots'][0]['schema'][0][0],record['snapshots'][1]['schema'][0][0])
        self.assertNotIn('private',str(first))

    def test_postaction_named_positional_discrepancy_is_successfully_observed(self):
        original_get=BSLValueTreeRow.get;original_method=Columns.get_method;changed=set()
        def get(receiver,name):
            if name.casefold() not in ('move','сдвинуть'):return original_method(receiver,name)
            return HostFunction(name,lambda *args:changed.add(id(receiver.table)),returns_value=False)
        def positional(row,index):
            value=original_get(row,index)
            return Decimal(9) if id(row.tree) in changed else value
        with patch.object(Columns,'get_method',get),patch.object(BSLValueTreeRow,'get',positional):record=self.probe(1)
        self.assertEqual(record['status'],'S')
        for old,new in zip(record['snapshots'][0]['nodes'],record['snapshots'][1]['nodes']):
            self.assertEqual(old.cells,old.named_cells);self.assertEqual(old.named_cells,new.named_cells)
            self.assertEqual(new.cells,(('N','9'),)*3);self.assertNotEqual(new.cells,new.named_cells)

    def test_error_capture_order_and_observer_failure_are_fail_closed(self):
        self.assertIn('Исключение\n            OriginalErrorDescription = ОписаниеОшибки();\n            Status = CBError(OriginalErrorDescription);',SOURCE)
        self.assertIn('Исключение\n        OriginalObserverErrorDescription = ОписаниеОшибки();',SOURCE)
        with patch.object(Columns,'get',side_effect=ValueError('private observer failure')):
            raw=emit()
        self.assertNotIn(b'private',raw)
        with self.assertRaises(wire.ObservationError):wire.validate_output(raw)

    def test_source_read_is_explicit_utf8_on_windows_default_codepage(self):
        original=Path.read_text
        def windows_read(path,*args,**kwargs):
            if not args and kwargs.get('encoding') is None:kwargs['encoding']='cp1252'
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',windows_read):namespace=runpy.run_path(str(Path(__file__).resolve()))
        self.assertEqual(namespace['SOURCE'],SOURCE)


if __name__=='__main__':unittest.main()
