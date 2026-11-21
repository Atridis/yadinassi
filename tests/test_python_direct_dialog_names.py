import unittest
from yadinassi.forms.form_runtime import FormSession
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.forms.form_dialogs import QuestionDialogMode,DialogReturnCode

class DirectDialogNameTests(unittest.TestCase):
    def run_source(self,body):
        session=FormSession('Procedure Event() '+body+' EndProcedure',allow_extensions=True);seen=[]
        session.interpreter.register_function('Capture',lambda *args:seen.append(args))
        session.open();session._begin(session.revision)
        try:session._invoke('Event','client',[])
        finally:session._busy=False;session._gate.release()
        return seen
    def test_exact_english_and_russian_public_members(self):
        seen=self.run_source('Capture(QuestionDialogMode.YesNoCancel, РежимДиалогаВопрос.ДаНетОтмена, DialogReturnCode.Yes, КодВозвратаДиалога.Да);')
        self.assertEqual(seen,[(QuestionDialogMode.YES_NO_CANCEL,QuestionDialogMode.YES_NO_CANCEL,DialogReturnCode.YES,DialogReturnCode.YES)])
    def test_private_members_and_namespace_writes_rejected(self):
        for body in ('Capture(QuestionDialogMode.__dict__);','DialogReturnCode=1;','QuestionDialogMode.YesNoCancel=1;'):
            with self.subTest(body=body),self.assertRaises((BSLRuntimeError,BoundaryViolation)):self.run_source(body)
