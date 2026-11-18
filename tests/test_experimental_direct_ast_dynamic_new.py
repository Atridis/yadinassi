"""Dynamic construction uses the same finite boundary, never an evaluator."""
import test_experimental_direct_ast_externals as external_cases

class DynamicNewTests(external_cases.DirectASTExternalTests):
    def test_dynamic_new_expression_order_and_results(self):
        for source in (
            'A=New("Array");A.Add(3);R=A[0];A=0;',
            'Args=New Array;Args.Add("N");Args.Add(7);S=New("Structure",Args);R=S.N;S=0;Args=0;',
            'R=New("DoesNotExist",Touch());',
            'R=New(Touch(),Touch());',
            'R=New(Type("Number"),Touch());',
        ):
            with self.subTest(source=source):self.paired(source)
