"""Owning profiles use direct AST code, preserving original public scenarios."""
import unittest
from unittest.mock import patch

class OwningProfilesTests(unittest.TestCase):
    def test_posting_style_unknown_host_argument_never_leaks_sentinel(self):
        from yadinassi.execution.codegen.direct_emitter import compile_owned
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext
        from yadinassi.syntax.parser import parse
        from yadinassi.types.errors import BSLRuntimeError
        text='Procedure Event() Capture(Missing);EndProcedure Event();'
        plan=compile_owned(parse(text),source_text=text,source_name='<host-binding>')
        seen=[];context=BoundaryContext(services={'capture':seen.append})
        # An undefined argument is not converted into a host call.
        with self.assertRaises(BSLRuntimeError):plan.run({},context=context)
        self.assertEqual(seen,[])
