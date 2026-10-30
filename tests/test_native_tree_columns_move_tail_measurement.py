"""Competing synthetic tail/conversion models, not native semantics."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.value_trees import BSLValueTreeColumnCollection as Columns, BSLValueTreeColumn, BSLValueTreeRow
from yadinassi.values import HostFunction
from scripts import native_1c_tree_columns_move_tail_contract as wire
from test_native_tree_columns_move_measurement import model as original_model

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'integrational_tests/measurements/tree_columns_move_tail.bsl').read_text(encoding='utf-8')
HELPERS=SOURCE[:SOURCE.index('Сообщить("CT-C1:')]


def emit():
    out=[];Interpreter(out.append).execute(SOURCE)
    return ('\n'.join(out)+'\n').encode('ascii')


@contextmanager
def model(policy='noop'):
    """Competing hypothetical implementations, not claims about native 1C."""
    original=Columns.get_method
    def get(receiver,name):
        if name.casefold() not in ('move','сдвинуть'):
            return original(receiver,name)
        def action(column,offset):
            deleted=type(column) is BSLValueTreeColumn and column.table is receiver.table and column._deleted
            if deleted:
                if policy=='noop':return
                if policy=='reject':raise ValueError('synthetic deleted selector')
                if policy=='reinsert':
                    column._deleted=False
                    receiver.items.insert(int(offset)-1,column)
                    for row in receiver.table._all_rows:row.cells[column]=Decimal(0)
                    return
                raise ValueError('synthetic policy')
            if type(column) is Decimal:index=int(column)
            else:index=next(i for i,c in enumerate(receiver.items) if c is column)
            receiver.items.insert(index+int(offset),receiver.items.pop(index))
        return HostFunction(name,action,returns_value=False)
    with patch.object(Columns,'get_method',get):yield


class TailObserverTests(unittest.TestCase):
    def probe(self,case):
        vm=Interpreter();vm.execute(HELPERS)
        return wire.validate_payload(vm.execute(f'CTProbe({case})').encode(),case)

    def test_explicit_missing_method_model_has_all6_full_fresh_fixtures_not_availability(self):
        with original_model('missing'):raw=emit()
        records=wire.validate_output(raw)
        self.assertEqual(len(raw),1691)
        self.assertEqual(len(records),6)
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

    def test_deleted_tail_noop_and_reject_are_distinct_observations(self):
        for case in range(3,7):
            with model('noop'):noop=self.probe(case)
            with model('reject'):rejected=self.probe(case)
            self.assertEqual(noop['status'],'S')
            self.assertEqual(rejected['status'],'O')
            self.assertEqual(noop['snapshots'],rejected['snapshots'])
            self.assertEqual(*noop['snapshots'])
        with model('noop'):wire.require_available(emit())
        with model('reject'):wire.require_available(emit())

    def test_reinsertion_exceeding_snapshot_domain_is_not_false_acceptance(self):
        # Four columns are outside this probe's explicit three-column domain.
        # This cannot prove absence of reinsertion: it must fail acquisition.
        with model('reinsert'):
            vm=Interpreter();vm.execute(HELPERS)
            for case in range(3,7):
                payload=vm.execute(f'CTProbe({case})').encode()
                self.assertEqual(payload,b'XO')
                with self.assertRaises(wire.ObservationError):wire.validate_payload(payload,case)
            raw=emit()
        with self.assertRaises(wire.ObservationError):wire.require_available(raw)

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
        self.assertIn('Исключение\n            OriginalErrorDescription = ОписаниеОшибки();\n            Status = CTError(OriginalErrorDescription);',SOURCE)
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
