"""Dynamic construction uses the same finite boundary, never an evaluator."""
import unittest
from test_experimental_direct_ast_externals import DirectSourceAssertions

class DynamicNewTests(DirectSourceAssertions,unittest.TestCase):
    def test_dynamic_new_expression_order_and_results(self):
        for source, checks in (
            ('A=New("Array");A.Add(3);R=A[0];A=0;', {'expected': {'a': 0, 'r': 3}}),
            ('Args=New Array;Args.Add("N");Args.Add(7);S=New("Structure",Args);R=S.N;S=0;Args=0;', {'expected': {'args': 0, 'r': 7, 's': 0}}),
            ('R=New("DoesNotExist",Touch());', dict(error='DoesNotExist', touches=1)),
            ('R=New(Touch(),Touch());', dict(error='ожидается имя типа', touches=2)),
            ('R=New(Type("Number"),Touch());', dict(error='не имеет direct конструктора', touches=1)),
        ):
            with self.subTest(source=source):self.check_source(source,**checks)
