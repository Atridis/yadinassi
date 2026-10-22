"""Cache-probe instrumentation, never an oracle for native 1C cache semantics.

Competing synthetic caches run the actual BSL helpers. Their outputs are not
native evidence and are never written to the integration output directory.
"""
from scripts.native_historical_replay import FILL_EXCLUDE_PROBE_BLOCKS, FILL_INCLUDE_PROBE_BLOCKS, DESCRIPTOR_MAP_PROBE_BLOCKS, FIELD_REFERENCE_BLOCKS, without_descriptor_map_probes
from collections import Counter
from contextlib import ExitStack
from decimal import Decimal
import gc
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import weakref

from yadinassi import Interpreter, ast, serialization
from yadinassi.parser import parse
from yadinassi.structures import BSLStructure
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, HostFunction


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало уточняющих проб кэша строки списка.\n',
           '// Конец уточняющих проб кэша строки списка.\n\n')
BODY = ('// Начало уточняющих наблюдений кэша строки списка.\n',
        '// Конец уточняющих наблюдений кэша строки списка.\n')
FINAL = 'table.list.string-cache.checkpoint.complete: [ok]'
GROUPS = ('initialize', 'structural', 'controls', 'empty', 'copy')
INITIAL = ('ValueUnread', 'ValueScalar', 'ValueItem',
           'PresentationUnread', 'PresentationItem')
STRUCTURAL = ('Add', 'Insert', 'Delete', 'Clear', 'LoadValues', 'LoadEmpty',
              'Move', 'SortValue', 'SortPresentation')
CONTROLS = ('FillChecks', 'MoveNoop', 'SortValueNoop',
            'SortPresentationNoop', 'DeleteError')


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def section(markers):
    return source().split(markers[0], 1)[1].split(markers[1], 1)[0]


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def plain(value):
    if type(value) is BSLArray:
        return [plain(item) for item in value.items]
    if type(value) is BSLStructure:
        return {pair.key: plain(pair.value) for pair in value}
    return value


def rows(owner):
    return tuple((item.value, item.presentation, item.check, item._id)
                 for item in owner.items)


def rendered(state):
    return '|'.join(row[1] or 'v=' + str(row[0]) for row in state)


def observations():
    return [node.expression for node in parse(section(BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


class Instrumentation:
    """Intentionally synthetic first-read caches, with identity-only logs.

    Weak keys and scalar snapshots avoid keeping item owners artificially alive.
    Membership, not truthiness, distinguishes a cached empty string from a miss.
    """
    def __init__(self, initialize='list', invalidate='lazy', copy='fresh',
                 fail=None, text=None, truthy_miss=False, helper_mutation=None):
        self.initialize, self.invalidate, self.copy_policy = initialize, invalidate, copy
        self.fail, self.text, self.truthy_miss = fail, text, truthy_miss
        self.cache = weakref.WeakKeyDictionary()
        self.events, self.actions, self.outputs = [], [], []
        self.vm = Interpreter(self.outputs.append)
        self.vm.register_function('Строка', self.stringify, 'String')
        self.vm.register_function('ЗначениеВСтрокуВнутр', self.write, 'ValueToStringInternal')
        helpers = source().split('#Область МассивыИСтруктуры', 1)[0]
        if helper_mutation:
            helpers = helpers.replace(
                'Функция ПоляКэшаСписка(Знач Список)\n',
                'Функция ПоляКэшаСписка(Знач Список)\n' + helper_mutation, 1)
        self.vm.execute(helpers)

    @staticmethod
    def reject_raw(value):
        if type(value) in (BSLValueList, BSLValueListItem):
            raise AssertionError('raw list/item serialization is forbidden')
        if type(value) is BSLArray:
            for item in value.items:
                Instrumentation.reject_raw(item)
        if type(value) is BSLStructure:
            for pair in value:
                Instrumentation.reject_raw(pair.value)

    def write(self, value):
        self.reject_raw(value)
        return serialization.value_to_string_internal(value)

    def stringify(self, value):
        if type(value) is BSLValueListItem:
            owner = value._owner_ref()
            if owner is None or owner._by_id.get(value._id) is not value:
                raise AssertionError('owner must stay alive throughout observation')
            kind, state = 'item', ((value.value, value.presentation, value.check, value._id),)
            self.events.append((kind, id(owner), state))
        elif type(value) is BSLValueList:
            owner, kind, state = value, 'list', rows(value)
            self.events.append((kind, id(owner), state))
        else:
            kind = 'scalar'
            self.events.append((kind, value))
        if kind == self.fail:
            raise ValueError('synthetic ' + kind + ' conversion failure')
        if self.text is not None:
            return self.text
        if kind == 'scalar':
            return 'scalar:' + str(value)
        if kind == 'item':
            if self.initialize == 'item' and owner not in self.cache:
                self.cache[owner] = rendered(rows(owner))
            return rendered(state)
        missing = not self.cache.get(owner) if self.truthy_miss else owner not in self.cache
        if missing:
            self.cache[owner] = rendered(state)
        return self.cache[owner]

    def __enter__(self):
        self.stack = ExitStack()
        original = BSLValueList.get_method
        harness = self
        methods = {'add', 'insert', 'delete', 'clear', 'loadvalues', 'move',
                   'sortbyvalue', 'sortbypresentation', 'fillchecks', 'copy'}

        def get_method(owner, name):
            method = original(owner, name)
            key = name.casefold()
            if key not in methods:
                return method

            def action(*args):
                before = rows(owner)
                try:
                    result = method(*args)
                except Exception:
                    harness.actions.append((key, id(owner), before, rows(owner), 'error'))
                    raise
                harness.actions.append((key, id(owner), before, rows(owner), 'ok'))
                if key == 'copy':
                    if harness.copy_policy == 'eager':
                        harness.cache[result] = rendered(rows(result))
                    elif harness.copy_policy == 'inherited' and owner in harness.cache:
                        harness.cache[result] = harness.cache[owner]
                elif owner in harness.cache:
                    if harness.invalidate == 'eager':
                        harness.cache[owner] = rendered(rows(owner))
                    elif harness.invalidate == 'lazy':
                        del harness.cache[owner]
                elif harness.initialize == 'insert' and key in ('add', 'insert'):
                    harness.cache[owner] = rendered(rows(owner))
                return result

            return HostFunction(name, action, returns_value=method.returns_value)

        self.stack.enter_context(patch.object(BSLValueList, 'get_method', get_method))
        return self

    def __exit__(self, *args):
        self.stack.__exit__(*args)

    def run(self, expression):
        return plain(self.vm.execute(expression))


class ValueListStringCacheCheckpointTests(unittest.TestCase):
    def test_new_blocks_restore_old_source_and_preserve_current_native_evidence(self):
        text = source()
        for start, end in (
            *FILL_EXCLUDE_PROBE_BLOCKS, *FILL_INCLUDE_PROBE_BLOCKS, *DESCRIPTOR_MAP_PROBE_BLOCKS, *FIELD_REFERENCE_BLOCKS,
            ('// Начало заключительных проб пустой строки кэша списка.\n', '// Конец заключительных проб пустой строки кэша списка.\n\n'),
            ('// Начало заключительных наблюдений пустой строки кэша списка.\n', '// Конец заключительных наблюдений пустой строки кэша списка.\n'),
            HELPERS, BODY):
            self.assertEqual(text.count(start), 1)
            self.assertEqual(text.count(end), 1)
            before, rest = text.split(start, 1)
            _, after = rest.split(end, 1)
            text = before + after
        self.assertEqual(blob(('\ufeff' + text).encode()),
                         'eb8e11cbd332225cfbdeb19ac4b203691ad45662')
        native = (ROOT / 'tests/fixtures/native_windows/collections.out').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(blob(native),
                         '97e90791a4011bd7f6ef2922533f92f698557cbd')
        self.assertEqual(len(native), 200954)
        self.assertEqual(len(native.splitlines()), 4579)
        self.assertIn(FINAL.encode(), native)
        self.assertNotIn(b'list.string-cache.final.complete', native)

    def test_five_fixed_labels_full_parse_and_all_declarations_first(self):
        calls = observations()
        self.assertEqual([call.arguments[0].value for call in calls],
                         ['list.string-cache.' + group for group in GROUPS])
        for call in calls:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(a, ast.Literal) and type(a.value) is str
                                for a in call.arguments))
            self.assertLess(len(call.arguments[1].value), 100)
            parse('Result = ' + call.arguments[1].value)
        self.assertEqual(source().count(FINAL), 1)
        self.assertLess(source().index(BODY[1]), source().index('// Начало заключительных наблюдений пустой строки кэша списка.'))
        self.assertTrue(without_descriptor_map_probes(source()).endswith('Сообщить("table.checkpoint.complete: [ok]");\n'))
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_source_loader_ignores_cp1252_platform_default(self):
        expected = source()
        original = Path.read_text
        def platform_read(path, encoding=None, errors=None):
            return original(path, encoding=encoding or 'cp1252', errors=errors)
        with patch.object(Path, 'read_text', platform_read):
            self.assertNotEqual(SOURCE.read_text(errors='replace'), expected)
            self.assertEqual(source(), expected)
            self.assertEqual(len(observations()), 5)

    def test_all_twenty_one_microcases_reached_and_records_serialize_safely(self):
        with Instrumentation() as h:
            results = [h.run(call.arguments[1].value) for call in observations()]
            self.assertEqual(list(results[0]), list(INITIAL))
            self.assertEqual(list(results[1]), list(STRUCTURAL))
            self.assertEqual(list(results[2]), list(CONTROLS))
            self.assertEqual(sum(map(len, results[:3])) + 2, 21)
            self.assertEqual(Counter(event[0] for event in h.events),
                             {'list': 59, 'item': 9, 'scalar': 1})
            h.events.clear()
            h.vm.execute(section(BODY))
            self.assertEqual(Counter(event[0] for event in h.events),
                             {'list': 59, 'item': 9, 'scalar': 1})
            self.assertEqual([text.split(': [', 1)[0] for text in h.outputs],
                             ['table.list.string-cache.' + group for group in GROUPS]
                             + [FINAL.split(':')[0]])
            for text in h.outputs:
                self.assertNotIn('[serialize-error]', text)
                self.assertNotIn('[iteration-error]', text)
                self.assertNotIn('[value-error]', text)
            labels = [line.split('=', 1)[0] for text in h.outputs
                      for line in text.splitlines() if line.startswith('  ')]
            # Paths are unique within each grouped record, not across records.
            for text in h.outputs:
                paths = [line.split('=', 1)[0] for line in text.splitlines()
                         if line.startswith('  ')]
                self.assertEqual(len(paths), len(set(paths)))
            self.assertGreater(len(labels), 400)

    def test_field_only_snapshot_does_not_prime_and_detects_accidental_conversion(self):
        for extra in ('', '    Игнор = РезультатТекстаСписка(Список);\n',
                      '    Игнор = РезультатТекстаСписка(Список.Get(0));\n'):
            with self.subTest(extra=extra), Instrumentation(helper_mutation=extra) as h:
                owner = BSLValueList()
                for index in range(9):
                    owner.add(Decimal(index), 'label')
                h.vm.register_function('OwnerForProbe', lambda: owner)
                state = h.run('ПоляКэшаСписка(OwnerForProbe())')
                self.assertEqual(state['Count'], 9)
                self.assertEqual(state['Items'][-1], '[limit]')
                self.assertEqual([row[3] for row in state['Items'][:-1]], list(range(8)))
                if extra:
                    with self.assertRaises(AssertionError):
                        self.assertEqual(h.events, [])
                else:
                    self.assertEqual(h.events, [])
                    self.assertNotIn(owner, h.cache)

    def test_initialize_mutations_and_exact_conversion_order(self):
        for case, kind, trigger in [
            ('ValueUnread', 'value', 'none'), ('ValueScalar', 'value', 'scalar'),
            ('ValueItem', 'value', 'item'), ('PresentationUnread', 'presentation', 'none'),
            ('PresentationItem', 'presentation', 'item'),
        ]:
            with self.subTest(case=case), Instrumentation() as h:
                result = h.run(f'ИнициализацияКэшаСписка("{kind}", "{trigger}")')
                expected = [(8, ''), (9, ''), (10, '')] if kind == 'value' else [
                    (7, 'middle'), (7, 'latest'), (7, 'after')]
                for phase, (value, presentation) in zip(('Middle', 'Before', 'After'), expected):
                    self.assertEqual(result[phase], {
                        'Count': 1, 'Items': [[Decimal(value), presentation, False, Decimal(0)]]})
                    self.assertEqual(result[phase + 'Status'], 'ok')
                prefix = [] if trigger == 'none' else [trigger]
                self.assertEqual([event[0] for event in h.events], prefix + ['list', 'item', 'list'])
                self.assertEqual(result['Trigger'] == 'not-run', trigger == 'none')
                self.assertEqual(h.actions[0][3][0][:2],
                                 (7, '' if kind == 'value' else 'start'))
                self.assertEqual(h.events[-3][2], tuple(map(tuple, result['Before']['Items'])))
                self.assertEqual(h.events[-2][2], tuple(map(tuple, result['After']['Items'])))
                if trigger == 'item':
                    self.assertEqual(h.events[0][2], tuple(map(tuple, result['Middle']['Items'])))
                elif trigger == 'scalar':
                    self.assertEqual(h.events[0], ('scalar', Decimal(8)))

    def test_insert_item_and_first_list_initialization_have_different_signatures(self):
        expected = {
            'insert': ['v=7', 'v=7', 'v=7', 'start', 'start'],
            'item': ['v=9', 'v=9', 'v=8', 'latest', 'middle'],
            'list': ['v=9', 'v=9', 'v=9', 'latest', 'latest'],
        }
        signatures = []
        for policy, texts in expected.items():
            with self.subTest(policy=policy), Instrumentation(initialize=policy, invalidate='never') as h:
                result = h.run('НачалоКэшаСписка()')
                first = [case['First']['Text'] for case in result.values()]
                self.assertEqual(first, texts)
                self.assertEqual([case['Second']['Text'] for case in result.values()], texts)
                self.assertEqual([case['ItemAfter']['Text'] for case in result.values()],
                                 ['v=10'] * 3 + ['after'] * 2)
                self.assertEqual(result['ValueScalar']['Trigger']['Text'], 'scalar:8')
                signatures.append(tuple(first))
        self.assertEqual(len(set(signatures)), 3)

    def test_structural_actions_and_noops_have_expected_field_order_and_ids(self):
        pending = [(40, 'pending', False, 0), (10, 'c', False, 1), (20, 'a', False, 2)]
        ordered = [(11, 'aa', False, 0), (20, 'b', False, 1), (30, 'c', False, 2)]
        expected = {
            'Add': pending + [(50, 'new', False, 3)],
            'Insert': [(50, 'new', False, 3)] + pending,
            'Delete': [pending[0], pending[2]], 'Clear': [],
            'LoadValues': [(70, '', False, 3), (80, '', False, 4)], 'LoadEmpty': [],
            'Move': [pending[1], pending[0], pending[2]],
            'SortValue': [pending[1], pending[2], pending[0]],
            'SortPresentation': [pending[2], pending[1], pending[0]],
            'FillChecks': [(v, p, True, i) for v, p, _, i in pending],
            'MoveNoop': pending, 'SortValueNoop': ordered,
            'SortPresentationNoop': ordered, 'DeleteError': pending,
        }
        for action, after in expected.items():
            with self.subTest(action=action), Instrumentation() as h:
                result = h.run(f'ДействиеКэшаСписка("{action}")')
                is_ordered = action in ('SortValueNoop', 'SortPresentationNoop')
                initial = ([(10, 'a', False, 0), (20, 'b', False, 1), (30, 'c', False, 2)]
                           if is_ordered else
                           [(30, 'b', False, 0), (10, 'c', False, 1), (20, 'a', False, 2)])
                self.assertEqual(result['Prepare'], 'ok')
                self.assertEqual(result['PendingStatus'], 'ok')
                self.assertEqual(result['Initial'], {'Count': 3, 'Items': list(map(list, initial))})
                self.assertEqual(result['Warm'], {'Status': 'ok', 'Text': rendered(initial)})
                self.assertEqual(result['Status'], 'error' if action == 'DeleteError' else 'ok')
                self.assertEqual(result['Before']['Items'],
                                 list(map(list, ordered if is_ordered else pending)))
                self.assertEqual(result['AfterAction'], {'Count': len(after), 'Items': list(map(list, after))})
                for phase, value, presentation in [('Between', 99, 'between'), ('After', 100, 'after')]:
                    changed = list(after)
                    if changed:
                        changed[0] = (value, presentation, after[0][2], after[0][3])
                    self.assertEqual(result[phase], {'Count': len(after), 'Items': list(map(list, changed))})
                    self.assertEqual(result[phase + 'Status'], 'ok' if after else 'empty')
                self.assertEqual([event[0] for event in h.events], ['list'] * 3)
                for event, phase in zip(h.events, ('Initial', 'Between', 'After')):
                    self.assertEqual(event[2], tuple(map(tuple, result[phase]['Items'])))
                self.assertEqual(h.actions[-1][3], tuple(after))
                self.assertEqual(h.actions[-1][4], result['Status'])
                method = {'LoadEmpty': 'loadvalues', 'DeleteError': 'delete',
                          'SortValue': 'sortbyvalue', 'SortValueNoop': 'sortbyvalue',
                          'SortPresentation': 'sortbypresentation',
                          'SortPresentationNoop': 'sortbypresentation',
                          'MoveNoop': 'move'}.get(action, action.lower())
                self.assertEqual(h.actions[-1][0], method)

    def test_post_action_mutation_distinguishes_eager_lazy_and_never_invalidation(self):
        for action in STRUCTURAL + CONTROLS:
            signatures = []
            for policy in ('eager', 'lazy', 'never'):
                with self.subTest(action=action, policy=policy), Instrumentation(invalidate=policy) as h:
                    result = h.run(f'ДействиеКэшаСписка("{action}")')
                    phase = ('Initial' if policy == 'never' or action == 'DeleteError'
                             else 'AfterAction' if policy == 'eager' else 'Between')
                    self.assertEqual(result['First'], {
                        'Status': 'ok', 'Text': rendered(result[phase]['Items'])})
                    self.assertEqual(result['Second'], result['First'])
                    signatures.append(result['First']['Text'])
            expected_count = 1 if action == 'DeleteError' else 2 if action in ('Clear', 'LoadEmpty') else 3
            self.assertEqual(len(set(signatures)), expected_count, action)

    def test_warmed_empty_string_is_a_cache_hit_not_a_falsy_sentinel(self):
        outputs = []
        for broken in (False, True):
            with Instrumentation(invalidate='never', truthy_miss=broken) as h:
                result = h.run('ПустойКэшСписка()')
                self.assertEqual(result['Warm'], {'Status': 'ok', 'Text': ''})
                self.assertEqual(result['Before'], {'Count': 0, 'Items': []})
                self.assertEqual(result['AfterAction']['Items'], [[7, 'first', False, 0]])
                self.assertEqual(result['FirstState']['Items'], [[7, 'between', False, 0]])
                self.assertEqual(result['BetweenStatus'], 'ok')
                self.assertEqual(result['After']['Items'], [[7, 'second', False, 0]])
                self.assertEqual(result['ItemAfter'], {'Status': 'ok', 'Text': 'second'})
                self.assertEqual(result['Second'], result['First'])
                outputs.append(result['First']['Text'])
        self.assertEqual(outputs, ['', 'between'])
        for policy, expected in [('lazy', 'between'), ('eager', 'first')]:
            with Instrumentation(invalidate=policy) as h:
                result = h.run('ПустойКэшСписка()')
                self.assertEqual(result['First']['Text'], expected)
                self.assertEqual(result['Second']['Text'], expected)

    def test_copy_distinguishes_fresh_eager_and_inherited_caches_without_aliasing(self):
        for policy, expected in [('fresh', 'copy-between'), ('eager', 'source-current'), ('inherited', 'start')]:
            with self.subTest(policy=policy), Instrumentation(copy=policy) as h:
                result = h.run('КопияКэшаСписка()')
                self.assertEqual(result['Status'], 'ok')
                self.assertEqual(result['Before'], result['SourceAfter'])
                self.assertEqual(result['CopyAfter'], result['SourceAfter'])
                self.assertEqual(result['SourceAfter']['Items'], [[7, 'source-current', False, 0]])
                self.assertEqual(result['Between']['Items'], [[8, 'copy-between', False, 0]])
                self.assertEqual(result['After']['Items'], [[9, 'copy-after', False, 0]])
                self.assertEqual(result['First'], {'Status': 'ok', 'Text': expected})
                self.assertEqual(result['Second'], result['First'])
                self.assertEqual(result['Source']['Text'], 'start')
                self.assertEqual(result['SourceItem']['Text'], 'source-current')
                owners = [event[1] for event in h.events if event[0] == 'list']
                self.assertEqual(owners[::2], [owners[0]] * 2)
                self.assertEqual(owners[1::2], [owners[1]] * 2)
                self.assertNotEqual(owners[0], owners[1])

    def test_logs_and_cache_do_not_keep_owners_alive(self):
        with Instrumentation(initialize='item') as h:
            owner = BSLValueList()
            item = owner.get_method('Add')(Decimal(7), 'live')
            ref = weakref.ref(owner)
            h.stringify(item)
            h.stringify(owner)
            self.assertEqual(len(h.cache), 1)
            del owner
            gc.collect()
            self.assertIsNone(ref())
            self.assertEqual(len(h.cache), 0)
            self.assertEqual(len(h.actions), 1)
            with self.assertRaisesRegex(AssertionError, 'owner must stay alive'):
                h.stringify(item)
            for collection in (h.events, h.actions):
                self.assertTrue(all(not isinstance(part, (BSLValueList, BSLValueListItem))
                                    for entry in collection for part in entry))

    def test_scalar_item_and_list_conversion_failures_are_independent(self):
        for failure in ('scalar', 'item', 'list'):
            with self.subTest(failure=failure), Instrumentation(fail=failure) as h:
                result = h.run('НачалоКэшаСписка()')
                self.assertEqual(list(result), list(INITIAL))
                for case in result.values():
                    self.assertEqual(case['Prepare'], 'ok')
                    self.assertEqual(case['AfterStatus'], 'ok')
                    for key, kind in [('First', 'list'), ('Second', 'list'), ('ItemAfter', 'item')]:
                        self.assertEqual(case[key]['Status'], 'error' if failure == kind else 'ok')
                        self.assertEqual(case[key]['Text'] is None, failure == kind)
                self.assertEqual(result['ValueScalar']['Trigger']['Status'],
                                 'error' if failure == 'scalar' else 'ok')
                self.assertEqual(result['ValueItem']['Trigger']['Status'],
                                 'error' if failure == 'item' else 'ok')
                failed = h.run('ДействиеКэшаСписка("DeleteError")')
                self.assertEqual(failed['Status'], 'error')
                self.assertEqual(failed['AfterAction']['Count'], 3)
                self.assertEqual(failed['BetweenStatus'], 'ok')
                self.assertEqual(failed['AfterStatus'], 'ok')
                self.assertEqual(failed['Second']['Status'], 'error' if failure == 'list' else 'ok')

    def test_field_count_id_and_iteration_errors_do_not_hide_string_observations(self):
        original = BSLValueListItem.get_member
        for index, field in enumerate(('value', 'presentation', 'check')):
            def read(item, name):
                if name.casefold() == field:
                    raise ValueError('synthetic field failure')
                return original(item, name)
            with self.subTest(field=field), Instrumentation() as h:
                with patch.object(BSLValueListItem, 'get_member', read):
                    result = h.run('ДействиеКэшаСписка("DeleteError")')
                for phase in ('Initial', 'Before', 'AfterAction', 'Between', 'After'):
                    self.assertEqual(result[phase]['Items'][0][index], '[' + field + '-error]')
                    self.assertEqual(result[phase]['Items'][0][3], 0)
                self.assertEqual(result['Status'], 'error')
                self.assertEqual(result['First']['Status'], 'ok')
                self.assertEqual(result['Second']['Status'], 'ok')
        for target, method, marker in [(BSLValueListItem, 'get_id', '[id-error]'),
                                       (BSLValueList, 'count', '[error]'),
                                       (BSLValueList, '__iter__', '[iteration-error]')]:
            with self.subTest(method=method), Instrumentation() as h:
                with patch.object(target, method, side_effect=ValueError('synthetic read failure')):
                    result = h.run('ИнициализацияКэшаСписка("value", "none")')
                state = result['Before']
                self.assertEqual(state['Count'] if method == 'count' else
                                 state['Items'][0] if method == '__iter__' else
                                 state['Items'][0][3], marker)
                self.assertEqual(result['First']['Status'], 'ok')
                self.assertEqual(result['ItemAfter']['Status'], 'ok')
                self.assertEqual(result['Second']['Status'], 'ok')

    def test_failed_scalar_value_read_does_not_skip_later_initialization_cases(self):
        original = BSLValueListItem.get_member
        def fail_value(item, name):
            if name.casefold() == 'value':
                raise ValueError('synthetic Value getter failure')
            return original(item, name)
        with Instrumentation() as h, patch.object(BSLValueListItem, 'get_member', fail_value):
            result = h.run('НачалоКэшаСписка()')
            self.assertEqual(list(result), list(INITIAL))
            self.assertEqual(result['ValueScalar']['Trigger'],
                             {'Status': '[value-read-error]', 'Text': ''})
            self.assertEqual(Counter(event[0] for event in h.events), {'list': 10, 'item': 7})
            for case in result.values():
                self.assertEqual(case['Before']['Items'][0][0], '[value-error]')
                self.assertEqual(case['AfterStatus'], 'ok')
                self.assertEqual(case['First']['Status'], 'ok')
                self.assertEqual(case['ItemAfter']['Status'], 'ok')
                self.assertEqual(case['Second']['Status'], 'ok')

    def test_partial_action_and_field_write_failures_preserve_actual_post_error_state(self):
        original_delete = BSLValueList.delete
        def delete_then_fail(owner, selector):
            original_delete(owner, selector)
            raise ValueError('synthetic failure after delete')
        with Instrumentation() as h, patch.object(BSLValueList, 'delete', delete_then_fail):
            result = h.run('ИзмененияКэшаСписка("structural")')
            self.assertEqual(list(result), list(STRUCTURAL))
            self.assertEqual(result['Delete']['Status'], 'error')
            self.assertEqual(result['Delete']['AfterAction']['Count'], 2)
            self.assertEqual(result['Delete']['AfterAction']['Items'][1][3], 2)
            self.assertEqual(result['Delete']['Second']['Status'], 'ok')
            self.assertEqual(result['SortPresentation']['Status'], 'ok')
        original_set = BSLValueListItem.set_member
        def write_then_fail(item, name, value):
            original_set(item, name, value)
            raise ValueError('synthetic failure after field write')
        with Instrumentation() as h, patch.object(BSLValueListItem, 'set_member', write_then_fail):
            result = h.run('ИнициализацияКэшаСписка("value", "none")')
            for phase, value in [('Middle', 8), ('Before', 9), ('After', 10)]:
                self.assertEqual(result[phase + 'Status'], 'error')
                self.assertEqual(result[phase]['Items'][0][0], value)
            self.assertEqual(result['First']['Status'], 'ok')
            self.assertEqual(result['Second']['Status'], 'ok')

    def test_prepare_and_copy_failures_do_not_abort_later_groups(self):
        with Instrumentation() as h, patch.object(BSLValueList, 'add', side_effect=ValueError('synthetic Add failure')):
            h.vm.execute(section(BODY))
            self.assertEqual(len(h.outputs), 6)
            self.assertEqual(h.outputs[-1], FINAL)
            for text in h.outputs:
                self.assertNotIn(': [error]', text)
                self.assertNotIn('[serialize-error]', text)
            self.assertIn('ValueUnread.Prepare={"S","error"}', h.outputs[0])
            self.assertIn('SortPresentation.Prepare={"S","error"}', h.outputs[1])
            self.assertIn('DeleteError.Prepare={"S","error"}', h.outputs[2])
        with Instrumentation() as h, patch.object(BSLValueList, 'copy', side_effect=ValueError('synthetic Copy failure')):
            result = h.run('КопияКэшаСписка()')
            self.assertEqual(result['Status'], 'error')
            for name in ('CopyAfter', 'BetweenStatus', 'Between', 'First',
                         'AfterStatus', 'After', 'Second'):
                self.assertEqual(result[name], 'not-run')
            self.assertEqual(result['SourceAfter']['Items'], [[7, 'source-current', False, 0]])
            self.assertEqual(result['Source']['Text'], 'start')
            self.assertEqual(result['SourceItem']['Text'], 'source-current')
            self.assertEqual([event[0] for event in h.events], ['list', 'list', 'item'])

    def test_empty_add_failure_skips_only_item_dependencies_not_list_conversions(self):
        for fail in (None, 'list'):
            with self.subTest(fail=fail), Instrumentation(fail=fail) as h:
                with patch.object(BSLValueList, 'add', side_effect=ValueError('synthetic Add failure')):
                    result = h.run('ПустойКэшСписка()')
                self.assertEqual(result['Status'], 'error')
                for name in ('BetweenStatus', 'AfterStatus', 'ItemAfter'):
                    self.assertEqual(result[name], 'not-run')
                for name in ('Before', 'AfterAction', 'FirstState', 'After'):
                    self.assertEqual(result[name], {'Count': 0, 'Items': []})
                for name in ('Warm', 'First', 'Second'):
                    self.assertEqual(result[name], {
                        'Status': 'error' if fail else 'ok', 'Text': None if fail else ''})
                self.assertEqual([event[0] for event in h.events], ['list'] * 3)

    def test_exact_encoded_empty_special_and_error_like_strings_remain_successes(self):
        samples = [
            ('', '{"S",""}'),
            ('a\nb', r'{"S","a\nb"}'),
            (r'a\nb', r'{"S","a\\nb"}'),
            ('"\r\tЯ😀', r'{"S","""\r\tЯ"\\d83d"\\de00"}'),
            ('[error]', '{"S","[error]"}'),
            ('[serialize-error]', '{"S","[serialize-error]"}'),
        ]
        for text, encoded in samples:
            with self.subTest(text=text), Instrumentation(text=text) as h:
                h.vm.execute('НаблюдатьТаблицы("cache-test", "ПустойКэшСписка()")')
                lines = h.outputs[0].splitlines()
                for phase in ('Warm', 'First', 'ItemAfter', 'Second'):
                    self.assertIn(f'  {phase}.Status={{"S","ok"}}', lines)
                    self.assertIn(f'  {phase}.Text={encoded}', lines)
                self.assertEqual(sum('.Text=' in line for line in lines), 4)

    def test_raw_list_or_item_serialization_is_rejected_even_when_nested(self):
        with Instrumentation() as h:
            owner = BSLValueList()
            item = owner.add(Decimal(7))
            for value in (owner, item):
                with self.assertRaisesRegex(AssertionError, 'raw list/item'):
                    h.write(value)
                nested = BSLArray()
                nested.items.append(value)
                with self.assertRaisesRegex(AssertionError, 'raw list/item'):
                    h.write(nested)


if __name__ == '__main__':
    unittest.main()
