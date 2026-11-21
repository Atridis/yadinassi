"""Parser control-flow index shape checks; no retired execution engine."""
import unittest
from unittest.mock import patch
from yadinassi.syntax.parser import parse, prepare_control_flow


class PreparedControlFlowTests(unittest.TestCase):
    def test_iterative_match_rejects_empty_child_replacement_and_new_branch(self):
        body = parse('If True Then Else EndIf;')
        plan = prepare_control_flow(body)
        self.assertTrue(plan.matches(body))
        body[0].otherwise = []
        self.assertFalse(plan.matches(body))
        plan = prepare_control_flow(body)
        body[0].branches.append((body[0].branches[0][0], []))
        self.assertFalse(plan.matches(body))

    def test_matching_leaf_does_not_reenumerate_nonexistent_children(self):
        from yadinassi.syntax import parser
        body = parse('X=1;')
        plan = prepare_control_flow(body)
        with patch.object(parser, '_control_flow_children', side_effect=AssertionError('leaf traversal')):
            self.assertTrue(plan.matches(body))
        body[0] = parse('X=2;')[0]
        self.assertFalse(plan.matches(body))

    def test_matching_preserves_depth_first_container_read_order(self):
        from yadinassi.syntax import parser
        body = parse('If True Then While False Do EndDo; Else For I=1 To 1 Do EndDo; EndIf; Try Except EndTry;')
        plan = prepare_control_flow(body)
        expected = [body[0], body[0].branches[0][1][0], body[0].otherwise[0], body[1]]
        observed = []
        original = parser._control_flow_children
        def record(node):
            observed.append(node)
            return original(node)
        with patch.object(parser, '_control_flow_children', side_effect=record):
            self.assertTrue(plan.matches(body))
        self.assertEqual([id(node) for node in observed], [id(node) for node in expected])
