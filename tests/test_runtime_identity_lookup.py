"""Exact type/owned identity lookups must not introduce host hooks or forgery."""
import unittest
import weakref
from decimal import Decimal
from unittest.mock import patch
from yadinassi.execution import owned_syntax as owned
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
from yadinassi import Interpreter
from yadinassi.types.type_values import type_of
from yadinassi.types.values import BSLType, BSLArray
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.collections.value_trees import BSLValueTree


class RuntimeIdentityLookupTests(unittest.TestCase):
    def test_static_and_dynamic_type_results_remain_exact(self):
        cases = [(None, BSLType.UNDEFINED), (True, BSLType.BOOLEAN),
                 (Decimal(1), BSLType.NUMBER), ('x', BSLType.STRING),
                 (BSLArray(), BSLType.ARRAY), (BSLValueTable(), BSLType.VALUE_TABLE),
                 (BSLValueTree(), BSLType.VALUE_TREE)]
        for value, expected in cases:
            with self.subTest(expected=expected): self.assertIs(type_of(value), expected)

    def test_every_static_type_matches_original_first_identity_scan(self):
        from yadinassi.types.type_values import _VALUE_TYPES
        for cls, _, _ in _VALUE_TYPES:
            with self.subTest(cls=cls.__name__):
                # Uninitialized instances are enough: static type reflection must
                # not read payloads or invoke constructor/descriptor effects.
                try: value = object.__new__(cls)
                except TypeError: value = cls()
                expected = next(kind for exact, kind, _ in _VALUE_TYPES if type(value) is exact)
                self.assertIs(type_of(value), expected)

    def test_foreign_type_and_subclass_reject_without_metaclass_hooks(self):
        class Meta(type):
            def __hash__(cls): raise AssertionError('metaclass hash')
            def __eq__(cls, other): raise AssertionError('metaclass equality')
        class Foreign(metaclass=Meta): pass
        class SubArray(BSLArray, metaclass=Meta): pass
        for value in (Foreign(), SubArray()):
            with self.assertRaises(TypeError): type_of(value)

    def test_private_kind_without_live_registration_is_not_owned(self):
        vm = Interpreter(); self.addCleanup(vm.close)
        node = parse('x=1;')[0]
        engine = vm._compiled(); engine.prepare([node])
        view = engine._owned.existing(node)
        self.assertIs(owned.syntax_kind(view), ast.Assign)
        fake = object.__new__(type(view))
        self.assertIs(owned.syntax_kind(fake), type(fake))
        self.assertFalse(owned.is_owned(fake))
        with patch.dict(owned._ORIGINS, {id(fake): weakref.ref(view)}):
            self.assertIs(owned.syntax_kind(fake), type(fake))
            self.assertIsNone(owned.owned_provenance(fake))

    def test_lost_registration_cannot_reuse_known_private_kind(self):
        vm = Interpreter(); self.addCleanup(vm.close)
        node = parse('x=1;')[0]; engine = vm._compiled(); engine.prepare([node])
        view = engine._owned.existing(node)
        with patch.dict(owned._ORIGINS, {}, clear=True):
            self.assertIs(owned.syntax_kind(view), type(view))
            self.assertFalse(owned.is_owned(view))
