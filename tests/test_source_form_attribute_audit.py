"""Detect retained scalar attribute conflicts without evaluating a module."""
import json
import unittest
from test_source_forms import FORM,CODE
from yadinassi.source_form_handler_audit import audit_handler_names
from yadinassi.form_program import compile_form_module

class SourceAttributeAuditTests(unittest.TestCase):
    def audit(self,code=CODE,raw=FORM):
        return audit_handler_names(raw,compile_form_module(code.decode()))

    def test_normal_form_has_no_attribute_conflicts(self):
        self.assertEqual(self.audit()['attribute_issues'],[])

    def test_variable_routine_and_function_collisions_case_insensitive(self):
        for declaration in (b'&AtClient\nVar greeting;',b'&AtServer\nProcedure GREETING()\nEndProcedure',b'&AtClient\nFunction Greeting()\nReturn 1;\nEndFunction'):
            with self.subTest(declaration=declaration):
                result=self.audit(declaration)
                self.assertEqual(result['attribute_issues'],['Greeting: form attribute shadows module declaration'])

    def test_no_context_duplicates_do_not_duplicate_conflicts(self):
        result=self.audit(b'&AtServerNoContext\nProcedure Greeting()\nEndProcedure')
        self.assertEqual(len(result['attribute_issues']),1)

    def test_reserved_scalar_attributes_not_storage_granted(self):
        for value in ('Object','Объект','WriteObject','ObjectField123'):
            raw=FORM.replace(b'Greeting',value.encode())
            with self.subTest(value=value):self.assertEqual(self.audit(raw=raw)['attribute_issues'],[value+': reserved object form attribute'])

    def test_removed_nonscalar_attributes_not_false_positive(self):
        raw=FORM.replace(b'xs:string',b'xs:base64Binary')
        self.assertEqual(self.audit(b'&AtClient\nVar Greeting;',raw)['attribute_issues'],[])

    def test_parameter_or_local_variable_does_not_shadow_form_module(self):
        code=b'&AtClient\nProcedure Other(Greeting)\nVar Local;\nEndProcedure'
        self.assertEqual(self.audit(code)['attribute_issues'],[])

    def test_output_lists_have_shared_utf8_budget_with_explicit_omissions(self):
        commands=b''.join(('<Command name="C%d" id="%d"><Action>%s%d</Action></Command>'%(i,i+1,'Я'*110,i)).encode() for i in range(40))
        raw=FORM[:FORM.index(b'<Commands>')]+b'<Commands>'+commands+b'</Commands></Form>'
        result=self.audit(b'',raw)
        lists=[result[k] for k in ('missing','signature_issues','attribute_issues')]
        self.assertLessEqual(sum(len(json.dumps(x,ensure_ascii=False).encode())+1 for values in lists for x in values),6144)
        self.assertEqual(len(result['missing'])+result['omitted_missing'],40)

    def test_attribute_issue_count_bounded(self):
        template=FORM[FORM.index(b'<Attribute name='):FORM.index(b'</Attribute>')+len(b'</Attribute>')]
        attrs=b''.join(template.replace(b'Greeting',('ObjectField'+str(i)).encode()).replace(b'id="1"',('id="'+str(i+10)+'"').encode()) for i in range(25))
        raw=FORM.replace(b'</Attributes>',attrs+b'</Attributes>')
        result=self.audit(raw=raw)
        self.assertEqual(len(result['attribute_issues']),16);self.assertEqual(result['omitted_attribute_issues'],9)

    def test_multicategory_utf8_overflow_is_counted_not_silent(self):
        missing=b''.join(('<Command name="C%d" id="%d"><Action>%s%d</Action></Command>'%(i,i+1,'Я'*110,i)).encode() for i in range(30))
        wrong=b''.join(('<Command name="%s%d" id="%d"><Action>Wrong</Action></Command>'%('Ж'*110,i,i+31)).encode() for i in range(20))
        raw=FORM[:FORM.index(b'<Commands>')]+b'<Commands>'+missing+wrong+b'</Commands></Form>'
        result=self.audit(b'&AtClient\nProcedure Wrong()\nEndProcedure',raw)
        self.assertEqual(result['status'],'names-checked')
        self.assertGreater(result['omitted_signature_issues'],4)
        self.assertEqual(len(result['signature_issues'])+result['omitted_signature_issues'],20)
        self.assertEqual(len(result['missing'])+result['omitted_missing'],30)
        size=sum(len(json.dumps(x,ensure_ascii=False).encode())+1 for k in ('missing','signature_issues','attribute_issues') for x in result[k])
        self.assertLessEqual(size,6144)
