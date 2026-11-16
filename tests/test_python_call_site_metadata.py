import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse_expression
from yadinassi.python_translation_expressions import prepare_expressions, UnsupportedExpression


class CallSiteMetadataTests(unittest.TestCase):
    def test_owned_call_shape_and_operand_charge(self):
        vm=Interpreter();engine=vm._compiled()
        node=parse_expression('(Host)(1,)')
        lease=engine.prepare_transient([node],expression_entry=True)
        try:
            view=engine._owned.existing(node)
            plan=prepare_expressions([view],max_source_bytes=100000,owned_leaves=True)
            site=plan.call_sites[id(view)]
            self.assertIs(site.node,view)
            self.assertIs(site.callee,view.callee.expression)
            self.assertEqual((site.callee_kind,site.name,site.has_omissions),('name','Host',True))
            with self.assertRaises(UnsupportedExpression):
                prepare_expressions([view],max_source_bytes=100000,owned_leaves=True,max_bindings=plan.binding_count-1)
            self.assertIsNone(plan.bind(vm,guard=lambda n:None,access=None).call_site(node))
        finally:lease.close()

    def test_mutable_standalone_plan_has_no_frozen_call_shape(self):
        node=parse_expression('Host(1)')
        plan=prepare_expressions([node])
        self.assertFalse(plan.call_sites)

    def test_retained_unit_prunes_unrelated_call_site(self):
        from yadinassi.syntax.parser import parse
        vm=Interpreter();engine=vm._compiled()
        program=parse('Function F() Return Host(); EndFunction\nOther();')
        engine.prepare(program)
        units={id(unit):unit for _,unit in engine._python_units.values()}
        unit=next(u for u in units.values() if len(u.expressions.call_sites)==2)
        keep=next(s for s in unit.expressions.call_sites.values() if s.name=='Host')
        retained=unit.retained({id(keep.node)})
        self.assertEqual(list(retained.expressions.call_sites),[id(keep.node)])
        self.assertIs(retained.expressions.call_sites[id(keep.node)],keep)
        self.assertEqual(retained.binding_count,unit.binding_count)
