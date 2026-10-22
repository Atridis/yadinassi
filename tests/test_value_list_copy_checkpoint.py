"""Owner-confirmed Copy evidence integrity and probe instrumentation.

Synthetic policies below deliberately disagree. They establish that the BSL
observer distinguishes identity/allocation policies without selecting one. Native replay is separate from these synthetic policies.
Full native and frozen comparison still consume the complete scenario.
"""
from scripts.native_historical_replay import FILL_EXCLUDE_PROBE_BLOCKS, FILL_INCLUDE_PROBE_BLOCKS, DESCRIPTOR_MAP_PROBE_BLOCKS, FIELD_REFERENCE_BLOCKS
from contextlib import ExitStack
from decimal import Decimal
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, ast, serialization
from yadinassi.parser import parse
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray, HostFunction

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало компактных проб копирования списка.\n',
           '// Конец компактных проб копирования списка.\n\n')
BODY = ('// Начало наблюдений копирования списка.\n',
        '// Конец наблюдений копирования списка.\n')
FINAL = 'table.list.copy.checkpoint.complete: [ok]'
CASES = ('fresh-empty', 'fresh', 'value-asc', 'value-desc', 'presentation-asc',
         'presentation-desc', 'deleted-reordered', 'clear-empty', 'clear-refilled', 'nested')


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def strip_probe(text):
    for start, end in (
        *FILL_EXCLUDE_PROBE_BLOCKS, *FILL_INCLUDE_PROBE_BLOCKS, *DESCRIPTOR_MAP_PROBE_BLOCKS, *FIELD_REFERENCE_BLOCKS,
        ('// Начало заключительных проб пустой строки кэша списка.\n', '// Конец заключительных проб пустой строки кэша списка.\n\n'),
        ('// Начало заключительных наблюдений пустой строки кэша списка.\n', '// Конец заключительных наблюдений пустой строки кэша списка.\n'),
        ('// Начало уточняющих проб кэша строки списка.\n', '// Конец уточняющих проб кэша строки списка.\n\n'),
        ('// Начало уточняющих наблюдений кэша строки списка.\n', '// Конец уточняющих наблюдений кэша строки списка.\n'),
        ('// Начало компактных проб строкового представления списка.\n', '// Конец компактных проб строкового представления списка.\n\n'),
        ('// Начало наблюдений строкового представления списка.\n', '// Конец наблюдений строкового представления списка.\n'),
        HELPERS, BODY):
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


def section(markers):
    return source().split(markers[0], 1)[1].split(markers[1], 1)[0]


def observations():
    return [node.expression for node in parse(section(BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def plain(value):
    if type(value) is BSLArray:
        return [plain(item) for item in value.items]
    return value


def field(value, *names):
    for name in names:
        value = value.get_member(name)
    return plain(value)


class Instrumentation:
    def __init__(self, policy='fresh'):
        self.policy = policy
        self.copies, self.owners, self.events, self.outputs = [], [], [], []
        self.vm = Interpreter(output=self.outputs.append)
        self.vm.register_function('ЗначениеВСтрокуВнутр', self.write, 'ValueToStringInternal')
        self.vm.execute(source().split('#Область МассивыИСтруктуры', 1)[0])

    def write(self, value):
        if type(value) in (BSLValueList, BSLValueListItem):
            raise AssertionError('raw list/item serialization is forbidden')
        return serialization.value_to_string_internal(value)

    def copy(self, owner, name):
        self.events.append((name, owner))
        self.owners.append(owner)  # Both owners remain live, including test inspection.
        if self.policy == 'fail-allocator':
            owner._next_id += 2
            raise ValueError('synthetic allocator-only mutation before failure')
        if self.policy == 'fail-fields':
            owner.items[0].presentation = 'synthetic changed'
            raise ValueError('synthetic field mutation before failure')
        if self.policy == 'same-owner':
            self.copies.append(owner)
            return owner
        result = BSLValueList()
        items = list(owner.items)
        if self.policy in ('reverse', 'alias-reverse'):
            items.reverse()
        if self.policy == 'alias-reverse':
            result.items = items
            result._by_id = {item._id: item for item in items}
            result._next_id = owner._next_id
        else:
            for item in items:
                result.add(item.value, item.presentation, item.check)
            if self.policy in ('preserve', 'history'):
                for original, copied in zip(items, result.items):
                    copied._id = original._id
                result._by_id = {item._id: item for item in result.items}
                result._next_id = max(result._by_id, default=-1) + 1
                if self.policy == 'history':
                    result._next_id = owner._next_id
        self.copies.append(result)
        return result

    def __enter__(self):
        self.stack = ExitStack()
        original = BSLValueList.get_method
        harness = self
        def get_method(owner, name):
            if name.casefold() in ('copy', 'скопировать'):
                return HostFunction(name, lambda: harness.copy(owner, name))
            return original(owner, name)
        self.stack.enter_context(patch.object(BSLValueList, 'get_method', get_method))
        return self

    def __exit__(self, *args):
        self.stack.__exit__(*args)

    def run(self, kind):
        return self.vm.execute(f'ИсторияКопированияСписка("{kind}")')


class ValueListCopyCheckpointTests(unittest.TestCase):
    def test_exact_base_and_protected_native_evidence(self):
        self.assertEqual(blob(('\ufeff' + strip_probe(source())).encode()),
                         'f09b5ebe948c9a44790b164b0ca6e7cdff5f3fd6')
        for name, expected in {
            'collections.out': '97e90791a4011bd7f6ef2922533f92f698557cbd',
            'dates.out': '05d23c46540b301820f2ac81c8a67fc0e1273dc8',
            'functions.out': '6df192ac9d10c07755948d7c14cfed9e2311c65f',
            'numbers.out': 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13',
            'strings.out': 'a1ecb5458c3eb10b0df52cd9ae241994a2e4f462',
            'values.out': '016f30d6f3bdb1a814e86a70e3bcf424383a0d27',
        }.items():
            data = (ROOT / 'tests/fixtures/native_windows' / name).read_bytes()
            self.assertEqual(blob(data.replace(b'\r\n', b'\n')), expected)
        self.assertEqual(blob((ROOT / 'integrational_tests/meta.md').read_bytes().replace(b'\r\n', b'\n')),
                         'f76530bce7bd3b8a54055b2390ec7551024c62e2')
        self.assertEqual(list((ROOT / 'tests/fixtures/native_windows').glob('*.err')), [])
        self.assertIn('__version__ = "0.3.2"', (ROOT / 'yadinassi/__init__.py').read_text())
        self.assertIn(FINAL, (ROOT / 'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8'))

    def test_complete_owner_evidence_preserves_every_prior_byte(self):
        # Owner Atridis commit 0601200672edcc1cd5ab6703d0ef47e958329846.
        # Normalize Git checkout line endings only, never any native content.
        data = (ROOT / 'tests/fixtures/native_windows/collections.out').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(blob(data), '97e90791a4011bd7f6ef2922533f92f698557cbd')
        # Isolate historical Copy evidence; full comparators use the entire file.
        data = data.split(b'table.list.string.empty:', 1)[0] + b'table.checkpoint.complete: [ok]\n'
        self.assertEqual(blob(data), 'd4cce35fea3cc5271a871c26062c1b6167c0b092')
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '9e1962801f19b6ca24cbd64ec82574e6e2bbb826a3b45481f249f89e6f5b2d01')
        self.assertEqual((len(data), len(data.splitlines())), (162177, 3937))
        before, added = data.split(b'table.list.copy.fresh-empty:', 1)
        self.assertEqual(len(before), 149066)
        self.assertEqual(blob(before + b'table.checkpoint.complete: [ok]\n'),
                         'b934bc3fe6d8c8f6b9d4ba23972ccb29bd3d00f6')
        tail = b'table.list.copy.fresh-empty:' + added
        labels = [line.split(b': [', 1)[0].decode() for line in tail.splitlines()
                  if line.startswith(b'table.list.copy.')]
        self.assertEqual(labels, ['table.list.copy.' + case for case in CASES]
                         + ['table.list.copy.checkpoint.complete'])
        self.assertEqual(len(tail.splitlines()), 307)
        self.assertTrue(tail.endswith((FINAL + '\ntable.checkpoint.complete: [ok]\n').encode()))
        for marker in ('[error]', '[iteration-error]', '[serialize-error]', '[limit]',
                       '[id-error]', '[find-error]', 'not-run'):
            self.assertNotIn(marker.encode(), tail)

    def test_native_fixture_text_uses_utf8_under_legacy_default_encoding(self):
        # Reproduce a pre-UTF-8 Windows default without changing host locale.
        original = Path.read_text
        reads = []
        def legacy_read(path, encoding=None, errors=None):
            reads.append((path, encoding))
            return original(path, encoding=encoding or 'cp1252', errors=errors)
        with patch.object(Path, 'read_text', legacy_read):
            self.test_exact_base_and_protected_native_evidence()
        self.assertIn((ROOT / 'tests/fixtures/native_windows/collections.out', 'utf-8'), reads)

    def test_fixed_unique_records_and_declarations_before_statements(self):
        calls = observations()
        self.assertEqual([call.arguments[0].value for call in calls], ['list.copy.' + case for case in CASES])
        self.assertEqual(source().count(FINAL), 1)
        for call in calls:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(a, ast.Literal) and type(a.value) is str for a in call.arguments))
            self.assertLess(len(call.arguments[1].value), 100)
            parse('Result = ' + call.arguments[1].value)
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_each_record_reaches_copy_once_and_serializes_in_order(self):
        with Instrumentation() as h:
            h.vm.execute(section(BODY))
            self.assertEqual(len(h.events), len(CASES))
            self.assertEqual([name for name, _ in h.events].count('Скопировать'), 3)
            self.assertEqual([line.split(': [', 1)[0] for line in h.outputs],
                             ['table.list.copy.' + case for case in CASES] + [FINAL.split(':')[0]])
            for text in h.outputs:
                for error in ('[serialize-error]', '[iteration-error]', '[limit]', '[id-error]', '[find-error]'):
                    self.assertNotIn(error, text)
                self.assertNotIn(': [error]', text)
            self.assertTrue(all(h.owners[i] is not h.copies[i] for i in range(len(CASES))))

    def test_actual_permutations_and_history_reach_copy(self):
        expected = {
            'fresh-empty': ([], 0), 'fresh': ([0, 1, 2], 3),
            'value-asc': ([1, 2, 0], 3), 'value-desc': ([0, 2, 1], 3),
            'presentation-asc': ([2, 0, 1], 3), 'presentation-desc': ([1, 0, 2], 3),
            'deleted-reordered': ([2, 0], 4), 'clear-empty': ([], 3),
            'clear-refilled': ([3, 4], 5), 'nested': ([2, 1], 3),
        }
        for case, (ids, next_id) in expected.items():
            with self.subTest(case=case), Instrumentation() as h:
                result = h.run(case)
                self.assertEqual(field(result, 'Prepare'), 'ok')
                self.assertEqual([row[3] for row in field(result, 'Before', 'Items')], ids)
                self.assertEqual(field(result, 'SourceNext', 'ID'), next_id)
                self.assertEqual(field(result, 'Before', 'Items'), field(result, 'Source', 'Items'))
                self.assertEqual(field(result, 'Before', 'Find'), field(result, 'Source', 'Find'))
                self.assertEqual(field(result, 'CopyLinks', 'Order'), [-1] * len(ids))
                self.assertEqual(field(result, 'SourceLinks', 'Order'), list(range(len(ids))))
                self.assertEqual(field(result, 'CountsAfterSourceAdd'), [len(ids) + 1, len(ids)])
                self.assertEqual(field(result, 'CountsAfterCopyAdd'), [len(ids) + 1, len(ids) + 1])

    def test_competing_copy_id_and_allocator_policies_are_distinguishable(self):
        results = []
        for policy in ('fresh', 'preserve', 'history'):
            with Instrumentation(policy) as h:
                result = h.run('deleted-reordered')
                results.append(([row[3] for row in field(result, 'Copy', 'Items')],
                                field(result, 'Copy', 'Find'), field(result, 'CopyNext', 'ID')))
                self.assertEqual(field(result, 'SourceNext', 'ID'), 4)
                self.assertTrue(field(result, 'SourceNext', 'Found'))
                self.assertTrue(field(result, 'CopyNext', 'Found'))
        self.assertEqual(results, [([0, 1], [0, 1, -1, -1, -1, -1], 2),
                                   ([2, 0], [1, -1, 0, -1, -1, -1], 3),
                                   ([2, 0], [1, -1, 0, -1, -1, -1], 4)])

    def test_reordered_fields_and_aliases_are_not_hidden(self):
        for policy in ('reverse', 'alias-reverse'):
            with self.subTest(policy=policy), Instrumentation(policy) as h:
                result = h.run('fresh')
                self.assertEqual([row[0] for row in field(result, 'Copy', 'Items')], [20, 10, 30])
                self.assertEqual(field(result, 'CopyLinks', 'Order'),
                                 [2, 1, 0] if policy == 'alias-reverse' else [-1, -1, -1])
        with Instrumentation('same-owner') as h:
            result = h.run('fresh')
            self.assertTrue(field(result, 'SameList'))
            self.assertEqual(field(result, 'CountsAfterSourceAdd'), [4, 4])
            self.assertEqual(field(result, 'CountsAfterCopyAdd'), [5, 5])

    def test_nested_snapshots_are_eager_and_item_fields_are_independent(self):
        with Instrumentation() as h:
            result = h.run('nested')
            self.assertEqual(field(result, 'Before', 'Items')[1][0], [1])
            self.assertEqual(field(result, 'Copy', 'Items')[1][0], [1])
            self.assertTrue(field(result, 'Nested', 'SameValue'))
            self.assertEqual(field(result, 'Nested', 'SharedSource', 'Items')[1][0], [1, 2])
            self.assertEqual(field(result, 'Nested', 'SharedCopy', 'Items')[1][0], [1, 2])
            self.assertEqual(field(result, 'Nested', 'Source', 'Items')[1][:3], [[1, 2], 'b', True])
            self.assertEqual(field(result, 'Nested', 'Copy', 'Items')[1][:3], [77, 'copy', False])

    def test_copy_failure_retains_post_error_fields_and_allocator_observation(self):
        for policy in ('fail-fields', 'fail-allocator'):
            with self.subTest(policy=policy), Instrumentation(policy) as h:
                result = h.run('fresh')
                self.assertEqual(field(result, 'Status'), 'error')
                self.assertEqual(field(result, 'CopyNext'), 'not-run')
                self.assertEqual(field(result, 'SourceNext', 'Status'), 'ok')
                self.assertEqual(field(result, 'CountsAfterSourceAdd'), [4, '[error]'])
                if policy == 'fail-fields':
                    self.assertEqual(field(result, 'Source', 'Items')[0][1], 'synthetic changed')
                    self.assertEqual(field(result, 'Before', 'Items')[0][1], 'b')
                else:
                    self.assertEqual(field(result, 'SourceNext', 'ID'), 5)

    def test_setup_failure_is_distinct_and_does_not_call_copy(self):
        def fail(owner, *args):
            owner.items.reverse()
            raise ValueError('synthetic setup mutation before failure')
        with Instrumentation() as h, patch.object(BSLValueList, 'sort_by_value', fail):
            result = h.run('value-asc')
            self.assertEqual(field(result, 'Prepare'), 'error')
            self.assertEqual(field(result, 'Status'), 'not-run')
            self.assertEqual([row[3] for row in field(result, 'Before', 'Items')], [2, 1, 0])
            self.assertEqual(h.events, [])

    def test_snapshot_fields_id_find_count_and_iteration_fail_independently(self):
        for failing in ('value', 'get_id', 'find_by_id', 'count', '__iter__'):
            with self.subTest(failing=failing), Instrumentation() as h:
                original = getattr(BSLValueListItem if failing in ('value', 'get_id') else BSLValueList,
                                   'get_member' if failing == 'value' else failing)
                def fail(owner, *args):
                    selected = owner._owner_ref() if type(owner) is BSLValueListItem else owner
                    if selected in h.copies and (failing != 'value' or args[0].casefold() == 'value'):
                        raise ValueError('synthetic independent observer failure')
                    return original(owner, *args)
                cls = BSLValueListItem if failing in ('value', 'get_id') else BSLValueList
                with patch.object(cls, 'get_member' if failing == 'value' else failing, fail):
                    result = h.run('fresh')
                self.assertEqual(field(result, 'Status'), 'ok')
                rows = field(result, 'Copy', 'Items')
                if failing == '__iter__':
                    self.assertEqual(rows, ['[iteration-error]'])
                    self.assertEqual(field(result, 'Copy', 'Count'), 3)
                else:
                    self.assertEqual(len(rows), 3)
                    self.assertEqual(rows[0][1:3], ['b', True])
                    if failing == 'value':
                        self.assertEqual(rows[0][0], '[value-error]')
                    elif failing == 'get_id':
                        self.assertEqual(rows[0][3], '[id-error]')
                    elif failing == 'find_by_id':
                        self.assertEqual(rows[0][4], '[find-error]')
                    else:
                        self.assertEqual(field(result, 'Copy', 'Count'), '[error]')
                        self.assertEqual(rows[0][0], 30)

    def test_source_iteration_failure_does_not_erase_before_or_skip_copy(self):
        original = BSLValueList.__iter__
        with Instrumentation() as h:
            def fail(owner):
                if owner not in h.copies:
                    raise ValueError('synthetic source observation failure')
                return original(owner)
            with patch.object(BSLValueList, '__iter__', fail):
                result = h.run('fresh')
            self.assertEqual(field(result, 'Before', 'Count'), 3)
            self.assertEqual(field(result, 'Before', 'Items'), ['[iteration-error]'])
            self.assertEqual(field(result, 'ReferenceStatus'), 'error')
            self.assertEqual(field(result, 'SourceLinks'), 'not-run')
            self.assertEqual(field(result, 'CopyLinks'), 'not-run')
            self.assertEqual(field(result, 'Status'), 'ok')
            self.assertEqual(len(h.events), 1)
            self.assertEqual(field(result, 'Copy', 'Count'), 3)
            self.assertEqual(field(result, 'SourceNext', 'ID'), 3)

    def test_lookup_distinguishes_missing_and_foreign_reference_without_indexof(self):
        with Instrumentation() as h:
            owner, other = BSLValueList(), BSLValueList()
            item = owner.add(Decimal(1))
            foreign = other.add(Decimal(2))
            h.vm.variables['target'] = owner
            original = BSLValueList.find_by_id
            def lookup(current, identifier):
                if current is owner and identifier == 1:
                    return foreign
                return original(current, identifier)
            with patch.object(BSLValueList, 'find_by_id', lookup), patch.object(
                    BSLValueList, 'index_of', side_effect=AssertionError('must not use IndexOf')):
                result = h.vm.execute('СнимокКопированияСписка(Target)')
            self.assertEqual(field(result, 'Find'), [0, -2, -1, -1, -1, -1])
            self.assertTrue(field(result, 'Items')[0][4])
            self.assertIs(owner.items[0], item)

    def test_add_failure_after_mutation_retains_changed_count_and_continues_other_owner(self):
        original = BSLValueList.add
        def fail(owner, *args):
            result = original(owner, *args)
            if len(args) > 1 and args[1] == 'source-next':
                raise ValueError('synthetic append before failure')
            return result
        with Instrumentation() as h, patch.object(BSLValueList, 'add', fail):
            result = h.run('fresh')
            self.assertEqual(field(result, 'SourceNext', 'Status'), 'error')
            self.assertEqual(field(result, 'CountsAfterSourceAdd'), [4, 3])
            self.assertEqual(field(result, 'CopyNext', 'Status'), 'ok')
            self.assertEqual(field(result, 'CountsAfterCopyAdd'), [4, 4])


if __name__ == '__main__':
    unittest.main()
