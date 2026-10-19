"""Immutable native TypeDescription probes and exact owner-output parity."""
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
from yadinassi.parser import parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
START = '// Нативный checkpoint описаний типов.'
OLD_BODY = '// Значение, тип и настоящий прямой/обратный кодек.'
BODY = '// Описания типов: наблюдения без заранее заданных ответов.'
FINAL = 'types.checkpoint.complete: [ok]'


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
    def test_fixed_bounded_matrix(self):
        observations = calls()
        self.assertEqual(len(observations), 146)
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
            # Fixed Eval strings include native syntax-error controls. The
            # outer source must parse; these strings need not be valid syntax.
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
                      'description.types-copy', 'description.contains',
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
                                 'types.next: [{"N",5}]'])

    def test_snapshot_records_real_codec_and_nested_inverse_for_existing_value(self):
        vm = Interpreter()
        vm.execute(helpers())
        result = vm.execute('СнимокТипов(12.5)')
        self.assertEqual(result.get('Write'), '{"N",12.5}')
        self.assertEqual(result.get('ReadWrite'), result.get('Write'))
        self.assertEqual(result.get('ReadType'), result.get('Type'))
        self.assertTrue(result.get('Equal'))
        self.assertIn('{"N",12.5}', result.get('Nested'))

    def test_snapshot_failed_stages_do_not_prevent_record(self):
        vm = Interpreter()
        vm.register_function('UnknownHost', lambda: object())
        vm.execute(helpers())
        result = vm.execute('СнимокТипов(UnknownHost())')
        for field in ('Type', 'Write', 'ReadType', 'Nested'):
            self.assertEqual(result.get(field), '[error]')

    def test_original_type_observations_match_owner_output_exactly(self):
        # Run helpers and the original 146 probes independently; the full-file
        # comparator additionally covers preceding XML and every other output byte.
        output = []
        Interpreter(output=output.append).execute(helpers() + BODY + source().split(BODY, 1)[1])
        expected = (ROOT / 'integrational_tests/output/values.out').read_text(encoding='utf-8-sig')
        expected = expected.split('xml.checkpoint.complete: [ok]\n', 1)[1]
        expected = expected.split('types.checkpoint.complete: [ok]\n', 1)[0] + FINAL + '\n'
        actual = native_outputs.normalize_newlines('\n'.join(output) + '\n')
        self.assertEqual(actual, expected)




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
                         '2d49d5f557c6994e9d21594880c1c9fb482cf7f68fb39148a4049ecedc7add15')
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

    def test_standalone_supplement_matches_owner_output_exactly(self):
        _, supplement = split_type_supplement(SOURCE.read_text(encoding='utf-8-sig'))
        output = []
        Interpreter(output=output.append).execute(supplement)
        expected = (ROOT / 'integrational_tests/output/values.out').read_text(encoding='utf-8-sig')
        expected = expected.split('types.checkpoint.complete: [ok]\n', 1)[1]
        actual = native_outputs.normalize_newlines('\n'.join(output) + '\n')
        self.assertEqual(actual, expected)


class StrictNativeGateTests(unittest.TestCase):
    def test_original_comparator_file_is_unchanged(self):
        actual = (ROOT / 'tests/test_native_outputs.py').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(actual).hexdigest(), '964a0505512651473dcaf6f8bf038d89bf7934ea254e772fc2e1ea17aca5738b')

    def test_original_frozen_full_native_comparator_is_unchanged(self):
        text = (ROOT / 'scripts/smoke_test.py').read_text(encoding='utf-8')
        block = ('def check_saved_native_outputs('
                 + text.split('def check_saved_native_outputs(', 1)[1]
                 .split('def check_timezone_configuration(', 1)[0])
        self.assertEqual(hashlib.sha256(block.encode('utf-8')).hexdigest(),
                         "9f73caaec2334b4bcdf745819ae39d69fa3d8e8de065f7ace5ead14cc48914a8")

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
