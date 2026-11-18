"""Omitted slots are validated at the reached call before argument effects."""
import test_experimental_direct_ast_externals as external_cases

class OmissionTests(external_cases.DirectASTExternalTests):
    def test_omitted_slots_and_unreachable_calls(self):
        for source in (
            'R=1;If False Then A=New Array(,Touch());EndIf;',
            'R=1;If False Then A=New Structure(,Touch());EndIf;',
            'A=New Array(,Touch());',
            'A=New Map(,Touch());',
            'A=New Structure(,Touch());',
            'A=New Array;A.Insert(Touch(),);',
            'A=New Array;A.Set(,Touch());',
            'A=New Array;A.Add(,Touch());',
            'New Array().Insert(Touch(),);',
            'R=Touch(,Touch());',
            'R=StrFindByRegularExpression("ab","a",,,).Value;',
            'R=New NumberQualifiers(,,);',
        ):
            with self.subTest(source=source):self.paired(source)
