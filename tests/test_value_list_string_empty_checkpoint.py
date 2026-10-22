"""Final empty-result probes: competing synthetic caches, not native answers."""
from scripts.native_historical_replay import DESCRIPTOR_MAP_PROBE_BLOCKS, FIELD_REFERENCE_BLOCKS, without_field_reference_probes, without_descriptor_map_probes
from collections import Counter
from decimal import Decimal
import gc
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import weakref

from yadinassi import ast
from yadinassi.parser import parse
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray


# Load the shared synthetic instrumentation without depending on unittest's
# discovery sys.path or importing its TestCase into this module's discovery.
_spec = importlib.util.spec_from_file_location(
    '_empty_probe_cache_support', Path(__file__).with_name('test_value_list_string_cache_checkpoint.py'))
cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cache)
source, section, blob = cache.source, cache.section, cache.blob
HELPERS = ('// Начало заключительных проб пустой строки кэша списка.\n',
           '// Конец заключительных проб пустой строки кэша списка.\n\n')
BODY = ('// Начало заключительных наблюдений пустой строки кэша списка.\n',
        '// Конец заключительных наблюдений пустой строки кэша списка.\n')
FINAL = 'table.list.string-cache.final.complete: [ok]'
GROUPS = ('empty-result', 'short-sorts')


def synthetic_text(state):
    # In particular, one empty value is "", while two empty values yield "|".
    # This separator/fallback is an instrument, not an asserted 1C convention.
    return '|'.join(row[1] or str(row[0]) for row in state)


class Instrumentation(cache.Instrumentation):
    def __enter__(self):
        super().__enter__()
        self.stack.enter_context(patch.object(cache, 'rendered', synthetic_text))
        return self


def observations():
    return [node.expression for node in parse(section(BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


class ValueListStringEmptyCheckpointTests(unittest.TestCase):
    def test_only_new_blocks_removed_restore_source_and_native_output_stays_untouched(self):
        text = source()
        for start, end in (*DESCRIPTOR_MAP_PROBE_BLOCKS, *FIELD_REFERENCE_BLOCKS, HELPERS, BODY):
            self.assertEqual(text.count(start), 1)
            self.assertEqual(text.count(end), 1)
            before, rest = text.split(start, 1)
            _, after = rest.split(end, 1)
            text = before + after
        self.assertEqual(blob(('\ufeff' + text).encode()),
                         '137dca5e4b6a47ea083a0dfe989e07c22d91a9e6')
        native = (cache.ROOT / 'tests/fixtures/native_windows/collections.out').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(blob(native), '97e90791a4011bd7f6ef2922533f92f698557cbd')
        self.assertEqual((len(native), len(native.splitlines())), (200954, 4579))
        for marker in (FINAL, 'list.string-cache.empty-result', 'list.string-cache.short-sorts'):
            self.assertNotIn(marker.encode(), native)

    def test_two_fixed_labels_parse_complete_source_with_declarations_first(self):
        calls = observations()
        self.assertEqual([call.arguments[0].value for call in calls],
                         ['list.string-cache.' + group for group in GROUPS])
        for call in calls:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(arg, ast.Literal) and type(arg.value) is str
                                for arg in call.arguments))
            self.assertLess(len(call.arguments[1].value), 100)
            parse('Result = ' + call.arguments[1].value)
        self.assertEqual(source().count(FINAL), 1)
        self.assertTrue(without_field_reference_probes(without_descriptor_map_probes(source())).endswith(BODY[1] + 'Сообщить("table.checkpoint.complete: [ok]");\n'))
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_source_loader_uses_explicit_utf8_under_cp1252_default(self):
        expected = source()
        original = Path.read_text
        def platform_read(path, encoding=None, errors=None):
            return original(path, encoding=encoding or 'cp1252', errors=errors)
        with patch.object(Path, 'read_text', platform_read):
            self.assertNotEqual(cache.SOURCE.read_text(errors='replace'), expected)
            self.assertEqual(source(), expected)
            self.assertEqual(len(observations()), 2)

    def test_five_cases_reached_with_exact_conversion_counts_and_unique_paths(self):
        with Instrumentation() as h:
            empty, sorts = [h.run(call.arguments[1].value) for call in observations()]
            self.assertEqual(list(empty), ['Value', 'Cleared', 'Separated'])
            self.assertEqual(list(sorts), ['Value', 'Presentation'])
            self.assertEqual(Counter(event[0] for event in h.events), {'list': 15, 'item': 3})
            self.assertEqual(Counter(action[0] for action in h.actions),
                             {'add': 6, 'sortbyvalue': 1, 'sortbypresentation': 1})
            h.events.clear()
            h.vm.execute(section(BODY))
            self.assertEqual(Counter(event[0] for event in h.events), {'list': 15, 'item': 3})
            self.assertEqual([text.split(': [', 1)[0] for text in h.outputs],
                             ['table.list.string-cache.' + group for group in GROUPS]
                             + [FINAL.split(':')[0]])
            for text in h.outputs:
                for error in ('[serialize-error]', '[iteration-error]', '[value-error]', ': [error]'):
                    self.assertNotIn(error, text)
                paths = [line.split('=', 1)[0] for line in text.splitlines() if line.startswith('  ')]
                self.assertEqual(len(paths), len(set(paths)))

    def test_empty_cases_preserve_field_count_order_ids_and_unprimed_conversion_order(self):
        for kind in ('Value', 'Cleared', 'Separated'):
            with self.subTest(kind=kind), Instrumentation(invalidate='never') as h:
                result = h.run(f'ПустойРезультатКэшаСписка("{kind}")')
                tail = [['', '', False, Decimal(1)]] if kind == 'Separated' else []
                for phase, value, presentation in [
                    ('Before', '', ''), ('ValueState', 'A', ''),
                    ('PresentationState', 'A', 'B'),
                ]:
                    self.assertEqual(result[phase], {
                        'Count': 1 + len(tail), 'Items': [[value, presentation, False, Decimal(0)]] + tail})
                for status in ('Prepare', 'ValueStatus', 'PresentationStatus'):
                    self.assertEqual(result[status], 'ok')
                self.assertEqual(result['ItemAfter'], {'Status': 'ok', 'Text': 'B'})
                self.assertEqual(h.actions[0][3], (('', 'label' if kind == 'Cleared' else '', False, 0),))
                self.assertEqual([event[0] for event in h.events], ['list', 'list', 'list', 'item'])
                for event, phase in zip(h.events[:3], ('Before', 'ValueState', 'PresentationState')):
                    self.assertEqual(event[2], tuple(map(tuple, result[phase]['Items'])))
                self.assertEqual(h.events[3][2], (('A', 'B', False, 0),))
                self.assertEqual(len({event[1] for event in h.events}), 1)

    def test_real_empty_cache_hit_and_truthy_miss_bug_have_different_signatures(self):
        signatures = {}
        for broken in (False, True):
            with self.subTest(broken=broken), Instrumentation(truthy_miss=broken) as h:
                result = h.run('ПустыеРезультатыКэшаСписка()')
                self.assertEqual([case['Warm'] for case in result.values()],
                                 [{'Status': 'ok', 'Text': text} for text in ('', '', '|')])
                signature = tuple(case['ValueText']['Text'] for case in result.values())
                self.assertEqual(signature, ('A', 'A', '|') if broken else ('', '', '|'))
                self.assertEqual(tuple(case['PresentationText']['Text'] for case in result.values()), signature)
                self.assertTrue(all(case['ValueText']['Status'] == 'ok'
                                    and case['PresentationText']['Status'] == 'ok'
                                    for case in result.values()))
                signatures[broken] = signature
        self.assertNotEqual(signatures[False][:2], signatures[True][:2])
        self.assertEqual(signatures[False][2], signatures[True][2])  # Nonempty separator control.

    def test_singleton_sorts_distinguish_eager_lazy_and_absent_invalidation(self):
        for flag, method in [('Ложь', 'sortbyvalue'), ('Истина', 'sortbypresentation')]:
            observed = []
            for policy, expected in [('eager', 'pending'), ('lazy', 'between'), ('never', 'start')]:
                with self.subTest(method=method, policy=policy), Instrumentation(invalidate=policy) as h:
                    result = h.run(f'КороткаяСортировкаКэшаСписка({flag})')
                    for phase, label in [('Initial', 'start'), ('Before', 'pending'),
                                         ('AfterAction', 'pending'), ('Between', 'between'), ('After', 'after')]:
                        self.assertEqual(result[phase], {'Count': 1, 'Items': [[7, label, False, 0]]})
                    for name in ('Prepare', 'PendingStatus', 'Status', 'BetweenStatus', 'AfterStatus'):
                        self.assertEqual(result[name], 'ok')
                    self.assertEqual(result['Warm'], {'Status': 'ok', 'Text': 'start'})
                    self.assertEqual(result['First'], {'Status': 'ok', 'Text': expected})
                    self.assertEqual(result['Second'], result['First'])
                    self.assertEqual([event[0] for event in h.events], ['list'] * 3)
                    self.assertEqual([event[2][0][1] for event in h.events], ['start', 'between', 'after'])
                    self.assertEqual(h.actions[-1][0], method)
                    self.assertEqual(h.actions[-1][2], h.actions[-1][3])
                    observed.append(result['First']['Text'])
            self.assertEqual(len(set(observed)), 3)

    def test_field_snapshot_negative_controls_detect_accidental_list_or_item_priming(self):
        for injection in ('', '    Игнор = РезультатТекстаСписка(Список);\n',
                          '    Игнор = РезультатТекстаСписка(Список.Get(0));\n'):
            with self.subTest(injection=injection), Instrumentation(
                    initialize='item', helper_mutation=injection) as h:
                owner = BSLValueList()
                owner.add('', '')
                h.vm.register_function('OwnerForProbe', lambda: owner)
                state = h.run('ПоляКэшаСписка(OwnerForProbe())')
                self.assertEqual(state, {'Count': 1, 'Items': [['', '', False, 0]]})
                self.assertEqual(bool(h.events), bool(injection))
                self.assertEqual(owner in h.cache, bool(injection))
                h.events.clear()
                h.vm.execute(section(BODY))
                counts = Counter(event[0] for event in h.events)
                self.assertEqual(counts == {'list': 15, 'item': 3}, not bool(injection))

    def test_item_owners_stay_live_without_logs_or_cache_retaining_them(self):
        with Instrumentation(initialize='item') as h:
            owner = BSLValueList()
            item = owner.get_method('Add')('', '')
            ref = weakref.ref(owner)
            self.assertEqual(h.stringify(item), '')
            self.assertEqual(h.stringify(owner), '')
            self.assertEqual(len(h.cache), 1)
            del owner
            gc.collect()
            self.assertIsNone(ref())
            self.assertEqual(len(h.cache), 0)
            self.assertEqual(len(h.actions), 1)
            with self.assertRaisesRegex(AssertionError, 'owner must stay alive'):
                h.stringify(item)

    def test_list_and_item_conversion_failures_leave_fields_and_other_conversions_visible(self):
        for failure in ('list', 'item'):
            with self.subTest(failure=failure), Instrumentation(fail=failure) as h:
                result = h.run('ПустыеРезультатыКэшаСписка()')
                self.assertEqual(list(result), ['Value', 'Cleared', 'Separated'])
                for case in result.values():
                    self.assertEqual(case['ValueState']['Items'][0][:2], ['A', ''])
                    self.assertEqual(case['PresentationState']['Items'][0][:2], ['A', 'B'])
                    self.assertEqual(case['ValueStatus'], 'ok')
                    self.assertEqual(case['PresentationStatus'], 'ok')
                    for phase, kind in [('Warm', 'list'), ('ValueText', 'list'),
                                        ('PresentationText', 'list'), ('ItemAfter', 'item')]:
                        self.assertEqual(case[phase]['Status'], 'error' if failure == kind else 'ok')
                        self.assertEqual(case[phase]['Text'] is None, failure == kind)
                sorts = h.run('КороткиеСортировкиКэшаСписка()')
                for case in sorts.values():
                    self.assertEqual(case['Status'], 'ok')
                    self.assertEqual(case['After']['Items'], [[7, 'after', False, 0]])
                    self.assertEqual(case['Second']['Status'], 'error' if failure == 'list' else 'ok')

    def test_field_read_errors_do_not_become_conversion_or_mutation_failures(self):
        original = BSLValueListItem.get_member
        for index, field in enumerate(('value', 'presentation', 'check')):
            def read(item, name):
                if name.casefold() == field:
                    raise ValueError('synthetic field read failure')
                return original(item, name)
            with self.subTest(field=field), Instrumentation() as h:
                with patch.object(BSLValueListItem, 'get_member', read):
                    result = h.run('ПустойРезультатКэшаСписка("Value")')
                for phase in ('Before', 'ValueState', 'PresentationState'):
                    self.assertEqual(result[phase]['Items'][0][index], '[' + field + '-error]')
                    self.assertEqual(result[phase]['Items'][0][3], 0)
                for phase in ('Warm', 'ValueText', 'PresentationText', 'ItemAfter'):
                    self.assertEqual(result[phase]['Status'], 'ok')
                self.assertEqual(result['PresentationStatus'], 'ok')

    def test_prepare_failure_does_not_abort_later_cases_or_groups(self):
        with Instrumentation() as h, patch.object(
                BSLValueList, 'add', side_effect=ValueError('synthetic preparation failure')):
            h.vm.execute(section(BODY))
            self.assertEqual(len(h.outputs), 3)
            self.assertEqual(h.outputs[-1], FINAL)
            for text, cases in zip(h.outputs, [('Value', 'Cleared', 'Separated'), ('Value', 'Presentation')]):
                for case in cases:
                    self.assertIn(f'  {case}.Prepare={{"S","error"}}', text)
                self.assertNotIn(': [error]', text)
                self.assertNotIn('[serialize-error]', text)
            self.assertEqual(h.events, [])
            self.assertEqual(len(h.actions), 5)

    def test_partial_field_and_sort_failures_preserve_post_error_fields_and_later_reads(self):
        original = BSLValueListItem.set_member
        def write_then_fail(item, name, value):
            original(item, name, value)
            if value in ('A', 'B'):
                raise ValueError('synthetic failure after field write')
        with Instrumentation() as h, patch.object(BSLValueListItem, 'set_member', write_then_fail):
            result = h.run('ПустыеРезультатыКэшаСписка()')
            for case in result.values():
                self.assertEqual(case['ValueStatus'], 'error')
                self.assertEqual(case['PresentationStatus'], 'error')
                self.assertEqual(case['ValueState']['Items'][0][:2], ['A', ''])
                self.assertEqual(case['PresentationState']['Items'][0][:2], ['A', 'B'])
                self.assertEqual(case['ItemAfter'], {'Status': 'ok', 'Text': 'B'})
                self.assertEqual(case['PresentationText']['Status'], 'ok')
        def partial_sort(owner, direction=None):
            owner.items[0].value = Decimal(11)
            owner.items[0].presentation = 'sort-partial'
            raise ValueError('synthetic failure after sort mutation')
        with Instrumentation() as h, patch.object(
                BSLValueList, 'sort_by_value', partial_sort), patch.object(
                BSLValueList, 'sort_by_presentation', partial_sort):
            result = h.run('КороткиеСортировкиКэшаСписка()')
            for case in result.values():
                self.assertEqual(case['Status'], 'error')
                self.assertEqual(case['AfterAction'], {'Count': 1, 'Items': [[11, 'sort-partial', False, 0]]})
                self.assertEqual(case['Between']['Items'], [[11, 'between', False, 0]])
                self.assertEqual(case['After']['Items'], [[11, 'after', False, 0]])
                self.assertEqual(case['BetweenStatus'], 'ok')
                self.assertEqual(case['Second']['Status'], 'ok')

    def test_exact_encoded_empty_and_separator_results_are_success_not_missing_values(self):
        with Instrumentation() as h:
            h.vm.execute(section(BODY))
            lines = h.outputs[0].splitlines()
            for case, text in [('Value', ''), ('Cleared', ''), ('Separated', '|')]:
                for phase in ('Warm', 'ValueText', 'PresentationText'):
                    self.assertIn(f'  {case}.{phase}.Status={{"S","ok"}}', lines)
                    self.assertIn(f'  {case}.{phase}.Text={{"S","{text}"}}', lines)
                self.assertIn(f'  {case}.ItemAfter.Text={{"S","B"}}', lines)
            self.assertEqual(sum('.Text=' in line for line in lines), 12)

    def test_raw_owner_serialization_is_rejected_and_renderer_patch_is_scoped(self):
        original = cache.rendered
        with Instrumentation() as h:
            owner = BSLValueList()
            item = owner.add('')
            for value in (owner, item):
                with self.assertRaisesRegex(AssertionError, 'raw list/item'):
                    h.write(value)
                nested = BSLArray()
                nested.items.append(value)
                with self.assertRaisesRegex(AssertionError, 'raw list/item'):
                    h.write(nested)
            self.assertEqual(h.stringify(owner), '')
        self.assertIs(cache.rendered, original)
        self.assertEqual(cache.rendered((('', '', False, 0),)), 'v=')


if __name__ == '__main__':
    unittest.main()
