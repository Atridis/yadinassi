"""Extended Raise evaluates description then optional values through canonical errors."""
import unittest
from yadinassi import Interpreter
from yadinassi.types.errors import BSLError
from test_experimental_direct_ast_externals import DirectSourceAssertions


class RaiseTests(DirectSourceAssertions,unittest.TestCase):
    def test_extended_raise_metadata(self):
        self.check_source(
            'Try Raise("hello",,"code","info");Except R=ErrorInfo().Description;C=ErrorInfo().Code;A=ErrorInfo().AdditionalInformation;EndTry;',
            expected={'r':'hello','c':'code','a':'info'})

    def test_extended_raise_evaluates_operands_in_order(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
        events=[]
        for name,value in [('Describe','hello'),('Code','code'),('Info','info')]:
            vm.register_function(name,lambda name=name,value=value: events.append(name) or value)
        vm.execute('Try Raise(Describe(),,Code(),Info());Except R=ErrorInfo().Description;C=ErrorInfo().Code;A=ErrorInfo().AdditionalInformation;EndTry;')
        self.assertEqual(events,['Describe','Code','Info'])
        self.assertEqual(vm.variables,{'r':'hello','c':'code','a':'info'})

    def test_unreached_raise_has_no_effects(self):
        self.check_source('If False Then Raise("unused",,Touch());EndIf;R=1;',expected={'r':1})

    def test_invalid_raise_metadata_and_syntax(self):
        self.check_source('Try Raise("outer",,,New Array);Except R=ErrorInfo().Description;EndTry;',
                          expected={'r':'Дополнительная информация должна быть строкой'})
        self.check_source('Raise "hello","code";',error="Ожидается ';'",kind=BSLError)
