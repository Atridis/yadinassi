import unittest
from yadinassi import python_direct_detached_metadata as metadata

class MetadataDispatchTests(unittest.TestCase):
    def test_only_three_exact_receiver_classes_are_owned(self):
        for cls in (metadata._ROOT,metadata._OBJECT,metadata._COLLECTION):
            self.assertTrue(metadata._owns(object.__new__(cls)))
            class Child(cls):pass
            self.assertFalse(metadata._owns(object.__new__(Child)))
        for value in (None,True,1,'metadata',[],{},object()):
            self.assertFalse(metadata._owns(value))

    def test_no_user_equality_or_hash_hook(self):
        class Meta(type):
            def __eq__(self,other):raise AssertionError('class equality')
            def __hash__(self):raise AssertionError('class hash')
        class Value(metaclass=Meta):
            def __eq__(self,other):raise AssertionError('instance equality')
        self.assertFalse(metadata._owns(Value()))
