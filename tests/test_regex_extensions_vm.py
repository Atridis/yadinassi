"""Local bounded VM contract pending real native extensions measurement."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import regex_functions as api, regex_parser as limits
from yadinassi.regex_parser import RegexLimitError

class RegexExtensionsVMTests(unittest.TestCase):
    def groups(self,result):return [(g._value,int(g._position),int(g._length)) for g in result.get_groups().items]
    def test_leading_case_flag(self):self.assertTrue(api.str_like('AbC','(?i)abc'))
    def test_scoped_flags_restore(self):
        self.assertTrue(api.str_like('AbC','(?i:a)b(?i:c)'));self.assertFalse(api.str_like('ABC','(?i:a)b(?i:c)'))
    def test_scoped_disable_overrides_leading(self):
        self.assertTrue(api.str_like('Ab','(?i)a(?-i:b)'));self.assertFalse(api.str_like('AB','(?i)a(?-i:b)'))
    def test_leading_disable_overrides_external_argument(self):self.assertFalse(api.str_like('A','(?-i)a',True))
    def test_scope_reenable_nested_under_disable(self):self.assertTrue(api.str_like('aBc','(?i)(?-i:a(?i:b)c)'))
    def test_multiline_and_dotall(self):self.assertEqual(api.str_find('x\na\nb','(?ms)^a.b$')._value,'a\nb')
    def test_scoped_dotall_restore(self):
        self.assertTrue(api.str_like('\n\n','(?s:.)(?s:.)'));self.assertFalse(api.str_like('\n\n','(?s:.).'))
    def test_flagged_character_class(self):self.assertTrue(api.str_like('AB','(?i:[a-z]+)'))
    def test_leading_flags_cover_alternation(self):self.assertTrue(api.str_like('B','(?i)a|b'))
    def test_positive_lookahead_preserves_capture_but_not_position(self):
        r=api.str_find('ab','(?=(a))a');self.assertEqual((r._value,int(r._position)),('a',1));self.assertEqual(self.groups(r),[('a',1,1)])
    def test_negative_lookahead_discards_captures(self):
        r=api.str_find('b','(?!(a))b');self.assertEqual(r._value,'b');self.assertEqual(self.groups(r),[('',0,0)])
    def test_assertion_capture_escape_is_explicitly_closed(self):
        with self.assertRaises(ValueError):api.str_like('aab',r'(?=(a|aa))\1b')
    def test_alternative_does_not_bypass_closed_capture_escape(self):
        with self.assertRaises(ValueError):api.str_like('aab',r'(?=(a|aa))\1b|aab')
    def test_local_capture_reference_inside_assertion_is_retained(self):
        self.assertTrue(api.str_like('aa',r'(?=(a)\1)aa'))
        self.assertTrue(api.str_like('aa',r'(a)(?=\1)\1'))
    def test_nested_lookahead_uses_iterative_frames(self):self.assertTrue(api.str_like('a','(?='*20+'a'+')'*20+'a'))
    def test_negative_waits_for_all_inner_alternatives(self):
        self.assertFalse(api.str_like('b','(?!a|b)b'));self.assertTrue(api.str_like('c','(?!a|b)c'))
    def test_inner_failure_restores_outer_captures(self):
        r=api.str_find('ab',r'(a)(?:(?=(x))x|b)');self.assertEqual(self.groups(r),[('a',1,1),('',0,0)])
    def test_nested_negative_and_positive(self):
        self.assertTrue(api.str_like('a','(?!(?!a))a'));self.assertFalse(api.str_like('b','(?!(?!a))b'))
    def test_backreference_consumes_original_capture(self):self.assertEqual(api.str_find('xx abab yy',r'(ab)\1')._value,'abab')
    def test_backreference_case_flag(self):self.assertTrue(api.str_like('aA',r'(?i)(a)\1'))
    def test_backreference_uses_call_site_flag(self):
        self.assertFalse(api.str_like('aA',r'(?i)(a)(?-i:\1)'));self.assertTrue(api.str_like('aA',r'(a)(?i:\1)'))
    def test_unmatched_reference_fails(self):self.assertFalse(api.str_like('b',r'(a)?b\1'))
    def test_empty_captured_reference_succeeds(self):self.assertTrue(api.str_like('',r'()\1'))
    def test_multidigit_reference(self):self.assertTrue(api.str_like('aaaaaaaaaaa','(a)'*10+r'\10'))
    def test_zero_width_find_all_advances(self):
        results=api.str_find_all('aa','(?=(a))').items;self.assertEqual(len(results),2);self.assertEqual([int(r._position) for r in results],[1,2])
    def test_replace_uses_assertion_capture(self):self.assertEqual(api.str_replace('aa','(?=(a))','<$1>'),'<a>a<a>a')
    def test_nullable_assertion_loop_terminates(self):self.assertTrue(api.str_like('a','(?:(?=a))*a'))
    def test_shared_work_budget_not_reset_by_assertions(self):
        with patch.object(limits,'MAX_WORK',150),self.assertRaises(RegexLimitError):api.str_find('a'*60,'(?=a*a*a*b)a')
    def test_shared_state_budget_includes_assertion_callers(self):
        with patch.object(limits,'MAX_STATES',2),self.assertRaises(RegexLimitError):api.str_like('a','(?=(?=(?=a)))a')
    def test_host_re_not_used_for_matching(self):
        with patch('re.compile',side_effect=AssertionError('host regex forbidden')),patch('re.search',side_effect=AssertionError('host regex forbidden')):
            self.assertTrue(api.str_like('aA',r'(?i)(a)(?=a)\1'))
    def test_matching_function_does_not_recurse(self):
        source=Path(api.__file__).with_name('regex_vm.py').read_text(encoding='utf-8');tree=ast.parse(source);run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='run' for n in ast.walk(run)))
