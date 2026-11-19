"""Closed constructor and optional regex service boundaries."""
import unittest
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.formats.regex import regex_functions


class DirectRegexServicesTests(unittest.TestCase):
    def test_aliases_and_optional_holes(self):
        for name in ('StrFindByRegularExpression','СтрНайтиПоРегулярномуВыражению','Alias'):
            vm=Interpreter();vm.register_function('Alias',regex_functions.str_find)
            self.assertEqual(vm.execute(name+'("a1b2","[0-9]",,,2).Value;'),'2')

    def test_invalid_holes_and_arity_precede_argument_effects(self):
        for source in ('StrLikeByRegularExpression(Effect());',
                       'StrFindByRegularExpression(,Effect(),,,2);',
                       'StrFindByRegularExpression(Effect(),"a",,,,,,);',
                       'StrLen(Effect(),);'):
            vm=Interpreter();effects=[];vm.register_function('Effect',lambda:effects.append(1) or 'a')
            vm.execute('Try '+source+' Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught']);self.assertEqual(effects,[])

    def test_prepared_call_uses_current_registration(self):
        vm=Interpreter();effects=[]
        plan=vm.prepare('StrFindByRegularExpression("a1","[0-9]",,);')
        vm.register_function('StrFindByRegularExpression',lambda *args:effects.append(args))
        with self.assertRaisesRegex(Exception,'Пропуск аргументов'):vm.execute_prepared(plan)
        self.assertEqual(effects,[])

    def test_mutated_bound_implementation_never_receives_sentinel(self):
        vm=Interpreter();effects=[]
        function=vm.functions['strfindbyregularexpression']
        def mutate():
            function.function=lambda *args:effects.append(args)
            return 'a1'
        vm.register_function('Mutate',mutate)
        with self.assertRaisesRegex(BoundaryViolation,'implementation changed'):
            vm.execute('StrFindByRegularExpression(Mutate(),"[0-9]",,);')
        self.assertEqual(effects,[])

    def test_replaced_registry_does_not_rebind_current_call(self):
        vm=Interpreter();effects=[]
        def replace():
            vm.register_function('StrFindByRegularExpression',lambda *args:effects.append(args))
            return 'a1'
        vm.register_function('Replace',replace)
        self.assertEqual(vm.execute('StrFindByRegularExpression(Replace(),"[0-9]",,).Value;'),'1')
        self.assertEqual(effects,[])

    def test_closed_owner_during_argument_evaluation(self):
        vm=Interpreter();vm.register_function('Close',lambda:vm.close() or 'a')
        with self.assertRaises(BoundaryViolation):vm.execute('StrFindByRegularExpression(Close(),"a",,);')

    def test_json_constructor_and_namespace_roundtrip(self):
        vm=Interpreter()
        self.assertEqual(vm.execute('W=New JSONWriter;W.SetString(New JSONWriterSettings(JSONLineBreak.None));'
            'W.WriteValue("hello");Text=W.Close();R=New JSONReader;R.SetString(Text);ReadJSON(R);'),'hello')

    def test_json_constructor_override_is_rejected_before_effects(self):
        vm=Interpreter();effects=[]
        vm.register_type('JSONWriterSettings',lambda *args:effects.append(args))
        vm.register_function('Effect',lambda:effects.append(1))
        with self.assertRaises(BoundaryViolation):vm.execute('New JSONWriterSettings(Effect());')
        self.assertEqual(effects,[])

    def test_regex_types_are_runtime_catchable_but_not_constructible(self):
        for name in ('ResultOfSearchByRegularExpression','ResultOfSearchByRegularExpressionGroup',
                     'РезультатПоискаПоРегулярномуВыражению','ГруппаРезультатаПоискаПоРегулярномуВыражению'):
            vm=Interpreter();vm.execute('Try New '+name+';Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught'])

    def test_services_in_server_and_dual_contexts(self):
        for directive in ('&AtServer','&AtServerNoContext','&AtClientAtServerNoContext'):
            vm=Interpreter(compilation_profile='managed-thick-file')
            vm.execute(directive+'\nFunction F() W=New JSONWriter;'
                'W.SetString(New JSONWriterSettings(JSONLineBreak.None));'
                'W.WriteValue(StrFindByRegularExpression("a1b2","[0-9]",,,2).Value);'
                'Return W.Close();EndFunction')
            self.assertEqual(vm.execute('F();'),'"2"')

    def test_regex_binding_released_without_cyclic_gc(self):
        import gc
        import weakref
        from unittest.mock import patch
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext
        original=BoundaryContext.resolve_service;references=[]
        def capture(context,*args,**kwargs):
            bound=original(context,*args,**kwargs)
            references.append(weakref.ref(bound))
            return bound
        enabled=gc.isenabled();gc.disable()
        try:
            with patch.object(BoundaryContext,'resolve_service',capture):
                vm=Interpreter()
                vm.execute('StrLikeByRegularExpression("a","a");')
                vm.execute('StrLikeByRegularExpression("a","a",);')
            self.assertEqual(len(references),2)
            self.assertTrue(all(reference() is None for reference in references))
        finally:
            if enabled:gc.enable()
