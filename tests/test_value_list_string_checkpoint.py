"""String-observer instrumentation, not a native formatting oracle.

Synthetic conversions deliberately disagree and fail independently. Their output
is never saved as native evidence. Complete-output comparators remain strict.
"""
from collections import Counter
from contextlib import ExitStack
from decimal import Decimal
import hashlib
import re
import gc
import weakref
from pathlib import Path
import unittest
from unittest.mock import patch

if __package__:
    from .native_observations import read_observation
else:
    from native_observations import read_observation

from yadinassi import Interpreter, ast, serialization
from yadinassi.parser import parse
from yadinassi.structures import BSLStructure
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, HostFunction, NULL

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало компактных проб строкового представления списка.\n',
           '// Конец компактных проб строкового представления списка.\n\n')
BODY = ('// Начало наблюдений строкового представления списка.\n',
        '// Конец наблюдений строкового представления списка.\n')
FINAL = 'table.list.string.checkpoint.complete: [ok]'
CASES = ('empty', 'absent', 'numbers-booleans', 'strings', 'dates', 'joins', 'load', 'live')


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def section(markers):
    return source().split(markers[0], 1)[1].split(markers[1], 1)[0]


def strip_probe(text):
    for start, end in (
        ('// Начало уточняющих проб кэша строки списка.\n', '// Конец уточняющих проб кэша строки списка.\n\n'),
        ('// Начало уточняющих наблюдений кэша строки списка.\n', '// Конец уточняющих наблюдений кэша строки списка.\n'),
        HELPERS, BODY):
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def observations():
    return [node.expression for node in parse(section(BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


def plain(value):
    if type(value) is BSLArray:
        return [plain(item) for item in value.items]
    if type(value) is BSLStructure:
        return {pair.key: plain(pair.value) for pair in value}
    return value


class Instrumentation:
    def __init__(self, policy='tagged', fail=None):
        self.policy, self.fail = policy, fail
        # Identity-only logs must not make weakly owned items artificially live.
        self.events, self.adds, self.loads, self.outputs = [], [], [], []
        self.vm = Interpreter(self.outputs.append)
        self.vm.register_function('Строка', self.stringify, 'String')
        self.vm.register_function('ЗначениеВСтрокуВнутр', self.write, 'ValueToStringInternal')
        self.vm.execute(source().split('#Область МассивыИСтруктуры', 1)[0])

    def write(self, value):
        if type(value) in (BSLValueList, BSLValueListItem):
            raise AssertionError('raw list/item serialization is forbidden')
        return serialization.value_to_string_internal(value)

    def item_text(self, item):
        if self.policy == 'tagged':
            return 'SYNTHETIC item ' + self.write(item.value) + '/' + item.presentation
        if item.presentation or self.policy == 'labels':
            return item.presentation
        # A deliberately chosen synthetic fallback, not a native expectation.
        return item.value if type(item.value) is str else 'fallback:' + self.write(item.value)

    def stringify(self, value):
        if type(value) is BSLValueListItem:
            owner = value._owner_ref()
            if owner is None or owner._by_id.get(value._id) is not value:
                raise AssertionError('owner must stay alive throughout observation')
            kind = 'item'
            event = (kind, id(owner), value.value, value.presentation, value.check, value._id)
        elif type(value) is BSLValueList:
            kind = 'list'
            event = (kind, id(value))
        else:
            kind = 'scalar'
            event = (kind, value)
        self.events.append(event)
        if kind == self.fail:
            raise ValueError('synthetic ' + kind + ' conversion failure')
        if kind == 'scalar':
            return 'SYNTHETIC scalar ' + self.write(value)
        if kind == 'item':
            return self.item_text(value)
        if self.policy == 'tagged':
            return 'SYNTHETIC list count=' + str(len(value.items))
        parts = [self.item_text(item) for item in value.items]
        if self.policy == 'skip':
            parts = [part for part in parts if part]
        return '; '.join(parts)

    def __enter__(self):
        self.stack = ExitStack()
        original = BSLValueList.get_method
        harness = self
        def get_method(owner, name):
            method = original(owner, name)
            if name.casefold() in ('add', 'добавить'):
                def add(*args):
                    harness.adds.append((id(owner), args))
                    return owner.add(*args)
                return HostFunction(name, add)
            if name.casefold() in ('loadvalues', 'загрузитьзначения'):
                def load(values):
                    harness.loads.append((id(owner), tuple(values.items)))
                    return owner.load_values(values)
                return HostFunction(name, load)
            return method
        self.stack.enter_context(patch.object(BSLValueList, 'get_method', get_method))
        return self

    def __exit__(self, *args):
        self.stack.__exit__(*args)

    def run(self, expression):
        return plain(self.vm.execute(expression))


class ValueListStringCheckpointTests(unittest.TestCase):
    def test_only_new_blocks_added_and_all_native_evidence_protected(self):
        self.assertEqual(blob(('\ufeff' + strip_probe(source())).encode()),
                         '0b7ad4f171bb45a201fe67e05a6dafe7f9e143fa')
        for name, expected in {
            'collections.out': '3a413ce8e775c5275cddac289ebee3a7063192bc',
            'dates.out': '05d23c46540b301820f2ac81c8a67fc0e1273dc8',
            'functions.out': '6df192ac9d10c07755948d7c14cfed9e2311c65f',
            'numbers.out': 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13',
            'strings.out': 'a1ecb5458c3eb10b0df52cd9ae241994a2e4f462',
            'values.out': '016f30d6f3bdb1a814e86a70e3bcf424383a0d27',
        }.items():
            data = (ROOT / 'integrational_tests/output' / name).read_bytes()
            self.assertEqual(blob(data.replace(b'\r\n', b'\n')), expected)
        self.assertEqual(blob((ROOT / 'integrational_tests/meta.md').read_bytes().replace(b'\r\n', b'\n')),
                         'f76530bce7bd3b8a54055b2390ec7551024c62e2')
        self.assertEqual(list((ROOT / 'integrational_tests/output').glob('*.err')), [])
        self.assertIn(FINAL, (ROOT / 'integrational_tests/output/collections.out').read_text(encoding='utf-8'))
        self.assertIn('__version__ = "0.3.2"', (ROOT / 'yadinassi/__init__.py').read_text(encoding='utf-8'))

    def test_complete_owner_string_evidence_and_live_cache_boundary(self):
        # Owner Atridis commit 87723a25f22d359bb72163e184a871d6448930d1.
        # Only checkout line-ending transport is normalized, not native text.
        data = (ROOT / 'integrational_tests/output/collections.out').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(blob(data), '3a413ce8e775c5275cddac289ebee3a7063192bc')
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         'e65040d2ed7a88cdf9e3bc33f242f39a20e76aa612cde6881002a6b4e5273451')
        self.assertEqual((len(data), len(data.splitlines())), (177019, 4142))
        before, added = data.split(b'table.list.string.empty:', 1)
        self.assertEqual(len(before), 162145)
        self.assertEqual(blob(before + b'table.checkpoint.complete: [ok]\n'),
                         'd4cce35fea3cc5271a871c26062c1b6167c0b092')
        tail = b'table.list.string.empty:' + added
        self.assertEqual(len(tail.splitlines()), 206)
        self.assertTrue(tail.endswith((FINAL + '\ntable.checkpoint.complete: [ok]\n').encode()))
        labels = re.findall(rb'^table\.list\.string\.([a-z.-]+): \[', tail, re.MULTILINE)
        self.assertEqual([label.decode() for label in labels], list(CASES) + ['checkpoint.complete'])
        records = {name: plain(read_observation(payload, compact=True))
                   for name, payload in re.findall(r'^table\.list\.string\.([a-z.-]+): \[\n(.*?)^\]\n',
                                                   tail.decode(), re.MULTILINE | re.DOTALL)}
        self.assertEqual(tuple(records), CASES)
        states = []
        def visit(value):
            if type(value) is dict:
                if set(value) == {'Count', 'Items', 'Text'}:
                    states.append(value)
                else:
                    for key, child in value.items():
                        if key in ('Prepare', 'Status'):
                            self.assertEqual(child, 'ok')
                        if key == 'SameItem':
                            self.assertIs(child, True)
                        visit(child)
        for record in records.values():
            visit(record)
        self.assertEqual(len(states), 36)
        self.assertEqual(sum(len(state['Items']) for state in states), 52)
        for state in states:
            self.assertEqual(state['Count'], len(state['Items']))
            conversions = [state['Text']]
            for index, row in enumerate(state['Items']):
                self.assertEqual(len(row), 6)
                self.assertEqual(row[3], index)
                self.assertIs(type(row[1]), str)
                self.assertIs(type(row[2]), bool)
                conversions.extend(row[4:])
            for conversion in conversions:
                self.assertEqual(conversion['Status'], 'ok')
                self.assertIs(type(conversion['Text']), str)
        # This proves stale text after these field changes, not when the cache
        # initializes or which structural operations invalidate it.
        live = records['live']
        self.assertEqual(live['Initial']['Text']['Text'], '7')
        self.assertEqual([live[key]['State']['Text']['Text'] for key in
                          ('Value', 'Label', 'LabeledValue', 'Checked', 'Unchecked', 'Whitespace', 'Cleared', 'Undefined')],
                         ['7'] * 8)
        self.assertEqual(live['Undefined']['State']['Items'][0][5]['Text'], '<Пустое значение>')

    def test_fixed_unique_labels_full_parse_and_declarations_first(self):
        calls = observations()
        self.assertEqual([call.arguments[0].value for call in calls], ['list.string.' + case for case in CASES])
        for call in calls:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(a, ast.Literal) and type(a.value) is str for a in call.arguments))
            self.assertLess(len(call.arguments[1].value), 100)
            parse('Result = ' + call.arguments[1].value)
        self.assertEqual(source().count(FINAL), 1)
        self.assertLess(source().index(BODY[1]), source().index('// Начало уточняющих наблюдений кэша строки списка.'))
        self.assertTrue(source().endswith('Сообщить("table.checkpoint.complete: [ok]");\n'))
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_each_record_reaches_all_conversions_and_preserves_owners(self):
        with Instrumentation() as h:
            h.vm.execute(section(BODY))
            self.assertEqual([text.split(': [', 1)[0] for text in h.outputs],
                             ['table.list.string.' + case for case in CASES] + [FINAL.split(':')[0]])
            self.assertEqual(Counter(event[0] for event in h.events),
                             {'list': 36, 'item': 52, 'scalar': 52})
            for text in h.outputs:
                for error in ('[serialize-error]', '[iteration-error]', '[limit]', '[id-error]', '[error]'):
                    self.assertNotIn(error, text)
            self.assertEqual([len(values) for _, values in h.loads], [0, 8])
            self.assertEqual([args for _, args in h.adds].count(()), 1)

    def test_harness_does_not_itself_keep_item_owners_alive(self):
        # Logs retain only integer identities, never a live owner. A released
        # negative control must fail the same guard used during the BSL run.
        with Instrumentation() as h:
            owner = BSLValueList()
            item = owner.add(Decimal(7))
            ref = weakref.ref(owner)
            h.stringify(item)
            h.stringify(owner)
            del owner
            gc.collect()
            self.assertIsNone(ref())
            with self.assertRaisesRegex(AssertionError, 'owner must stay alive'):
                h.stringify(item)
            h.vm.register_function('OrphanForProbe', lambda: item)
            with self.assertRaisesRegex(AssertionError, 'owner must stay alive'):
                h.run('РезультатТекстаСписка(OrphanForProbe())')

    def test_omitted_and_explicit_undefined_are_distinct_calls(self):
        with Instrumentation() as h:
            result = h.run('СкалярныеТекстыСписка("absent")')
            self.assertEqual([args for _, args in h.adds], [(), (None,), (NULL,)])
            for name, value in [('Omitted', None), ('Undefined', None), ('Null', NULL)]:
                state = result[name]['State']
                self.assertEqual(result[name]['Prepare'], 'ok')
                self.assertEqual(state['Items'][0][:4], [value, '', False, Decimal(0)])
                self.assertEqual(state['Items'][0][4]['Status'], 'ok')
                self.assertEqual(state['Items'][0][5]['Status'], 'ok')
                self.assertEqual(state['Text']['Status'], 'ok')

    def test_scalar_values_and_exact_strings_reach_independent_controls(self):
        groups = {
            'numbers-booleans': [Decimal(0), Decimal('-7.25'), Decimal('1234.5'), False, True],
            'strings': ['', ' ', 'Я😀', 'a; b', 'a\nb', r'a\nb'],
        }
        for group, expected in groups.items():
            with self.subTest(group=group), Instrumentation() as h:
                result = h.run(f'СкалярныеТекстыСписка("{group}")')
                rows = [entry['State']['Items'][0] for entry in result.values()]
                self.assertEqual([row[0] for row in rows], expected)
                for row in rows:
                    self.assertEqual(row[4]['Text'], 'SYNTHETIC scalar ' + h.write(row[0]))
                    self.assertNotEqual(row[4]['Text'], row[5]['Text'])
        with Instrumentation() as h:
            dates = h.run('СкалярныеТекстыСписка("dates")')
            rows = [entry['State']['Items'][0] for entry in dates.values()]
            self.assertEqual([h.write(row[0]) for row in rows],
                             ['{"D",00010101000000}', '{"D",20240229131415}'])

    def test_each_conversion_failure_leaves_both_other_conversions_visible(self):
        for failure in ('scalar', 'item', 'list'):
            with self.subTest(failure=failure), Instrumentation(fail=failure) as h:
                result = h.run('ОдинТекстСписка(1234.5)')['State']
                row = result['Items'][0]
                self.assertEqual(row[:4], [Decimal('1234.5'), '', False, Decimal(0)])
                actual = {'scalar': row[4], 'item': row[5], 'list': result['Text']}
                for kind, conversion in actual.items():
                    self.assertEqual(conversion['Status'], 'error' if kind == failure else 'ok')
                    self.assertEqual(conversion['Text'] is None, kind == failure)
                self.assertEqual([event[0] for event in h.events], ['scalar', 'item', 'list'])

    def test_fields_id_count_and_iteration_failures_are_independent(self):
        original = BSLValueListItem.get_member
        for field in ('value', 'presentation', 'check'):
            def get_member(item, name):
                if name.casefold() == field:
                    raise ValueError('synthetic field failure')
                return original(item, name)
            with self.subTest(field=field), Instrumentation() as h:
                with patch.object(BSLValueListItem, 'get_member', get_member):
                    state = h.run('ОдинТекстСписка(7)')['State']
                row = state['Items'][0]
                self.assertEqual(row[('value', 'presentation', 'check').index(field)], '[' + field + '-error]')
                self.assertEqual(row[3], Decimal(0))
                self.assertEqual(row[5]['Status'], 'ok')
                self.assertEqual(state['Text']['Status'], 'ok')
                if field == 'value':
                    self.assertEqual(row[4], '[value-read-error]')
                else:
                    self.assertEqual(row[4]['Status'], 'ok')
        for target, method, expected in [(BSLValueListItem, 'get_id', '[id-error]'),
                                         (BSLValueList, 'count', '[error]'),
                                         (BSLValueList, '__iter__', '[iteration-error]')]:
            with self.subTest(method=method), Instrumentation() as h:
                with patch.object(target, method, side_effect=ValueError('synthetic failure')):
                    state = h.run('ОдинТекстСписка(7)')['State']
                self.assertEqual(state['Text']['Status'], 'ok')
                if method == '__iter__':
                    self.assertEqual(state['Items'], [expected])
                elif method == 'count':
                    self.assertEqual(state['Count'], expected)
                    self.assertEqual(len(state['Items']), 1)
                else:
                    self.assertEqual(state['Items'][0][3], expected)
                    self.assertEqual(state['Items'][0][4]['Status'], 'ok')
                    self.assertEqual(state['Items'][0][5]['Status'], 'ok')

    def test_competing_empty_join_and_fallback_policies_are_distinguishable(self):
        results = {}
        for policy in ('preserve', 'skip', 'labels'):
            with Instrumentation(policy) as h:
                joins = h.run('СоставныеТекстыСписка()')
                results[policy] = [entry['State']['Text']['Text'] for entry in joins.values()]
                self.assertEqual([entry['State']['Count'] for entry in joins.values()], [2, 3, 2, 3, 3, 3, 3])
                self.assertEqual([row[3] for row in joins['Interior']['State']['Items']], [0, 1, 2])
        self.assertEqual(results['preserve'][:4], ['; A', 'A; ; B', 'A; ', '; ; '])
        self.assertEqual(results['skip'][:4], ['A', 'A; B', 'A', ''])
        self.assertEqual(results['labels'][:4], ['; ', '; ; ', '; ', '; ; '])
        self.assertEqual(len({tuple(result) for result in results.values()}), 3)

    def test_live_snapshots_keep_fields_identity_and_no_presentation_cache(self):
        with Instrumentation('preserve') as h:
            result = h.run('ЖивыеТекстыСписка()')
            self.assertEqual(h.adds[0][1], (Decimal(7), ''))  # Explicit empty at construction.
            names = ('Value', 'Label', 'LabeledValue', 'Checked', 'Unchecked', 'Whitespace', 'Cleared', 'Undefined')
            states = [result['Initial']] + [result[name]['State'] for name in names]
            rows = [state['Items'][0] for state in states]
            self.assertEqual([row[0] for row in rows],
                             [Decimal(7), Decimal('-7.25'), Decimal('-7.25')] + [Decimal('1234.5')] * 5 + [None])
            self.assertEqual([row[1] for row in rows], ['', '', 'fixed; Я😀', 'fixed; Я😀',
                                                     'fixed; Я😀', 'fixed; Я😀', ' ', '', ''])
            self.assertEqual([row[2] for row in rows], [False] * 4 + [True] + [False] * 4)
            self.assertEqual([row[3] for row in rows], [0] * 9)
            self.assertTrue(all(result[name]['SameItem'] is True and result[name]['Status'] == 'ok' for name in names))
            self.assertEqual(rows[2][5]['Text'], rows[3][5]['Text'])
            self.assertNotEqual(rows[2][4]['Text'], rows[3][4]['Text'])
            self.assertEqual(rows[6][5]['Text'], ' ')
            self.assertNotEqual(rows[6][5]['Text'], rows[7][5]['Text'])
            self.assertEqual(len({event[1] for event in h.events if event[0] == 'item'}), 1)

    def test_output_encoding_distinguishes_newline_and_literal_escape(self):
        with Instrumentation('preserve') as h:
            h.vm.execute('НаблюдатьТаблицы("test", "СкалярныеТекстыСписка(""strings"")")')
            text = h.outputs[0]
            newline = next(line for line in text.splitlines() if line.startswith('  Newline.State.Items='))
            escaped = next(line for line in text.splitlines() if line.startswith('  Escaped.State.Items='))
            self.assertIn(r'{"S","a\nb"}', newline)
            self.assertIn(r'{"S","a\\nb"}', escaped)
            self.assertNotEqual(newline.split('=', 1)[1], escaped.split('=', 1)[1])
            self.assertNotIn('[serialize-error]', text)

    def test_prepare_failures_preserve_state_and_do_not_hide_later_cases(self):
        with Instrumentation() as h:
            with patch.object(BSLValueList, 'add', side_effect=ValueError('synthetic Add failure')):
                result = h.run('СкалярныеТекстыСписка("absent")')
            self.assertEqual(list(result), ['Omitted', 'Undefined', 'Null'])
            self.assertEqual(len(h.adds), 3)
            for entry in result.values():
                self.assertEqual(entry['Prepare'], 'error')
                self.assertEqual(entry['State']['Count'], 0)
                self.assertEqual(entry['State']['Items'], [])
                self.assertEqual(entry['State']['Text']['Status'], 'ok')
        original = BSLValueList.load_values
        def fail_after_load(owner, values):
            original(owner, values)
            raise ValueError('synthetic failure after loading')
        with Instrumentation() as h:
            with patch.object(BSLValueList, 'load_values', fail_after_load):
                result = h.run('ЗагруженныеТекстыСписка()')
            self.assertEqual(result['Prepare'], 'error')
            self.assertEqual(result['State']['Count'], 8)
            self.assertEqual([row[3] for row in result['State']['Items']], list(range(8)))
            self.assertEqual(result['State']['Text']['Status'], 'ok')

    def test_failed_live_mutation_captures_post_error_state_and_continues(self):
        original = BSLValueListItem.set_member
        def fail_after_check(item, name, value):
            original(item, name, value)
            if name.casefold() == 'check':
                raise ValueError('synthetic failure after Check mutation')
        with Instrumentation() as h:
            with patch.object(BSLValueListItem, 'set_member', fail_after_check):
                result = h.run('ЖивыеТекстыСписка()')
            self.assertEqual(result['Checked']['Status'], 'error')
            self.assertEqual(result['Unchecked']['Status'], 'error')
            self.assertTrue(result['Checked']['State']['Items'][0][2])
            self.assertFalse(result['Unchecked']['State']['Items'][0][2])
            self.assertFalse(result['Initial']['Items'][0][2])
            self.assertEqual(result['Undefined']['Status'], 'ok')
            self.assertIsNone(result['Undefined']['State']['Items'][0][0])

    def test_successful_empty_or_error_like_text_is_not_a_failure_marker(self):
        with Instrumentation() as h:
            def text(value):
                if type(value) is BSLValueListItem:
                    return ''
                return '[error]' if type(value) is BSLValueList else '[serialize-error]'
            h.vm.register_function('Строка', text, 'String')
            result = h.run('ОдинТекстСписка(7)')['State']
            self.assertEqual(result['Items'][0][4], {'Status': 'ok', 'Text': '[serialize-error]'})
            self.assertEqual(result['Items'][0][5], {'Status': 'ok', 'Text': ''})
            self.assertEqual(result['Text'], {'Status': 'ok', 'Text': '[error]'})

    def test_snapshot_iteration_is_bounded_without_skipping_list_conversion(self):
        with Instrumentation() as h:
            owner = BSLValueList()
            for index in range(9):
                owner.add(Decimal(index))
            h.vm.register_function('OwnerForProbe', lambda: owner)
            state = h.run('СнимокТекстаСписка(OwnerForProbe())')
            self.assertEqual(state['Count'], 9)
            self.assertEqual(len(state['Items']), 9)
            self.assertEqual(state['Items'][-1], '[limit]')
            self.assertEqual(state['Text']['Status'], 'ok')
            self.assertEqual(Counter(event[0] for event in h.events), {'scalar': 8, 'item': 8, 'list': 1})


if __name__ == '__main__':
    unittest.main()
