"""Structure's BSL contract and interactions with existing runtime boundaries.

These are interpreter tests, not a claim of verification against native 1C.
The official 1Ci System Classes lesson documents identifier keys, replacement,
dot/bracket reads and iteration; other supported subset choices are documented
in the project. Tests intentionally do not impose native iteration order.
"""

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import BSLRuntimeError


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_empty_constructors_bilingual_and_case_insensitive(self):
        for expression in ['Новый Структура', 'New Structure',
                           'Новый сТрУкТуРа()', 'New sTrUcTuRe()']:
            with self.subTest(expression=expression):
                self.vm.execute(f's = {expression};')
                self.assertEqual(self.vm.execute('s.Count()'), Decimal(0))
                self.assertIs(type(self.vm.execute('s.Count()')), Decimal)
                self.assertEqual(self.vm.execute('String(s)'), 'Структура')

    def test_constructor_assigns_values_and_defaults_remaining_keys(self):
        self.vm.execute('''
            s = Новый Структура(" Имя, Сумма , Готово, Пустое ", "ёж", 12.5, Истина);
            Сообщить(s.Имя); Сообщить(s["Сумма"]); Сообщить(s.Готово);
            Сообщить(s.Пустое = Неопределено); Сообщить(s.Количество());
            t = New Structure("First,Second");
            Message(t.First = Undefined); Message(t.Second = Undefined);
        ''')
        self.assertEqual(self.output, ['ёж', '12.5', 'Да', 'Да', '4', 'Да', 'Да'])

    def test_constructor_keeps_explicit_undefined_and_object_identity(self):
        self.vm.execute('''
            a = New Array; s = New Structure("Empty,Items", Undefined, a);
            s.Items.Add(7); Message(a[0]); Message(s.Empty = Undefined);
        ''')
        self.assertEqual(self.output, ['7', 'Да'])
        self.assertIs(self.vm.execute('s.Items'), self.vm.variables['a'])

    def test_constructor_ignores_empty_fragments_and_trims_valid_names(self):
        # An explicit subset contract, not a native parity assertion.
        self.vm.execute('''
            s = New Structure(" , First, , Второе, ", 1, 2);
            Message(s.Count()); Message(s.First); Message(s.Второе);
            empty = New Structure(" , , "); Message(empty.Count());
        ''')
        self.assertEqual(self.output, ['2', '1', '2', '0'])

    def test_constructor_trims_fixed_unicode_white_space_around_fragments(self):
        whitespace = (' \t\n\v\f\r\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004'
                      '\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000')
        for character in whitespace:
            with self.subTest(codepoint=hex(ord(character))):
                text = f'{character}First{character},{character},{character}Второе{character}'
                self.vm.variables['keys'] = text
                self.vm.execute('s = New Structure(keys, 1, 2);')
                self.assertEqual(self.vm.execute('s.Count()'), Decimal(2))
                self.assertEqual(self.vm.execute('s.First'), Decimal(1))
                self.assertEqual(self.vm.execute('s.Второе'), Decimal(2))
                self.assertEqual(self.vm.variables['keys'], text)
                self.vm.variables['keys'] = character
                self.vm.execute('s = New Structure(keys);')
                self.assertEqual(self.vm.execute('s.Count()'), Decimal(0))

    def test_constructor_does_not_strip_c0_separators_bom_or_zero_width_space(self):
        self.vm.execute('s = New Structure("Known", 7); original = s;')
        for character in '\x00\x1c\x1d\x1e\x1f\u200b\ufeff':
            for text in [character, character + 'Name', 'Name' + character,
                         'First,' + character + ',Second']:
                with self.subTest(codepoint=hex(ord(character)), text=repr(text)):
                    self.vm.variables['keys'] = text
                    with self.assertRaises(BSLRuntimeError):
                        self.vm.execute('s = New Structure(keys, 1, 2);')
                    self.assertIs(self.vm.variables['s'], self.vm.variables['original'])
                    self.assertEqual(self.vm.execute('s.Known'), Decimal(7))

    def test_constructor_does_not_remove_internal_whitespace_from_keys(self):
        for character in [' ', '\t', '\n', '\u00a0', '\u2003', '\u202f', '\u3000']:
            with self.subTest(codepoint=hex(ord(character))):
                self.vm.variables['keys'] = 'First' + character + 'Second'
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('s = New Structure(keys);')

    def test_duplicate_constructor_keys_use_insert_replacement_semantics(self):
        self.vm.execute('''
            s = New Structure("First, first, FIRST", 1, 2, 3);
            Message(s.Count()); Message(s.First);
            For Each pair In s Do Message(pair.Key); EndDo;
            t = New Structure("Name,NAME", 1); Message(t.Name = Undefined);
        ''')
        self.assertEqual(self.output, ['1', '3', 'FIRST', 'Да'])

    def test_surplus_constructor_values_are_evaluated_then_ignored(self):
        self.vm.execute('''
            Var counter; counter = 0;
            Function NextValue() counter = counter + 1; Return counter; EndFunction
            s = New Structure("Only", NextValue(), NextValue());
            Message(s.Count()); Message(s.Only); Message(counter);
            empty = New Structure("", NextValue());
            Message(empty.Count()); Message(counter);
        ''')
        self.assertEqual(self.output, ['1', '1', '2', '0', '3'])

    def test_valid_cyrillic_latin_digit_and_underscore_keys(self):
        self.vm.execute('''
            s = New Structure("_1,Ёж2,Latin_3", 1, 2, 3);
            Message(s._1); Message(s.ёж2); Message(s["LATIN_3"]);
        ''')
        self.assertEqual(self.output, ['1', '2', '3'])

    def test_insert_replaces_case_insensitively_and_updates_key_spelling(self):
        self.vm.execute('''
            s = New Structure("MiXeD", 1);
            s.Вставить("mixed", 2); s.Insert("MIXED", 3);
            Message(s.Count()); Message(s.mixed); Message(s["mIxEd"]);
            For Each p In s Do Message(p.Key); EndDo;
        ''')
        self.assertEqual(self.output, ['1', '3', '3', 'MIXED'])

    def test_insert_optional_value_is_undefined_even_when_replacing(self):
        self.vm.execute('''
            s = New Structure; s.Insert("First");
            s.Вставить("Второе", 42); s.Вставить("второе");
            Message(s.First = Undefined); Message(s.Второе = Undefined);
            Message(s.Count());
        ''')
        self.assertEqual(self.output, ['Да', 'Да', '2'])

    def test_writable_named_and_string_index_access_share_storage(self):
        self.vm.execute('''
            s = New Structure("Name", 1); alias = s;
            s.nAME = 2; Message(alias["NAME"]);
            alias["name"] = 3; Message(s.Name);
            For Each p In s Do Message(p.Key); EndDo;
        ''')
        self.assertEqual(self.output, ['2', '3', 'Name'])

    def test_delete_absent_is_noop_clear_and_reuse_bilingual(self):
        self.vm.execute('''
            s = New Structure("First,Second", 1, 2);
            s.Delete("FIRST"); s.Удалить("missing"); Message(s.Count());
            Message(s.Property("First")); s.Очистить(); Message(s.Количество());
            s.Insert("Third", 3); Message(s.Third); s.Clear(); Message(s.Count());
        ''')
        self.assertEqual(self.output, ['1', 'Нет', '0', '3', '0'])

    def test_missing_property_reads_and_writes_do_not_create_keys(self):
        self.vm.execute('s = New Structure("Known", 7);')
        for code in ['s.Missing', 's["Missing"]',
                     's.Missing = 8', 's["Missing"] = 8']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)
            self.assertEqual(self.vm.execute('s.Count()'), Decimal(1))
            self.assertEqual(self.vm.execute('s.Known'), Decimal(7))
            self.assertIs(self.vm.execute('s.Property("Missing")'), False)

    def test_invalid_insert_keys_are_rejected_without_mutation(self):
        self.vm.execute('s = New Structure("Known", 7);')
        for key in ['""', '"two words"', '"1first"', '"a-b"', '"a,b"',
                    '"a.b"', '"🙂"', '1', 'True', 'Undefined', 'New Array']:
            with self.subTest(key=key), self.assertRaises(BSLRuntimeError):
                self.vm.execute(f's.Insert({key}, 8)')
            self.assertEqual(self.vm.execute('s.Count()'), Decimal(1))
            self.assertEqual(self.vm.execute('s.Known'), Decimal(7))

    def test_constructor_invalid_identifiers_leave_assignment_unchanged(self):
        self.vm.execute('s = New Structure("Known", 7); original = s;')
        for expression in ['New Structure("a-b", 1)', 'New Structure("1first")',
                           'New Structure("Known,two words", 1, 2)',
                           'New Structure(1)', 'New Structure(True)',
                           'New Structure(New Array)']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(f's = {expression}')
            self.assertIs(self.vm.variables['s'], self.vm.variables['original'])
            self.assertEqual(self.vm.execute('s.Known'), Decimal(7))

    def test_numeric_boolean_and_undefined_indexes_are_rejected(self):
        self.vm.execute('s = New Structure("Known", 7);')
        for index in ['0', 'True', 'Undefined']:
            for code in [f's[{index}]', f's[{index}] = 9']:
                with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                    self.vm.execute(code)
            self.assertEqual(self.vm.execute('s.Known'), Decimal(7))
            self.assertEqual(self.vm.execute('s.Count()'), Decimal(1))

    def test_direct_key_arguments_are_strict_and_failure_preserves_outputs(self):
        self.vm.execute('s = New Structure("Known", 7); result = 99;')
        for key in ['""', '"bad-key"', '"a.b"',
                    '0', 'True', 'Undefined', 'New Array']:
            for code in [f's.Property({key}, result)', f's.Delete({key})',
                         f's[{key}]', f's[{key}] = 8', f's.Insert({key}, 8)']:
                with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                    self.vm.execute(code)
                self.assertEqual(self.vm.variables['result'], Decimal(99))
                self.assertEqual(self.vm.execute('s.Count()'), Decimal(1))
                self.assertEqual(self.vm.execute('s.Known'), Decimal(7))

    def test_property_ignores_outer_ascii_spaces_and_preserves_output_contract(self):
        # Confirmed by the owner-supplied native collections.out, unlike other
        # whitespace characters or trimming in Insert/Delete/index operations.
        self.vm.execute('''
            s = New Structure("Known,Empty", 7); result = 99;
            Message(s.Property("  kNoWn  ", result)); Message(result);
            Message(s.Свойство(" Known "));
            Message(s.Property(" Empty ", result)); Message(result = Undefined);
            result = 99;
            Message(s.Property(" Missing ", result)); Message(result = Undefined);
            Message(s.Count());
        ''')
        self.assertEqual(self.output, ['Да', '7', 'Да', 'Да', 'Да', 'Нет', 'Да', '2'])

    def test_property_trimming_does_not_change_keys_or_other_name_operations(self):
        self.vm.execute('s = New Structure("Known", 7); result = 99;')
        self.vm.execute('s.Property(" known ", result); '
                        'For Each pair In s Do Message(pair.Key); EndDo;')
        self.assertEqual(self.output, ['Known'])
        for code in ['s.Insert(" Known ", 8)', 's.Delete(" Known ")',
                     's[" Known "]', 's[" Known "] = 8']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)
            self.assertEqual(self.vm.execute('s.Known'), Decimal(7))
        for key in [' ', 'Known Name', '\tKnown\t', '\u00a0Known\u00a0']:
            with self.subTest(key=repr(key)):
                self.vm.variables['key'] = key
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('s.Property(key, result)')
                self.assertEqual(self.vm.variables['result'], Decimal(7))

    def test_wrong_method_arities_do_not_mutate_structure_or_output(self):
        self.vm.execute('s = New Structure("Known", 7); result = 99;')
        cases = ['s.Insert()', 's.Insert("Known", 8, 9)', 's.Delete()',
                 's.Delete("Known", 8)', 's.Clear(1)', 's.Count(1)',
                 's.Property()', 's.Property("Known", result, 8)']
        for code in cases:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)
            self.assertEqual(self.vm.execute('s.Known'), Decimal(7))
            self.assertEqual(self.vm.execute('s.Count()'), Decimal(1))
            self.assertEqual(self.vm.variables['result'], Decimal(99))

    def test_property_returns_boolean_without_output(self):
        self.vm.execute('s = New Structure("Present,Empty", 7);')
        for expression, expected in [('s.Property("pRESENT")', True),
                                     ('s.Свойство("Empty")', True),
                                     ('s.Property("Absent")', False)]:
            with self.subTest(expression=expression):
                self.assertIs(self.vm.execute(expression), expected)

    def test_property_writes_declared_output_and_resets_missing_to_undefined(self):
        self.vm.execute('''
            Var result;
            s = Новый Структура("Есть,Пусто", 42);
            Сообщить(s.Свойство("есть", result)); Сообщить(result);
            Сообщить(s.Property("Пусто", result)); Сообщить(result = Undefined);
            result = 99;
            Сообщить(s.Property("Missing", result)); Сообщить(result = Undefined);
        ''')
        self.assertEqual(self.output, ['Да', '42', 'Да', 'Да', 'Нет', 'Да'])

    def test_property_output_can_replace_its_receiver_variable(self):
        self.vm.execute('''
            s = New Structure("Value", 42); alias = s;
            Message(s.Property("Value", s)); Message(s); Message(alias.Value);
        ''')
        self.assertEqual(self.output, ['Да', '42', '42'])

    def test_property_output_keeps_stored_object_identity(self):
        self.vm.execute('''
            a = New Array; s = New Structure("Items", a); Var result;
            s.Property("Items", result); result.Add(7); Message(a[0]);
        ''')
        self.assertEqual(self.output, ['7'])
        self.assertIs(self.vm.variables['result'], self.vm.variables['a'])

    def test_property_output_forwards_references_and_preserves_val_cells(self):
        self.vm.execute('''
            Procedure Inner(Val s, output)
                s.Property("Value", output);
            EndProcedure
            Procedure Outer(Val s, output, Val local)
                Inner(s, output); Inner(s, local); Message(local);
            EndProcedure
            s = New Structure("Value", 42); x = 1; y = 2;
            Outer(s, x, y); Message(x); Message(y);
        ''')
        self.assertEqual(self.output, ['42', '42', '2'])
        self.assertIsNone(self.vm.locals)

    def test_property_outputs_are_live_aliases_inside_routines(self):
        self.vm.execute('''
            Procedure Fill(Val s, first, second)
                s.Property("Value", first); Message(second);
                s.Property("Missing", second); Message(first = Undefined);
            EndProcedure
            s = New Structure("Value", 42); x = 0; Fill(s, x, x);
            Message(x = Undefined);
        ''')
        self.assertEqual(self.output, ['42', 'Да', 'Да'])

    def test_property_output_uses_local_scope_without_rebinding_module_names(self):
        self.vm.execute('''
            Var result; result = 99;
            Function Read(Val result)
                s = New Structure("Value", 42);
                s.Property("Value", result); Return result;
            EndFunction
            Message(Read(7)); Message(result);
        ''')
        self.assertEqual(self.output, ['42', '99'])
        self.assertIsNone(self.vm.locals)

    def test_property_does_not_implicitly_declare_output_variables(self):
        self.vm.execute('s = New Structure("Value", 42);')
        with self.assertRaisesRegex(BSLError, 'не определена'):
            self.vm.execute('s.Property("Value", undeclared)')
        self.assertNotIn('undeclared', self.vm.variables)
        self.assertEqual(self.vm.execute('s.Value'), Decimal(42))

    def test_property_literal_and_computed_outputs_use_temporary_values(self):
        self.vm.execute('''
            s = New Structure("Value", 42); x = 1;
            Function Two() Return 2; EndFunction
            Message(s.Property("Value", 0));
            Message(s.Property("Value", x + 1));
            Message(s.Property("Missing", Two())); Message(x);
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Нет', '1'])

    def test_property_rejects_grouped_indexed_and_named_property_outputs(self):
        self.vm.execute('''
            s = New Structure("Value", 42); x = 7;
            a = New Array; a.Add(7); holder = New Structure("Value", 7);
        ''')
        for argument in ['(x)', '((x))', 'a[0]', '(a[0])',
                         'holder.Value', 'holder["Value"]', '(holder.Value)']:
            with self.subTest(argument=argument), self.assertRaisesRegex(BSLError, 'по ссылке пока'):
                self.vm.execute(f's.Property("Value", {argument})')
            self.assertEqual(self.vm.variables['x'], Decimal(7))
            self.assertEqual(self.vm.execute('a[0]'), Decimal(7))
            self.assertEqual(self.vm.execute('holder.Value'), Decimal(7))

    def test_routine_property_reference_limit_remains_and_val_reads_work(self):
        self.vm.execute('''
            s = New Structure("Value", 7);
            Procedure Change(x) x = 8; EndProcedure
            Function Read(Val x) Return x; EndFunction
        ''')
        for argument in ['s.Value', 's["Value"]', '(s.Value)', '(s["Value"])']:
            with self.subTest(argument=argument), self.assertRaisesRegex(BSLError, 'по ссылке пока'):
                self.vm.execute(f'Change({argument})')
            self.assertEqual(self.vm.execute(f'Read({argument})'), Decimal(7))
        self.assertEqual(self.vm.execute('s.Value'), Decimal(7))

    def test_grouped_direct_calls_keep_property_output_metadata(self):
        self.vm.execute('''
            s = New Structure("Value", 42); Var result;
            ((s.Property))("Value", result); Message(result);
            (s.Property)("Missing", result); Message(result = Undefined);
            (s.Свойство)("Value", result); Message(result);
        ''')
        self.assertEqual(self.output, ['42', 'Да', '42'])

    def test_structure_methods_are_not_first_class_property_values(self):
        self.vm.execute('s = New Structure;')
        for name in ['Property', 'Свойство', 'Insert', 'Delete', 'Clear', 'Count']:
            with self.subTest(name=name), self.assertRaises(BSLRuntimeError):
                self.vm.execute(f'method = s.{name}')
        self.assertNotIn('method', self.vm.variables)

    def test_same_name_property_and_method_dispatch_are_separate(self):
        self.vm.execute('''
            s = New Structure("Count,Property,Insert,Количество", 17, 18, 19, 20);
            Message(s.Count); Message(s.Count());
            s.Count = 21; Message(s["Count"]); Message((s.Count)());
            Message(s.Property); Message(s.Property("Count"));
            s.Insert("Extra", 22); Message(s.Insert); Message(s.Extra);
            Message(s.Количество); Message(s.Количество());
        ''')
        self.assertEqual(self.output, ['17', '4', '21', '4', '18', 'Да',
                                       '19', '22', '20', '5'])

    def test_nested_property_index_assignments_evaluate_receiver_once_in_order(self):
        self.vm.execute('''
            Var root, trace;
            root = New Structure("Child", New Structure("Value", 0)); trace = "";
            Function Receiver() trace = trace + "R"; Return root; EndFunction
            Function KeyName() trace = trace + "K"; Return "Value"; EndFunction
            Function NewValue() trace = trace + "V"; Return 7; EndFunction
            Receiver().Child[KeyName()] = NewValue();
            Message(trace); Message(root.Child.Value);
            trace = ""; Receiver()["Child"].Value = NewValue();
            Message(trace); Message(root.Child.Value);
        ''')
        self.assertEqual(self.output, ['RKV', '7', 'RV', '7'])

    def test_nested_property_call_receiver_and_arguments_are_evaluated_once(self):
        self.vm.execute('''
            Var root, trace;
            root = New Structure("Child", New Structure("Value", 42)); trace = "";
            Function Receiver() trace = trace + "R"; Return root; EndFunction
            Function KeyName() trace = trace + "K"; Return "Value"; EndFunction
            Function Temporary() trace = trace + "T"; Return 0; EndFunction
            Message(Receiver().Child.Property(KeyName(), Temporary())); Message(trace);
            trace = ""; Receiver().Child.Insert(KeyName(), Temporary());
            Message(trace); Message(root.Child.Value);
        ''')
        self.assertEqual(self.output, ['Да', 'RKT', 'RKT', '0'])

    def test_property_failure_does_not_overwrite_output_and_error_is_catchable(self):
        self.vm.execute('''
            s = New Structure("Value", 42); result = 99;
            Try s.Property(7, result); Except Message("caught"); EndTry;
            Message(result); Message(s.Value);
        ''')
        self.assertEqual(self.output, ['caught', '99', '42'])

    def test_output_written_before_later_error_survives_with_frames_restored(self):
        self.vm.execute('''
            Procedure Fill(Val s, output)
                s.Property("Value", output); failure = 1 / 0;
            EndProcedure
            s = New Structure("Value", 42); result = 99;
        ''', 'definitions.bsl')
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('Fill(s, result)', 'caller.bsl')
        self.assertEqual(caught.exception.source, 'definitions.bsl')
        self.assertEqual(self.vm.variables['result'], Decimal(42))
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.execute('s.Property("Value")'), True)

    def test_invalid_output_has_source_location_and_restores_caller_frame(self):
        self.vm.execute('s = New Structure("Value", 42); result = 99;')
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('\ns.Property("Value", (result));', 'output.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), ('output.bsl', 2))
        self.assertEqual(self.vm.variables['result'], Decimal(99))
        self.assertIsNone(self.vm.locals)

    def test_foreach_yields_bilingual_key_value_pairs_without_promising_order(self):
        self.vm.execute('''
            s = New Structure("First,Второе", 7, "ёж");
            For Each pair In s Do
                Message(pair.Key + ":" + pair.Value);
                Message(pair.Ключ + ":" + pair.Значение);
                Message(String(pair));
            EndDo;
        ''')
        self.assertCountEqual(self.output, ['First:7', 'First:7', 'КлючИЗначение',
                                            'Второе:ёж', 'Второе:ёж', 'КлючИЗначение'])

    def test_empty_foreach_and_nested_structure_array_iteration(self):
        self.vm.execute('''
            For Each pair In New Structure Do Message("bad"); EndDo;
            a = New Array; a.Add(New Structure("Value", 7));
            For Each s In a Do
                For Each pair In s Do Message(pair.Value); EndDo;
            EndDo;
        ''')
        self.assertEqual(self.output, ['7'])

    def test_iteration_pair_properties_are_readonly(self):
        self.vm.execute('s = New Structure("Value", 7); For Each pair In s Do EndDo;')
        for code in ['pair.Key = "Changed"', 'pair.Value = 8',
                     'pair.Ключ = "Changed"', 'pair.Значение = 8']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)
            self.assertEqual(self.vm.execute('pair.Key'), 'Value')
            self.assertEqual(self.vm.execute('pair.Value'), Decimal(7))
            self.assertEqual(self.vm.execute('s.Value'), Decimal(7))

    def test_pair_value_can_reference_mutable_collection_without_rebinding_pair(self):
        self.vm.execute('''
            a = New Array; s = New Structure("Items", a);
            For Each pair In s Do pair.Value.Add(7); EndDo;
            Message(a[0]); Message(s.Items.Count());
        ''')
        self.assertEqual(self.output, ['7', '1'])

    def test_iteration_pairs_snapshot_values_but_allow_existing_value_updates(self):
        self.vm.execute('''
            s = New Structure("First,Second", 1, 2); visited = 0;
            For Each pair In s Do
                If visited = 0 Then
                    Message(pair.Value < 10);
                    s.First = 11; s.Insert("SECOND", 12);
                    Message(pair.Value < 10);
                Else
                    Message(pair.Value > 10);
                EndIf;
                visited = visited + 1;
            EndDo;
            Message(visited); Message(s.First); Message(s.Second);
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да', '2', '11', '12'])

    def test_composition_changes_during_iteration_raise_catchable_subset_error(self):
        # Native 1C documents composition changes as undefined. Our explicit
        # boundary must remain catchable and must never leak a Python exception.
        for change in ['s.Insert("Added", 3)', 's.Delete(pair.Key)', 's.Clear()']:
            with self.subTest(change=change):
                self.output.clear()
                self.vm.execute(f'''
                    s = New Structure("First,Second", 1, 2);
                    Try
                        For Each pair In s Do {change}; EndDo;
                    Except Message("caught"); EndTry;
                    Message("after");
                ''')
                self.assertEqual(self.output, ['caught', 'after'])

    def test_composition_change_followed_by_break_does_not_advance_iterator(self):
        self.vm.execute('''
            s = New Structure("First,Second", 1, 2);
            For Each pair In s Do s.Clear(); Break; EndDo;
            Message(s.Count());
        ''')
        self.assertEqual(self.output, ['0'])

    def test_delete_of_missing_key_does_not_invalidate_iteration(self):
        self.vm.execute('''
            s = New Structure("First,Second", 1, 2); visited = 0;
            For Each pair In s Do s.Delete("Missing"); visited = visited + 1; EndDo;
            Message(visited);
        ''')
        self.assertEqual(self.output, ['2'])

    def test_ordinary_host_functions_receive_values_not_reference_wrappers(self):
        received = []
        self.vm.register_function('Observe', lambda *values: received.append(values))
        self.vm.execute('''
            s = New Structure("Value", 42); x = 7;
            Observe(x, s, s.Value); a = New Array; a.Add(x);
            Message(a[0]); Message(String(x));
        ''')
        self.assertEqual(received, [(Decimal(7), self.vm.variables['s'], Decimal(42))])
        self.assertEqual(self.output, ['7', '7'])

    def test_python_attributes_are_not_exposed_on_structures_pairs_or_methods(self):
        self.vm.execute('''
            s = New Structure("Value", 7); For Each pair In s Do EndDo;
            method = Message;
        ''')
        for receiver in ['s', 'pair', 'method']:
            for name in ['__class__', '__dict__', '__str__', 'items', 'function',
                         'get_member', 'set_member', 'by_reference', 'parameters']:
                for suffix in ['', '()']:
                    code = f'{receiver}.{name}{suffix}'
                    with self.subTest(code=code), self.assertRaises(BSLError):
                        self.vm.execute(code)

    def test_python_like_key_names_are_plain_user_values(self):
        self.vm.execute('''
            s = New Structure("__class__,items,get_member", 1, 2, 3);
            Message(s.__class__); Message(s.items); Message(s.get_member);
            s.__class__ = 4; Message(s["__class__"]);
        ''')
        self.assertEqual(self.output, ['1', '2', '3', '4'])


class StructureImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def load(self, module, main):
        (self.directory / 'Helpers.bsl').write_text(module, encoding='utf-8')
        path = self.directory / 'Main.bsl'
        path.write_text('// #Import Helpers.bsl\n' + main, encoding='utf-8')
        self.vm.execute(path.read_text(encoding='utf-8'), str(path))

    def test_imported_export_forwards_host_outputs_to_callers_and_val_locals(self):
        self.load('''
            Var result; result = 999;
            Procedure Fill(Val s, output) Export s.Property("Value", output); EndProcedure
            Function Local(Val s, Val output) Export
                s.Property("Value", output); Return output;
            EndFunction
            Function OwnValue() Export Return result; EndFunction
        ''', '''
            s = New Structure("Value", 42); Var result;
            Helpers.Fill(s, result); Message(result);
            result = 7; Message(Helpers.Local(s, result)); Message(result);
            Message(Helpers.OwnValue());
        ''')
        self.assertEqual(self.output, ['42', '42', '7', '999'])
        self.assertIsNone(self.vm.locals)

    def test_structures_returned_from_exports_preserve_aliases_and_method_dispatch(self):
        self.load('''
            Var data; data = New Structure("Value,Count", 1, 9);
            Function GetData() Export Return data; EndFunction
            Function Read() Export Return data.Value; EndFunction
        ''', '''
            s = Helpers.GetData(); s.Value = 42;
            Message(Helpers.Read()); Message(Helpers.GetData().Count);
            Message(Helpers.GetData().Count());
            result = 0; Helpers.GetData().Property("Value", result); Message(result);
        ''')
        self.assertEqual(self.output, ['42', '9', '2', '42'])

    def test_module_exports_and_private_state_stay_isolated(self):
        self.load('''
            Var data; data = New Structure("Value", 7);
            Function Public() Export Return data; EndFunction
            Function Private() Return data; EndFunction
        ''', 's = Helpers.Public();')
        for code in ['Helpers.data', 'Helpers.data.Value', 'Helpers.data = s',
                     'Helpers.Public = s', 'Helpers.Private()',
                     'Helpers.__dict__', 'Helpers.Public.__class__']:
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('Helpers.Public().Value'), Decimal(7))

    def test_imported_host_output_failure_preserves_source_scope_and_prior_writes(self):
        # Exercise canonical import paths even where temporary directories do
        # not themselves contain aliases (unlike macOS and Windows runners).
        subdirectory = self.directory / 'path_alias'
        subdirectory.mkdir()
        self.directory = subdirectory / '..'
        self.load('''
            Procedure Fill(Val s, output) Export
                s.Property("Value", output);
                s.Property("Value", (output));
            EndProcedure
        ''', 's = New Structure("Value", 42); result = 7;')
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('Helpers.Fill(s, result)', 'caller.bsl')
        self.assertEqual(caught.exception.source, str((self.directory / 'Helpers.bsl').resolve()))
        self.assertEqual(self.vm.variables['result'], Decimal(42))
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.execute('s.Value'), Decimal(42))


if __name__ == '__main__':
    unittest.main()
