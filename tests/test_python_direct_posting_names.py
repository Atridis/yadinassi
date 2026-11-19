"""Posting fields and canonical scalar calls have distinct name roles."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter,BSLRuntimeError
from yadinassi.experimental_direct_ast import compile_owned
from yadinassi.syntax.parser import parse
import test_document_posting_runtime as fixture

class PostingNamesTests(unittest.TestCase):
    def owner(self,module):
        owner=fixture.PostingRuntimeTests();owner.setUp();self.addCleanup(owner.doCleanups)
        owner.make(module)
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            guard=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            guard.start();self.addCleanup(guard.stop)
        return owner
    def test_number_call_keeps_field_read_and_ignores_parent_override(self):
        owner=self.owner('Procedure Posting(Cancel,Mode) AdditionalProperties.Insert("Read",Number);AdditionalProperties.Insert("Converted",Number(Number)+1);AdditionalProperties.Insert("Date",Date(2024,1,2)); EndProcedure')
        obj=owner.new(3);effects=[]
        owner.vm.register_function('Number',lambda *a:effects.append('parent'))
        owner.post()
        props=obj.get_member('AdditionalProperties')
        self.assertEqual(props.get_member('Read'),'3')
        self.assertEqual(props.get_member('Converted'),4)
        self.assertEqual(effects,[])
    def test_local_routine_and_parameter_precedence(self):
        owner=self.owner('Function LocalNumber(Val Number) Return Number+10;EndFunction Procedure Posting(Cancel,Mode) AdditionalProperties.Insert("N",LocalNumber(2));EndProcedure')
        obj=owner.new(3);owner.post()
        self.assertEqual(obj.get_member('AdditionalProperties').get_member('N'),12)
    def test_unknown_values_are_bsl_missing_names_not_python_nameerror(self):
        for expression in ('Documents','CommitTransaction'):
            with self.subTest(expression=expression):
                owner=self.owner('Procedure Posting(Cancel,Mode) AdditionalProperties.Insert("X",'+expression+');EndProcedure')
                obj=owner.new(3)
                with self.assertRaises(BSLRuntimeError) as caught:owner.post()
                self.assertNotIn("name 'v",str(caught.exception))
                self.assertTrue(obj.is_new())
                self.assertEqual(owner.rows(obj),())
    def test_lexical_locals_and_explicit_field_shadow(self):
        owner=self.owner('Procedure Posting(Cancel,Mode) Var Date; Date=8; N=5; AdditionalProperties.Insert("D",Date);AdditionalProperties.Insert("N",N);If False Then Missing=1;EndIf;Try AdditionalProperties.Insert("Bad",Missing);Except AdditionalProperties.Insert("Caught",True);EndTry;EndProcedure')
        obj=owner.new(3);owner.post();props=obj.get_member('AdditionalProperties')
        self.assertEqual(props.get_member('D'),8)
        self.assertEqual(props.get_member('N'),5)
        self.assertIs(props.get_member('Caught'),True)
    def test_default_compiler_does_not_admit_callable_field(self):
        from yadinassi.python_direct import PythonDirectUnsupported
        source='Number("3");'
        with self.assertRaises(PythonDirectUnsupported):
            compile_owned(parse(source),source_text=source,source_name='posting.bsl',external_names=('number',))
    def test_private_profile_validation(self):
        for options in ({'host_bindings':1},{'callable_externals':['number']},
                        {'callable_externals':('number',)}):
            with self.subTest(options=options),self.assertRaises((TypeError,ValueError)):
                compile_owned([],source_text='',source_name='posting.bsl',**options)
        with self.assertRaises(ValueError):
            compile_owned([],source_text='',source_name='posting.bsl',
                          external_names=('number',),callable_externals=('number',))
