"""Map's interpreter contract, including typed keys and runtime boundaries.

These are interpreter tests, not native-1C verification. Iteration assertions do
not require an order. Mutation-during-iteration diagnostics describe the explicit
supported subset, rather than unspecified native behavior.
"""

from decimal import Decimal
import os
from pathlib import Path
import random
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.structures import BSLStructure
from yadinassi.values import BSLArray


class MapTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_empty_constructors_bilingual_and_case_insensitive(self):
        for expression in ['Новый Соответствие', 'New Map',
                           'Новый сОоТвЕтСтВиЕ()', 'New mAp()']:
            with self.subTest(expression=expression):
                self.vm.execute(f'm = {expression};')
                self.assertEqual(self.vm.execute('m.Count()'), Decimal(0))
                self.assertIs(type(self.vm.execute('m.Количество()')), Decimal)
                self.assertEqual(self.vm.execute('String(m)'), 'Соответствие')

    def test_constructor_arguments_fail_without_overwriting_existing_map(self):
        self.vm.execute('m = New Map; m.Insert("kept", 7); original = m;')
        for expression in ['New Map(1)', 'New Map("key", 2)',
                           'New Соответствие(Undefined)', 'New Map(m)']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(f'm = {expression};')
            self.assertIs(self.vm.variables['m'], self.vm.variables['original'])
            self.assertEqual(self.vm.execute('m["kept"]'), Decimal(7))

    def test_insert_get_replace_and_count_bilingual(self):
        self.vm.execute('''
            m = Новый Соответствие;
            m.Вставить("Имя", "ёж"); m.Insert("Amount", 12.5);
            Сообщить(m.Получить("Имя")); Message(m.Get("Amount"));
            m.iNsErT("Amount", 42); m.ВсТаВиТь("Имя", "кот");
            Message(m.gEt("Amount")); Сообщить(m.ПОЛУЧИТЬ("Имя"));
            Message(m.cOuNt()); Сообщить(m.КОЛИЧЕСТВО());
        ''')
        self.assertEqual(self.output, ['ёж', '12.5', '42', 'кот', '2', '2'])

    def test_insert_optional_value_defaults_to_undefined_even_when_replacing(self):
        self.vm.execute('''
            m = New Map; m.Insert("new"); m.Insert("existing", 7);
            m.Вставить("existing"); m.Insert(Undefined);
            Message(m["new"] = Undefined); Message(m["existing"] = Undefined);
            Message(m.Get(Undefined) = Undefined); Message(m.Count());
            seen = 0;
            For Each pair In m Do
                Message(pair.Value = Undefined); seen = seen + 1;
            EndDo;
            Message(seen);
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да', '3', 'Да', 'Да', 'Да', '3'])

    def test_index_assignment_creates_and_replaces_with_shared_method_storage(self):
        self.vm.execute('''
            m = New Map; alias = m;
            m["new"] = 1; Message(alias.Get("new"));
            alias["new"] = 2; Message(m["new"]);
            m.Insert("new", 3); Message(alias["new"]);
            m.Insert(7, "number"); alias[7] = "updated";
            Message(m.Get(7)); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['1', '2', '3', 'updated', '2'])
        self.assertIs(self.vm.variables['m'], self.vm.variables['alias'])

    def test_absent_get_and_index_return_undefined_without_creating_entries(self):
        self.vm.execute('m = New Map; m.Insert("present", 7);')
        for key in ['"absent"', '0', 'True', 'Undefined', 'New Array', 'New Map']:
            for expression in [f'm.Get({key})', f'm.Получить({key})', f'm[{key}]']:
                with self.subTest(expression=expression):
                    self.assertIsNone(self.vm.execute(expression))
                    self.assertEqual(self.vm.execute('m.Count()'), Decimal(1))
        self.assertEqual(self.vm.execute('m["present"]'), Decimal(7))

    def test_delete_absent_is_noop_and_clear_allows_reuse_bilingual(self):
        self.vm.execute('''
            m = New Map; m.Insert("one", 1); m.Insert("two", 2);
            m.Delete("one"); m.Удалить("absent"); m.Delete(New Array);
            Message(m.Count()); Message(m.Get("one") = Undefined);
            m.Очистить(); Message(m.Количество()); m.Clear();
            m[Undefined] = 3; Message(m.Get(Undefined));
            m.Удалить(Undefined); Message(m.Count());
            m["again"] = 4; m.Clear(); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['1', 'Да', '0', '3', '0', '0'])

    def test_boolean_numeric_and_string_keys_are_different(self):
        self.vm.execute('''
            m = New Map;
            m.Insert(True, "true"); m.Insert(1, "one");
            m.Insert(False, "false"); m.Insert(0, "zero");
            m.Insert("1", "string one"); m.Insert("0", "string zero");
            Message(m.Get(True)); Message(m[1]); Message(m[False]);
            Message(m.Get(0)); Message(m["1"]); Message(m["0"]);
            m.Delete(True); Message(m.Get(True) = Undefined); Message(m[1]);
            m.Delete(0); Message(m[False]); Message(m[0] = Undefined);
            Message(m.Count());
        ''')
        self.assertEqual(self.output, ['true', 'one', 'false', 'zero',
                                       'string one', 'string zero', 'Да', 'one',
                                       'false', 'Да', '4'])

    def test_equal_decimal_scales_and_signed_zero_share_keys(self):
        self.vm.execute('''
            m = New Map; m.Insert(1, "first"); m.Insert(1.00, "replacement");
            m[0.000] = "zero"; m[-0] = "negative zero";
            m[1.0000] = "last"; Message(m.Count());
            Message(m.Get(1)); Message(m.Get(1.000)); Message(m[0]);
            m.Delete(1.0); Message(m[1] = Undefined); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['2', 'last', 'last', 'negative zero', 'Да', '1'])

    def test_string_keys_are_exact_case_sensitive_values_without_identifier_rules(self):
        self.vm.execute('''
            m = New Map;
            m["Name"] = 1; m["name"] = 2; m["NAME"] = 3;
            m[""] = 4; m[" two words "] = 5; m["a-b.c,🙂"] = 6;
            m["Ёж"] = 7; m["ёж"] = 8;
            Message(m.Count()); Message(m["Name"]); Message(m["name"]);
            Message(m["NAME"]); Message(m[""]); Message(m[" two words "]);
            Message(m["a-b.c,🙂"]); Message(m["Ёж"]); Message(m["ёж"]);
            Message(m["two words"] = Undefined); m.Delete("name");
            Message(m["Name"]); Message(m["NAME"]); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['8', '1', '2', '3', '4', '5', '6',
                                       '7', '8', 'Да', '1', '3', '7'])

    def test_unicode_keys_are_not_normalized_or_casefolded(self):
        self.vm.execute('m = New Map;')
        keys = ['é', 'e\u0301', 'ß', 'ss', 'İ', 'i', '\x00', '\n', ' ', '\u00a0']
        for index, key in enumerate(keys):
            self.vm.variables.update(key=key, value=Decimal(index))
            self.vm.execute('m.Insert(key, value)')
        self.assertEqual(self.vm.execute('m.Count()'), Decimal(len(keys)))
        for index, key in enumerate(keys):
            self.vm.variables['key'] = key
            self.assertEqual(self.vm.execute('m[key]'), Decimal(index))

    def test_undefined_is_a_key_and_an_explicit_value(self):
        self.vm.execute('''
            m = New Map; m.Insert(Undefined, "undefined key");
            m.Insert("empty", Undefined); m[Undefined] = 7;
            Message(m.Get(Undefined)); Message(m["empty"] = Undefined);
            Message(m.Count()); m.Delete(Undefined);
            Message(m[Undefined] = Undefined); Message(m.Count());
            For Each pair In m Do Message(pair.Key); EndDo;
        ''')
        self.assertEqual(self.output, ['7', 'Да', '2', 'Да', '1', 'empty'])

    def test_array_keys_use_identity_and_survive_mutation(self):
        self.vm.execute('''
            m = New Map; first = New Array; second = New Array; alias = first;
            first.Add(1); second.Add(1); m[first] = "first"; m[second] = "second";
            first.Add(2); Message(m.Get(alias)); Message(m[second]);
            m.Insert(alias, "replaced"); Message(m[first]); Message(m.Count());
            m.Delete(first); Message(m[alias] = Undefined); Message(m[second]);
        ''')
        self.assertEqual(self.output, ['first', 'second', 'replaced', '2', 'Да', 'second'])

    def test_structure_and_map_keys_use_identity_and_survive_mutation(self):
        self.vm.execute('''
            m = New Map; s = New Structure("Value", 1); same = New Structure("Value", 1);
            key = New Map; other = New Map; key["value"] = 1; other["value"] = 1;
            m[s] = "structure"; m[same] = "other structure";
            m[key] = "map"; m[other] = "other map";
            s.Value = 9; key.Clear(); key[key] = key;
            Message(m[s]); Message(m[same]); Message(m[key]); Message(m[other]);
            Message(m.Count()); Message(s = same); Message(key = other);
            Message(m[New Structure("Value", 9)] = Undefined);
            Message(m[New Map] = Undefined);
        ''')
        self.assertEqual(self.output, ['structure', 'other structure', 'map',
                                       'other map', '4', 'Нет', 'Нет', 'Да', 'Да'])

    def test_map_can_be_its_own_key_and_value(self):
        self.vm.execute('''
            m = New Map; m[m] = m; alias = m;
            Message(m.Get(m) = m); Message(alias[alias] = m);
            Message(m.Count()); Message(String(m));
            For Each pair In m Do
                Message(pair.Key = m); Message(pair.Value = m);
            EndDo;
            m.Delete(m); Message(m.Count()); Message(m[m] = Undefined);
        ''')
        self.assertEqual(self.output, ['Да', 'Да', '1', 'Соответствие',
                                       'Да', 'Да', '0', 'Да'])

    def test_mutually_referential_maps_do_not_recurse_during_key_lookup(self):
        self.vm.execute('''
            first = New Map; second = New Map;
            first[second] = first; second[first] = second;
            first[first] = second; second[second] = first;
            Message(first[second] = first); Message(second[first] = second);
            Message(first[first] = second); Message(second[second] = first);
            Message(first = second); Message(first.Count()); Message(second.Count());
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да', 'Да', 'Нет', '2', '2'])

    def test_host_unhashable_keys_use_identity_without_python_equality(self):
        class Unhashable:
            __hash__ = None

            def __eq__(self, other):
                raise AssertionError('Map keys must not invoke host equality')

        keys = [[], [], {}, {}, Unhashable(), Unhashable()]
        self.vm.execute('m = New Map;')
        for index, key in enumerate(keys):
            self.vm.variables.update(key=key, value=Decimal(index))
            self.vm.execute('m[key] = value;')
        keys[0].append('changed')
        keys[2]['changed'] = 1
        self.assertEqual(self.vm.execute('m.Count()'), Decimal(len(keys)))
        for index, key in enumerate(keys):
            self.vm.variables['key'] = key
            self.assertEqual(self.vm.execute('m.Get(key)'), Decimal(index))
        self.vm.variables['key'] = keys[-1]
        self.vm.execute('m.Delete(key);')
        self.assertIsNone(self.vm.execute('m[key]'))
        self.vm.variables['key'] = keys[-2]
        self.assertEqual(self.vm.execute('m[key]'), Decimal(len(keys) - 2))

    def test_host_hashable_objects_do_not_control_map_identity(self):
        class HostValue:
            def __hash__(self):
                raise AssertionError('Map must not invoke arbitrary host hashes')

            def __eq__(self, other):
                raise AssertionError('Map must not invoke arbitrary host equality')

        first, second = HostValue(), HostValue()
        self.vm.variables.update(first=first, second=second)
        self.vm.execute('''
            m = New Map; m[first] = 1; m[second] = 2;
            Message(m.Get(first)); Message(m[second]); Message(m.Count());
            m[first] = 3; m.Delete(second); Message(m[first]); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['1', '2', '2', '3', '1'])

    def test_host_metaclass_equality_and_hash_are_not_used_for_identity_keys(self):
        class HostileMeta(type):
            def __eq__(cls, other):
                raise AssertionError('Map must not invoke host metaclass equality')

            def __hash__(cls):
                raise AssertionError('Map must not invoke host metaclass hash')

        class HostValue(metaclass=HostileMeta):
            pass

        first, second = HostValue(), HostValue()
        self.assertTrue(_same_key(first, first))
        self.assertFalse(_same_key(first, second))
        self.vm.variables.update(first=first, second=second)
        self.vm.execute('''
            m = New Map; m.Insert(first, 1); m[second] = 2;
            Message(m.Get(first)); Message(m[second]); Message(m.Count());
            m[first] = 3; m.Insert(second, 4);
            Message(m[first]); Message(m.Get(second)); Message(m.Count());
            m.Delete(first); Message(m[first] = Undefined); Message(m[second]);
            m.Delete(second); m.Delete(first); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['1', '2', '2', '3', '4', '2', 'Да', '4', '0'])

    def test_host_integers_are_identity_keys_and_do_not_coerce_to_bsl_numbers(self):
        # Only language scalar types have value equality. Host integers are
        # intentionally outside that set, even when they compare equal in Python.
        first, second = int("123456789"), int("123456789")
        self.assertIsNot(first, second)
        self.vm.variables.update(first=first, second=second)
        self.vm.execute('''
            m = New Map; m[first] = "first host"; m[second] = "second host";
            m[123456789] = "BSL number";
            Message(m[first]); Message(m[second]); Message(m[123456789]);
            Message(m.Count()); m.Delete(first); Message(m[second]);
            Message(m[123456789]);
        ''')
        self.assertEqual(self.output, ['first host', 'second host', 'BSL number',
                                       '3', 'second host', 'BSL number'])

    def test_collection_values_and_host_calls_preserve_identity(self):
        observed = []
        self.vm.register_function('Observe', lambda *values: observed.append(values))
        self.vm.execute('''
            m = New Map; a = New Array; s = New Structure("Value", 1); child = New Map;
            m["array"] = a; m.Insert("structure", s); m["map"] = child;
            m.Get("array").Add(7); m["structure"].Value = 8; m["map"]["value"] = 9;
            Observe(m, m["array"], m.Get("structure"), m["map"]);
            Message(a[0]); Message(s.Value); Message(child["value"]);
        ''')
        self.assertEqual(self.output, ['7', '8', '9'])
        self.assertEqual(len(observed), 1)
        for actual, variable in zip(observed[0], ['m', 'a', 's', 'child']):
            self.assertIs(actual, self.vm.variables[variable])

    def test_maps_and_other_collections_have_identity_equality_not_deep_equality(self):
        self.vm.execute('''
            first = New Map; second = New Map;
            first["same"] = 1; second["same"] = 1; alias = first;
            Message(first = second); Message(first = alias);
            a = New Array; b = New Array; a.Add(1); b.Add(1); Message(a = b);
            s = New Structure("Value", 1); t = New Structure("Value", 1); Message(s = t);
            values = New Array; values.Add(first);
            Message(values.Find(second) = Undefined); Message(values.Find(alias));
        ''')
        self.assertEqual(self.output, ['Нет', 'Да', 'Нет', 'Нет', 'Да', '0'])

    def test_map_keys_are_never_dot_properties_or_callable_members(self):
        self.vm.execute('''
            m = New Map; m["Name"] = 7; m["Count"] = 8;
            m["Insert"] = 9; m["Количество"] = 10; m["__class__"] = 11;
            Message(m.Count()); Message(m["Count"]); Message((m.Count)());
            Message(m["Insert"]); Message(m["Количество"]); Message(m["__class__"]);
        ''')
        self.assertEqual(self.output, ['5', '8', '5', '9', '10', '11'])
        for code in ['m.Name', 'm.Name = 12', 'm.Name()',
                     'm.Count', 'm.Count = 12', 'm.Insert', 'm.Get',
                     'm.Количество', 'm.__class__']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('m["Name"]'), Decimal(7))
        self.assertEqual(self.vm.execute('m.Count()'), Decimal(5))

    def test_wrong_method_arities_do_not_mutate_map(self):
        self.vm.execute('m = New Map; m["kept"] = 7;')
        cases = ['m.Insert()', 'm.Insert("kept", 8, 9)', 'm.Get()', 'm.Get("kept", 8)',
                 'm.Delete()', 'm.Delete("kept", 8)', 'm.Clear(1)', 'm.Count(1)']
        for code in cases:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)
            self.assertEqual(self.vm.execute('m["kept"]'), Decimal(7))
            self.assertEqual(self.vm.execute('m.Count()'), Decimal(1))

    def test_omitted_host_arguments_keep_existing_subset_boundary(self):
        self.vm.execute('m = New Map; m["kept"] = 7;')
        for code in ['m.Insert(, 8)', 'm.Insert("kept",, 8)',
                     'm.Get(, 8)', 'm.Delete(, 8)', 'New Map(, 8)']:
            with self.subTest(code=code), self.assertRaisesRegex(BSLRuntimeError, 'Пропуск аргументов'):
                self.vm.execute(code)
            self.assertEqual(self.vm.execute('m["kept"]'), Decimal(7))
            self.assertEqual(self.vm.execute('m.Count()'), Decimal(1))

    def test_grouped_bilingual_method_calls_use_normal_dispatch(self):
        self.vm.execute('''
            m = New Map; ((m.Insert))("key", 7);
            Message((m.Get)("key")); Message(((m.Получить))("key"));
            (m.Вставить)("key", 8); Message(m["key"]);
            (m.Delete)("key"); Message((m.Count)());
        ''')
        self.assertEqual(self.output, ['7', '7', '8', '0'])

    def test_index_receiver_key_and_value_are_evaluated_once_left_to_right(self):
        self.vm.execute('''
            Var root, trace; root = New Map; trace = "";
            Function Receiver() trace = trace + "R"; Return root; EndFunction
            Function KeyValue() trace = trace + "K"; Return "key"; EndFunction
            Function Value() trace = trace + "V"; Return 7; EndFunction
            Receiver()[KeyValue()] = Value(); Message(trace); Message(root["key"]);
            trace = ""; Message(Receiver()[KeyValue()]); Message(trace);
            trace = ""; Receiver().Insert(KeyValue(), Value()); Message(trace);
            trace = ""; Message(Receiver().Get(KeyValue())); Message(trace);
            trace = ""; Receiver().Delete(KeyValue()); Message(trace); Message(root.Count());
        ''')
        self.assertEqual(self.output, ['RKV', '7', '7', 'RK', 'RKV', '7', 'RK', 'RK', '0'])

    def test_receiver_and_key_are_captured_before_later_argument_rebindings(self):
        self.vm.execute('''
            Var m, key; m = New Map; original = m; key = "before";
            Function ReplaceMap() m = New Map; Return "key"; EndFunction
            Function ReplaceKey() key = "after"; Return 7; EndFunction
            m[ReplaceMap()] = 1;
            Message(original["key"]); Message(m.Count());
            m[key] = ReplaceKey(); Message(m["before"]); Message(m["after"] = Undefined);
            original = m; m.Insert(ReplaceMap(), 8);
            Message(original["key"]); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['1', '0', '7', 'Да', '8', '0'])

    def test_nested_array_structure_and_map_assignment_evaluates_once(self):
        self.vm.execute('''
            Var root, trace; root = New Structure("Maps", New Array); trace = "";
            root.Maps.Add(New Map); root.Maps[0]["child"] = New Structure("Value", 0);
            Function Receiver() trace = trace + "R"; Return root; EndFunction
            Function Position() trace = trace + "I"; Return 0; EndFunction
            Function KeyValue() trace = trace + "K"; Return "child"; EndFunction
            Function Value() trace = trace + "V"; Return 7; EndFunction
            Receiver().Maps[Position()][KeyValue()].Value = Value();
            Message(trace); Message(root.Maps[0]["child"].Value);
        ''')
        self.assertEqual(self.output, ['RIKV', '7'])

    def test_argument_error_prevents_insertion_without_repeating_side_effects(self):
        self.vm.execute('''
            Var m, trace; m = New Map; trace = "";
            Function KeyValue() trace = trace + "K"; Return "new"; EndFunction
            Function BadValue() trace = trace + "V"; Raise "value failed"; EndFunction
            Try m.Insert(KeyValue(), BadValue()); Except Message("caught"); EndTry;
            Message(trace); Message(m.Count());
            trace = "";
            Try m[KeyValue()] = BadValue(); Except Message("caught index"); EndTry;
            Message(trace); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['caught', 'KV', '0', 'caught index', 'KV', '0'])
        self.assertIsNone(self.vm.locals)

    def test_val_parameters_share_object_mutation_but_isolate_rebinding(self):
        self.vm.execute('''
            Procedure Mutate(Val data)
                data["value"] = 7; data = New Map; data["local"] = 8;
            EndProcedure
            Function Identity(Val data) Return data; EndFunction
            m = New Map; alias = m; Mutate(m);
            Message(m["value"]); Message(m["local"] = Undefined);
            Message(Identity(m) = m); Message(alias = m); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['7', 'Да', 'Да', 'Да', '1'])
        self.assertIsNone(self.vm.locals)

    def test_by_reference_aliases_can_rebind_map_without_rebinding_val_snapshot(self):
        self.vm.execute('''
            Procedure Replace(first, second, Val snapshot)
                first = New Map; first["new"] = 7;
                Message(second["new"]); snapshot["old"] = 8;
            EndProcedure
            m = New Map; original = m; Replace(m, m, m);
            Message(m["new"]); Message(original["old"]);
            Message(m = original); Message(original["new"] = Undefined);
        ''')
        self.assertEqual(self.output, ['7', '7', '8', 'Нет', 'Да'])
        self.assertIsNone(self.vm.locals)

    def test_indexed_routine_arguments_keep_reference_limit_and_val_reads_work(self):
        self.vm.execute('''
            m = New Map; m["value"] = 7;
            Procedure Change(value) value = 8; EndProcedure
            Function Read(Val value) Return value; EndFunction
        ''')
        for argument in ['m["value"]', '(m["value"])']:
            with self.subTest(argument=argument), self.assertRaisesRegex(BSLRuntimeError, 'по ссылке пока'):
                self.vm.execute(f'Change({argument})')
            self.assertEqual(self.vm.execute(f'Read({argument})'), Decimal(7))
        self.assertEqual(self.vm.execute('m["value"]'), Decimal(7))

    def test_foreach_yields_readonly_bilingual_pairs_without_promising_order(self):
        self.vm.execute('''
            m = New Map; m["First"] = 7; m["Второе"] = "ёж";
            For Each pair In m Do
                Message(pair.Key + ":" + pair.Value);
                Message(pair.кЛюЧ + ":" + pair.зНаЧеНиЕ); Message(String(pair));
            EndDo;
        ''')
        self.assertCountEqual(self.output, ['First:7', 'First:7', 'КлючИЗначение',
                                           'Второе:ёж', 'Второе:ёж', 'КлючИЗначение'])

    def test_empty_and_nested_iteration_over_map_array_structure(self):
        self.vm.execute('''
            For Each pair In New Map Do Message("bad"); EndDo;
            m = New Map; m["one"] = New Structure("Items", New Array);
            m["one"].Items.Add(7); m["one"].Items.Add(8);
            For Each pair In m Do
                For Each field In pair.Value Do
                    For Each item In field.Value Do Message(item); EndDo;
                EndDo;
            EndDo;
        ''')
        self.assertEqual(self.output, ['7', '8'])

    def test_iteration_preserves_arbitrary_key_and_value_objects(self):
        observed = []
        self.vm.register_function('Observe', lambda key, value: observed.append((key, value)))
        self.vm.execute('''
            m = New Map; a = New Array; s = New Structure("Value", 7);
            m[a] = s; m[Undefined] = a; m[True] = m; m[1] = False;
            For Each pair In m Do Observe(pair.Key, pair.Value); EndDo;
        ''')
        self.assertEqual(len(observed), 4)
        expected = [(self.vm.variables['a'], self.vm.variables['s']),
                    (None, self.vm.variables['a']), (True, self.vm.variables['m']),
                    (Decimal(1), False)]
        for key, value in expected:
            matches = [(actual_key, actual_value) for actual_key, actual_value in observed
                       if _same_key(key, actual_key)]
            self.assertEqual(len(matches), 1)
            self.assertIs(matches[0][1], value)

    def test_iteration_pair_properties_cannot_be_rebound(self):
        self.vm.execute('m = New Map; m["key"] = 7; For Each pair In m Do EndDo;')
        for code in ['pair.Key = "changed"', 'pair.Value = 8',
                     'pair.Ключ = "changed"', 'pair.Значение = 8']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)
            self.assertEqual(self.vm.execute('pair.Key'), 'key')
            self.assertEqual(self.vm.execute('pair.Value'), Decimal(7))
            self.assertEqual(self.vm.execute('m["key"]'), Decimal(7))

    def test_iteration_pairs_are_identity_keys_not_equivalent_value_keys(self):
        # Pairs-as-keys identity is an interpreter contract, not native verification.
        for constructor in ['New Map', 'New Structure("entry", 7)']:
            with self.subTest(constructor=constructor):
                self.output.clear()
                self.vm.execute(f'''
                    source = {constructor}; source["entry"] = 7;
                    For Each pair In source Do saved = pair; EndDo;
                    m = New Map; m[saved] = "kept";
                    For Each pair In source Do fresh = pair; EndDo;
                    Message(m.Get(saved)); Message(m[fresh] = Undefined);
                    Message(saved = fresh); Message(saved.Key = fresh.Key);
                    Message(saved.Value = fresh.Value);
                    source["entry"] = 8;
                    Message(m[saved]); Message(saved.Value); Message(source["entry"]);
                    m.Insert(saved, "replaced"); m.Delete(fresh);
                    Message(m[saved]); Message(m.Count());
                    m.Delete(saved); Message(m.Count());
                ''')
                self.assertEqual(self.output, ['kept', 'Да', 'Нет', 'Да', 'Да',
                                               'kept', '7', '8', 'replaced', '1', '0'])

    def test_pair_key_and_value_collections_remain_mutable_aliases(self):
        self.vm.execute('''
            m = New Map; key = New Array; value = New Structure("Value", 1);
            m[key] = value;
            For Each pair In m Do pair.Key.Add(7); pair.Value.Value = 8; EndDo;
            Message(key[0]); Message(value.Value); Message(m[key].Value);
            Message(pair.Key = key); Message(pair.Value = value);
        ''')
        self.assertEqual(self.output, ['7', '8', '8', 'Да', 'Да'])

    def test_iteration_pair_snapshots_value_and_existing_updates_are_allowed(self):
        self.vm.execute('''
            m = New Map; m["one"] = 1; m["two"] = 2; visited = 0;
            For Each pair In m Do
                If visited = 0 Then
                    Message(pair.Value < 10); m["one"] = 11; m.Insert("two", 12);
                    Message(pair.Value < 10);
                Else Message(pair.Value > 10); EndIf;
                visited = visited + 1;
            EndDo;
            Message(visited); Message(m["one"]); Message(m["two"]);
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да', '2', '11', '12'])

    def test_composition_changes_during_iteration_raise_catchable_subset_error(self):
        for change in ['m.Insert("added", 3)', 'm["added"] = 3',
                       'm.Delete(pair.Key)', 'm.Clear()']:
            with self.subTest(change=change):
                self.output.clear()
                self.vm.execute(f'''
                    m = New Map; m["one"] = 1; m["two"] = 2;
                    Try For Each pair In m Do {change}; EndDo;
                    Except Message("caught"); EndTry; Message("after");
                ''')
                self.assertEqual(self.output, ['caught', 'after'])

    def test_iteration_detects_delete_reinsert_even_if_size_is_unchanged(self):
        self.vm.execute('''
            m = New Map; m["one"] = 1; m["two"] = 2;
            Try
                For Each pair In m Do m.Delete(pair.Key); m[pair.Key] = pair.Value; EndDo;
            Except Message("caught"); EndTry;
            Message(m.Count());
        ''')
        self.assertEqual(self.output, ['caught', '2'])

    def test_composition_change_then_break_does_not_advance_iterator(self):
        self.vm.execute('''
            m = New Map; m["one"] = 1; m["two"] = 2;
            For Each pair In m Do m.Clear(); Break; EndDo; Message(m.Count());
        ''')
        self.assertEqual(self.output, ['0'])

    def test_delete_absent_does_not_invalidate_iteration(self):
        self.vm.execute('''
            m = New Map; m[True] = 1; m["one"] = 2; visited = 0;
            For Each pair In m Do
                m.Delete(False); m.Delete(1); m.Delete("missing");
                visited = visited + 1;
            EndDo;
            Message(visited); Message(m.Count());
        ''')
        self.assertEqual(self.output, ['2', '2'])

    def test_python_attributes_are_not_exposed_on_maps_pairs_or_methods(self):
        self.vm.execute('m = New Map; m["key"] = 7; For Each pair In m Do EndDo; method = Message;')
        for receiver in ['m', 'pair', 'method']:
            for name in ['__class__', '__dict__', '__str__', '_items', '_version',
                         'items', 'function', 'get_member', 'get_method', 'set_member',
                         'reference_parameters', 'parameters']:
                for suffix in ['', '()']:
                    code = f'{receiver}.{name}{suffix}'
                    with self.subTest(code=code), self.assertRaises(BSLError):
                        self.vm.execute(code)

    def test_runtime_diagnostics_preserve_explicit_source_line_and_column(self):
        self.vm.execute('m = New Map; m["kept"] = 7;')
        for code, column in [('m.Get();', 3), ('m.Missing;', 4), ('m.Count(1);', 3)]:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError) as caught:
                self.vm.execute('\n  ' + code, 'map-error.bsl')
            self.assertEqual((caught.exception.source, caught.exception.line,
                              caught.exception.column), ('map-error.bsl', 2, column))
            self.assertEqual(self.vm.execute('m["kept"]'), Decimal(7))

    def test_caught_method_error_restores_frames_and_keeps_prior_mutations(self):
        self.vm.execute('''
            Procedure Fail(Val m)
                m["written"] = 42; m.Get();
            EndProcedure
            m = New Map;
            Try Fail(m); Except Message("caught"); Message(m["written"]); EndTry;
            m["after"] = 7; Message(m["after"]);
        ''')
        self.assertEqual(self.output, ['caught', '42', '7'])
        self.assertIsNone(self.vm.locals)

    def test_uncaught_method_error_keeps_definition_location_and_restores_frame(self):
        self.vm.execute('Procedure Fail(Val m)\n m["written"] = 42;\n m.Get();\nEndProcedure',
                        'definitions.bsl')
        self.vm.execute('m = New Map;')
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('Fail(m)', 'caller.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), ('definitions.bsl', 3))
        self.assertEqual(self.vm.execute('m["written"]'), Decimal(42))
        self.assertIsNone(self.vm.locals)

    def test_existing_structure_and_array_index_contracts_are_unchanged(self):
        self.vm.execute('s = New Structure("Known", 7); a = New Array(1); a[0] = 8;')
        for code in ['s["Missing"]', 's["Missing"] = 9', 's[0]', 's[True]',
                     'a["0"]', 'a[True]', 'a[1]', 'a[1] = 9']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)
        self.vm.execute('s.Insert("kNOWN", 9);')
        self.assertEqual(self.vm.execute('s["KNOWN"]'), Decimal(9))
        self.assertEqual(self.vm.execute('s.Count()'), Decimal(1))
        self.assertEqual(self.vm.execute('a[0]'), Decimal(8))


def _same_key(left, right):
    """Independent reference equality: typed primitives, object identity otherwise."""
    kind = type(left)
    if kind is type(None) or kind is bool or kind is Decimal or kind is str:
        return type(left) is type(right) and left == right
    return left is right


class MapReferenceModelTests(unittest.TestCase):
    def test_deterministic_randomized_operations_match_reference_model(self):
        vm = Interpreter(output=lambda text: None)
        vm.execute('m = New Map; another = New Map;')
        first_array, second_array = BSLArray(), BSLArray()
        first_structure, second_structure = BSLStructure(), BSLStructure()
        keys = [None, False, True, Decimal(0), Decimal('-0.00'), Decimal(1),
                Decimal('1.00'), Decimal('-7.5'), '', 'key', 'Key', ' key ',
                'ёж', 'Ёж', first_array, second_array, first_structure,
                second_structure, vm.variables['m'], vm.variables['another'], [], [], {}, {}]
        values = [None, False, True, Decimal(0), Decimal('123.45'), '', 'value',
                  first_array, first_structure, vm.variables['m'], {}]
        model = []
        observed = []
        vm.register_function('Observe', lambda key, value: observed.append((key, value)))
        rng = random.Random(0x1C14)

        def position(key):
            return next((index for index, (stored, _) in enumerate(model)
                         if _same_key(stored, key)), None)

        def put(key, value):
            index = position(key)
            if index is None:
                model.append((key, value))
            else:
                model[index] = (key, value)

        def assert_value(actual, expected):
            kind = type(expected)
            if kind is type(None) or kind is bool or kind is Decimal or kind is str:
                self.assertIs(type(actual), type(expected))
                self.assertEqual(actual, expected)
            else:
                self.assertIs(actual, expected)

        def verify():
            count = vm.execute('m.Count()')
            self.assertIs(type(count), Decimal)
            self.assertEqual(count, Decimal(len(model)))
            observed.clear()
            vm.execute('For Each pair In m Do Observe(pair.Key, pair.Value); EndDo;')
            self.assertEqual(len(observed), len(model))
            for key, value in model:
                matches = [actual for actual_key, actual in observed if _same_key(actual_key, key)]
                self.assertEqual(len(matches), 1)
                assert_value(matches[0], value)
            for key in keys:
                vm.variables['key'] = key
                index = position(key)
                expected = None if index is None else model[index][1]
                assert_value(vm.execute('m.Get(key)'), expected)
                assert_value(vm.execute('m[key]'), expected)

        # Ensure every key category occurs even before the randomized sequence.
        for index, key in enumerate(keys):
            value = values[index % len(values)]
            vm.variables.update(key=key, value=value)
            vm.execute('m.Insert(key, value)')
            put(key, value)
        verify()
        operations = ['insert', 'index', 'delete', 'get', 'clear', 'mutate']
        weights = [28, 28, 18, 14, 3, 9]
        for step in range(300):
            operation = rng.choices(operations, weights=weights)[0]
            key, value = rng.choice(keys), rng.choice(values)
            vm.variables.update(key=key, value=value)
            with self.subTest(step=step, operation=operation, key_type=type(key).__name__):
                if operation in ('insert', 'index'):
                    vm.execute('m.Insert(key, value)' if operation == 'insert' else 'm[key] = value;')
                    put(key, value)
                elif operation == 'delete':
                    vm.execute('m.Delete(key)')
                    index = position(key)
                    if index is not None:
                        model.pop(index)
                elif operation == 'clear':
                    vm.execute('m.Clear()')
                    model.clear()
                elif operation == 'get':
                    index = position(key)
                    assert_value(vm.execute('m.Get(key)'), None if index is None else model[index][1])
                else:
                    first_array.add(Decimal(step))
                    first_structure.insert('Step', Decimal(step))
                    keys[-4].append(step)
                    keys[-2]['step'] = step
                verify()


class MapImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def load(self, module, main, source=None):
        helper = self.directory / 'Helpers.bsl'
        helper.write_text(module, encoding='utf-8')
        path = self.directory / 'Main.bsl'
        path.write_text('// #Import Helpers.bsl\n' + main, encoding='utf-8')
        self.vm.execute(path.read_text(encoding='utf-8'), source or str(path))
        return helper

    def test_imported_exports_return_shared_maps_and_preserve_key_identity(self):
        self.load('''
            Var data, key; data = New Map; key = New Array; data[key] = 7;
            Function GetData() Export Return data; EndFunction
            Function GetKey() Export Return key; EndFunction
            Function Read() Export Return data[key]; EndFunction
            Procedure Fill(Val m, Val k) Export m[k] = data; EndProcedure
        ''', '''
            m = Helpers.GetData(); key = Helpers.GetKey(); m[key] = 42;
            Message(Helpers.Read()); Message(Helpers.GetData()[key]);
            local = New Map; Helpers.Fill(local, key);
            Message(local[key] = m); Message(local[New Array] = Undefined);
        ''')
        self.assertEqual(self.output, ['42', '42', 'Да', 'Да'])
        self.assertIsNone(self.vm.locals)

    def test_imported_val_rebinding_and_reference_forwarding_keep_alias_rules(self):
        self.load('''
            Procedure Inner(output) output = New Map; output["new"] = 42; EndProcedure
            Procedure Fill(Val data, output) Export
                data["mutated"] = 7; data = New Map; Inner(output);
            EndProcedure
        ''', '''
            m = New Map; alias = m; result = Undefined; Helpers.Fill(m, result);
            Message(m["mutated"]); Message(alias = m); Message(result["new"]);
        ''')
        self.assertEqual(self.output, ['7', 'Да', '42'])
        self.assertIsNone(self.vm.locals)

    def test_imported_maps_do_not_expose_private_module_state(self):
        self.load('''
            Var data; data = New Map; data["value"] = 7;
            Function Public() Export Return data; EndFunction
            Function Private() Return data; EndFunction
        ''', 'm = Helpers.Public();')
        for code in ['Helpers.data', 'Helpers.data["value"]', 'Helpers.data = m',
                     'Helpers.Private()', 'Helpers.__dict__', 'Helpers.Public.__class__']:
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('Helpers.Public()["value"]'), Decimal(7))

    def test_imported_error_uses_resolved_module_path_and_keeps_prior_mutations(self):
        alias = self.directory / 'alias'
        alias.mkdir()
        self.directory = alias / '..'
        helper = self.load('Procedure Fail(Val m) Export\n m["written"] = 42;\n m.Get();\nEndProcedure',
                           'm = New Map;')
        self.assertNotEqual(str(helper), str(helper.resolve()))
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('Helpers.Fail(m)', 'caller.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), (str(helper.resolve()), 3))
        self.assertEqual(self.vm.execute('m["written"]'), Decimal(42))
        self.assertIsNone(self.vm.locals)
        self.assertIsNone(self.vm.imports['helpers'].interpreter.locals)

    def test_relative_main_source_resolves_imported_error_but_keeps_main_label(self):
        # Windows cannot form a relative path between a checkout and a system
        # temporary directory on different drives. Keep this fixture beside cwd.
        same_drive = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(same_drive.cleanup)
        self.directory = Path(same_drive.name)
        source = os.path.relpath(self.directory / 'Main.bsl', Path.cwd())
        self.assertFalse(Path(source).is_absolute())
        helper = self.load('Function Fail() Export\n m = New Map;\n Return m.Get();\nEndFunction',
                           'm = New Map;', source=source)
        with self.assertRaises(BSLRuntimeError) as imported:
            self.vm.execute('Helpers.Fail()', source)
        self.assertEqual((imported.exception.source, imported.exception.line),
                         (str(helper.resolve()), 3))
        with self.assertRaises(BSLRuntimeError) as local:
            self.vm.execute('\nm.Get()', source)
        self.assertEqual((local.exception.source, local.exception.line), (source, 2))
        self.assertIsNone(self.vm.locals)

    def test_symlink_source_resolves_imported_map_error_to_real_module(self):
        real_directory = self.directory / 'real'
        real_directory.mkdir()
        link = self.directory / 'linked'
        try:
            link.symlink_to(real_directory, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Symlinks unavailable: {error}')
        self.directory = real_directory
        source = str(link / 'Main.bsl')
        helper = self.load('Procedure Fail(Val m) Export\n m["written"] = 42;\n m.Count(1);\nEndProcedure',
                           'm = New Map;', source=source)
        with self.assertRaises(BSLRuntimeError) as caught:
            self.vm.execute('Helpers.Fail(m)', source)
        self.assertEqual((caught.exception.source, caught.exception.line), (str(helper.resolve()), 3))
        self.assertEqual(self.vm.execute('m["written"]'), Decimal(42))
        self.assertIsNone(self.vm.locals)
        self.assertIsNone(self.vm.imports['helpers'].interpreter.locals)

    def test_imported_error_is_catchable_and_following_export_remains_usable(self):
        self.load('''
            Procedure Fail(Val m) Export m["written"] = 42; m.Delete(); EndProcedure
            Function Count(Val m) Export Return m.Count(); EndFunction
        ''', '''
            m = New Map;
            Try Helpers.Fail(m); Except Message(m["written"]); EndTry;
            Message(Helpers.Count(m)); m.Clear(); Message(Helpers.Count(m));
        ''')
        self.assertEqual(self.output, ['42', '1', '0'])
        self.assertIsNone(self.vm.locals)
        self.assertIsNone(self.vm.imports['helpers'].interpreter.locals)


if __name__ == '__main__':
    unittest.main()
