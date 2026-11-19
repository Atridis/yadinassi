import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_structure import structure_items

class LiteralStructureSchemaTests(unittest.TestCase):
    def execute(self, source):
        events=[];vm=Interpreter(execution_backend='python-direct', allow_extensions=True)
        vm.register_function('Observe',lambda value:events.append(value) or value)
        vm.execute(source)
        return events,list(structure_items(vm.variables['s']))

    def test_literal_duplicate_spelling_whitespace_and_omitted_values(self):
        cases=(
            ('s=New Structure(" Name, name ,NEXT",Observe(1),Observe(2));',
             [1,2],[('name',Decimal(2)),('NEXT',None)]),
            ('s=New Structure("ß,SS",1,2);',[],[('SS',Decimal(2))]),
            ('s=New Structure(" , , ",Observe(9));',[9],[]),
            ('s=New Structure;',[],[]),
            ('s=New Structure(("A,B"),1);',[],[('A',Decimal(1)),('B',None)]),
        )
        for source,events,items in cases:
            with self.subTest(source=source):
                self.assertEqual(self.execute(source),(events,items))

    def test_extra_values_still_evaluated_in_order(self):
        self.assertEqual(
            self.execute('s=New Structure("A",Observe(1),Observe(2),Observe(3));'),
            ([1,2,3],[('A',Decimal(1))]))

    def test_invalid_literal_fails_after_all_arguments(self):
        from yadinassi import BSLRuntimeError
        for source,expected_events,message in (
            ('s=New Structure("A,bad name",Observe(1),Observe(2));',[1,2],
             'Недопустимое имя свойства структуры: bad name'),
            ('s=New Structure("bad name",1/0);',[],'Деление на ноль'),
        ):
            with self.subTest(source=source):
                events=[];vm=Interpreter(execution_backend='python-direct', allow_extensions=True)
                vm.register_function('Observe',lambda value:events.append(value) or value)
                with self.assertRaisesRegex(BSLRuntimeError,message):vm.execute(source)
                self.assertEqual(events,expected_events)
                self.assertNotIn('s',vm.variables)

    def test_dynamic_fields_keep_runtime_path(self):
        self.assertEqual(
            self.execute('keys="A,a";s=New Structure(keys,Observe(1),Observe(2));'),
            ([1,2],[('a',Decimal(2))]))

    def test_successful_literal_never_calls_runtime_insert(self):
        from yadinassi.execution.codegen import experimental_naked_structure as helpers
        vm=Interpreter(execution_backend='python-direct')
        with patch.object(helpers,'structure_insert',side_effect=AssertionError('runtime insert')):
            vm.execute('s=New Structure("A,a,B",1,2,3);')
        self.assertEqual(list(structure_items(vm.variables['s'])),[('a',Decimal(2)),('B',Decimal(3))])
        self.assertEqual(vm.variables['s']._version,2)
        baseline=helpers.new_structure('A,a,B',Decimal(1),Decimal(2),Decimal(3))
        self.assertEqual(vm.variables['s']._version,baseline._version)
        self.assertEqual(list(structure_items(vm.variables['s'])),list(structure_items(baseline)))

    def test_each_allocation_is_fresh_and_values_alias(self):
        vm=Interpreter(execution_backend='python-direct')
        vm.execute('a=New Array;s=New Structure("A",a);t=New Structure("A",a);s.A.Add(7);r=t.A.Count();')
        self.assertEqual(vm.variables['r'],1);self.assertIsNot(vm.variables['s'],vm.variables['t'])
        self.assertIs(vm.variables['s']['a'],vm.variables['t']['a'])
