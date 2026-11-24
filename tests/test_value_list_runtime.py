"""Interpreter dispatch for the native-backed default-state ValueList subset."""

from decimal import Decimal
from pathlib import Path
import unittest

from yadinassi import BSLError, BSLRuntimeError, Interpreter
from tests.native_observations import extract_payload


class NativeValueListPositionsTests(unittest.TestCase):
    def test_positional_operations_match_all_eight_archived_records(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        expected = (root / 'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        output = []
        vm = Interpreter(output.append)
        self.addCleanup(vm.close)
        vm.execute(source.split('#Область МассивыИСтруктуры', 1)[0])
        for name in ('insert.boundaries', 'insert.coercion', 'get.access', 'get.boundaries',
                     'move.index', 'move.invalid', 'delete.index', 'id.find'):
            with self.subTest(name=name):
                label = 'list.' + name
                code, = (line for line in source.splitlines()
                         if line.startswith(f'НаблюдатьТаблицы("{label}",'))
                output.clear()
                vm.execute(code)
                self.assertEqual(len(output), 1)
                self.assertEqual(extract_payload(output[0], 'table.' + label),
                                 extract_payload(expected, 'table.' + label))

    def test_item_index_distinguishes_foreign_item_from_invalid_values(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        archive = (root / 'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        output = []
        vm = Interpreter(output.append)
        self.addCleanup(vm.close)
        vm.execute(source.split('#Область МассивыИСтруктуры', 1)[0])
        label = 'list.indexof'
        code, = (line for line in source.splitlines()
                 if line.startswith(f'НаблюдатьТаблицы("{label}",'))
        vm.execute_prepared(vm.prepare(code))
        self.assertEqual(len(output), 1)
        self.assertEqual(extract_payload(output[0], 'table.' + label),
                         extract_payload(archive, 'table.' + label))

    def test_foreign_item_move_matches_both_archived_records(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        expected = (root / 'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        output = []
        vm = Interpreter(output.append)
        self.addCleanup(vm.close)
        vm.execute(source.split('#Область МассивыИСтруктуры', 1)[0])
        for label in ('list.move.item', 'list.extra.foreign-move'):
            with self.subTest(label=label):
                code, = (line for line in source.splitlines()
                         if line.startswith(f'НаблюдатьТаблицы("{label}",'))
                output.clear()
                vm.execute_prepared(vm.prepare(code))
                self.assertEqual(len(output), 1)
                self.assertEqual(extract_payload(output[0], 'table.' + label),
                                 extract_payload(expected, 'table.' + label))


class ValueListRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.vm.execute('values = New ValueList; first = values.Add(10, "first", True); '
                        'values.Добавить(20, "second", False);')

    def test_types_constructor_aliases_and_presentation(self):
        self.assertTrue(self.vm.execute('(TypeOf(values) = Type("СписокЗначений"))'))
        self.assertTrue(self.vm.execute('(TypeOf(first) = Type("ValueListItem"))'))
        self.assertEqual(self.vm.execute('String(TypeOf(values))'), "Список значений")
        self.assertEqual(self.vm.execute('String(TypeOf(first))'), "Элемент списка значений")
        self.vm.execute('other = New("СписокЗначений"); typed = New (Type("ValueList"));')
        self.assertEqual(self.vm.execute('other.Count()'), Decimal(0))
        self.assertEqual(self.vm.execute('typed.Количество()'), Decimal(0))
        for code in ('New ValueList(1)', 'New ValueListItem', 'New ЭлементСпискаЗначений',
                     'Type("Список значений")', 'Type("Элемент списка значений")'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_identity_iteration_defaults_and_text(self):
        self.assertTrue(self.vm.execute('(values.Get(0) = first)'))
        self.assertTrue(self.vm.execute('(values[0] = first)'))
        self.assertEqual(self.vm.execute('String(values)'), "first; second")
        self.assertEqual(self.vm.execute('String(first)'), "first")
        self.vm.execute('For Each item In values Do Message(item.Value); EndDo;')
        self.assertEqual(self.output, ["10", "20"])
        self.vm.execute('description = values.ТипЗначения;')
        self.assertEqual(self.vm.execute('description.Types().Count()'), Decimal(0))
        self.assertIsNone(self.vm.execute('values.AvailableValues'))

    def test_optional_holes_and_defaults_for_named_receivers(self):
        self.vm.execute('a = values.Add(10, , True); '
                        'b = values.Вставить(0, , "missing", True); '
                        'c = values.Add(, , False);')
        self.assertEqual(self.vm.execute('a.Presentation'), "")
        self.assertIs(self.vm.execute('a.Check'), True)
        self.assertIsNone(self.vm.execute('b.Value'))
        self.assertEqual(self.vm.execute('b.Presentation'), "missing")
        self.assertIs(self.vm.execute('b.Check'), True)
        self.assertIsNone(self.vm.execute('c.Value'))
        self.assertIs(self.vm.execute('c.Check'), False)

    def test_delete_index_bounds_leave_items_and_warmed_presentation_unchanged(self):
        # Native collections.out, table.list.delete.index, rejects -1 and
        # Count() without deleting; table.list.string-cache.controls keeps
        # already rendered text across that failure.
        self.assertEqual(self.vm.execute('String(values)'), 'first; second')
        self.vm.execute('second=values.Get(1); first.Presentation="changed";')
        for index in ('-1', 'values.Count()'):
            with self.subTest(index=index):
                with self.assertRaises(BSLError):
                    self.vm.execute(f'values.Delete({index});')
                self.assertEqual(self.vm.execute('values.Count()'), Decimal(2))
                self.assertIs(self.vm.execute('(values.Get(0) = first)'), True)
                self.assertIs(self.vm.execute('(values.Get(1) = second)'), True)
                self.assertEqual(self.vm.execute('first.GetID()'), Decimal(0))
                self.assertEqual(self.vm.execute('second.GetID()'), Decimal(1))
                self.assertEqual(self.vm.execute('first.Presentation'), 'changed')
                self.assertEqual(self.vm.execute('String(values)'), 'first; second')
        self.vm.execute('values.Delete(1);')
        self.assertEqual(self.vm.execute('values.Count()'), Decimal(1))
        self.assertEqual(self.vm.execute('second.GetID()'), Decimal(-1))
        self.assertEqual(self.vm.execute('String(values)'), 'changed')

    def test_required_and_computed_receiver_holes_reject_before_effects(self):
        self.vm.execute('Var touches; touches = 0; '
                        'Function Touch() touches = touches + 1; Return 7; EndFunction '
                        'Function List() touches = touches + 1; Return New ValueList; EndFunction')
        for code in ('values.Insert(, Touch());', 'values.Get(, Touch());',
                     'values.FillChecks(, Touch());', 'List().Add(, Touch());'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('touches'), Decimal(0))
        self.vm.execute('List().Add(7);')
        self.assertEqual(self.vm.execute('touches'), Decimal(1))

    def test_mutable_properties_and_read_only_collection_slots(self):
        self.vm.execute('first.Значение = "new"; first.Представление = 7; first.Пометка = 0;')
        self.assertEqual(self.vm.execute('values[0].Value'), "new")
        self.assertEqual(self.vm.execute('values[0].Presentation'), "7")
        self.assertIs(self.vm.execute('values[0].Check'), False)
        for code in ('values[0] = first;', 'values[0] = 7;', 'values.ValueType = Undefined;',
                     'values.AvailableValues = Undefined;', 'first.Picture = Undefined;'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_plain_list_readonly_and_missing_properties_are_catchable(self):
        self.vm.execute(
            'Var Touches; Touches=0; '
            'Function Touch() Touches=Touches+1; Return 99; EndFunction'
        )
        cases = (
            ('values.ТипЗначения=Touch();', 'недоступно для записи'),
            ('values.AvailableValues=Touch();', 'недоступно для записи'),
            ('values.UnknownMember=Touch();', 'не обнаружено'),
            ('values.UnknownMember;', 'не обнаружено'),
        )
        source = 'value-list-properties.bsl'
        for prepared in (False, True):
            for code, reason in cases:
                with self.subTest(prepared=prepared, code=code):
                    program = '\n' + code
                    plan = self.vm.prepare(program, source) if prepared else None
                    with self.assertRaisesRegex(BSLRuntimeError, reason) as failure:
                        if prepared:
                            self.vm.execute_prepared(plan)
                        else:
                            self.vm.execute(program, source)
                    self.assertEqual((failure.exception.source, failure.exception.line,
                                      failure.exception.source_line), (source, 2, code))
        self.vm.execute('Denied=False; Try values.ValueType=Touch(); '
                        'Except Denied=True; EndTry;')
        self.assertIs(self.vm.execute('Denied'), True)
        self.assertEqual(self.vm.execute('Touches'), 0)
        self.assertEqual(self.vm.execute('values.Count()'), 2)
        self.assertIs(self.vm.execute('values.Get(0)'), self.vm.variables['first'])
        self.assertEqual(self.vm.execute('values.ValueType.Types().Count()'), 0)
        self.assertIsNone(self.vm.execute('values.ДоступныеЗначения'))

    def test_bilingual_methods_and_detached_fields(self):
        self.vm.execute('inserted = values.Вставить(0, 30); '
                        'values.Сдвинуть(first, 1);')
        self.assertEqual(self.vm.execute('values.Индекс(first)'), Decimal(2))
        self.assertTrue(self.vm.execute('(values.НайтиПоЗначению(10) = first)'))
        self.assertTrue(self.vm.execute('(values.НайтиПоИдентификатору(first.ПолучитьИдентификатор()) = first)'))
        self.vm.execute('values.Удалить(first); first.Значение = 99; first.Пометка = False;')
        self.assertEqual(self.vm.execute('first.GetID()'), Decimal(-1))
        self.assertEqual(self.vm.execute('first.Value'), Decimal(99))
        self.vm.execute('values.ЗаполнитьПометки(True); values.Очистить();')
        self.assertEqual(self.vm.execute('values.Count()'), Decimal(0))

    def test_returned_identity_and_writes_match_corrected_owner_probe(self):
        self.vm.execute('values = New ValueList; first = values.Add(10); '
                        'second = values.Insert(0, 20);')
        for expression in ('first = values.Get(1)', 'second = values.Get(0)',
                           'values.FindByValue(10) = first',
                           'values.FindByID(second.GetID()) = second'):
            self.assertTrue(self.vm.execute('(' + expression + ')'))
        self.vm.execute('first.Value = 11;')
        self.assertEqual(self.vm.execute('values[1].Value'), Decimal(11))

    def test_foreign_move_bilingual_dispatch_preserves_foreign_owner(self):
        self.vm.execute('foreign = New ValueList; foreign.Add(100); '
                        'foreignItem = foreign.Add(200); foreign.Add(300); '
                        'values.Сдвинуть(foreignItem, 1);')
        self.assertTrue(self.vm.execute('(values.Get(1) = first)'))
        self.assertEqual(self.vm.execute('foreign.Get(1).Value'), Decimal(200))
        self.vm.execute('values.Add(30); foreign.Delete(foreignItem); '
                        'values.Move(foreignItem, 1);')
        self.assertTrue(self.vm.execute('(values.Get(0) = first)'))
        self.assertEqual(self.vm.execute('foreignItem.GetID()'), Decimal(-1))
        self.assertEqual(self.vm.execute('foreign.Count()'), Decimal(2))
        self.vm.execute('Try values.Move(foreignItem, 2); Except '
                        'Message(Find(ErrorDescription(), "пока не поддерживается") > 0); EndTry;')
        self.assertEqual(self.output, ["Да"])
        self.assertTrue(self.vm.execute('(values.Get(0) = first)'))

    def test_item_move_does_not_generalize_to_other_offsets_or_deleted_local_items(self):
        self.vm.execute('foreign = New ValueList; foreignItem = foreign.Add(100); '
                        'removed = values.Add(30); values.Delete(removed);')
        for statement in ('values.Move(foreignItem, -1)', 'values.Move(foreignItem, 1.5)',
                          'values.Move(removed, 1)', 'values.Delete(foreignItem)'):
            with self.subTest(statement=statement):
                with self.assertRaises(BSLError):
                    self.vm.execute(statement + ';')
                self.assertTrue(self.vm.execute('(values.Get(0) = first)'))
                self.assertEqual(self.vm.execute('values.Count()'), 2)
                self.assertTrue(self.vm.execute('(foreign.Get(0) = foreignItem)'))

    def test_copy_load_unload_bilingual_dispatch(self):
        self.vm.execute('copy = values.Скопировать(); a = values.ВыгрузитьЗначения(); '
                        'copy.ЗагрузитьЗначения(a);')
        self.assertEqual(self.vm.execute('copy.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('copy.Get(0).Value'), Decimal(10))
        self.assertEqual(self.vm.execute('copy.Get(0).Presentation'), "")
        self.assertEqual(self.vm.execute('copy.Get(0).GetID()'), Decimal(2))
        self.assertFalse(self.vm.execute('(copy.Get(0) = first)'))

    def test_procedures_cannot_be_used_as_functions_or_mutate_on_rejection(self):
        for expression in ('values.Clear()', 'values.Delete(0)', 'values.Move(0, 1)',
                           'values.LoadValues(New Array)', 'values.FillChecks(True)'):
            with self.assertRaises(BSLError):
                self.vm.execute('answer = ' + expression + ';')
            self.assertEqual(self.vm.execute('values.Count()'), Decimal(2))
            self.assertTrue(self.vm.execute('(values[0] = first)'))

    def test_host_attributes_and_out_of_scope_methods_are_not_exposed(self):
        for code in ('values.items', 'values._next_id', 'first._id', 'first._owner_ref',
                     'values.ChooseItem()', 'first.Picture',
                     'For Each x In first Do EndDo;', 'first[0]'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_observed_property_reference_arguments_enter_callee(self):
        self.vm.execute('Var entered; entered = False; '
                        'Procedure ReadReference(x) entered = True; EndProcedure '
                        'Procedure ReadValue(Val x) Message(x); EndProcedure')
        for field in ("Value", "Presentation", "Check"):
            self.vm.execute(f'entered = False; ReadReference(first.{field});')
            self.assertIs(self.vm.execute('entered'), True)
        self.vm.execute('ReadValue(first.Value);')
        self.assertEqual(self.output, ["10"])
        self.assertEqual(self.vm.execute('first.Value'), Decimal(10))


if __name__ == "__main__":
    unittest.main()
