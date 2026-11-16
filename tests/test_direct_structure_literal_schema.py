import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.experimental_naked_structure import structure_items

class LiteralStructureSchemaTests(unittest.TestCase):
    def pair(self,source):
        results=[]
        for backend in ('interpreter','python-direct'):
            events=[];vm=Interpreter(execution_backend=backend)
            vm.register_function('Observe',lambda value:events.append(value) or value)
            error=None
            try:vm.execute(source)
            except Exception as e:error=(type(e).__name__,str(e))
            s=vm.variables.get('s')
            if s is None:items=None
            elif backend=='python-direct':items=list(structure_items(s))
            else:items=[(pair.key,pair.value) for pair in s]
            results.append((events,items,error))
        self.assertEqual(results[0],results[1])
        return results[1]

    def test_literal_duplicate_spelling_whitespace_and_omitted_values(self):
        for source in ('s=New Structure(" Name, name ,NEXT",Observe(1),Observe(2));',
                       's=New Structure("ß,SS",1,2);',
                       's=New Structure(" , , ",Observe(9));',
                       's=New Structure;',
                       's=New Structure(("A,B"),1);'):
            with self.subTest(source=source):self.pair(source)

    def test_extra_values_still_evaluated_in_order(self):
        events,items,error=self.pair('s=New Structure("A",Observe(1),Observe(2),Observe(3));')
        self.assertEqual(events,[1,2,3]);self.assertEqual(items,[('A',Decimal(1))])

    def test_invalid_literal_fails_after_all_arguments(self):
        self.pair('s=New Structure("A,bad name",Observe(1),Observe(2));')
        self.pair('s=New Structure("bad name",1/0);')

    def test_dynamic_fields_keep_runtime_path(self):
        self.pair('keys="A,a";s=New Structure(keys,Observe(1),Observe(2));')

    def test_successful_literal_never_calls_runtime_insert(self):
        from yadinassi import experimental_naked_structure as helpers
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
