"""Omitted slots are validated at the reached call before argument effects."""
import unittest
from yadinassi.types.errors import BSLError
from test_experimental_direct_ast_externals import DirectSourceAssertions

class OmissionTests(DirectSourceAssertions,unittest.TestCase):
    def test_omitted_slots_and_unreachable_calls(self):
        for source, checks in (
            ('R=1;If False Then A=New Array(,Touch());EndIf;', {'expected': {'r': 1}}),
            ('R=1;If False Then A=New Structure(,Touch());EndIf;', {'expected': {'r': 1}}),
            ('A=New Array(,Touch());', dict(error='Пропуск аргументов', touches=0)),
            ('A=New Map(,Touch());', dict(error='Пропуск аргументов', touches=0)),
            ('A=New Structure(,Touch());', dict(error='Пропуск аргументов', touches=0)),
            ('A=New Array;A.Insert(Touch(),);', dict(error='Пропуск аргументов', touches=0)),
            ('A=New Array;A.Set(,Touch());', dict(error='Пропуск аргументов', touches=0)),
            ('A=New Array;A.Add(,Touch());', dict(error='Пропуск аргументов', touches=0)),
            ('New Array().Insert(Touch(),);', dict(error='Недопустимое обращение', touches=0, kind=BSLError)),
            ('R=Touch(,Touch());', dict(error='Пропуск аргументов', touches=0)),
            ('R=StrFindByRegularExpression("ab","a",,,).Value;', {'expected': {'r': 'a'}}),
            ('R=New NumberQualifiers(,,);', dict(error='Пропуск аргументов', touches=0)),
        ):
            with self.subTest(source=source):self.check_source(source,**checks)
