"""Bounded table call-site holes: defaults, eager rejection, owner guards."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.collections.value_tables import BSLValueTable


class DirectTableOmissionsTests(unittest.TestCase):
    def test_defaults_source_ast_prepared_execute_and_eval_without_vm(self):
        setup='T=New ValueTable;T.Columns.Add("A");T.Add();'
        body='C=T.Columns.Add(,,"Header",);D=T.Columns.Insert(0,"D",,);R=T.Copy(,"A");'
        for route in ('source','ast','prepared','execute','eval'):
            with self.subTest(route=route),patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                vm=Interpreter();vm.execute(setup)
                if route=='source':vm.execute(body)
                elif route=='ast':vm.execute_program(parse(body))
                elif route=='prepared':vm.execute_prepared(vm.prepare(body))
                elif route=='execute':vm.execute('Var C,D,R;Execute("'+body.replace('"','""')+'");')
                else:
                    vm.execute('C=Eval("T.Columns.Add(,,""Header"",)");D=Eval("T.Columns.Insert(0,""D"",,)");R=Eval("T.Copy(,""A"")");')
                self.assertEqual(vm.execute('C.Name'),'');self.assertEqual(vm.execute('C.Title'),'Header')
                self.assertEqual(vm.execute('C.Width'),0);self.assertEqual(vm.execute('D.Title'),'')
                self.assertEqual(vm.execute('R.Count()'),1);self.assertEqual(vm.execute('R.Columns.Count()'),1)

    def test_required_and_excess_holes_reject_before_argument_effects(self):
        vm=Interpreter(allow_extensions=True);vm.execute('T=New ValueTable;T.Columns.Add("A");R=T.Add();')
        seen=[];vm.register_function('Effect',lambda:seen.append('effect') or 0)
        for text in ('T.Columns.Insert(,Effect())','T.FillValues(,Effect())','T.Get(,Effect())',
                     'R.Set(,Effect())','T.Copy(Effect(),,)','T.Columns.Add("B",,Effect(),,)'):
            with self.subTest(text=text),self.assertRaises(BSLError):vm.execute(text)
            self.assertEqual(seen,[])

    def test_optional_versus_explicit_undefined_and_aliases(self):
        vm=Interpreter()
        vm.execute('T=New ТаблицаЗначений;C=T.Колонки.Добавить(,,"Header");D=T.Колонки.Вставить(0,"D",,,);T.Добавить();T.ЗаполнитьЗначения(7,);R=T.Скопировать(,);Q=T.СкопироватьКолонки();')
        self.assertEqual(vm.execute('C.Name'),'');self.assertEqual(vm.execute('D.Width'),0)
        self.assertEqual(vm.execute('R.Count()'),1);self.assertEqual(vm.execute('Q.Count()'),0)
        with self.assertRaises(BSLError):vm.execute('T.Columns.Add(Undefined);')

    def test_valid_effect_order_and_once(self):
        vm=Interpreter(allow_extensions=True);vm.execute('T=New ValueTable;');seen=[]
        vm.register_function('Arg',lambda tag,value:seen.append(tag) or value)
        vm.execute('C=T.Columns.Insert(Arg("index",0),Arg("name","X"),,Arg("title","H"),Arg("width",4));')
        self.assertEqual(seen,['index','name','title','width']);self.assertEqual(vm.execute('C.Width'),4)

    def test_owner_mutation_and_close_rechecked_after_arguments(self):
        for action in ('owner','close'):
            vm=Interpreter(allow_extensions=True);vm.execute('T=New ValueTable;Cols=T.Columns;');columns=vm.variables['cols']
            def effect():
                if action=='owner':columns.table=object()
                else:vm.close()
                return 'H'
            vm.register_function('Effect',effect)
            with self.subTest(action=action),self.assertRaises(BoundaryViolation):vm.execute('Cols.Add(,,Effect());')
            self.assertEqual(columns.items,[])

    def test_computed_receiver_and_subclass_remain_unadmitted(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Receiver',lambda:seen.append('receiver') or BSLValueTable())
        with self.assertRaises(BSLError):vm.execute('Receiver().Copy(,);')
        self.assertEqual(seen,[])
        class Foreign(BSLValueTable):
            def get_method(self,name):seen.append('get_method');raise AssertionError
        vm.variables['bad']=Foreign()
        with self.assertRaises(BoundaryViolation):vm.execute('Bad.Copy(,);')
        self.assertEqual(seen,[])

    def test_bounded_slice_write_guard_is_not_relaxed(self):
        vm=Interpreter(allow_extensions=True);vm.execute('T=New ValueTable;');table=vm.variables['t'];table._bounded_slice_read=True
        seen=[];vm.register_function('Effect',lambda:seen.append('effect') or 'H')
        for code in ('T.Columns.Add(,,Effect());','T.FillValues(Effect(),);','T.Copy(,);'):
            with self.assertRaises(BSLError):vm.execute(code)
            self.assertEqual(seen,[])

    def test_native_default_column_record_is_distinct_from_omission_control(self):
        fixture=(Path(__file__).resolve().parents[1]/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        record=fixture.split('table.mutate.column-add-default: [',1)[1].split('\n]',1)[0]
        for field,value in (('Name','{"S",""}'),('Title','{"S",""}'),('Width','{"N",0}')):
            self.assertIn('Result.'+field+'='+value,record)
        # Partial omitted slots are checked against canonical runtime above;
        # this frozen observation establishes defaults, not a new native probe.
