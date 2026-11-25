"""Original catalog UI workflows must not reach the legacy AST dispatcher."""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from yadinassi.runtime import Interpreter
from yadinassi.forms.form_runtime import FormSession
from yadinassi.forms.form_model import BSLFormField
from yadinassi.execution.direct.python_direct_form_objects import get,setter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
import test_main_demo_host as host_tests

class DirectCatalogUITests(unittest.TestCase):
    def workflow(self,name):
        with ExitStack() as stack:
            for method in ('execute_program',):
                stack.enter_context(patch.object(Interpreter,method,side_effect=AssertionError('legacy '+method)))
            host_tests.MainDemoHostTests(name).debug()
    def test_original_kind_edit_save_navigation_no_vm(self):
        self.workflow('test_original_kind_change_handler_normalizes_and_survives_navigation')
    def test_original_product_edit_save_listcheck_reopen_no_vm(self):
        self.workflow('test_product_reference_sections_save_list_check_and_reopen_in_same_database')
    def test_foreign_and_replaced_control_denied_before_write(self):
        session=FormSession('');other=FormSession('')
        session._busy=True;other._busy=True
        context=SimpleNamespace(session=session,_check=session.form._check)
        local=BSLFormField(session.form,'Field');session.form.items._values['field']=local
        foreign=BSLFormField(other.form,'Field');other.form.items._values['field']=foreign
        try:
            with self.assertRaises(BoundaryViolation):get(context,foreign,'Name')
            write=setter(context,local,'Title')
            session.form.items._values['field']=BSLFormField(session.form,'Field')
            with self.assertRaises(BoundaryViolation):write('bad')
            self.assertEqual(local.title,'')
            with self.assertRaises(ValueError):get(context,session.form.items._values['field'],'__dict__')
        finally:session._busy=False;other._busy=False
