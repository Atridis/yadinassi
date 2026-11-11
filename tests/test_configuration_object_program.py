"""Closed AST projections, not source rewriting or native Object compatibility."""
import unittest
from yadinassi.form_program import compile_form_module
from yadinassi.syntax import ast

class ObjectProgramTests(unittest.TestCase):
    def compile(self, body, side='AtServer'):
        return compile_form_module('&'+side+'\nProcedure Run()\n'+body+'\nEndProcedure',
                                   object_fields=('Code', 'Description'))

    def test_object_members_lower_to_separate_scalar_names(self):
        node = self.compile('Object.Description = Object.Code;').server.program()[0].body[0]
        self.assertEqual(node.target.name, 'ObjectField2')
        self.assertEqual(node.value.name, 'ObjectField1')

    def test_if_tuple_branches_are_lowered_and_cloned(self):
        program = self.compile('If Object.Code = "x" Then Object.Description = "y"; EndIf;')
        branch = program.server.program()[0].body[0].branches[0]
        self.assertEqual(branch[0].left.name, 'ObjectField1')
        self.assertEqual(branch[1][0].target.name, 'ObjectField2')
        branch[1][0].target.name = 'changed'
        self.assertEqual(program.server.program()[0].body[0].branches[0][1][0].target.name, 'ObjectField2')

    def test_contextless_object_access_rejected(self):
        with self.assertRaises(ValueError): self.compile('Object.Code = "x";', 'AtServerNoContext')
        for side, call in [('AtClient', 'WriteObject();'), ('AtServerNoContext', 'WriteObject();'),
                           ('AtServer', 'WriteObject(1);')]:
            with self.subTest(side=side), self.assertRaises(ValueError): self.compile(call, side)

    def test_object_receiver_cannot_escape(self):
        for body in ('X = Object;', 'X = Object.Unknown;', 'X = Object.Description.Length;',
                     'X = Object["Code"];', 'X = Object.Description[0];'):
            with self.subTest(body=body), self.assertRaises(ValueError): self.compile(body)

    def test_reserved_declarations_and_direct_private_names_rejected(self):
        for body in ('Var Object;', 'Var ObjectField1;', 'ObjectField1 = "x";',
                     'For Object = 1 To 2 Do EndDo;'):
            with self.subTest(body=body), self.assertRaises(ValueError): self.compile(body)
        with self.assertRaises(ValueError):
            compile_form_module('&AtClient\nProcedure Run(Object)\nEndProcedure', object_fields=('Code',))

    def test_normal_sources_and_strings_are_not_rewritten(self):
        program = self.compile('X = "Object.Code";')
        self.assertEqual(program.server.program()[0].body[0].value.value, 'Object.Code')
        ordinary = compile_form_module('&AtServer\nProcedure Run()\nObject = 1;\nEndProcedure')
        self.assertEqual(ordinary.server.program()[0].body[0].target.name, 'Object')
