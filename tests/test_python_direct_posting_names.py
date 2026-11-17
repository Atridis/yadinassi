"""Posting fields and canonical scalar calls have distinct name roles."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter,BSLRuntimeError
from yadinassi.experimental_naked_collections import prepare
from yadinassi.python_direct_posting import _POSTING_REPAIRS
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
        from yadinassi.experimental_naked_collections import UnsupportedNakedSyntax
        with self.assertRaises(UnsupportedNakedSyntax):
            prepare('Number("3");',_trusted_entry=True,repairs=_POSTING_REPAIRS,external_names=('number',))
    def test_private_profile_validation(self):
        for options in ({'_host_routine_bindings':1},{'_host_callable_externals':['number']},
                        {'_host_callable_externals':('number',)},
                        {'_host_routine_bindings':True,'repairs':()}):
            with self.subTest(options=options),self.assertRaises((TypeError,ValueError)):
                prepare('',_trusted_entry=True,**options)
        with self.assertRaises(ValueError):
            prepare('',_trusted_entry=True,repairs=_POSTING_REPAIRS,external_names=('number',),
                    parsed_ast=None,_host_callable_externals=('number',))
