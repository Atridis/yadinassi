"""Short-circuit structural comparison retains exact types and live field reads."""
from dataclasses import dataclass, fields, is_dataclass
import unittest
from uuid import UUID
from yadinassi.configuration.configuration_inventory_enums import _same


def reference(expected, actual):
    if type(expected) is not type(actual): return False
    if type(expected) is UUID:
        try: value = actual.int
        except AttributeError: return False
        return type(value) is int and expected.int == value
    if type(expected) is tuple:
        return len(expected) == len(actual) and all(reference(a,b) for a,b in zip(expected,actual))
    if is_dataclass(expected):
        try:
            return all(reference(getattr(expected,f.name),getattr(actual,f.name)) for f in fields(expected))
        except AttributeError: return False
    return expected == actual


@dataclass
class Pair:
    first: object
    second: object


class SameLoopTests(unittest.TestCase):
    def test_equal_and_changed_schema_shapes_match_reference(self):
        values = [None, False, True, 0, 1, 'x', b'x', UUID(int=1), (), (1,'x'),
                  Pair(1, Pair((UUID(int=2),), ('x',False)))]
        for left in values:
            for right in values:
                with self.subTest(left=left,right=right):
                    self.assertEqual(_same(left,right), reference(left,right))

    def test_early_difference_does_not_read_next_field(self):
        for compare in (_same, reference):
            class Traced(Pair):
                def __getattribute__(self,name):
                    if name == 'second': raise AssertionError('late field read')
                    return super().__getattribute__(name)
            self.assertFalse(compare(Traced(1,2),Traced(2,2)))

    def test_later_field_read_observes_mutation_by_earlier_comparison(self):
        for compare in (_same, reference):
            actual = Pair(None, 'old')
            class Mutator:
                def __eq__(self, other):
                    actual.second = 'new'
                    return True
            actual.first = Mutator()
            self.assertTrue(compare(Pair(Mutator(),'new'),actual))

    def test_uuid_integer_payload_must_be_exact_int_without_equality_hook(self):
        class EvilInt(int):
            def __eq__(self, other): raise AssertionError('int hook')
        forged = UUID(int=1);object.__setattr__(forged,'int',EvilInt(1))
        self.assertFalse(_same(UUID(int=1),forged))
        delattr_forged = UUID(int=1);object.__delattr__(delattr_forged,'int')
        self.assertFalse(_same(UUID(int=1),delattr_forged))

    def test_attribute_error_scope_matches_dataclass_ancestor(self):
        class Broken:
            def __eq__(self, other): raise AttributeError('payload')
        for compare in (_same,reference):
            with self.assertRaises(AttributeError): compare(Broken(),Broken())
            with self.assertRaises(AttributeError): compare((Broken(),),(Broken(),))
            self.assertFalse(compare(Pair((Broken(),),1),Pair((Broken(),),1)))
        actual = Pair(1,2);del actual.second
        self.assertFalse(_same(Pair(1,2),actual))

    def test_leaf_equality_result_is_not_forced_to_bool_at_root(self):
        sentinel = object()
        class Custom:
            def __eq__(self,other): return sentinel
        self.assertIs(_same(Custom(),Custom()),sentinel)
        self.assertTrue(_same((Custom(),),(Custom(),)))

    def test_cycle_still_terminates_with_recursion_error(self):
        left=Pair(1,None);right=Pair(1,None)
        left.second=left;right.second=right
        for compare in (_same, reference):
            with self.assertRaises(RecursionError): compare(left,right)

    def test_stop_iteration_equality_and_getattr_keep_generator_boundary(self):
        class EqualityStop:
            def __eq__(self, other): raise StopIteration('equality hook')
        class GetterStop(Pair):
            def __getattribute__(self, name):
                if name == 'first': raise StopIteration('field hook')
                return super().__getattribute__(name)

        cases = [
            (EqualityStop(), EqualityStop(), StopIteration),
            ((EqualityStop(),), (EqualityStop(),), RuntimeError),
            (Pair(EqualityStop(), 0), Pair(EqualityStop(), 0), RuntimeError),
            ((Pair(EqualityStop(), 0),), (Pair(EqualityStop(), 0),), RuntimeError),
            (GetterStop(1, 2), GetterStop(1, 2), RuntimeError),
            ((GetterStop(1, 2),), (GetterStop(1, 2),), RuntimeError),
            (Pair(GetterStop(1, 2), 0), Pair(GetterStop(1, 2), 0), RuntimeError),
        ]
        for left, right, error_type in cases:
            outcomes = []
            for compare in (reference, _same):
                with self.assertRaises(error_type) as caught:
                    compare(left, right)
                error = caught.exception
                cause = error.__cause__
                outcomes.append((type(error), error.args,
                                 type(cause), None if cause is None else cause.args))
                if error_type is RuntimeError:
                    self.assertIsInstance(cause, StopIteration)
                    self.assertTrue(error.__suppress_context__)
                    self.assertIs(error.__context__, cause)
            self.assertEqual(*outcomes)

    def test_stop_iteration_bool_is_outside_current_generator_boundary(self):
        class BoolStop:
            def __bool__(self): raise StopIteration('bool hook')
        result = BoolStop()
        class EqualityResult:
            def __eq__(self, other): return result
        for compare in (reference, _same):
            self.assertIs(compare(EqualityResult(), EqualityResult()), result)
        cases = [
            ((EqualityResult(),), (EqualityResult(),), StopIteration),
            (Pair(EqualityResult(), 0), Pair(EqualityResult(), 0), StopIteration),
            (((EqualityResult(),),), ((EqualityResult(),),), RuntimeError),
            (Pair((EqualityResult(),), 0), Pair((EqualityResult(),), 0), RuntimeError),
            ((Pair(EqualityResult(), 0),), (Pair(EqualityResult(), 0),), RuntimeError),
        ]
        for left, right, error_type in cases:
            outcomes = []
            for compare in (reference, _same):
                with self.assertRaises(error_type) as caught:
                    compare(left, right)
                error = caught.exception
                cause = error.__cause__
                outcomes.append((type(error), error.args,
                                 type(cause), None if cause is None else cause.args))
                if error_type is RuntimeError:
                    self.assertIsInstance(cause, StopIteration)
                    self.assertTrue(error.__suppress_context__)
                    self.assertIs(error.__context__, cause)
            self.assertEqual(*outcomes)
