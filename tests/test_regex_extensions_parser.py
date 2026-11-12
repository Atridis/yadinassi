"""Authored grammar/limit tests; these are not native observation fixtures."""
import unittest
from unittest.mock import patch
from yadinassi.regex_parser import Parser, Budget, RegexLimitError
from yadinassi.regex_vm import Program

class RegexExtensionsParserTests(unittest.TestCase):
    def parse(self, pattern): return Parser(pattern,Budget()).parse()
    def test_leading_flags_wrap_all_alternatives(self):
        n,g=self.parse('(?im)a|b');self.assertEqual(n[:3],('flags',3,0));self.assertEqual(g,0)
    def test_leading_disable_and_sequential_override(self):
        n,_=self.parse('(?i)(?-i)(?s)a');self.assertEqual(n[:3],('flags',4,1))
    def test_scoped_flags_do_not_capture(self):
        n,g=self.parse('(?i:a)(?-m:b)(c)');self.assertEqual(g,1);self.assertEqual(n[1][0][:3],('flags',1,0))
    def test_lookahead_does_not_capture_itself(self):
        n,g=self.parse('(?=(a))(?!(b))');self.assertEqual(g,2);self.assertEqual(n[1][0][:2],('look',True));self.assertEqual(n[1][1][:2],('look',False))
    def test_numeric_reference_requires_prior_closed_group(self):
        n,g=self.parse(r'(a)\1');self.assertEqual(n[1][1],('backref',1));self.assertEqual(g,1)
    def test_ten_is_group_ten_not_group_one_plus_literal(self):
        n,g=self.parse('(a)'*10+r'\10');self.assertEqual(g,10);self.assertEqual(n[1][-1],('backref',10))
    def test_self_forward_unknown_and_octal_references_refuse(self):
        for pattern in (r'\1(a)',r'(\1a)',r'(a)\2',r'(a)\10',r'\0',r'[\1]'):
            with self.subTest(pattern=pattern),self.assertRaises(ValueError):self.parse(pattern)
    def test_unsupported_and_ambiguous_flags_refuse(self):
        for pattern in ('(?x)a','(?i-i)a','(?ii)a','(?-)a','(?i-)a','(?i--m)a','a(?i)b','(?i'):
            with self.subTest(pattern=pattern),self.assertRaises(ValueError):self.parse(pattern)
    def test_unknown_lookaround_named_and_conditional_groups_refuse(self):
        for pattern in ('(?<=a)','(?<!a)','(?P<x>a)','(?<x>a)','(?>a)','(?(1)a|b)'):
            with self.subTest(pattern=pattern),self.assertRaises(ValueError):self.parse(pattern)
    def test_direct_assertion_quantification_refuses(self):
        for pattern in ('(?=a)*','(?!a)+','(?=a){2}'):
            with self.assertRaises(ValueError):self.parse(pattern)
    def test_nested_assertion_depth_remains_bounded(self):
        with self.assertRaises(RegexLimitError):self.parse('(?='*34+'a'+')'*34)
    def test_subprogram_code_uses_shared_limit(self):
        b=Budget();n,g=Parser('(?=(a|b|c))x',b).parse()
        with patch('yadinassi.regex_parser.MAX_CODE',4),self.assertRaises(RegexLimitError):Program(n,g,b)
