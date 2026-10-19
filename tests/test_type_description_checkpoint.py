"""Safety/packaging tests only; native TypeDescription answers remain unknown."""
from dataclasses import fields, is_dataclass
from pathlib import Path
import unittest
import tempfile
import hashlib
if __package__:
    from . import test_native_outputs as native_outputs
else:
    import test_native_outputs as native_outputs
from scripts.smoke_test import pending_types_checkpoint, validate_pending_types_output

from yadinassi import Interpreter, ast
from yadinassi.parser import parse, parse_expression

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
START = '// Нативный checkpoint описаний типов.'
OLD_BODY = '// Значение, тип и настоящий прямой/обратный кодек.'
BODY = '// Описания типов: наблюдения без заранее заданных ответов.'
FINAL = 'types.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


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
    def test_fixed_bounded_parseable_matrix(self):
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
            parse_expression(expression)
        self.assertTrue(source().rstrip().endswith('Сообщить("' + FINAL + '");'))

    def test_declarations_precede_main_and_new_constructors_are_only_strings(self):
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            else:
                started = True
        # The helper AST may instantiate only pre-existing containers; unresolved
        # TypeDescription/qualifier constructors must remain inside protected Eval.
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

    def test_complete_program_reaches_pending_marker_without_prediction(self):
        output = []
        Interpreter(output=output.append).execute(source())
        self.assertEqual(output[-1], FINAL)
        pending = [line for line in output if line.startswith('types.')]
        self.assertEqual(len(pending), 147)
        self.assertEqual([line.split(': [', 1)[0] for line in pending[:-1]],
                         ['types.' + c.arguments[0].value for c in calls()])
        # Current interpreter errors are packaging observations, never a golden.
        for line in pending[:-1]:
            self.assertRegex(line, r'(?s)^types\.[a-z0-9.-]+: \[(?:error|serialize-error|\{.*\})\]$')


class PendingTypesGateTests(unittest.TestCase):
    """The new tail is packaging-only until the owner supplies real 1C output."""

    def test_source_gate_rejects_changes_to_confirmed_or_pending_blocks(self):
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

    def test_pending_framing_rejects_extra_missing_reordered_and_malformed_output(self):
        expected = 'unchanged native prefix\n'
        first = 'types.first: [{\n{"N",1}\n}]\n'
        second = 'types.second: [serialize-error]\n'
        final = 'types.checkpoint.complete: [ok]\n'
        labels = ['types.first', 'types.second']
        validate_pending_types_output(expected + first + second + final, expected, labels)
        validate_pending_types_output(expected + first.replace('{\n{"N",1}\n}', 'error')
                                      + second + final, expected, labels)
        for body in (first + final, second + first + final,
                     first + first + second + final,
                     first + second + final + 'extra\n',
                     'extra\n' + first + second + final,
                     first + 'extra\n' + second + final,
                     first + second + final + final,
                     first + second, first.replace('}]\n', '}\n') + second + final,
                     first + second.replace('serialize-error', 'guessed') + final):
            with self.subTest(body=body), self.assertRaises(AssertionError):
                validate_pending_types_output(expected + body, expected, labels)
        with self.assertRaises(AssertionError):
            validate_pending_types_output('changed native prefix\n' + first + second + final,
                                          expected, labels)
        with self.assertRaises(AssertionError):
            validate_pending_types_output(expected + first + second + final, expected,
                                          ['types.first', 'types.first'])


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

    def test_strict_comparator_rejects_appended_or_altered_pending_tail(self):
        # Synthetic fixtures only: the normal comparator must reject an extra
        # tail even when that tail is valid pending-checkpoint framing.
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
