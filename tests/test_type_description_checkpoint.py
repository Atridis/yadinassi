"""Compact TypeDescription probes confirmed by owner commit f28dcc51a6b631cb4a8a3526dfcdc57172efbfc6."""
from dataclasses import fields, is_dataclass
from pathlib import Path
import unittest
import tempfile
import hashlib
import subprocess
from unittest.mock import patch
from scripts import smoke_test
if __package__:
    from . import test_native_outputs as native_outputs
else:
    import test_native_outputs as native_outputs
from scripts.smoke_test import (pending_types_checkpoint, split_type_supplement,
                                TYPES_SUPPLEMENT_HELPERS_START, TYPES_SUPPLEMENT_BODY_START)

from yadinassi import Interpreter, ast
from yadinassi.parser import parse, parse_expression

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
START = '// Нативный checkpoint описаний типов.'
OLD_BODY = '// Значение, тип и настоящий прямой/обратный кодек.'
BODY = '// Описания типов: наблюдения без заранее заданных ответов.'
FINAL = 'types.checkpoint.complete: [ok]'
REMOVED_RESEARCH_LABELS = {
    'description.contains', 'description.contains-missing', 'description.contains-wrong',
    'description.property-aliases',
    'adjust.default.number', 'adjust.default.string', 'adjust.default.date',
    'adjust.default.boolean', 'adjust.default.number-string', 'adjust.default.string-number',
    'adjust.default.number-date', 'adjust.default.undefined-number', 'adjust.default.null',
    'adjust.default.empty',
}


def source():
    return split_type_supplement(SOURCE.read_text(encoding='utf-8-sig'))[0]


def helpers():
    return START + source().split(START, 1)[1].split(OLD_BODY, 1)[0]


def calls():
    return [n.expression for n in parse(source())
            if isinstance(n, ast.ExpressionStatement)
            and isinstance(n.expression, ast.Call)
            and isinstance(n.expression.callee, ast.Name)
            and n.expression.callee.name == 'НаблюдатьТипы']


def walk(value):
    if is_dataclass(value):
        yield value
        for field in fields(value):
            yield from walk(getattr(value, field.name))
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk(item)


class TypeDescriptionCheckpointTests(unittest.TestCase):
    def test_compact_formatter_preserves_scalar_bytes_and_container_kinds(self):
        # Local formatter contract, never a newly manufactured native golden.
        from decimal import Decimal
        from yadinassi.serialization import value_to_string_internal
        from yadinassi.structures import BSLStructure
        from yadinassi.values import BSLArray, NULL
        vm = Interpreter()
        vm.execute(helpers())
        scalars = [None, NULL, False, Decimal(0), '0', '',
                   'quotes " and delimiters ;[]= with \\n and CR\rLF\nTAB\t Я😀']
        for value in scalars:
            vm.register_function('FormatterValue', lambda: value)
            actual = vm.execute('ПолеКомпактныхТипов(FormatterValue())')
            expected = value_to_string_internal(value).replace('\\', '\\\\').replace('\r', '\\r').replace('\n', '\\n')
            self.assertEqual(actual, expected)
            self.assertNotIn('\r', actual)
            self.assertNotIn('\n', actual)
        representations = []
        for value in (BSLArray(), BSLStructure(), BSLStructure('Count', Decimal(0))):
            vm.register_function('FormatterValue', lambda: value)
            representations.append(vm.execute('ПоляКомпактныхТипов(FormatterValue(), "value")'))
        self.assertEqual(len(set(representations)), 3)

        # Actual controls and their literal escape spellings must never collide.
        from yadinassi.serialization import value_from_string_internal
        pairs = ['\n', r'\n', '\r', r'\r', '\\', '"', ';[]=', '\t', r'\t', '\x00']
        encoded = []
        for value in pairs:
            vm.register_function('FormatterValue', lambda: value)
            text = vm.execute('ПолеКомпактныхТипов(FormatterValue())')
            encoded.append(text)
            restored, position = [], 0
            escapes = {'\\': '\\', 'n': '\n', 'r': '\r', 't': '\t'}
            while position < len(text):
                if text[position] == '\\':
                    self.assertLess(position + 1, len(text))
                    self.assertIn(text[position + 1], escapes)
                    restored.append(escapes[text[position + 1]])
                    position += 2
                else:
                    restored.append(text[position])
                    position += 1
            self.assertEqual(value_from_string_internal(''.join(restored)), value)
        self.assertEqual(len(set(encoded)), len(pairs))

    def test_fixed_bounded_matrix(self):
        observations = calls()
        self.assertEqual(len(observations), 132)
        labels = set()
        for call in observations:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(a, ast.Literal) and type(a.value) is str
                                for a in call.arguments))
            label, expression = [a.value for a in call.arguments]
            self.assertNotIn(label, labels)
            labels.add(label)
            self.assertRegex(label, r'^[a-z0-9.-]+$')
            self.assertLess(len(expression), 250)
            self.assertNotRegex(expression, r'[\r\n]')
            self.assertNotRegex(expression, r'(?i)\b(?:Eval|Execute|Import|Goto|While|For)\b')
            # Obsolete direct-constructor controls were removed; every retained
            # main expression must compile. Explicit syntax probes live in the supplement.
            parse_expression(expression)
        self.assertTrue(source().rstrip().endswith('Сообщить("' + FINAL + '");'))

    def test_declarations_precede_main_and_new_constructors_are_only_strings(self):
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            else:
                started = True
        # Preserve the owner probe layout: helper AST constructors are containers;
        # TypeDescription/qualifier constructors remain inside protected Eval.
        for node in walk(parse(helpers())):
            if isinstance(node, ast.New):
                self.assertIn(node.name.casefold(), ('структура', 'массив'))
        self.assertNotIn('Новый Квалификаторы', helpers())
        self.assertNotIn('New TypeDescription', helpers())

    def test_matrix_covers_every_planned_family_and_decisive_boundaries(self):
        probes = {c.arguments[0].value: c.arguments[1].value for c in calls()}
        for family in ('description', 'number', 'string', 'date', 'binary'):
            for case in ('default.en', 'default.ru', 'configured', 'type.names'):
                self.assertIn(family + '.' + case, probes)
            self.assertIn('readonly.' + family, probes)
        for family in ('allowedsign', 'allowedlength', 'datefractions'):
            self.assertIn(family + '.namespace', probes)
            self.assertIn(family + '.type-name', probes)
        for label in ('description.copy.add-remove', 'description.copy.qualifiers',
                      'description.copy.override', 'description.all-qualifiers',
                      'description.types-copy',
                      'number.ctor.fraction-exceeds', 'number.ctor.max38',
                      'number.ctor.above38', 'adjust.qualified-number.half',
                      'adjust.qualified-number.negative-half',
                      'adjust.qualified-number.round-overflow', 'adjust.nonnegative',
                      'adjust.string.utf16-cut', 'adjust.string.fixed-short',
                      'adjust.date.date', 'adjust.date.time', 'adjust.date.datetime',
                      'adjust.union-number-string.boolean',
                      'adjust.union-string-number.boolean'):
            self.assertIn(label, probes)

    def test_unknown_and_bad_expressions_do_not_abort_next_probe(self):
        output = []
        vm = Interpreter(output=output.append)
        vm.register_function('UnserializableHost', lambda: object())
        vm.execute(helpers() + '''
НаблюдатьТипы("missing", "NoSuchFunction()");
НаблюдатьТипы("syntax", "@");
НаблюдатьТипы("unserializable", "UnserializableHost()");
НаблюдатьТипы("next", "2 + 3");
''')
        self.assertEqual(output, ['types.missing: [error]', 'types.syntax: [error]',
                                 'types.unserializable: [serialize-error]',
                                 'types.next: [value={"N",5}]'])

    def test_snapshot_records_real_codec_and_nested_inverse_for_existing_value(self):
        vm = Interpreter()
        vm.execute(helpers())
        result = vm.execute('СнимокТипов(12.5)')
        self.assertEqual(result.get('Write'), '{"N",12.5}')
        self.assertTrue(result.get('ReadWriteEqual'))
        self.assertNotIn('readwrite', result._items)  # Equal stream is represented once.
        self.assertTrue(result.get('TypeReadEqual'))
        self.assertEqual(result.get('ReadType'), result.get('Type'))
        self.assertTrue(result.get('Equal'))
        self.assertIn('{"N",12.5}', result.get('Nested'))

    def test_qualifier_snapshot_retains_exact_differing_inverse_from_owner_evidence(self):
        import re
        from yadinassi.serialization import value_to_string_internal
        from yadinassi.values import BSLType
        # Exact fields of the genuine compact owner record, not generated goldens.
        native = (ROOT / 'integrational_tests/output/values.out').read_text(encoding='utf-8-sig')
        records = re.findall(r'^types\.number\.default\.en: \[(.*)\]$', native, re.MULTILINE)
        self.assertEqual(len(records), 1)
        expected_write = '{"#",f6f6ce00-392c-49ed-8c6e-4e0295fd4051}'
        for name, value in (('Write', expected_write), ('ReadType', BSLType.UNDEFINED),
                            ('ReadWriteEqual', False), ('ReadWrite', '{"U"}')):
            field = 'value.' + name + '=' + value_to_string_internal(value)
            self.assertRegex(records[0], re.escape(field) + r'(?:;|$)')
        vm = Interpreter()
        vm.execute(helpers())
        result = vm.execute('СнимокТипов(New NumberQualifiers())')
        self.assertEqual(result.get('Write'), expected_write)
        self.assertEqual(result.get('ReadType'), BSLType.UNDEFINED)
        self.assertFalse(result.get('ReadWriteEqual'))
        self.assertEqual(result.get('ReadWrite'), '{"U"}')

    def test_supplement_retains_raw_inverse_when_a_stage_changes(self):
        # Synthetic stage failure/change is a formatter observability test,
        # not a claim about a new native TypeDescription conversion.
        _, supplement = split_type_supplement(SOURCE.read_text(encoding='utf-8-sig'))
        vm = Interpreter()
        vm.execute(supplement.split(TYPES_SUPPLEMENT_BODY_START, 1)[0])
        ordinary = vm.execute('КвалификаторыОписанияДополнения(New TypeDescription("Number"))')
        self.assertTrue(ordinary.get('ReadWriteEqual'))
        self.assertNotIn('readwrite', ordinary._items)
        vm.register_function('ЗначениеИзСтрокиВнутр', lambda text: None)
        changed = vm.execute('КвалификаторыОписанияДополнения(New TypeDescription("Number"))')
        self.assertEqual(changed.get('Write'), ordinary.get('Write'))
        self.assertFalse(changed.get('ReadWriteEqual'))
        self.assertEqual(changed.get('ReadWrite'), '{"U"}')

    def test_snapshot_failed_stages_do_not_prevent_record(self):
        vm = Interpreter()
        vm.register_function('UnknownHost', lambda: object())
        vm.execute(helpers())
        result = vm.execute('СнимокТипов(UnknownHost())')
        for field in ('Type', 'Write', 'ReadType', 'Nested'):
            self.assertEqual(result.get(field), '[error]')

    def test_compact_type_observations_match_owner_output_and_ordered_labels(self):
        import re
        output = []
        Interpreter(output=output.append).execute(helpers() + BODY + source().split(BODY, 1)[1])
        expected = (ROOT / 'integrational_tests/output/values.out').read_text(encoding='utf-8-sig')
        expected = expected.split('xml.checkpoint.complete: [ok]\n', 1)[1]
        expected = expected.split('types.checkpoint.complete: [ok]\n', 1)[0] + FINAL + '\n'
        native_labels = re.findall(r'^types\.([a-z0-9.-]+): \[', expected, re.M)
        self.assertFalse(set(native_labels) & REMOVED_RESEARCH_LABELS)
        compact_labels = [c.arguments[0].value for c in calls()] + ['checkpoint.complete']
        self.assertEqual(compact_labels, native_labels)
        actual = native_outputs.normalize_newlines('\n'.join(output) + '\n')
        self.assertEqual(actual, expected)
        self.assertEqual(output[-1], FINAL)
        self.assertEqual([line.split(': [', 1)[0] for line in output],
                         ['types.' + label for label in compact_labels])

    def test_full_native_comparator_accepts_confirmed_values_output(self):
        case = native_outputs.NativeOutputTests('test_native_outputs')
        case.compare_script(SOURCE)




class HistoricalTypesSourceTests(unittest.TestCase):
    """Preserve historical source bytes independently of native semantic tests."""

    def test_source_gate_rejects_changes_to_historical_blocks(self):
        program = (SOURCE).read_text(encoding='utf-8-sig')
        confirmed, labels = pending_types_checkpoint(program)
        self.assertTrue(confirmed.endswith('Сообщить("xml.checkpoint.complete: [ok]");\n'))
        self.assertTrue(labels)
        for changed in (program.replace('НаблюдатьNull', 'ИзменитьNull', 1),
                        program.replace('НаблюдатьТипы', 'ИзменитьТипы', 1),
                        program + 'Сообщить("extra");\n',
                        program.replace('types.checkpoint.complete', 'types.changed', 1),
                        program.replace('// Описания типов:', '// Another:', 1)):
            with self.subTest(changed=changed[-100:]), self.assertRaises(AssertionError):
                pending_types_checkpoint(changed)

class SupplementalTypesGateTests(unittest.TestCase):
    def test_split_recovers_exact_original_and_rejects_mutations(self):
        program = SOURCE.read_text(encoding='utf-8-sig')
        original, supplement = split_type_supplement(program)
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),
                         smoke_test.TYPES_ORIGINAL_SOURCE_SHA256)
        self.assertEqual(split_type_supplement(original), (original, ''))
        self.assertTrue(supplement.startswith(TYPES_SUPPLEMENT_HELPERS_START))
        self.assertIn(TYPES_SUPPLEMENT_BODY_START, supplement)
        for changed in (program.replace('НаблюдатьNull', 'ИзменитьNull', 1),
                        program.replace('НаблюдатьДополнениеТипов', 'ИзменитьДополнение', 1),
                        program.replace('contains.present', 'contains.changed', 1),
                        program.replace(TYPES_SUPPLEMENT_BODY_START, '// missing', 1),
                        program.replace(TYPES_SUPPLEMENT_HELPERS_START, '// missing', 1),
                        program + 'Сообщить("extra");\n'):
            with self.subTest(changed=changed[-100:]), self.assertRaises(AssertionError):
                split_type_supplement(changed)

    def test_compact_supplement_matches_confirmed_native_output(self):
        _, supplement = split_type_supplement(SOURCE.read_text(encoding='utf-8-sig'))
        output = []
        Interpreter(output=output.append).execute(supplement)
        expected = (ROOT / 'integrational_tests/output/values.out').read_text(encoding='utf-8-sig')
        expected = expected.split('types.checkpoint.complete: [ok]\n', 1)[1]
        actual = native_outputs.normalize_newlines('\n'.join(output) + '\n')
        self.assertEqual(actual, expected)
        self.assertEqual(output[-1], 'types-extra.checkpoint.complete: [ok]')


class StrictNativeGateTests(unittest.TestCase):
    def test_comparator_has_reviewed_source_bound_historical_replay(self):
        actual = (ROOT / 'tests/test_native_outputs.py').read_bytes().replace(b'\r\n', b'\n')
        # Reviewed migration preserves every captured output byte and binds the
        # complete historical source; live Docker compares all current cases.
        self.assertEqual(hashlib.sha256(actual).hexdigest(), 'ccd67894a076324b057b692257bce55b40aaf46ba03574d801a0e3f16d83fbb6')

    def test_frozen_full_native_comparator_has_reviewed_historical_replay(self):
        text = (ROOT / 'scripts/smoke_test.py').read_text(encoding='utf-8')
        block = ('def check_saved_native_outputs('
                 + text.split('def check_saved_native_outputs(', 1)[1]
                 .split('def check_timezone_configuration(', 1)[0])
        self.assertEqual(hashlib.sha256(block.encode('utf-8')).hexdigest(),
                         "e9ee8ad13bfdaac35780e4a3509a874fcd410e8eb05d1b892a2181573262ee62")

    def test_frozen_full_modes_and_bounded_command_aliases(self):
        expected = (ROOT / 'integrational_tests/output/values.out').read_text(encoding='utf-8-sig')
        full_source = SOURCE.read_text(encoding='utf-8-sig')
        _, command_source = split_type_supplement(full_source)
        marker = 'types.checkpoint.complete: [ok]\n'
        command_expected = expected.split(marker, 1)[1]
        # Account for Windows quoting, escaped quotes, UTF-16 surrogate pairs,
        # and the terminating NUL, even when this regression runs on Linux.
        def windows_units(args):
            return len(subprocess.list2cmdline(args).encode('utf-16-le')) // 2 + 1
        executable = 'C:\\Program Files\\Yadinassi 🚀\\yadinassi.exe'
        self.assertGreaterEqual(windows_units([executable, '-c', full_source]), 32767)
        self.assertLess(windows_units([executable, '--command', command_source]), 16000)
        def windows_run(args, **kwargs):
            self.assertLess(windows_units(args), 32767)
            is_command = len(args) > 1 and args[1] in ('-c', '-с', '--command')
            return subprocess.CompletedProcess(args, 0, command_expected if is_command else expected, '')
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(smoke_test.subprocess, 'run', side_effect=windows_run) as run, \
                    patch.object(smoke_test, 'check_timezone_configuration'):
                smoke_test.check_xml_checkpoint(executable,
                                                directory=Path(temporary) / 'valid', env={})
                self.assertEqual(run.call_count, 6)
                arguments = [call.args[0] for call in run.call_args_list]
                self.assertEqual(Path(arguments[0][1]).read_text(encoding='utf-8-sig'),
                                 full_source)
                self.assertEqual(arguments[1], [executable, '-'])
                self.assertEqual(run.call_args_list[1].kwargs['input'], full_source)
                self.assertEqual(arguments[2], [executable])
                self.assertEqual(run.call_args_list[2].kwargs['input'], full_source + '/exit\n')
                self.assertEqual([args[1] for args in arguments[3:]], ['-c', '-с', '--command'])
                for args in arguments[3:]:
                    self.assertEqual(args[2], command_source)
            for index, changed in enumerate((expected.split(marker)[0] + marker,
                                              expected.replace('types-extra.', 'altered.', 1),
                                              expected.replace('types.', 'altered.', 1),
                                              expected + 'extra\n')):
                result = subprocess.CompletedProcess([], 0, changed, '')
                with patch.object(smoke_test.subprocess, 'run', return_value=result), \
                        self.assertRaises(AssertionError):
                    smoke_test.check_xml_checkpoint(executable,
                                                    directory=Path(temporary) / str(index), env={})
            # Correct full output cannot hide a changed or missing command sample.
            for index, changed in enumerate(('', command_expected + 'extra\n',
                                             command_expected.replace('types-extra.', 'altered.', 1))):
                results = [subprocess.CompletedProcess([], 0, expected, '')] * 3
                results += [subprocess.CompletedProcess([], 0, changed, '')]
                with patch.object(smoke_test.subprocess, 'run', side_effect=results), \
                        self.assertRaises(AssertionError):
                    smoke_test.check_xml_checkpoint(executable,
                                                    directory=Path(temporary) / ('command' + str(index)), env={})

    def test_strict_comparator_rejects_appended_or_altered_tail(self):
        # Synthetic fixtures only: the normal comparator must reject an extra
        # tail even when that tail resembles valid checkpoint framing.
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            (base / 'tests').mkdir()
            (base / 'output').mkdir()
            script = base / 'tests/values.bsl'
            expected = base / 'output/values.out'
            for label, tail in (('appended', 'types.checkpoint.complete: [ok]'),
                                ('altered', 'types.probe: [error]')):
                with self.subTest(label=label):
                    script.write_text('Message("confirmed"); Message("' + tail + '");', encoding='utf-8')
                    expected.write_text('confirmed\n', encoding='utf-8')
                    case = native_outputs.NativeOutputTests('test_native_outputs')
                    case.native_root = base
                    with self.assertRaises(AssertionError):
                        case.compare_script(script)


if __name__ == '__main__':
    unittest.main()
