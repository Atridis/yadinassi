import unittest
from decimal import Decimal as D
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.collections.plain_value_list import PlainValueList,PlainValueListItem
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation

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

    def test_foreach_uses_live_value_list_items_without_rebinding_receiver(self):
        vm=self.vm()
        source=('L=New ValueList; First=L.Add(1); L.Add(2); Alias=L; Seen=New Array; '
                'For Each Item In L Do '
                'If Item.Value=1 Then Alias.Add(3); L=New ValueList; Item.Value=10; EndIf; '
                'Seen.Add(Item.Value); EndDo; '
                'Empty=New ValueList; For Each Item In Empty Do Seen.Add(99); EndDo;')
        from yadinassi.syntax.parser import parse
        plan=vm.prepare_program(parse(source))
        with patch.object(PlainValueList,'__iter__',side_effect=AssertionError('non-native iterator'),create=True):
            vm.execute_prepared(plan)
        self.assertEqual(vm.variables['seen'],[D(10),D(2),D(3)])
        self.assertEqual(len(vm.variables['l']),0)
        original=vm.variables['alias']
        self.assertIs(vm.variables['first'],original[0])
        self.assertIs(vm.variables['item'],original[2])

    def test_foreach_in_routine_uses_an_evaluated_bilingual_value_list(self):
        vm=self.vm()
        source=('Функция СуммаСписка() Список=Вычислить("Новый СписокЗначений"); '
                'Список.Добавить(2); Список.Добавить(5); Р=0; '
                'Для Каждого Элемент Из Список Цикл Р=Р+Элемент.Значение; КонецЦикла; '
                'Возврат Р; КонецФункции\nВычислить("СуммаСписка()")')
        self.assertEqual(vm.execute(source),D(7))

    def test_value_list_index_replacement_is_catchable_after_operand_evaluation(self):
        vm=self.vm()
        vm.execute('Var Calls; Function Arg(Val Tag) Calls.Add(Tag); Return 0; EndFunction\n'
                   'Calls=New Array; L=New ValueList; First=L.Add(4); '
                   'Caught=0; Try L[Arg("index")]=Arg("value"); Except Caught=Caught+1; EndTry; '
                   'Try Execute("L[0]=7;"); Except Caught=Caught+1; EndTry; '
                   'Try L[0]=New ValueList; Except Caught=Caught+1; EndTry;')
        self.assertEqual(vm.variables['calls'],['index','value'])
        self.assertEqual(vm.variables['caught'],D(3))
        self.assertEqual(len(vm.variables['l']),1)
        self.assertIs(vm.variables['l'][0],vm.variables['first'])
        self.assertEqual(vm.variables['first'][0],D(4))

    def test_value_list_sort_directions_keep_equal_items_stable_and_live(self):
        from yadinassi.syntax.parser import parse
        for english,russian,items in (
                ('SortByValue','СортироватьПоЗначению',('2,"z"','1,"m"','2,"a"')),
                ('SortByPresentation','СортироватьПоПредставлению',('3,"b"','2,"a"','1,"b"'))):
            with self.subTest(method=english):
                vm=self.vm()
                vm.execute('L=New ValueList; A=L.Add('+items[0]+'); B=L.Add('+items[1]+'); C=L.Add('+items[2]+');')
                owner=vm.variables['l']
                identities=tuple(vm.variables[name] for name in ('a','b','c'))
                ids=tuple(item.get_id() for item in identities)
                for call,order in (
                        (f'L.{english}();',(1,0,2)),
                        (f'L.{english}(SortDirection.Desc);',(0,2,1)),
                        (f'L.{russian}(НаправлениеСортировки.Возр);',(1,0,2)),
                        (f'L.{russian}(НаправлениеСортировки.Убыв);',(0,2,1)),
                        (f'L.{english}(Undefined);',(1,0,2)),
                ):
                    plan=vm.prepare_program(parse(call))
                    vm.execute_prepared(plan)
                    self.assertIs(vm.variables['l'],owner)
                    self.assertEqual(len(owner),3)
                    for index,original in enumerate(order):
                        self.assertIs(owner[index],identities[original])
                    self.assertEqual(tuple(item.get_id() for item in identities),ids)

    def test_value_list_rejects_nondirections_without_reordering(self):
        vm=self.vm()
        vm.execute('L=New ValueList; A=L.Add(2,"b"); B=L.Add(1,"a");')
        owner=vm.variables['l']
        for name in ('SortByValue','SortByPresentation'):
            for direction in ('True','False','0','"Asc"','Null','SearchDirection.FromBegin'):
                with self.subTest(name=name,direction=direction):
                    vm.execute(f'Try L.{name}({direction}); Caught=False; Except Caught=True; EndTry;')
                    self.assertIs(vm.variables['caught'],True)
                    self.assertEqual(len(owner),2)
                    self.assertIs(owner[0],vm.variables['a'])
                    self.assertIs(owner[1],vm.variables['b'])

    def test_value_list_sorts_exact_dates_by_ticks_and_retains_equal_item_order(self):
        vm=self.vm()
        vm.execute('L=New ValueList; Base=Date(2024,1,1); A=L.Add(Base+0.0002); '
                   'B=L.Add(Base); C=L.Add(Base+0.0001); D=L.Add(Base+0.0001);')
        owner=vm.variables['l']
        items=tuple(vm.variables[name] for name in ('a','b','c','d'))
        identifiers=tuple(item.get_id() for item in items)
        for code, order in (('L.SortByValue();',(1,2,3,0)),
                            ('L.СортироватьПоЗначению(НаправлениеСортировки.Убыв);',(0,2,3,1))):
            vm.execute(code)
            self.assertIs(vm.variables['l'],owner)
            for i,j in enumerate(order):
                self.assertIs(owner[i],items[j])
            self.assertEqual(tuple(item.get_id() for item in items),identifiers)

    def test_value_list_mixed_scalar_order_and_empty_ties(self):
        for values, asc, desc in (
                (('"2"','Date(2024,1,1)','2','True','Undefined','Null','False','0'),
                 (4,5,6,3,7,2,0,1),(1,0,2,7,3,6,5,4)),
                (('Null','Undefined','Null','Undefined'),(1,3,0,2),(0,2,1,3)),
                (('0','True','-1','False','2.0','2'),(3,1,2,0,4,5),(4,5,0,2,1,3)),
                (('"a"','"Z"','False'),(2,1,0),(0,1,2)),
        ):
            with self.subTest(values=values):
                vm=self.vm()
                vm.execute('L=New ValueList;' + ''.join(f'L.Add({value});' for value in values))
                owner=vm.variables['l']
                original=tuple(owner)
                for suffix,order in (('()',asc),('(SortDirection.Desc)',desc)):
                    vm.execute('L.SortByValue'+suffix+';')
                    self.assertEqual(tuple(item.get_id() for item in owner),order)
                    for item, index in zip(owner,order):
                        self.assertIs(item,original[index])

    def test_value_list_procedure_in_value_position_binds_receiver_but_not_arguments(self):
        vm=self.vm()
        vm.execute('Var L, Seen; L=New ValueList; First=L.Add(2,"b"); L.Add(1,"a"); Seen=New Array; '
                   'Function Receiver() Seen.Add("receiver"); Return L; EndFunction; '
                   'Function Argument() Seen.Add("argument"); Return 0; EndFunction;')
        owner=vm.variables['l']
        for call in ('Delete(Argument())','Очистить()','Сдвинуть(Argument(),Argument())',
                     'FillChecks(Argument())','ЗагрузитьЗначения(Argument())',
                     'SortByValue(Argument())','СортироватьПоПредставлению()'):
            with self.subTest(call=call):
                vm.execute(f'Try Out=Receiver().{call}; Caught=False; Except Caught=True; EndTry;')
                self.assertIs(vm.variables['caught'],True)
                self.assertNotIn('out',vm.variables)
                self.assertEqual(len(owner),2)
                self.assertIs(owner[0],vm.variables['first'])
                self.assertEqual(owner[0][2],False)
        self.assertEqual(vm.variables['seen'],['receiver']*7)
        vm.execute('Receiver().SortByValue(); Added=Receiver().Add(3);')
        self.assertEqual(owner[0][0],D(1))
        self.assertIs(owner[2],vm.variables['added'])
        self.assertEqual(vm.variables['seen'],['receiver']*9)

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
            'L.Add(X+1);',
            'L.Insert(0,X+1);'):
            vm=self.vm();data=PlainValueList();vm.variables['l']=data
            class Opaque:
                def __add__(self,other):vm.close();return D(9)
            vm.variables['x']=Opaque()
            with self.assertRaises(BoundaryViolation):vm.execute(code)
            self.assertEqual(len(data),0)

    def test_public_insert_and_add_keep_live_item_identity(self):
        vm = self.vm()
        data = PlainValueList()
        vm.variables['l'] = data
        vm.execute_prepared(vm.prepare('A=L.Add(2); B=L.Insert(0,1);'))
        self.assertIs(data[0], vm.variables['b'])
        self.assertIs(data[1], vm.variables['a'])
        self.assertEqual([item[0] for item in data], [1,2])
