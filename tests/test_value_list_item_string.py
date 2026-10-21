"""Scalar item text from authenticated owner commit 87723a25.

These expectations cover item conversions only, not the separate list cache.
Host/type/resource tests describe Yadinassi boundaries, not native 1C limits.
The original integration source and output are never rewritten by these tests.
"""

from decimal import Decimal as D, localcontext
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter, value_lists
from yadinassi.dates import BSLDate, literal_date
from yadinassi.maps import BSLMap
from yadinassi.structures import BSLStructure
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, BSLType, NULL, to_string


ROOT = Path(__file__).resolve().parents[1]


class ValueListItemStringTests(unittest.TestCase):
    def test_native_scalar_fallbacks_are_exact(self):
        cases = (
            (None, "<Пустое значение>"),
            (NULL, "<Пустое значение>"),
            (D(0), "0"),
            (D("-7.25"), "-7,25"),
            (D("1234.5"), "1\u00a0234,5"),
            (False, "Нет"),
            (True, "Да"),
            ("", ""),
            (" ", " "),
            ("Я😀", "Я😀"),
            ("a; b", "a; b"),
            ("a\nb", "a\nb"),
            (r"a\nb", r"a\nb"),
            (BSLDate(0), "01.01.0001 0:00:00"),
            (literal_date("20240229131415"), "29.02.2024 13:14:15"),
        )
        owner = BSLValueList()
        for value, expected in cases:
            with self.subTest(value=value):
                item = owner.add(value)
                self.assertEqual(str(item), expected)
                self.assertEqual(item.presentation, "")
                if value is None or value is NULL:
                    self.assertEqual(to_string(value), "")
                else:
                    self.assertEqual(to_string(value), expected)
        self.assertEqual(str(owner.add()), "<Пустое значение>")

    def test_native_live_value_label_and_check_changes(self):
        owner = BSLValueList()
        item = owner.add(D(7))
        steps = (
            (None, None, "7"),
            ("Value", D("-7.25"), "-7,25"),
            ("Presentation", "fixed; Я😀", "fixed; Я😀"),
            ("Value", D("1234.5"), "fixed; Я😀"),
            ("Check", True, "fixed; Я😀"),
            ("Check", False, "fixed; Я😀"),
            ("Presentation", " ", " "),
            ("Presentation", "", "1\u00a0234,5"),
            ("Value", None, "<Пустое значение>"),
        )
        for field, value, expected in steps:
            if field is not None:
                item.set_member(field, value)
            before = item.__dict__.copy()
            owner_before = owner.__dict__.copy()
            owner_items, owner_ids = tuple(owner.items), dict(owner._by_id)
            with self.subTest(field=field, value=value):
                self.assertEqual(str(item), expected)
                self.assertEqual(str(item), expected)
                self.assertEqual(item.__dict__, before)
                self.assertEqual(owner.__dict__, owner_before)
                self.assertIs(owner.items, owner_before["items"])
                self.assertIs(owner._by_id, owner_before["_by_id"])
                self.assertEqual(tuple(owner.items), owner_items)
                self.assertEqual(owner._by_id, owner_ids)
                self.assertIs(item._owner_ref(), owner)
                self.assertIs(owner.find_by_id(D(0)), item)
                self.assertEqual(item.get_id(), D(0))

    def test_explicit_labels_do_not_call_scalar_or_object_renderers(self):
        owner = BSLValueList()
        values = (None, NULL, False, D("1e1000000000"), "", BSLDate(0),
                  BSLArray(), BSLMap(), BSLStructure(), BSLType.STRING,
                  BSLValueList())
        for value in values:
            for presentation in (" ", "fixed; Я😀", "a\nb", r"a\nb"):
                item = owner.add(value, presentation)
                with self.subTest(kind=type(value), presentation=presentation):
                    with patch.object(value_lists, "to_string",
                                      side_effect=AssertionError("value renderer called")):
                        self.assertEqual(str(item), presentation)
                    self.assertIs(item.value, value)

    def test_unobserved_objects_reject_without_hooks_or_traversal(self):
        class Hostile:
            def __str__(self):
                raise AssertionError("host string")
            def __bool__(self):
                raise AssertionError("host truth")
            def __eq__(self, other):
                raise AssertionError("host equality")
            def __len__(self):
                raise AssertionError("host length")

        class HostMeta(type):
            def __eq__(self, other):
                raise AssertionError("host type equality")
            def __hash__(self):
                raise AssertionError("host type hash")

        class Host(metaclass=HostMeta):
            __str__ = Hostile.__str__

        class HostString(str):
            __str__ = Hostile.__str__
            __bool__ = Hostile.__bool__
            __len__ = Hostile.__len__

        class HostDecimal(D):
            __str__ = Hostile.__str__
            def is_finite(self):
                raise AssertionError("host decimal")

        class HostDate(BSLDate):
            __str__ = Hostile.__str__

        class HostArray(BSLArray):
            __str__ = Hostile.__str__

        owner = BSLValueList()
        cycle = BSLArray()
        cycle.items.append(cycle)
        values = (Hostile(), Host(), HostString("x"), HostDecimal(1),
                  HostDate(0), HostArray(), object(), 1, 1.5, cycle,
                  BSLStructure(), BSLMap(), BSLType.STRING, owner)
        with patch.object(value_lists, "to_string",
                          side_effect=AssertionError("unobserved formatter")):
            for value in values:
                item = BSLValueListItem(owner, 0, value)
                with self.subTest(kind=type(value)):
                    with self.assertRaisesRegex(ValueError, "пока не поддерживается"):
                        str(item)
                    item.presentation = "safe"
                    self.assertEqual(str(item), "safe")
            for presentation in (Hostile(), HostString(""), HostString("label"),
                                 None, D(7)):
                item = BSLValueListItem(owner, 0, D(7), presentation)
                with self.assertRaisesRegex(ValueError, "пока не поддерживается"):
                    str(item)

    def test_rendered_text_budget_covers_fallbacks_and_labels(self):
        owner = BSLValueList()
        for value, label, expected in (
                (None, "", "<Пустое значение>"),
                (NULL, "", "<Пустое значение>"),
                (False, "", "Нет"),
                (D("1234.5"), "", "1\u00a0234,5"),
                ("Я😀\n", "", "Я😀\n"),
                (BSLDate(0), "", "01.01.0001 0:00:00"),
                (BSLArray(), "label", "label")):
            item = owner.add(value, label)
            before = item.__dict__.copy()
            with self.subTest(value=value, label=label):
                with patch.object(value_lists, "_MAX_TEXT", len(expected)):
                    self.assertEqual(str(item), expected)
                with patch.object(value_lists, "_MAX_TEXT", len(expected) - 1):
                    with self.assertRaisesRegex(ValueError, "предел ресурсов"):
                        str(item)
                self.assertEqual(item.__dict__, before)
        with patch.object(value_lists, "_MAX_TEXT", 0):
            self.assertEqual(str(owner.add("")), "")

    def test_numeric_and_date_rejections_preserve_values_and_labels_bypass_them(self):
        owner = BSLValueList()
        for value in (D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"),
                      D("1" * 4097), D("1e4096"), D("1e-4097"),
                      D("1." + "0" * 324 + "1"),
                      D("0." + "0" * 324 + "5"), BSLDate(0, boundary=True)):
            item = BSLValueListItem(owner, 0, value)
            with self.subTest(kind=type(value)):
                with self.assertRaises(ValueError):
                    str(item)
                self.assertIs(item.value, value)
                item.presentation = "safe"
                self.assertEqual(str(item), "safe")

    def test_supported_numeric_limits_and_context_are_preserved(self):
        owner = BSLValueList()
        cases = (
            (D("1e4095"), "1" + "\u00a0000" * 1365),
            (D("1" * 4096), "1" + "\u00a0111" * 1365),
            (D("1e-4096"), "0"),
            (D("0e1000000000"), "0"),
            (D("-0e-1000000000"), "0"),
            (D("0." + "1" * 324 + "6"), "0," + "1" * 323 + "2"),
            (D("1234." + "0" * 4092), "1\u00a0234"),
        )
        with localcontext() as context:
            context.prec = 1
            context.Emin, context.Emax = -2, 2
            for signal in context.traps:
                context.traps[signal] = True
            context.clear_flags()
            for value, expected in cases:
                item = owner.add(value)
                before = value.as_tuple()
                self.assertEqual(str(item), expected)
                self.assertIs(item.value, value)
                self.assertEqual(value.as_tuple(), before)
            self.assertFalse(any(context.flags.values()))

    def test_huge_numeric_exponents_reject_without_expansion(self):
        program = """
from decimal import Decimal
from yadinassi.value_lists import BSLValueList
owner = BSLValueList()
for spelling in ('1e1000000000', '-1e1000000000', '1e-1000000000'):
    item = owner.add(Decimal(spelling))
    try:
        str(item)
    except ValueError as error:
        assert 'предел ресурсов' in str(error)
    else:
        raise AssertionError('unbounded number accepted')
    item.presentation = 'safe'
    assert str(item) == 'safe'
print('guarded')
"""
        completed = subprocess.run([sys.executable, "-c", program], cwd=ROOT,
                                   capture_output=True, text=True, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "guarded\n")
        self.assertEqual(completed.stderr, "")

    def test_bilingual_string_dispatch_and_catchable_object_boundary(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute('owner = New ValueList; item = owner.Add(); '
                   'Message(String(item)); item.Значение = 1234.5; '
                   'Сообщить(Строка(item)); item.Представление = " "; '
                   'Message(String(item)); item.Presentation = ""; '
                   'item.Value = New Array; saved = "unchanged";')
        self.assertEqual(output, ["<Пустое значение>", "1\u00a0234,5", " "])
        with self.assertRaises(BSLError):
            vm.execute("saved = String(item);")
        self.assertEqual(vm.execute("saved"), "unchanged")
        vm.execute('item.Presentation = "array label"; Message(String(item));')
        self.assertEqual(output[-1], "array label")
        self.assertEqual(vm.execute("item.GetID()"), D(0))
        self.assertEqual(vm.execute("owner.Count()"), D(1))


if __name__ == "__main__":
    unittest.main()
