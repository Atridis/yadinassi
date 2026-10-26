"""Local API/budget/generalization policy; observed native witnesses are separate."""
from decimal import Decimal as D, localcontext, Inexact, Rounded
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.text_documents import BSLTextDocument
from yadinassi.values import BSLArray, BSLType
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_values import type_by_name, type_of
from yadinassi.serialization import value_to_string_internal
from yadinassi.value_checks import value_is_filled
from yadinassi.xml_values import xml_string


class TextDocumentLocalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.doc = BSLTextDocument()
        self.doc.set_text('A\r\nB')

    def snapshot(self):
        return (self.doc.get_text(), self.doc.line_count(),
                [self.doc.get_line(D(i)) for i in range(1, int(self.doc.line_count()) + 1)])

    def test_aliases_dynamic_constructor_and_displays(self):
        vm = Interpreter(lambda _: None)
        for name in ('TextDocument', 'ТекстовыйДокумент', 'тЕкСтОвЫйДоКуМеНт'):
            vm.execute(f'd = New {name}();')
            self.assertIs(vm.execute('TypeOf(d)'), BSLType.TEXT_DOCUMENT)
            self.assertEqual(vm.execute('d.lInEcOuNt()'), D(0))
            self.assertEqual(vm.execute('String(d)'), 'ТекстовыйДокумент')
            self.assertEqual(vm.execute('String(TypeOf(d))'), 'Текстовый документ')
            self.assertIs(type(vm.execute(f'New("{name}")')), BSLTextDocument)
            self.assertIs(type(vm.execute(f'New(Type("{name}"))')), BSLTextDocument)
        self.assertIs(type_of(self.doc), type_by_name('TextDocument'))
        with self.assertRaises(ValueError): type_by_name('Текстовый документ')

    def test_argument_arity_and_no_implicit_text_conversion(self):
        vm = Interpreter(lambda _: None)
        vm.execute('d = New TextDocument(); d.SetText("A");')
        for code in ('New TextDocument(Undefined)', 'd.SetText()', 'd.AddLine()',
                     'd.GetLine()', 'd.LineCount(1)', 'd.Clear(1)',
                     'd.InsertLine(1)', 'd.ReplaceLine(1)', 'd.DeleteLine()',
                     'd.SetText(1)', 'd.SetText(True)', 'd.SetText(Undefined)',
                     'd.InsertLine(1, False)', 'd.ReplaceLine(1, Null)'):
            with self.subTest(code=code), self.assertRaises(BSLError): vm.execute(code)
            self.assertEqual(vm.execute('d.GetText()'), 'A')

    def test_unmeasured_indices_fail_without_mutation(self):
        before = self.snapshot()
        for index in (D(-1), D('0.1'), D('NaN'), D('Infinity'), True, 1, '1', None):
            for method, args in ((self.doc.get_line, ()), (self.doc.insert_line, ('X',)),
                                 (self.doc.replace_line, ('X',)), (self.doc.delete_line, ())):
                with self.subTest(index=index, method=method.__name__), self.assertRaises((TypeError, ValueError)):
                    method(index, *args)
                self.assertEqual(self.snapshot(), before)

    def test_unmeasured_line_delimiters_are_local_errors_not_native_claims(self):
        before = self.snapshot()
        for value in ('X\rY', 'X\r\nY', 'X\n', '\n', '\r', 'X\r'):
            for method, args in ((self.doc.add_line, ()), (self.doc.insert_line, (D(1),)),
                                 (self.doc.replace_line, (D(1),))):
                with self.subTest(value=value, method=method.__name__), self.assertRaises(ValueError):
                    method(*args, value)
                self.assertEqual(self.snapshot(), before)
        # The same delimiters are supported as exact SetText input.
        self.doc.set_text('X\r\nY\rZ\n')
        self.assertEqual(self.snapshot(), ('X\r\nY\rZ\n', D(3), ['X', 'Y', 'Z']))

    def test_local_scalar_unicode_policy_rejects_lone_surrogates_atomically(self):
        before = self.snapshot()
        for value in ('\ud800', '\udfff', 'x\ud83d\ude00'):
            with self.assertRaises(ValueError): self.doc.set_text(value)
            self.assertEqual(self.snapshot(), before)
        self.doc.set_text('Ж😀e\u0301\u2028Z')
        self.assertEqual(self.doc.line_count(), D(1))
        self.assertEqual(self.doc.get_line(D(1)), 'Ж😀e\u0301\u2028Z')

    def test_new_crlf_edit_seams_are_rejected_without_collapsing_empty_lines(self):
        # These shapes are not in native44. Fail closed rather than infer the
        # platform's line-boundary handling from the raw concatenated text.
        for initial, method, args in (
                ('A\r', 'add_line', ('',)),
                ('A\rB', 'insert_line', (D(2), '')),
                ('A\rB', 'replace_line', (D(2), '')),
                ('A\rX\n\nB', 'delete_line', (D(2),))):
            self.doc.set_text(initial)
            before = self.snapshot()
            with self.subTest(method=method), self.assertRaises(ValueError):
                getattr(self.doc, method)(*args)
            self.assertEqual(self.snapshot(), before)
        # Keeping an already present CRLF is not the unmeasured seam case.
        self.doc.set_text('A\r\n')
        self.doc.add_line('')
        self.assertEqual(self.snapshot(), ('A\r\n\n', D(2), ['A', '']))

    def test_text_budget_counts_utf16_and_failure_keeps_state(self):
        self.doc.clear()
        with patch('yadinassi.text_documents._MAX_TEXT_UNITS', 4):
            self.doc.set_text('😀😀')
            self.assertEqual(self.doc.get_text(), '😀😀')
            for method, args in ((self.doc.set_text, ('😀😀a',)), (self.doc.add_line, ('',)),
                                 (self.doc.insert_line, (D(0), 'a')),
                                 (self.doc.replace_line, (D(1), '😀😀'))):
                with self.assertRaises(ValueError): method(*args)
                self.assertEqual(self.doc.get_text(), '😀😀')
            self.doc.replace_line(D(0), 'a')
            self.assertEqual(self.doc.get_text(), 'a\n')

    def test_line_budget_checks_set_and_all_mutations_before_commit(self):
        before = self.snapshot()
        with patch('yadinassi.text_documents._MAX_LINES', 2):
            for method, args in ((self.doc.set_text, ('1\n2\n3',)),
                                 (self.doc.add_line, ('X',)),
                                 (self.doc.insert_line, (D(0), 'X')),
                                 (self.doc.replace_line, (D(2), 'X\nY'))):
                with self.assertRaises(ValueError): method(*args)
                self.assertEqual(self.snapshot(), before)
            self.doc.delete_line(D(1))
            self.doc.add_line('X')
            self.assertEqual(self.snapshot(), ('B\nX\n', D(2), ['B', 'X']))

    def test_huge_integer_indices_never_expand_to_host_integers(self):
        huge = D('1e1000000')
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.traps[Inexact] = ctx.traps[Rounded] = True
            self.assertEqual(self.doc.get_line(huge), '')
            before = self.snapshot()
            self.doc.replace_line(huge, 'X')
            self.doc.delete_line(huge)
            self.assertEqual(self.snapshot(), before)
            self.doc.insert_line(huge, 'X')
        self.assertEqual(self.snapshot(), ('A\r\nB\nX\n', D(3), ['A', 'B', 'X']))

    def test_algorithmic_extensions_do_not_hardcode_captured_witnesses(self):
        # Generic bounded model beyond the original A/B/X/Y witnesses, not new
        # native measurements. Unchanged mixed separators survive every edit.
        self.doc.set_text('one\rtwo\nthree\r\nfour')
        self.doc.insert_line(D(3), 'alpha\nbeta')
        self.assertEqual(self.doc.get_text(), 'one\rtwo\nalpha\nbeta\nthree\r\nfour')
        self.doc.replace_line(D(2), 'changed')
        self.doc.delete_line(D(5))
        self.assertEqual(self.snapshot(), ('one\rchanged\nalpha\nbeta\nfour', D(5),
                                          ['one', 'changed', 'alpha', 'beta', 'four']))
        self.doc.delete_line(D(0))
        self.doc.insert_line(D(0), '')
        self.assertEqual(self.snapshot(), ('\n', D(1), ['']))

    def test_no_file_ui_properties_indexer_iteration_or_host_members(self):
        vm = Interpreter(lambda _: None)
        vm.execute('d = New TextDocument();')
        for code in ('d.Read("not-opened")', 'd.Write("not-written")', 'd.Show()',
                     'd.ReadAsync("not-opened")', 'd.Text', 'd._text', 'd.Encoding',
                     'd.Text="X"', 'd[0]', 'd[0]="X"', 'For Each x In d Do EndDo;'):
            with self.subTest(code=code), self.assertRaises(BSLError): vm.execute(code)
        self.assertEqual(vm.execute('d.GetText()'), '')

    def test_codecs_descriptors_filled_and_context_transport_remain_closed(self):
        for value in (self.doc, BSLType.TEXT_DOCUMENT):
            with self.assertRaisesRegex(ValueError, 'ТекстовыйДокумент пока не поддерживается'):
                value_to_string_internal(value)
            with self.assertRaises((TypeError, ValueError)): xml_string(value)
            with self.assertRaises((TypeError, ValueError)): value_is_filled(value)
        for argument in ('TextDocument', 'ТекстовыйДокумент'):
            with self.assertRaises((TypeError, ValueError)): BSLTypeDescription(argument)
        kinds = BSLArray(); kinds.items = [BSLType.TEXT_DOCUMENT]
        with self.assertRaises((TypeError, ValueError)): BSLTypeDescription(kinds)
        vm = Interpreter(lambda _: None)
        vm.execute('&AtServer\nProcedure Reject(Val x)\nEndProcedure\nd=New TextDocument(); d.SetText("kept");')
        with self.assertRaises(BSLError): vm.execute('Reject(d);')
        vm.execute('a=New Array(); a.Add(d);')
        with self.assertRaises(BSLError): vm.execute('Reject(a);')
        vm.execute('&AtServer\nFunction GiveDocument()\nReturn New TextDocument();\nEndFunction')
        with self.assertRaises(BSLError): vm.execute('GiveDocument();')
        self.assertEqual(vm.execute('d.GetText()'), 'kept')

    def test_same_side_aliases_keep_one_mutable_document_without_properties(self):
        vm = Interpreter(lambda _: None)
        vm.execute('Procedure Fill(Val d) d.SetText("changed"); EndProcedure\n'
                   'd=New TextDocument(); a=d; Fill(d);')
        self.assertEqual(vm.execute('a.GetText()'), 'changed')
        vm.execute('d.Clear(); d.AddLine("again");')
        self.assertEqual(vm.execute('a.GetLine(1)'), 'again')


if __name__ == '__main__': unittest.main()
