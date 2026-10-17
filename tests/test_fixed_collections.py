"""Fixed collection contracts, including native 1C regressions at 1c4e20f.

Direct mutable arrays freeze recursively; structure/map values and object keys
remain aliases. Pair iteration checks deliberately avoid a native order promise.
Cyclic direct array paths remain a catchable, unverified subset limitation.
"""

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.structures import BSLFixedStructure, BSLStructure
from yadinassi.values import BSLArray, BSLFixedArray


class FixedCollectionTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def make_collections(self):
        self.vm.execute('''
            array = New Array; array.Add(7);
            structure = New Structure("Known", 7);
            map = New Map; map["Known"] = 7;
            fa = New FixedArray(array);
            fs = New FixedStructure(structure);
            fm = New FixedMap(map);
        ''')

    def test_source_constructors_are_bilingual_case_insensitive_and_presentable(self):
        cases = [('Array', 'FixedArray', 'ФиксированныйМассив'),
                 ('Structure', 'FixedStructure', 'ФиксированнаяСтруктура'),
                 ('Map', 'FixedMap', 'ФиксированноеСоответствие')]
        for source, english, russian in cases:
            for name in [english, english.upper(), russian, russian.lower()]:
                with self.subTest(name=name):
                    self.vm.execute(f'fixed = Новый {name}(New {source});')
                    self.assertEqual(self.vm.execute('fixed.cOuNt()'), Decimal(0))
                    self.assertIs(type(self.vm.execute('fixed.Количество()')), Decimal)
                    self.assertEqual(self.vm.execute('String(fixed)'), russian)
                    self.assertIs(self.vm.execute(f'(TypeOf(fixed) = Type("{english}"))'), True)

    def test_fixed_structure_empty_and_string_constructors(self):
        for expression in ['New FixedStructure', 'New FixedStructure()',
                           'Новый ФиксированнаяСтруктура',
                           'New FixedStructure("")']:
            with self.subTest(expression=expression):
                self.assertEqual(self.vm.execute(f'({expression}).Count()'), Decimal(0))
        self.vm.execute('''
            fs = New FixedStructure("Name,Ёж,Empty", "value", 7);
            Message(fs.nAME); Message(fs["ёж"]); Message(fs.Empty = Undefined);
            Message(fs.Count());
        ''')
        self.assertEqual(self.output, ['value', '7', 'Да', '3'])

    def test_fixed_structure_string_constructor_matches_structure_key_rules(self):
        # These key-list choices are the interpreter's established subset.
        self.vm.execute('''
            child = New Array;
            fs = New FixedStructure(" First, , first,Items, ", 1, 2, child);
            Message(fs.Count()); Message(fs.FIRST); fs.Items.Add(9);
            Message(child[0]);
            For Each pair In fs Do Message(pair.Key); EndDo;
        ''')
        self.assertEqual(self.output[:3], ['2', '2', '9'])
        self.assertCountEqual(self.output[3:], ['first', 'Items'])
        for keys in ['"bad-key"', '"1first"', '"two words"', '"a.b"']:
            with self.subTest(keys=keys), self.assertRaises(BSLRuntimeError):
                self.vm.execute(f'New FixedStructure({keys})')

    def test_invalid_constructors_preserve_existing_assignment(self):
        self.make_collections()
        cases = {
            'fa': ['New FixedArray', 'New FixedArray()', 'New FixedArray(1)',
                   'New FixedArray(True)', 'New FixedArray(Undefined)',
                   'New FixedArray("x")', 'New FixedArray(structure)',
                   'New FixedArray(map)', 'New FixedArray(array, array)'],
            'fs': ['New FixedStructure(1)', 'New FixedStructure(True)',
                   'New FixedStructure(Undefined)', 'New FixedStructure(array)',
                   'New FixedStructure(map)', 'New FixedStructure(structure, 1)'],
            'fm': ['New FixedMap', 'New FixedMap()', 'New FixedMap(1)',
                   'New FixedMap(True)', 'New FixedMap(Undefined)',
                   'New FixedMap("x")', 'New FixedMap(array)',
                   'New FixedMap(structure)', 'New FixedMap(map, map)'],
        }
        for name, expressions in cases.items():
            original = self.vm.variables[name]
            for expression in expressions:
                with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                    self.vm.execute(f'{name} = {expression}')
                self.assertIs(self.vm.variables[name], original)
                self.assertEqual(self.vm.execute(f'{name}.Count()'), Decimal(1))

    def test_constructor_source_is_evaluated_once(self):
        self.vm.execute('''
            Var calls, array, structure, map;
            calls = 0; array = New Array; structure = New Structure; map = New Map;
            Function Source(Val value) calls = calls + 1; Return value; EndFunction
            fa = New FixedArray(Source(array));
            fs = New FixedStructure(Source(structure));
            fm = New FixedMap(Source(map)); Message(calls);
        ''')
        self.assertEqual(self.output, ['3'])

    def test_array_reads_bounds_find_and_strict_typed_equality(self):
        self.vm.execute('''
            a = New Array; a.Add(True); a.Add(1); a.Add("1"); a.Add(Undefined);
            fa = New FixedArray(a);
            Message(fa.Количество()); Message(fa.ВГраница());
            Message(fa[0]); Message(fa.Получить(1)); Message(fa.gEt(2));
            Message(fa.Найти(True)); Message(fa.Find(1)); Message(fa.Find("1"));
            Message(fa.Find(Undefined)); Message(fa.Find(False) = Undefined);
            empty = New FixedArray(New Array); Message(empty.UBound());
            Message(empty.Find(Undefined) = Undefined);
        ''')
        self.assertEqual(self.output, ['4', '3', 'Да', '1', '1', '0', '1', '2',
                                       '3', 'Да', '-1', 'Да'])
        self.assertIs(type(self.vm.execute('fa.UBound()')), Decimal)
        self.assertIs(type(self.vm.execute('fa.Find(1)')), Decimal)

    def test_array_indexes_are_integer_numbers_in_bounds(self):
        self.make_collections()
        for index in ['-1', '1', '1.5', 'True', '"0"', 'Undefined', 'New Array']:
            for expression in [f'fa[{index}]', f'fa.Get({index})']:
                with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                    self.vm.execute(expression)
        self.assertEqual(self.vm.execute('fa.Get(0)'), Decimal(7))

    def test_array_find_keeps_mutable_structure_and_map_identity_behavior(self):
        self.vm.execute('''
            record = New Structure("Known", 7); map = New Map; map["Known"] = 7;
            source = New Array; source.Add(record); source.Add(map);
            fixed = New FixedArray(source);
            Message(fixed.Find(record)); Message(fixed.Найти(map));
            Message(fixed.Find(New Structure("Known", 7)) = Undefined);
            other = New Map; other["Known"] = 7; Message(fixed.Find(other) = Undefined);
            fixed[0].Known = 8; fixed[1]["Known"] = 9;
            Message(record.Known); Message(map["Known"]);
            Message(fixed.Find(record)); Message(fixed.Find(map));
        ''')
        self.assertEqual(self.output, ['0', '1', 'Да', 'Да', '8', '9', '0', '1'])

    def test_read_method_aliases_are_case_insensitive_for_all_fixed_types(self):
        self.make_collections()
        self.vm.execute('''
            Message(fa.cOuNt()); Message(fa.кОлИчЕсТвО());
            Message(fa.uBoUnD()); Message(fa.вГрАнИцА());
            Message(fa.gEt(0)); Message(fa.пОлУчИтЬ(0));
            Message(fa.fInD(7)); Message(fa.нАйТи(7));
            Message(fs.cOuNt()); Message(fs.кОлИчЕсТвО());
            Message(fs.pRoPeRtY("Known")); Message(fs.сВоЙсТвО("Known"));
            Message(fm.cOuNt()); Message(fm.кОлИчЕсТвО());
            Message(fm.gEt("Known")); Message(fm.пОлУчИтЬ("Known"));
        ''')
        self.assertEqual(self.output, ['1', '1', '0', '0', '7', '7', '0', '0',
                                       '1', '1', 'Да', 'Да', '1', '1', '7', '7'])

    def test_array_snapshot_is_independent_of_source_top_level_mutation(self):
        self.vm.execute('''
            a = New Array; a.Add(7); a.Add(8); fa = New FixedArray(a);
            a[0] = 70; a.Delete(1); a.Add(9); a.Clear();
            Message(fa.Count()); Message(fa[0]); Message(fa[1]);
        ''')
        self.assertEqual(self.output, ['2', '7', '8'])

    def test_array_copy_back_recursively_converts_direct_nested_fixed_arrays(self):
        self.vm.execute('''
            leaf = New Array; leaf.Add(7); fixedLeaf = New FixedArray(leaf);
            branch = New Array; branch.Add(fixedLeaf); fixedBranch = New FixedArray(branch);
            root = New Array; root.Add(fixedBranch); fixedRoot = New FixedArray(root);
            copy = New Array(fixedRoot);
            Message(TypeOf(copy) = Type("Array"));
            Message(TypeOf(copy[0]) = Type("Array"));
            Message(TypeOf(copy[0][0]) = Type("Array"));
            copy[0][0][0] = 8; copy[0][0].Add(9); copy[0].Add(10); copy.Add(11);
            Message(copy.Count()); Message(copy[0].Count()); Message(copy[0][0].Count());
            Message(copy[0][0][0]); Message(fixedRoot[0][0][0]);
            Message(fixedRoot.Count()); Message(fixedRoot[0].Count());
            Message(fixedRoot[0][0].Count());
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да', '2', '2', '2',
                                       '8', '7', '1', '1', '1'])

    def test_array_copy_back_copies_each_repeated_fixed_array_occurrence(self):
        # Native nested.copy-back-second and nested.fixed-leaf both remain 11.
        self.vm.execute('''
            leaf = New Array; leaf.Add(11); fixedLeaf = New FixedArray(leaf);
            branch = New Array; branch.Add(fixedLeaf); branch.Add(fixedLeaf);
            fixedBranch = New FixedArray(branch);
            root = New Array; root.Add(fixedBranch); root.Add(fixedBranch);
            fixedRoot = New FixedArray(root); copy = New Array(fixedRoot);
            copy[0][0][0] = 12; copy[0][0].Add(13); copy[0].Add(14);
            Message(copy[0][1][0]); Message(copy[1][0][0]); Message(copy[1][1][0]);
            Message(copy[1].Count()); Message(copy[0][1].Count());
            Message(fixedRoot[0][0][0]); Message(fixedLeaf[0]);
        ''')
        self.assertEqual(self.output, ['11', '11', '11', '2', '1', '11', '11'])
        self.assertIs(self.vm.execute('fixedRoot[0]'), self.vm.variables['fixedbranch'])
        self.assertIs(self.vm.execute('fixedRoot[1]'), self.vm.variables['fixedbranch'])
        self.assertIs(self.vm.execute('fixedRoot[0][0]'), self.vm.variables['fixedleaf'])
        self.assertIsNot(self.vm.execute('copy[0]'), self.vm.execute('copy[1]'))
        leaves = [self.vm.execute(f'copy[{branch}][{leaf}]')
                  for branch in range(2) for leaf in range(2)]
        self.assertEqual(len({id(leaf) for leaf in leaves}), 4)

    def test_array_copy_back_does_not_traverse_non_array_collection_values(self):
        self.vm.execute('''
            leaf = New FixedArray(New Array(1));
            record = New Structure("Leaf", leaf); map = New Map; map["Leaf"] = leaf;
            root = New Array; root.Add(record); root.Add(map);
            fixedRoot = New FixedArray(root); copy = New Array(fixedRoot);
            Message(TypeOf(copy[0].Leaf) = Type("FixedArray"));
            Message(TypeOf(copy[1]["Leaf"]) = Type("FixedArray"));
            copy[0].Insert("Extra", 7); copy[1]["Extra"] = 8;
            Message(record.Extra); Message(map["Extra"]);
        ''')
        self.assertEqual(self.output, ['Да', 'Да', '7', '8'])
        self.assertIs(self.vm.execute('fixedRoot[0]'), self.vm.variables['record'])
        self.assertIs(self.vm.execute('copy[0]'), self.vm.variables['record'])
        self.assertIs(self.vm.execute('copy[1]'), self.vm.variables['map'])

    def test_structure_snapshot_preserves_key_spelling_and_casefold_lookup(self):
        self.vm.execute('''
            s = New Structure("MiXeD,Ёж", 7, 8); fs = New FixedStructure(s);
            s.Insert("MIXED", 70); s.Delete("Ёж"); s.Insert("Other", 9); s.Clear();
            Message(fs.mixed); Message(fs["ЁЖ"]); Message(fs.Count());
            Message(fs.Свойство("mixed")); Message(fs.Property("other"));
            For Each pair In fs Do Message(pair.Key); EndDo;
        ''')
        self.assertEqual(self.output[:5], ['7', '8', '2', 'Да', 'Нет'])
        self.assertCountEqual(self.output[5:], ['MiXeD', 'Ёж'])

    def test_structure_property_outputs_keep_reference_and_missing_contracts(self):
        self.vm.execute('''
            child = New Array; fs = New FixedStructure("Known,Empty,Items", 7, Undefined, child);
            Var result;
            Message(fs.Property(" known ", result)); Message(result);
            Message(fs.Свойство("Empty", result)); Message(result = Undefined);
            result = 99; Message(fs.Property("Missing", result)); Message(result = Undefined);
            ((fs.Property))("Items", result); result.Add(9); Message(child[0]);
            Message(fs.Property("Known", 0)); Message(fs.Property("Known", 1 + 1));
        ''')
        self.assertEqual(self.output, ['Да', '7', 'Да', 'Да', 'Нет', 'Да', '9', 'Да', 'Да'])
        self.assertIs(self.vm.variables['result'], self.vm.variables['child'])

    def test_structure_property_output_can_rebind_receiver_and_forward_reference(self):
        self.vm.execute('''
            Procedure Read(Val fixed, result) fixed.Property("Known", result); EndProcedure
            Procedure Outer(Val fixed, result, Val local)
                Read(fixed, result); Read(fixed, local); Message(local);
            EndProcedure
            fs = New FixedStructure("Known", 7); alias = fs; x = 1; y = 2;
            Outer(fs, x, y); Message(x); Message(y);
            Message(fs.Property("Known", fs)); Message(fs); Message(alias.Known);
        ''')
        self.assertEqual(self.output, ['7', '7', '2', 'Да', '7', '7'])
        self.assertIsNone(self.vm.locals)

    def test_structure_property_errors_preserve_output_and_reference_boundaries(self):
        self.make_collections()
        self.vm.execute('result = 99; a = New Array(1); holder = New Structure("Value", 99);')
        for expression in ['fs.Property(1, result)', 'fs.Property("bad-key", result)',
                           'fs.Property("Known", (result))', 'fs.Property("Known", a[0])',
                           'fs.Property("Known", holder.Value)',
                           'fs.Property("Known", result, 1)', 'fs.Property()']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
            self.assertEqual(self.vm.variables['result'], Decimal(99))
            self.assertEqual(self.vm.execute('fs.Known'), Decimal(7))
        with self.assertRaisesRegex(BSLError, 'не определена'):
            self.vm.execute('fs.Property("Known", undeclared)')
        self.assertNotIn('undeclared', self.vm.variables)

    def test_structure_unknown_and_invalid_properties_do_not_create_entries(self):
        self.make_collections()
        for expression in ['fs.Missing', 'fs["Missing"]', 'fs["bad-key"]',
                           'fs[" Known "]', 'fs[0]', 'fs[True]', 'fs[Undefined]']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        self.assertEqual(self.vm.execute('fs.Count()'), Decimal(1))
        self.assertIs(self.vm.execute('fs.Property("Missing")'), False)

    def test_structure_method_property_collisions_are_separate_and_readonly(self):
        self.vm.execute('''
            fs = New FixedStructure("Count,Property,Insert,Количество", 17, 18, 19, 20);
            Message(fs.Count); Message(fs.Count()); Message((fs.Count)());
            Message(fs.Property); Message(fs.Property("Count")); Message(fs.Insert);
            Message(fs.Количество); Message(fs.Количество());
        ''')
        self.assertEqual(self.output, ['17', '4', '4', '18', 'Да', '19', '20', '4'])
        for expression in ['fs.Count = 8', 'fs["Property"] = 8', 'fs.Insert("Extra", 8)',
                           '(fs.Insert)("Extra", 8)']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        self.assertEqual(self.vm.execute('fs.Count'), Decimal(17))
        self.assertEqual(self.vm.execute('fs.Count()'), Decimal(4))

    def test_structure_snapshot_and_copy_back_are_shallow(self):
        self.vm.execute('''
            child = New Array; record = New Structure("Value", 1); nested = New Map;
            s = New Structure("Items,Record,Nested", child, record, nested);
            fs = New FixedStructure(s); copy = New Structure(fs);
            fs.Items.Add(7); copy.Record.Value = 8; copy.Nested["value"] = 9;
            Message(child[0]); Message(record.Value); Message(nested["value"]);
            copy.Items = New Array; copy.Insert("Extra", 2); copy.Delete("Record");
            Message(fs.Count()); Message(fs.Items.Count()); Message(fs.Record.Value);
            s.Clear(); Message(fs.Count()); Message(copy.Count());
        ''')
        self.assertEqual(self.output, ['7', '8', '9', '3', '1', '8', '3', '3'])
        self.assertIs(self.vm.execute('fs.Items'), self.vm.variables['child'])
        self.assertIs(self.vm.execute('fs.Record'), self.vm.variables['record'])
        self.assertIs(self.vm.execute('fs.Nested'), self.vm.variables['nested'])
        self.assertIs(self.vm.execute('copy.Nested'), self.vm.variables['nested'])

    def test_map_snapshot_and_copy_back_are_shallow(self):
        self.vm.execute('''
            child = New Array; record = New Structure("Value", 1); nested = New Map;
            m = New Map; m["items"] = child; m["record"] = record; m["nested"] = nested;
            fm = New FixedMap(m); copy = New Map(fm);
            fm["items"].Add(7); copy["record"].Value = 8; copy["nested"]["value"] = 9;
            Message(child[0]); Message(record.Value); Message(nested["value"]);
            copy["items"] = New Array; copy.Insert("extra", 2); copy.Delete("record");
            m.Clear(); Message(fm.Count()); Message(fm["items"].Count());
            Message(fm["record"].Value); Message(copy.Count());
        ''')
        self.assertEqual(self.output, ['7', '8', '9', '3', '1', '8', '3'])
        self.assertIs(self.vm.execute('fm["items"]'), self.vm.variables['child'])
        self.assertIs(self.vm.execute('fm["record"]'), self.vm.variables['record'])
        self.assertIs(self.vm.execute('copy["nested"]'), self.vm.variables['nested'])

    def test_map_snapshot_is_independent_of_source_replacement_deletion_and_insert(self):
        self.vm.execute('''
            m = New Map; m["Known"] = 7; m["Empty"] = Undefined;
            fm = New FixedMap(m); m["Known"] = 70; m.Delete("Empty"); m["New"] = 8;
            Message(fm.Получить("Known")); Message(fm.Get("Empty") = Undefined);
            Message(fm.Get("New") = Undefined); Message(fm.Count());
            m.Clear(); Message(fm["Known"]); Message(fm.Количество());
        ''')
        self.assertEqual(self.output, ['7', 'Да', 'Да', '2', '7', '2'])

    def test_fixed_map_missing_index_errors_but_get_and_present_undefined_are_readable(self):
        # Native fixed-map.missing versus fixed-map.get-missing.
        self.vm.execute('''
            present = New FixedArray(New Array); absent = New FixedArray(New Array);
            values = New Map; values["Known"] = 7; values["Empty"] = Undefined;
            values[present] = Undefined; snapshot = New FixedMap(values);
            alias = snapshot; copy = New Map(snapshot); result = 99;
        ''')
        for receiver in ['snapshot', 'alias']:
            for key in ['"Missing"', 'False', '1', 'Undefined', 'absent']:
                with self.subTest(receiver=receiver, key=key):
                    with self.assertRaises(BSLRuntimeError):
                        self.vm.execute(f'result = {receiver}[{key}]')
                    self.assertEqual(self.vm.variables['result'], Decimal(99))
                    for method in ['Get', 'Получить', 'gEt', 'пОлУчИтЬ']:
                        self.assertIsNone(self.vm.execute(f'{receiver}.{method}({key})'))
                    self.assertEqual(self.vm.execute(f'{receiver}.Count()'), Decimal(3))
                    self.assertEqual(self.vm.execute(f'{receiver}["Known"]'), Decimal(7))
                    self.assertIsNone(self.vm.execute(f'{receiver}["Empty"]'))
                    self.assertIsNone(self.vm.execute(f'{receiver}[present]'))
        for receiver in ['values', 'copy']:
            self.assertIsNone(self.vm.execute(f'{receiver}["Missing"]'))
            self.assertIsNone(self.vm.execute(f'{receiver}[absent]'))
            self.assertEqual(self.vm.execute(f'{receiver}.Count()'), Decimal(3))
        self.vm.execute('''
            For Each pair In snapshot Do
                Try alias["Missing"]; Except Message("caught"); EndTry;
            EndDo;
            Message(snapshot.Count());
        ''')
        self.assertEqual(self.output, ['caught', 'caught', 'caught', '3'])

    def test_map_typed_scalar_keys_and_exact_string_keys_survive_copying(self):
        self.vm.execute('''
            m = New Map; m[True] = "boolean"; m[1] = "number"; m["1"] = "string";
            m[Undefined] = "undefined"; m["Key"] = "upper"; m["key"] = "lower";
            m[Type("Number")] = "type"; fm = New FixedMap(m); copy = New Map(fm);
            Message(fm[True]); Message(fm.Get(1.00)); Message(fm["1"]);
            Message(fm[Undefined]); Message(fm["Key"]); Message(fm["key"]);
            Message(fm[TypeOf(42)]); Message(fm.Count()); Message(copy.Count());
            Message(copy[Type("Число")]); Message(fm.Get(False) = Undefined);
            Message(fm.Получить("Missing") = Undefined); Message(fm.Count());
        ''')
        self.assertEqual(self.output, ['boolean', 'number', 'string', 'undefined',
                                       'upper', 'lower', 'type', '7', '7', 'type',
                                       'Да', 'Да', '7'])

    def test_map_object_keys_keep_identity_and_aliases_after_mutation(self):
        self.vm.execute('''
            key = New Array; other = New Array; record = New Structure; nested = New Map;
            m = New Map; m[key] = "array"; m[record] = "structure"; m[nested] = "map";
            m[m] = m; fm = New FixedMap(m); copy = New Map(fm);
            key.Add(1); record.Insert("Value", 2); nested["Value"] = 3; m.Clear();
            Message(fm[key]); Message(fm.Get(other) = Undefined); Message(fm[record]);
            Message(copy[nested]); Message(fm[m] = m); Message(copy[m] = m);
            Message(fm.Count());
        ''')
        self.assertEqual(self.output, ['array', 'Да', 'structure', 'map', 'Да', 'Да', '4'])

    def test_map_hostile_host_keys_never_call_equality_or_hash(self):
        class Hostile:
            def __eq__(self, other):
                raise AssertionError('host equality must not run')

            def __hash__(self):
                raise AssertionError('host hashing must not run')

        first, second = Hostile(), Hostile()
        self.vm.variables.update(first=first, second=second)
        self.vm.execute('''
            m = New Map; m[first] = 7; m[second] = 8;
            fm = New FixedMap(m); copy = New Map(fm); m.Clear();
            Message(fm[first]); Message(copy[second]); Message(fm.Count());
        ''')
        self.assertEqual(self.output, ['7', '8', '2'])

    def test_map_keys_are_not_dot_properties_even_when_named_like_methods(self):
        self.vm.execute('''
            m = New Map; m["Get"] = 7; m["Count"] = 8; m["__class__"] = 9;
            fm = New FixedMap(m);
            Message(fm["Get"]); Message(fm["Count"]); Message(fm["__class__"]);
            Message(fm.Count()); Message((fm.Get)("Get"));
        ''')
        self.assertEqual(self.output, ['7', '8', '9', '3', '7'])
        for expression in ['fm.Get', 'fm.Count', 'fm.__class__', 'fm.Get = 0', 'fm.Name']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)

    def test_fixed_collection_equality_uses_identity_not_contents(self):
        # Native fixed-*.equal-alias/copy/different cover each fixed type.
        self.make_collections()
        for name, constructor, mutation in [
                ('fa', 'New FixedArray(array)', 'array[0] = 8'),
                ('fs', 'New FixedStructure(structure)', 'structure.Known = 8'),
                ('fm', 'New FixedMap(map)', 'map["Known"] = 8')]:
            self.vm.execute(f'''
                alias = {name}; sameContents = {constructor};
                {mutation}; differentContents = {constructor};
            ''')
            for other, expected in [('alias', True), (name, True),
                                    ('sameContents', False), ('differentContents', False)]:
                with self.subTest(fixed=name, other=other):
                    self.assertIs(self.vm.execute(f'({name} = {other})'), expected)
                    self.assertIs(self.vm.execute(f'({other} = {name})'), expected)
                    self.assertIs(self.vm.execute(f'({name} <> {other})'), not expected)
                    self.assertIs(self.vm.execute(f'({other} <> {name})'), not expected)
            self.assertIs(self.vm.variables['alias'], self.vm.variables[name])
            self.assertEqual(self.vm.execute(f'{name}.Count()'), Decimal(1))

    def test_fixed_identity_does_not_change_distinct_types_or_mutable_comparisons(self):
        self.make_collections()
        for left in ['fa', 'fs', 'fm']:
            for right in ['fa', 'fs', 'fm', 'array', 'structure', 'map',
                          'Undefined', 'True', '7', '"7"', 'Type("FixedArray")']:
                if left == right:
                    continue
                with self.subTest(left=left, right=right):
                    self.assertIs(self.vm.execute(f'({left} = {right})'), False)
                    self.assertIs(self.vm.execute(f'({right} = {left})'), False)
                    self.assertIs(self.vm.execute(f'({left} <> {right})'), True)
        self.vm.execute('''
            alias = array; other = New Array; other.Add(7);
            Message(array = alias); Message(array = other);
            Message(structure = New Structure("Known", 7)); Message(map = New Map);
            Message(True = 1); Message(1 = 1.00); Message(Type("Array") = Type("Массив"));
        ''')
        self.assertEqual(self.output, ['Да', 'Нет', 'Нет', 'Нет', 'Да', 'Да', 'Да'])

    def test_mutable_and_fixed_array_find_fixed_values_by_identity(self):
        self.make_collections()
        for name, constructor, other in [
                ('fa', 'New FixedArray(array)', 'fs'),
                ('fs', 'New FixedStructure(structure)', 'fm'),
                ('fm', 'New FixedMap(map)', 'fa')]:
            self.vm.execute(f'''
                alias = {name}; sameContents = {constructor};
                bag = New Array; bag.Add({name}); bag.Add(7); bag.Add({name});
                fixedBag = New FixedArray(bag);
            ''')
            self.assertIs(self.vm.execute('fixedBag[0]'), self.vm.variables[name])
            for receiver in ['bag', 'fixedBag']:
                for method in ['Find', 'Найти']:
                    with self.subTest(fixed=name, receiver=receiver, method=method):
                        self.assertEqual(self.vm.execute(f'{receiver}.{method}({name})'), Decimal(0))
                        self.assertEqual(self.vm.execute(f'{receiver}.{method}(alias)'), Decimal(0))
                        self.assertIsNone(self.vm.execute(f'{receiver}.{method}(sameContents)'))
                        self.assertEqual(self.vm.execute(f'{receiver}.{method}(7)'), Decimal(1))
                        self.assertIsNone(self.vm.execute(f'{receiver}.{method}({other})'))

    def test_fixed_map_keys_use_identity_across_insert_get_delete_and_copy(self):
        # Native fixed-*.key-* observes distinct entries for equal contents.
        self.make_collections()
        for key, constructor in [('fa', 'New FixedArray(array)'),
                                 ('fs', 'New FixedStructure(structure)'),
                                 ('fm', 'New FixedMap(map)')]:
            with self.subTest(key=key):
                self.vm.execute(f'''
                    alias = {key}; sameContents = {constructor}; absent = {constructor};
                    values = New Map; values[True] = "boolean"; values[1] = "number";
                    values["1"] = "string"; values[Undefined] = "undefined";
                    values[Type("Number")] = "type";
                    values.Insert({key}, 7); values.Вставить(sameContents, 8);
                    values[alias] = 9;
                    snapshot = New FixedMap(values); copy = New Map(snapshot);
                ''')
                for receiver in ['values', 'snapshot', 'copy']:
                    for method in ['Get', 'Получить']:
                        self.assertEqual(self.vm.execute(f'{receiver}.{method}(alias)'), Decimal(9))
                        self.assertEqual(self.vm.execute(f'{receiver}.{method}(sameContents)'), Decimal(8))
                        self.assertIsNone(self.vm.execute(f'{receiver}.{method}(absent)'))
                    self.assertEqual(self.vm.execute(f'{receiver}[{key}]'), Decimal(9))
                    self.assertEqual(self.vm.execute(f'{receiver}[sameContents]'), Decimal(8))
                    self.assertEqual(self.vm.execute(f'{receiver}.Count()'), Decimal(7))
                    for scalar, value in [('True', 'boolean'), ('1', 'number'), ('"1"', 'string'),
                                          ('Undefined', 'undefined'), ('Type("Число")', 'type')]:
                        self.assertEqual(self.vm.execute(f'{receiver}[{scalar}]'), value)
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('snapshot[absent]')
                self.vm.execute('''
                    values.Удалить(alias); values.Delete(absent); copy.Delete(sameContents);
                ''')
                self.assertIsNone(self.vm.execute('values.Get(alias)'))
                self.assertIsNone(self.vm.execute('copy.Get(sameContents)'))
                self.assertEqual(self.vm.execute('values[sameContents]'), Decimal(8))
                self.assertEqual(self.vm.execute('copy[alias]'), Decimal(9))
                self.assertEqual(self.vm.execute('snapshot[alias]'), Decimal(9))
                self.assertEqual(self.vm.execute('snapshot[sameContents]'), Decimal(8))
                self.assertEqual(self.vm.execute('values.Count()'), Decimal(6))
                self.assertEqual(self.vm.execute('copy.Count()'), Decimal(6))
                self.assertEqual(self.vm.execute('snapshot.Count()'), Decimal(7))
                pairs = list(self.vm.variables['snapshot'])
                self.assertTrue(any(pair.key is self.vm.variables[key] for pair in pairs))
                self.assertTrue(any(pair.key is self.vm.variables['samecontents'] for pair in pairs))

    def test_fixed_subclass_equality_and_map_keys_never_call_host_equality_or_hash(self):
        class HostileEquality:
            def __eq__(self, other):
                raise AssertionError('fixed host equality must not run')

            def __hash__(self):
                raise AssertionError('fixed host hashing must not run')

        for base, source in [(BSLFixedArray, BSLArray()),
                             (BSLFixedStructure, BSLStructure()),
                             (BSLFixedMap, BSLMap())]:
            class HostFixed(HostileEquality, base):
                pass

            with self.subTest(type=base.__name__):
                first, second = HostFixed(source), HostFixed(source)
                self.vm.variables.update(first=first, alias=first, second=second,
                                         ordinary=base(source))
                for left, right, expected in [('first', 'first', True), ('first', 'alias', True),
                                               ('first', 'second', False),
                                               ('first', 'ordinary', False),
                                               ('ordinary', 'first', False)]:
                    self.assertIs(self.vm.execute(f'({left} = {right})'), expected)
                    self.assertIs(self.vm.execute(f'({left} <> {right})'), not expected)
                self.vm.execute('''
                    bag = New Array; bag.Add(first); fixedBag = New FixedArray(bag);
                    values = New Map; values.Insert(first, 7); values[second] = 8;
                    values.Вставить(alias, 9); snapshot = New FixedMap(values);
                    copy = New Map(snapshot);
                ''')
                for receiver in ['bag', 'fixedBag']:
                    self.assertEqual(self.vm.execute(f'{receiver}.Find(alias)'), Decimal(0))
                    self.assertIsNone(self.vm.execute(f'{receiver}.Найти(second)'))
                for receiver in ['values', 'snapshot', 'copy']:
                    self.assertEqual(self.vm.execute(f'{receiver}[alias]'), Decimal(9))
                    self.assertEqual(self.vm.execute(f'{receiver}.Получить(second)'), Decimal(8))
                    self.assertIsNone(self.vm.execute(f'{receiver}.Get(ordinary)'))
                    self.assertEqual(self.vm.execute(f'{receiver}.Count()'), Decimal(2))
                self.vm.execute('values.Delete(alias); copy.Удалить(second);')
                self.assertIsNone(self.vm.execute('values.Get(first)'))
                self.assertEqual(self.vm.execute('snapshot[first]'), Decimal(9))
                self.assertEqual(self.vm.execute('snapshot[second]'), Decimal(8))

    def test_fixed_identity_does_not_override_ordinary_host_equality(self):
        class HostValue:
            def __eq__(self, other):
                return True

        class HostArray(BSLArray):
            def __eq__(self, other):
                return True

        for kind in [HostValue, HostArray]:
            with self.subTest(type=kind.__name__):
                first, second = kind(), kind()
                self.assertIsNot(first, second)
                self.vm.variables.update(first=first, second=second)
                self.assertIs(self.vm.execute('(first = second)'), True)
                self.assertIs(self.vm.execute('(first <> second)'), False)
                self.vm.execute('bag = New Array; bag.Add(first);')
                self.assertEqual(self.vm.execute('bag.Find(second)'), Decimal(0))
                self.assertIs(self.vm.execute('(first = 1)'), False)

    def test_direct_mutable_arrays_freeze_recursively_without_changing_source(self):
        # Native nested.freeze/types/after-source-write/snapshot-write.
        self.vm.execute('''
            leaf = New Array; leaf.Add(5);
            branch = New Array; branch.Add(leaf);
            root = New Array; root.Add(branch); root.Add(leaf);
            fixed = New ФиксированныйМассив(root);
            leaf[0] = 6; leaf.Add(7); branch.Add(8); root.Clear();
            Message(TypeOf(fixed[0]) = Type("FixedArray"));
            Message(TypeOf(fixed[0][0]) = Type("ФиксированныйМассив"));
            Message(TypeOf(fixed[1]) = Type("FixedArray"));
            Message(fixed[0][0][0]); Message(fixed[1][0]);
            Message(fixed.Count()); Message(fixed[0].Count()); Message(fixed[0][0].Count());
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да', '5', '5', '2', '1', '1'])
        for expression in ['fixed[0][0][0] = 9', 'fixed[0].Add(9)', 'fixed[1].Очистить()']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        self.assertEqual(self.vm.execute('leaf[0]'), Decimal(6))
        self.assertEqual(self.vm.execute('leaf.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('fixed[0][0][0]'), Decimal(5))

    def test_recursive_freezing_stops_at_structures_maps_and_already_fixed_items(self):
        self.vm.execute('''
            child = New Array; child.Add(7); fixedChild = New FixedArray(child);
            record = New Structure("Child", child); map = New Map; map["Child"] = child;
            fixedRecord = New FixedStructure(record); fixedMap = New FixedMap(map);
            branch = New Array; branch.Add(child); branch.Add(record); branch.Add(map);
            branch.Add(fixedChild); branch.Add(fixedRecord); branch.Add(fixedMap);
            root = New Array; root.Add(branch); fixedRoot = New FixedArray(root);
            child[0] = 8;
            Message(fixedRoot[0][0][0]); Message(fixedRoot[0][1].Child[0]);
            Message(fixedRoot[0][2]["Child"][0]); Message(fixedRoot[0][3][0]);
            Message(fixedRoot[0][4].Child[0]); Message(fixedRoot[0][5]["Child"][0]);
            copy = New Array(fixedRoot); copy[0][0][0] = 9;
            Message(fixedRoot[0][0][0]); Message(child[0]);
        ''')
        self.assertEqual(self.output, ['7', '8', '8', '7', '8', '8', '7', '8'])
        for index, name in [(1, 'record'), (2, 'map'), (3, 'fixedchild'),
                            (4, 'fixedrecord'), (5, 'fixedmap')]:
            self.assertIs(self.vm.execute(f'fixedRoot[0][{index}]'), self.vm.variables[name])
            if index != 3:
                self.assertIs(self.vm.execute(f'copy[0][{index}]'), self.vm.variables[name])
        self.assertIsInstance(self.vm.execute('copy[0][3]'), BSLArray)
        self.assertIsNot(self.vm.execute('copy[0][3]'), self.vm.variables['child'])

    def test_cyclic_direct_array_paths_remain_explicit_unverified_limitations(self):
        # The native scenario does not probe cycles. Keep this a subset contract.
        self.make_collections()
        original = self.vm.variables['fa']
        self.vm.execute('''
            cyclic = New Array; cyclic.Add(cyclic);
            indirect = New Array; child = New Array;
            indirect.Add(child); child.Add(indirect);
            prefix = New Array; prefix.Add(New Array(1)); prefix.Add(indirect);
        ''')
        for source in ['cyclic', 'indirect', 'prefix']:
            with self.subTest(source=source), self.assertRaisesRegex(
                    BSLRuntimeError, 'пока не поддерживается'):
                self.vm.execute(f'fa = New FixedArray({source})')
            self.assertIs(self.vm.variables['fa'], original)
            self.assertEqual(self.vm.execute('fa[0]'), Decimal(7))
            self.assertIs(self.vm.execute('cyclic[0]'), self.vm.variables['cyclic'])
            self.assertIs(self.vm.execute('indirect[0][0]'), self.vm.variables['indirect'])
            self.assertEqual(self.vm.execute('prefix.Count()'), Decimal(2))
            self.vm.execute(f'''
                Try New FixedArray({source}); Except Message("caught"); EndTry;
            ''')
        self.assertEqual(self.output, ['caught'] * 3)

    def test_cycles_through_shallow_structure_and_map_values_are_retained(self):
        self.vm.execute('''
            root = New Array; record = New Structure("Root", root);
            map = New Map; map["Root"] = root; root.Add(record); root.Add(map);
            fixed = New FixedArray(root); copy = New Array(fixed);
        ''')
        for receiver in ['fixed', 'copy']:
            self.assertIs(self.vm.execute(f'{receiver}[0].Root'), self.vm.variables['root'])
            self.assertIs(self.vm.execute(f'{receiver}[1]["Root"]'), self.vm.variables['root'])

    def test_same_fixed_source_constructor_is_rejected_and_preserves_original(self):
        self.make_collections()
        for name, constructor in [('fa', 'FixedArray'), ('fs', 'FixedStructure'),
                                  ('fm', 'FixedMap')]:
            original = self.vm.variables[name]
            with self.subTest(constructor=constructor), self.assertRaises(BSLRuntimeError):
                self.vm.execute(f'{name} = New {constructor}({name})')
            self.assertIs(self.vm.variables[name], original)
            self.assertEqual(self.vm.execute(f'{name}.Count()'), Decimal(1))
            self.vm.execute(f'''
                Try New {constructor}({name}); Except Message("caught"); EndTry;
            ''')
        self.assertEqual(self.output, ['caught'] * 3)

    def test_all_mutating_methods_and_index_assignments_are_rejected(self):
        self.make_collections()
        cases = {
            'fa': ['fa[0] = 8', 'fa.Set(0, 8)', 'fa.Установить(0, 8)',
                   'fa.Add(8)', 'fa.Добавить(8)', 'fa.Insert(0, 8)',
                   'fa.Вставить(0, 8)', 'fa.Delete(0)', 'fa.Удалить(0)',
                   'fa.Clear()', 'fa.Очистить()'],
            'fs': ['fs.Known = 8', 'fs["Known"] = 8', 'fs.Missing = 8',
                   'fs["Missing"] = 8', 'fs.Insert("Known", 8)',
                   'fs.Вставить("New", 8)', 'fs.Delete("Known")',
                   'fs.Удалить("Missing")', 'fs.Clear()', 'fs.Очистить()'],
            'fm': ['fm["Known"] = 8', 'fm["Missing"] = 8', 'fm.Known = 8',
                   'fm.Insert("Known", 8)', 'fm.Вставить("New", 8)',
                   'fm.Delete("Known")', 'fm.Удалить("Missing")',
                   'fm.Clear()', 'fm.Очистить()'],
        }
        for name, expressions in cases.items():
            for expression in expressions:
                with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                    self.vm.execute(expression)
                self.assertEqual(self.vm.execute(f'{name}.Count()'), Decimal(1))
                index = '0' if name == 'fa' else '"Known"'
                self.assertEqual(self.vm.execute(f'{name}[{index}]'), Decimal(7))

    def test_read_method_arities_and_omitted_arguments_are_checked(self):
        self.make_collections()
        for expression in ['fa.Count(1)', 'fa.UBound(1)', 'fa.Get()', 'fa.Get(0, 1)',
                           'fa.Find()', 'fa.Find(7, 8)', 'fs.Count(1)',
                           'fs.Property()', 'fs.Property("Known", 1, 2)',
                           'fm.Count(1)', 'fm.Get()', 'fm.Get("Known", 1)',
                           'New FixedArray(,)', 'New FixedStructure(,)', 'New FixedMap(,)',
                           'fa.Get(,)', 'fm.Get(,)']:
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)
        self.assertEqual(self.vm.execute('fa[0]'), Decimal(7))
        self.assertEqual(self.vm.execute('fs.Known'), Decimal(7))
        self.assertEqual(self.vm.execute('fm["Known"]'), Decimal(7))

    def test_array_iteration_is_ordered_and_unchanged_when_source_mutates(self):
        self.vm.execute('''
            a = New Array; a.Add(1); a.Add(2); a.Add(3); fa = New FixedArray(a);
            For Each value In fa Do Message(value); a.Clear(); EndDo;
            For Each value In New FixedArray(New Array) Do Message("bad"); EndDo;
        ''')
        self.assertEqual(self.output, ['1', '2', '3'])

    def test_structure_and_map_iteration_keep_original_pairs_after_source_mutation(self):
        for source, fixed, populate in [('Structure', 'FixedStructure',
                                        'source.Insert("First", 1); source.Insert("Second", 2);'),
                                       ('Map', 'FixedMap',
                                        'source["First"] = 1; source["Second"] = 2;')]:
            with self.subTest(type=fixed):
                self.output.clear()
                self.vm.execute(f'''
                    source = New {source}; {populate} fixed = New {fixed}(source);
                    For Each pair In fixed Do
                        Message(pair.Key + ":" + pair.Value);
                        Message(pair.Ключ + ":" + pair.Значение);
                        Message(TypeOf(pair) = Type("KeyAndValue")); source.Clear();
                    EndDo;
                    For Each pair In New {fixed}(New {source}) Do Message("bad"); EndDo;
                ''')
                self.assertCountEqual(self.output, ['First:1', 'First:1', 'Да',
                                                    'Second:2', 'Second:2', 'Да'])

    def test_iteration_pairs_are_readonly_but_nested_values_remain_mutable(self):
        for constructor in ['New FixedStructure(New Structure("Items", child))',
                            'New FixedMap(map)']:
            with self.subTest(constructor=constructor):
                self.output.clear()
                self.vm.execute(f'''
                    child = New Array; map = New Map; map["Items"] = child;
                    fixed = {constructor};
                    For Each pair In fixed Do pair.Value.Add(7); EndDo;
                    Message(child[0]);
                ''')
                self.assertEqual(self.output, ['7'])
                for expression in ['pair.Key = "Other"', 'pair.Value = 8',
                                   'pair.Ключ = "Other"', 'pair.Значение = 8']:
                    with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                        self.vm.execute(expression)
                self.assertIs(self.vm.execute('pair.Value'), self.vm.variables['child'])

    def test_copy_back_constructors_produce_mutable_independent_collections(self):
        self.make_collections()
        self.vm.execute('''
            a = New Массив(fa); s = New Структура(fs); m = New Соответствие(fm);
            a[0] = 8; a.Add(9); s.Known = 8; s.Insert("Extra", 9);
            m["Known"] = 8; m["Extra"] = 9;
            Message(a.Count()); Message(s.Count()); Message(m.Count());
            Message(fa[0]); Message(fs.Known); Message(fm["Known"]);
            Message(TypeOf(a) = Type("Array")); Message(TypeOf(s) = Type("Structure"));
            Message(TypeOf(m) = Type("Map"));
        ''')
        self.assertEqual(self.output, ['2', '2', '2', '7', '7', '7', 'Да', 'Да', 'Да'])

    def test_copy_back_constructor_rejects_wrong_fixed_collection_and_surplus_values(self):
        self.make_collections()
        for expression in ['New Array(fs)', 'New Array(fm)', 'New Array(fa, 1)',
                           'New Structure(fa)', 'New Structure(fm)', 'New Structure(fs, 1)',
                           'New Map(fa)', 'New Map(fs)', 'New Map(fm, 1)']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)

    def test_mutable_array_subclass_presentation_does_not_call_host_str(self):
        class HostArray(BSLArray):
            def __str__(self):
                raise AssertionError("array presentation must not invoke host code")

        self.vm.variables['embedded'] = HostArray()
        self.vm.execute('Message(embedded); Message(String(embedded)); '
                        'Message("type:" + embedded);')
        self.assertEqual(self.output, ['Массив', 'Массив', 'type:Массив'])

    def test_python_storage_and_mutation_helpers_are_not_exposed(self):
        self.make_collections()
        for receiver in ['fa', 'fs', 'fm']:
            for name in ['items', '_items', '_version', '__class__', '__dict__',
                         'get_member', 'set_member', 'get_method', 'checked_index',
                         '_freeze_items', 'get_index', 'set']:
                for suffix in ['', '()']:
                    with self.subTest(receiver=receiver, name=name, suffix=suffix):
                        with self.assertRaises(BSLError):
                            self.vm.execute(f'{receiver}.{name}{suffix}')
        # Ordinary user keys may legitimately have Python-looking spellings.
        self.vm.execute('''
            fixed = New FixedStructure("__class__,items,get_member", 1, 2, 3);
            Message(fixed.__class__); Message(fixed.items); Message(fixed.get_member);
        ''')
        self.assertEqual(self.output, ['1', '2', '3'])

    def test_read_receivers_and_arguments_are_evaluated_once_in_order(self):
        self.vm.execute('''
            Var root, trace; trace = "";
            source = New Map; source["Known"] = 7; root = New FixedMap(source);
            Function Receiver() trace = trace + "R"; Return root; EndFunction
            Function KeyName() trace = trace + "K"; Return "Known"; EndFunction
            Message(Receiver()[KeyName()]); Message(trace); trace = "";
            Message((Receiver().Get)(KeyName())); Message(trace);
        ''')
        self.assertEqual(self.output, ['7', 'RK', '7', 'RK'])

    def test_failed_mutation_reports_source_line_and_remains_catchable(self):
        self.make_collections()
        for expression in ['fa[0] = 8;', 'fs.Known = 8;', 'fm["Known"] = 8;']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError) as caught:
                self.vm.execute('\n' + expression, 'fixed.bsl')
            self.assertEqual((caught.exception.source, caught.exception.line), ('fixed.bsl', 2))
        self.vm.execute('''
            Try fa.Clear(); Except Message(ErrorDescription() <> ""); EndTry;
            Try fs.Insert("Other", 1); Except Message(ErrorDescription() <> ""); EndTry;
            Try fm.Delete("Known"); Except Message(ErrorDescription() <> ""); EndTry;
            Message(fa[0]); Message(fs.Known); Message(fm["Known"]);
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да', '7', '7', '7'])

    def test_fixed_errors_report_source_location_and_restore_routine_scope(self):
        self.make_collections()
        self.vm.execute('''
            Procedure CopyFixed(Val fixed) result = New FixedArray(fixed); EndProcedure
            Procedure Lookup(Val map, Val key) result = map[key]; EndProcedure
            cyclic = New Array; cyclic.Add(cyclic);
        ''', 'fixed-definitions.bsl')
        for expression in ['CopyFixed(fa)', 'CopyFixed(cyclic)',
                           'Lookup(fm, "Missing")', 'Lookup(fm, fs)']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError) as caught:
                self.vm.execute(expression, 'caller.bsl')
            self.assertEqual(caught.exception.source, 'fixed-definitions.bsl')
            self.assertIsNone(self.vm.locals)
            self.assertNotIn('result', self.vm.variables)
        for expression in ['fm["Missing"]', 'fm[fs]', 'New FixedArray(cyclic)',
                           'New FixedArray(fa)', 'New FixedStructure(fs)', 'New FixedMap(fm)']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError) as caught:
                self.vm.execute('\n' + expression, 'fixed-boundaries.bsl')
            self.assertEqual((caught.exception.source, caught.exception.line),
                             ('fixed-boundaries.bsl', 2))
        self.assertEqual(self.vm.execute('fa[0]'), Decimal(7))
        self.assertEqual(self.vm.execute('fs.Known'), Decimal(7))
        self.assertEqual(self.vm.execute('fm["Known"]'), Decimal(7))

    def test_routine_returns_aliases_and_val_rebinding_does_not_mutate_fixed_values(self):
        self.make_collections()
        self.vm.execute('''
            Function Echo(Val value) Return value; EndFunction
            Procedure Local(Val value) value = Undefined; EndProcedure
            Procedure Replace(value) value = Undefined; EndProcedure
            returnedArray = Echo(fa); returnedStructure = Echo(fs); returnedMap = Echo(fm);
            Message(returnedArray.Count()); Message(returnedStructure.Count()); Message(returnedMap.Count());
            Local(fa); Local(fs); Local(fm);
            Message(fa.Count()); Message(fs.Count()); Message(fm.Count());
            alias = fm; Replace(fm); Message(fm = Undefined); Message(alias.Count());
        ''')
        self.assertEqual(self.output, ['1', '1', '1', '1', '1', '1', 'Да', '1'])
        self.assertIs(self.vm.variables['returnedarray'], self.vm.variables['fa'])
        self.assertIs(self.vm.variables['returnedstructure'], self.vm.variables['fs'])
        self.assertIs(self.vm.variables['returnedmap'], self.vm.variables['alias'])
        self.assertIsNone(self.vm.locals)

    def test_imported_exports_construct_return_and_forward_fixed_collection_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / 'Fixed.bsl'
            module.write_text('''
                Var stored;
                stored = New FixedStructure("Count,Items", 9, New Array);
                Function Record() Export Return stored; EndFunction
                Function ArrayValue() Export
                    source = New Array; source.Add(7); Return New FixedArray(source);
                EndFunction
                Function MapValue(Val key) Export
                    source = New Map; source[key] = stored; Return New FixedMap(source);
                EndFunction
                Procedure Read(Val record, result) Export record.Property("Count", result); EndProcedure
                Procedure Fail(Val record) Export record.Count = 0; EndProcedure
            ''', encoding='utf-8-sig')
            self.vm.execute('''// #Import Fixed.bsl
                fs = Fixed.Record(); fa = Fixed.ArrayValue(); key = New Array;
                fm = Fixed.MapValue(key); Var result;
                Fixed.Read(fs, result); Message(result); Message(fs.Count());
                Message(fa[0]); Message(fm[key].Count); Message(Fixed.Record().Count);
                fs.Items.Add(8); Message(Fixed.Record().Items[0]);
            ''', str(root / 'Main.bsl'))
            self.assertEqual(self.output, ['9', '2', '7', '9', '9', '8'])
            self.assertIs(self.vm.execute('fm[key]'), self.vm.variables['fs'])
            self.assertIs(self.vm.execute('Fixed.Record()'), self.vm.variables['fs'])
            with self.assertRaises(BSLRuntimeError) as caught:
                self.vm.execute('Fixed.Fail(fs)', 'caller.bsl')
            self.assertEqual(caught.exception.source, str(module.resolve()))
            self.assertIsNone(self.vm.locals)
            self.assertEqual(self.vm.execute('Fixed.Record().Count'), Decimal(9))


if __name__ == '__main__':
    unittest.main()
