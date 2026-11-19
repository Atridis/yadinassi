import unittest
from unittest.mock import patch
from yadinassi.native_bare_collections import BareArray, BareStructure
from yadinassi.native_bare_structure_ops import bare_fill_property_values


class RecoveredBareFill(unittest.TestCase):
    def test_basic_preserves_keys_identity_missing_and_none(self):
        target=BareStructure('Keep,Copy,Null',1,2,3)
        payload=BareArray();source=BareStructure('Copy,Null,Extra',payload,None,9)
        alias=target;original=dict(source)
        self.assertIsNone(bare_fill_property_values(target,source))
        self.assertIs(target,alias);self.assertEqual(list(dict.keys(target)),['keep','copy','null'])
        self.assertEqual(target.get('Keep'),1);self.assertIs(target.get('Copy'),payload)
        self.assertIsNone(target.get('Null'));self.assertEqual(dict(source),original)
        target.get('Copy').add(7);self.assertEqual(source.get('Copy').get(0),7)
    def test_two_argument_path_does_not_parse_filters(self):
        target=BareStructure('A',1);source=BareStructure('A',2)
        with patch('yadinassi.native_bare_structure_ops._filter_names',side_effect=AssertionError('unexpected filter parser')):
            bare_fill_property_values(target,source)
            bare_fill_property_values(target,source,None,None)
        self.assertEqual(target.get('A'),2)
    def test_include_normalizes_deduplicates_and_skips_unknown(self):
        target=BareStructure('A,B,Keep',1,2,3);source=BareStructure('A,B,Extra',8,9,10)
        bare_fill_property_values(target,source,' A, a, UNKNOWN,Extra, , ')
        self.assertEqual(dict(target),{'a':8,'b':2,'keep':3})
    def test_exclude_wins_with_include(self):
        target=BareStructure('A,B,C',1,2,3);source=BareStructure('A,B,C',8,9,None)
        bare_fill_property_values(target,source,'a,B,c',' B,unknown ')
        self.assertEqual(dict(target),{'a':8,'b':2,'c':None})
    def test_exclude_without_include(self):
        target=BareStructure('A,B',1,2);source=BareStructure('A,B',8,9)
        bare_fill_property_values(target,source,None,'a')
        self.assertEqual(dict(target),{'a':1,'b':9})
    def test_empty_include_and_empty_exclude_are_distinct(self):
        target=BareStructure('A',1);source=BareStructure('A',8)
        bare_fill_property_values(target,source,' , ')
        self.assertEqual(target.get('A'),1)
        bare_fill_property_values(target,source,None,' , ')
        self.assertEqual(target.get('A'),8)
    def test_invalid_filters_do_not_partially_mutate(self):
        for include,exclude in ((1,None),(None,False),('a',[])):
            target=BareStructure('A',1);source=BareStructure('A',8)
            with self.assertRaises(TypeError):bare_fill_property_values(target,source,include,exclude)
            self.assertEqual(dict(target),{'a':1})
    def test_exact_bare_operands_only(self):
        for target,source in (({},BareStructure()),(BareStructure(),{}),(None,BareStructure()),(BareStructure(),1)):
            with self.assertRaises(NotImplementedError):bare_fill_property_values(target,source)
    def test_self_fill_and_empty_structures(self):
        target=BareStructure('A,B',1,None)
        bare_fill_property_values(target,target,'A,B','b')
        self.assertEqual(dict(target),{'a':1,'b':None})
        bare_fill_property_values(BareStructure(),target)
        bare_fill_property_values(target,BareStructure())
        self.assertEqual(dict(target),{'a':1,'b':None})

if __name__=='__main__':unittest.main()
