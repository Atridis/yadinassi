import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectValueConstructorTests(unittest.TestCase):
    def test_source_ast_prepared_bilingual_family(self):
        source='D=New TypeDescription("String",,New StringQualifiers(4,AllowedLength.Fixed));R=D.AdjustValue("ab");T=Новый ТаблицаЗначений;T.Колонки.Добавить("A");T.Добавить().A=R;N=T.Count();'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(vm.variables['r'],'ab  ');self.assertEqual(vm.variables['n'],1)
        for en,ru in (('TypeDescription','ОписаниеТипов'),('ValueTable','ТаблицаЗначений'),('NumberQualifiers','КвалификаторыЧисла'),('StringQualifiers','КвалификаторыСтроки'),('DateQualifiers','КвалификаторыДаты'),('BinaryDataQualifiers','КвалификаторыДвоичныхДанных')):
            vm=Interpreter();vm.execute('A=New '+en+';B=Новый '+ru+';R=TypeOf(A)=TypeOf(B);')
            self.assertTrue(vm.variables['r'])

    def test_constructor_override_and_mutation_reject_before_dispatch(self):
        for name in ('TypeDescription','ValueTable','NumberQualifiers','StringQualifiers','DateQualifiers','BinaryDataQualifiers'):
            vm=Interpreter(allow_extensions=True);seen=[];vm.register_function('Effect',lambda:seen.append(1))
            vm.register_type(name,lambda *args:seen.append(args))
            with self.assertRaises(BoundaryViolation):vm.execute('New '+name+'(Effect());')
            self.assertEqual(seen,[])
            vm=Interpreter(allow_extensions=True);factory=vm.types[name.casefold()]
            def effect():factory.function=lambda *args:seen.append(args);return None
            vm.register_function('Effect',effect)
            with self.assertRaises(BoundaryViolation):vm.execute('New '+name+'(Effect());')
            self.assertEqual(seen,[])

    def test_invalid_qualifiers_and_holes_remain_checked(self):
        for source in ('New DateQualifiers(1)','New TypeDescription("Unknown")','New TypeDescription("Number",New StringQualifiers(4))','New NumberQualifiers(5,)','New ValueTable(,)'):
            vm=Interpreter();vm.execute('Try '+source+';Except Caught=True;EndTry;');self.assertTrue(vm.variables['caught'],source)

    def test_revocation_during_constructor_arguments(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('Close',lambda:vm.close() or 'String')
        with self.assertRaises(BoundaryViolation):vm.execute('New TypeDescription(Close());')

    def test_server_and_nocontext_scalar_descriptors(self):
        for directive in ('AtServer','AtServerNoContext','AtClientAtServerNoContext'):
            vm=Interpreter(compilation_profile='managed-thick-file');vm.execute('&'+directive+'\nFunction F() D=New TypeDescription("Number",New NumberQualifiers(5,2));Return D.AdjustValue(1.245);EndFunction R=F();')
            self.assertEqual(str(vm.variables['r']),'1.25')

    def test_descriptor_omission_does_not_leak_to_replaced_factory(self):
        vm=Interpreter(allow_extensions=True);seen=[];factory=vm.types['typedescription']
        def effect():factory.function=lambda *args:seen.append(args);return 'String'
        vm.register_function('Effect',effect)
        with self.assertRaises(BoundaryViolation):vm.execute('New TypeDescription(Effect(),,);')
        self.assertEqual(seen,[])
