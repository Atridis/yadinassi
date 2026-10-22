"""Linux include traversal and unchanged Windows/bounded fill contracts."""

from decimal import Decimal
from itertools import product
import unittest

from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.native_targets import (
    LINUX_8_3_27_1508, WINDOWS_8_3_27_2342,
    current_native_target, target_context,
)
from yadinassi.structures import BSLFixedStructure, BSLStructure, fill_property_values


TARGETS = (None, WINDOWS_8_3_27_2342, LINUX_8_3_27_1508)


def interpreter(name):
    return Interpreter() if name is None else Interpreter(native_target=name)


def structure(items, reverse=False):
    result = BSLStructure()
    for key, value in reversed(items) if reverse else items:
        result.insert(key, value)
    return result


class NativeTargetFillTests(unittest.TestCase):
    def test_native_72_case_matrix_and_unchanged_windows_order(self):
        # Linux native target-probes.v1.fill: 3 absence kinds x 3 missing
        # positions x 2 target orders x 2 source orders x 2 source types.
        for name in TARGETS:
            vm = interpreter(name)
            for absence, position, target_reverse, source_reverse, fixed_source in product(
                    ('source', 'target', 'both'), range(3), (False, True),
                    (False, True), (False, True)):
                case = (name, absence, position, target_reverse, source_reverse, fixed_source)
                with self.subTest(case=case):
                    target_items = [('ProbeName', 'старое'), ('ProbeNumber', Decimal(5))]
                    source_items = [('ProbeName', 'Я😀'), ('ProbeNumber', Decimal(9))]
                    if absence == 'source':
                        target_items.append(('Missing', 'old-missing'))
                    if absence == 'target':
                        source_items.append(('Missing', 'new-missing'))
                    target = structure(target_items, target_reverse)
                    source = structure(source_items, source_reverse)
                    if fixed_source:
                        source = BSLFixedStructure(source)
                    original_source = [(pair.key, pair.value) for pair in source]
                    original_keys = [pair.key for pair in target]
                    vm.variables.update(target=target, source=source)
                    names = ['ProbeName', 'ProbeNumber']
                    names.insert(position, 'Missing')
                    vm.variables['selection'] = ','.join(names)
                    with self.assertRaises(BSLRuntimeError) as caught:
                        vm.execute('FillPropertyValues(target, source, selection);', 'fill.bsl')
                    self.assertEqual(caught.exception.message, 'Свойство структуры не найдено: Missing')
                    self.assertEqual(caught.exception.source, 'fill.bsl')
                    expected = (('Я😀', Decimal(9)) if position == 0 else
                                ('старое', Decimal(9)) if position == 1 else
                                ('старое', Decimal(5))) if name == LINUX_8_3_27_1508 else (
                                    ('старое', Decimal(5)) if position == 0 else
                                    ('Я😀', Decimal(5)) if position == 1 else
                                    ('Я😀', Decimal(9)))
                    self.assertEqual((target.get('ProbeName'), target.get('ProbeNumber')), expected)
                    self.assertEqual([pair.key for pair in target], original_keys)
                    self.assertEqual([(pair.key, pair.value) for pair in source], original_source)
                    self.assertEqual(target.property('Missing'), absence == 'source')
                    if absence == 'source':
                        self.assertEqual(target.get('Missing'), 'old-missing')
                    self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)

    def test_linux_original_unknown_include_copies_nothing_and_can_recover(self):
        vm = Interpreter(native_target=LINUX_8_3_27_1508)
        vm.execute('target = New Structure("Имя,Количество", "старое", 5); '
                   'source = New Structure("Имя,Количество", "Я😀", 9); '
                   'Try FillPropertyValues(target, source, "Имя,НетТакогоСвойства"); '
                   'Except caught = True; EndTry;')
        self.assertTrue(vm.variables['caught'])
        self.assertEqual(vm.execute('target.Имя'), 'старое')
        self.assertEqual(vm.execute('target.Количество'), Decimal(5))
        vm.execute('FillPropertyValues(target, source, "Имя,Количество");')
        self.assertEqual(vm.execute('target.Имя'), 'Я😀')
        self.assertEqual(vm.execute('target.Количество'), Decimal(9))

    def test_direct_helper_explicit_linux_context_and_default_windows(self):
        source = BSLStructure('First,Last', 'new-first', 'new-last')
        for name in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            target = BSLStructure('First,Last', 'old-first', 'old-last')
            with target_context(name), self.assertRaisesRegex(ValueError, 'Missing'):
                fill_property_values(target, source, 'First,Missing,Last')
            expected = ('old-first', 'new-last') if name == LINUX_8_3_27_1508 else (
                'new-first', 'old-last')
            self.assertEqual((target.get('First'), target.get('Last')), expected)
        self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)

    def test_success_preserves_spelling_aliases_duplicates_undefined_and_composition(self):
        for name in TARGETS:
            with self.subTest(name=name):
                vm = interpreter(name)
                vm.execute('''
                    items = New Array(); source = New Structure("a,b", items, Undefined);
                    target = New Structure("A,B,Other", 1, 2, 3); alias = target;
                    FillPropertyValues(target, source, "a,B,A"); target.A.Add(7);
                ''')
                target = vm.variables['target']
                self.assertIs(target, vm.variables['alias'])
                self.assertIs(target.get('A'), vm.variables['items'])
                self.assertIsNone(target.get('B'))
                self.assertEqual(target.get('Other'), Decimal(3))
                self.assertEqual([pair.key for pair in target], ['A', 'B', 'Other'])
                self.assertEqual(vm.execute('source.a[0]'), Decimal(7))

    def test_no_list_and_exclude_paths_are_identical_in_every_target(self):
        for name, suffix in product(TARGETS,
                ('', ', Undefined', ', , Undefined', ', Undefined, Undefined',
                 ', , "First"', ', Undefined, "First"')):
            with self.subTest(name=name, suffix=suffix):
                vm = interpreter(name)
                vm.execute('target = New Structure("First,Last,Keep", 1, 2, 3); '
                           'source = New Structure("First,Last,Extra", 10, 20, 30); '
                           f'FillPropertyValues(target, source{suffix});')
                target = vm.variables['target']
                self.assertEqual(target.get('First'), Decimal(1 if '"First"' in suffix else 10))
                self.assertEqual(target.get('Last'), Decimal(20))
                self.assertEqual(target.get('Keep'), Decimal(3))
                self.assertFalse(target.property('Extra'))

    def test_fixed_target_guards_and_errors_are_not_relaxed(self):
        for name in TARGETS:
            vm = interpreter(name)
            vm.execute('target = New FixedStructure("First,Last", 1, 2); '
                       'source = New Structure("First,Last", 10, 20); '
                       'FillPropertyValues(target, source); '
                       'FillPropertyValues(target, source, Undefined, Undefined);')
            for suffix, message in (
                    (', "First"', 'Списки свойств для фиксированного приемника пока не поддерживаются'),
                    (', ""', 'Списки свойств для фиксированного приемника пока не поддерживаются'),
                    (', , "First"', 'Списки свойств для фиксированного приемника пока не поддерживаются'),
                    (', "First", "Last"', 'Одновременные списки заполнения и исключения пока не поддерживаются')):
                with self.subTest(name=name, suffix=suffix):
                    with self.assertRaises(BSLRuntimeError) as caught:
                        vm.execute(f'FillPropertyValues(target, source{suffix});')
                    self.assertEqual(caught.exception.message, message)
            self.assertEqual(vm.execute('target.First'), Decimal(1))
            self.assertEqual(vm.execute('target.Last'), Decimal(2))

    def test_validation_messages_and_no_mutation_remain_unchanged(self):
        cases = [
            ('1, source', 'ЗаполнитьЗначенияСвойств: приемник должен быть структурой'),
            ('target, 1', 'ЗаполнитьЗначенияСвойств: источник должен быть структурой'),
            ('target, source, 1', 'ЗаполнитьЗначенияСвойств: список свойств должен быть строкой'),
            ('target, source, Undefined, True', 'ЗаполнитьЗначенияСвойств: список свойств должен быть строкой'),
            ('target, source, "First", "Last"', 'Одновременные списки заполнения и исключения пока не поддерживаются'),
            ('target, source, ""', 'Пустые имена или пробелы в списках свойств пока не поддерживаются'),
            ('target, source, " First"', 'Пустые имена или пробелы в списках свойств пока не поддерживаются'),
            ('target, source, Undefined, "Missing"', 'Отсутствующие исключаемые свойства пока не поддерживаются'),
        ]
        for name in TARGETS:
            for args, message in cases:
                with self.subTest(name=name, args=args):
                    # Isolate each observation, including newly measured successes.
                    vm = interpreter(name)
                    vm.execute('target = New Structure("First,Last", 1, 2); '
                               'source = New Structure("First,Last", 10, 20);')
                    if name == LINUX_8_3_27_1508 and args in (
                            'target, source, ""', 'target, source, " First"'):
                        vm.execute(f'FillPropertyValues({args});')
                        expected_first = 1 if args.endswith('""') else 10
                        self.assertEqual(vm.execute('target.First'), Decimal(expected_first))
                        self.assertEqual(vm.execute('target.Last'), Decimal(2))
                        continue
                    with self.assertRaises(BSLRuntimeError) as caught:
                        vm.execute(f'FillPropertyValues({args});')
                    self.assertEqual(caught.exception.message, message)
                    self.assertEqual(vm.execute('target.First'), Decimal(1))
                    self.assertEqual(vm.execute('target.Last'), Decimal(2))

    def test_malformed_tokens_still_fail_lazily_in_selected_traversal_order(self):
        for name, malformed, position in product(
                TARGETS, ('', ' First', 'Last ', ' ', 'bad-name'), range(3)):
            with self.subTest(name=name, malformed=malformed, position=position):
                vm = interpreter(name)
                vm.execute('target = New Structure("First,Last", 1, 2); '
                           'source = New Structure("First,Last", 10, 20);')
                names = ['First', 'Last']
                names.insert(position, malformed)
                vm.variables['selection'] = ','.join(names)
                # Native PR86 accepts raw empties and surrounding ASCII spaces
                # only on Linux INCLUDE; whitespace-only remains an error.
                if name == LINUX_8_3_27_1508 and malformed in ('', ' First', 'Last '):
                    vm.execute('FillPropertyValues(target, source, selection);')
                    self.assertEqual(vm.execute('target.First'), Decimal(10))
                    self.assertEqual(vm.execute('target.Last'), Decimal(20))
                    continue
                with self.assertRaises(BSLRuntimeError) as caught:
                    vm.execute('FillPropertyValues(target, source, selection);')
                message = ('Недопустимое имя свойства структуры: bad-name'
                           if malformed == 'bad-name' else
                           'Пустые имена или пробелы в списках свойств пока не поддерживаются')
                self.assertEqual(caught.exception.message, message)
                traversal = list(reversed(names)) if name == LINUX_8_3_27_1508 else names
                copied = traversal[:traversal.index(malformed)]
                self.assertEqual(vm.execute('target.First'), Decimal(10 if 'First' in copied else 1))
                self.assertEqual(vm.execute('target.Last'), Decimal(20 if 'Last' in copied else 2))

    def test_alias_identity_omission_arity_and_procedure_checks_before_operands(self):
        for name in TARGETS:
            vm = interpreter(name)
            observed = []
            vm.register_function('Touch', lambda: observed.append('touch'))
            vm.execute('target = New Structure("First", 1); source = New Structure("First", 2);')
            for alias in ('FillPropertyValues', 'ЗаполнитьЗначенияСвойств'):
                self.assertIs(vm.functions[alias.casefold()].function, fill_property_values)
                for code, message in (
                        (f'{alias}(Touch());', 'ожидает от 2 до 4 аргументов'),
                        (f'{alias}(Touch(), source, Undefined, Undefined, Touch());', 'ожидает от 2 до 4 аргументов'),
                        (f'{alias}(, Touch());', 'Пропуск аргументов'),
                        (f'{alias}(Touch(), , "First");', 'Пропуск аргументов'),
                        (f'result = {alias}(Touch(), source);', 'Процедура не возвращает значение')):
                    with self.subTest(name=name, code=code):
                        with self.assertRaisesRegex(BSLRuntimeError, message):
                            vm.execute(code)
                        self.assertEqual(observed, [])
                vm.execute(f'({alias})(target, source, , "First");')
                self.assertEqual(vm.execute('target.First'), Decimal(1))
            vm.execute('Function Receiver() Touch(); Return New Array(); EndFunction')
            with self.assertRaisesRegex(BSLRuntimeError, 'Пропуск аргументов'):
                vm.execute('Receiver().Add(, 1);')
            self.assertEqual(observed, [])

    def test_operand_evaluation_remains_once_left_to_right_before_reverse_copy(self):
        for name in TARGETS:
            vm = interpreter(name)
            observed = []

            def argument(tag, value):
                observed.append(tag)
                return value

            vm.register_function('Arg', argument)
            vm.execute('target = New Structure("First,Last", 1, 2); '
                       'source = New Structure("First,Last", 10, 20);')
            with self.assertRaisesRegex(BSLRuntimeError, 'Missing'):
                vm.execute('FillPropertyValues(Arg("a", target), Arg("b", source), '
                           'Arg("c", "First,Missing,Last"), Arg("d", Undefined));')
            self.assertEqual(observed, ['a', 'b', 'c', 'd'])
            self.assertEqual((vm.execute('target.First'), vm.execute('target.Last')),
                             (Decimal(1), Decimal(20)) if name == LINUX_8_3_27_1508
                             else (Decimal(10), Decimal(2)))
