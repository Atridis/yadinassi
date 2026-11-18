"""Extended Raise evaluates description then optional values through canonical errors."""
import test_experimental_direct_ast_externals as external_cases

class RaiseTests(external_cases.DirectASTExternalTests):
    def test_extended_raise_metadata_and_order(self):
        for source in (
            'Try Raise "hello","code",,"info";Except R=ErrorInfo().Description;C=ErrorInfo().Code;A=ErrorInfo().AdditionalInformation;EndTry;',
            'Try Raise Touch(),Touch();Except R=ErrorDescription();EndTry;',
            'If False Then Raise "unused",Touch();EndIf;R=1;',
            'Try Raise "outer",,,New Array;Except R=ErrorDescription();EndTry;',
        ):
            with self.subTest(source=source):self.paired(source)
