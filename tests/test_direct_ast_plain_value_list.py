import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.collections.plain_value_list import PlainValueList,PlainValueListItem
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectPlainValueListTests(unittest.TestCase):
    def vm(self, *, allow_extensions=False):
        vm=Interpreter(allow_extensions=allow_extensions);self.addCleanup(vm.close);return vm
    def test_general_default_dynamic_and_four_fields(self):
        vm=self.vm(allow_extensions=True);vm.register_function('Input',lambda:D(7))
        vm.execute('L=New ValueList;Item=L.Add(Input(),"seven",True);Item.Presentation="changed";Item.Value=9;R=L.Get(0).Value;Text=Item.Presentation;N=L.Count();Found=L.FindByID(Item.GetID());')
        self.assertIs(type(vm.variables['l']),PlainValueList)
        item=vm.variables['item'];self.assertIs(type(item),PlainValueListItem)
        self.assertEqual(list(item),[D(9),'changed',True,None]);self.assertEqual(vm.variables['r'],D(9));self.assertEqual(vm.variables['n'],D(1));self.assertIs(vm.variables['found'],item)
        vm.execute('Other=New("ValueList");Other.Add(4);S=Other[0].Value;')
        self.assertIs(type(vm.variables['other']),PlainValueList);self.assertEqual(vm.variables['s'],D(4))

    def test_val_item_field_reads_use_live_slots_without_copyback(self):
        vm = self.vm(allow_extensions=True)
        vm.execute('L=New ValueList; Item=L.Add(10,"old",True,"image"); '
                   'Function ReadAndAssign(Val field) '
                   'result=field; field=Undefined; Return result; EndFunction')
        original = vm.variables['item']
        effects = []

        def receiver():
            effects.append('receiver')
            return original

        vm.register_function('Receiver', receiver)
        for field, expected in (('Value', D(10)), ('Значение', D(10)),
                                ('Presentation', 'old'), ('Представление', 'old'),
                                ('Check', True), ('Пометка', True),
                                ('Picture', 'image'), ('Картинка', 'image')):
            with self.subTest(field=field):
                effects.clear()
                result = vm.execute(f'ReadAndAssign(Receiver().{field})')
                self.assertEqual(result, expected)
                self.assertIs(type(result), type(expected))
                self.assertEqual(effects, ['receiver'])
                self.assertEqual(list(original), [D(10), 'old', True, 'image'])

    def test_hostile_index_and_equality_do_not_gain_callbacks(self):
        vm=self.vm();seen=[]
        class Hostile:
            def __index__(self):seen.append('index');vm.close();return 0
            def __int__(self):seen.append('int');vm.close();return 0
            def __eq__(self,other):seen.append('eq');vm.close();return True
        vm.variables['opaque']=Hostile()
        vm.execute('L=New ValueList;Item=L.Add(3);A=L=Opaque;B=Opaque=L;C=Item=Opaque;D=Opaque=Item;')
        self.assertFalse(any(vm.variables[k] for k in ('a','b','c','d')));self.assertEqual(seen,[])
        with self.assertRaises(Exception):vm.execute('R=L.Get(Opaque);After=1;')
        self.assertEqual(seen,[]);self.assertNotIn('after',vm.variables)
    def test_actual_close_cannot_mutate_published_list(self):
        vm=self.vm();data=PlainValueList();vm.variables['l']=data
        class Opaque:
            def __add__(self,other):vm.close();return D(9)
        vm.variables['x']=Opaque()
        with self.assertRaises(BoundaryViolation):vm.execute('L.Add(X+1);After=1;')
        self.assertEqual(len(data),0);self.assertNotIn('after',vm.variables)

    def test_routine_public_alias_and_argument_revoke(self):
        for code in (
            'Procedure F(Val X,Val L) R=X+1;L.Add(7);EndProcedure;F(X,L);',
            'Procedure F(Val X,Val L) L.Add(X+1);EndProcedure;F(X,L);',
            'L.Add(X+1);'):
            vm=self.vm();data=PlainValueList();vm.variables['l']=data
            class Opaque:
                def __add__(self,other):vm.close();return D(9)
            vm.variables['x']=Opaque()
            with self.assertRaises(BoundaryViolation):vm.execute(code)
            self.assertEqual(len(data),0)
