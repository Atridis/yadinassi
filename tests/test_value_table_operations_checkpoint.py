"""Probe integrity only: native Sort/GroupBy outputs must come from the owner."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, ast
from yadinassi.parser import parse
from yadinassi.value_tables import BSLValueTable
from yadinassi.values import HostFunction

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало компактных проб Sort/GroupBy.\n', '// Конец компактных проб Sort/GroupBy.\n\n')
BODY = ('// Начало наблюдений Sort/GroupBy.\n', '// Конец наблюдений Sort/GroupBy.\n')


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def canonical_output_bytes(data):
    # Only checkout/launcher line endings. Compact escaped scalar CR/LF bytes
    # remain untouched; this is not a relaxed native output comparison.
    return data.replace(b'\r\n', b'\n')


def section(markers):
    return source().split(markers[0], 1)[1].split(markers[1], 1)[0]


def observations():
    return [node.expression for node in parse(section(BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


class ValueTableOperationsCheckpointTests(unittest.TestCase):
    def test_owner_source_and_outputs_preserved_exactly(self):
        old = source()
        for start, end in (HELPERS, BODY):
            before, rest = old.split(start, 1)
            _, after = rest.split(end, 1)
            old = before + after
        data = ('\ufeff' + old).encode()
        self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
                         'cf922dbeabcd77f5a0ea27fec7164d246d78e9eb')
        for name, expected in (
            ('collections', '6645f7fa667dfe498cef9109fb7b42078dfb9c43'),
            ('values', '016f30d6f3bdb1a814e86a70e3bcf424383a0d27'),
        ):
            data = canonical_output_bytes((ROOT / f'integrational_tests/output/{name}.out').read_bytes())
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(), expected)

    def test_owner_output_integrity_accepts_crlf_and_preserves_escapes(self):
        self.assertEqual(canonical_output_bytes(b'row\r\n{"S","literal \\r\\n"}\r\n'),
                         b'row\n{"S","literal \\r\\n"}\n')
        original = Path.read_bytes
        def windows_bytes(path):
            data = original(path)
            if path.suffix == '.out':
                return data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            return data
        with patch.object(Path, 'read_bytes', windows_bytes):
            self.test_owner_source_and_outputs_preserved_exactly()

    def test_fixed_unique_bounded_expressions(self):
        calls = observations()
        self.assertEqual(len(calls), 62)
        labels = []
        for call in calls:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(a, ast.Literal) and type(a.value) is str for a in call.arguments))
            label, expression = (a.value for a in call.arguments)
            self.assertRegex(label, r'^ops\.(sort|group)\.[a-z0-9-]+$')
            self.assertLess(len(expression), 200)
            self.assertNotRegex(expression, r'[\r\n]')
            parse('Result = ' + expression + ';')
            labels.append(label)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(sum(label.startswith('ops.sort.') for label in labels), 24)
        self.assertIn('table.ops.checkpoint.complete: [ok]', section(BODY))

    def test_full_source_compiles_and_declarations_precede_statements(self):
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True
        self.assertNotIn('Новый ТаблицаЗначений;', section(HELPERS))
        self.assertNotIn('Новый CompareValues', section(HELPERS))

    def test_every_probe_reaches_its_target_method_and_serializes(self):
        # Host instrumentation is an observability test, never a native oracle:
        # it proves setup succeeded, the operation executes once, and scalar
        # output survives. It deliberately accepts even invalid native inputs.
        invoked = []
        original = BSLValueTable.get_method

        def get_method(table, name):
            if name.casefold() in ('sort', 'сортировать', 'groupby', 'свернуть'):
                def record(*args):
                    invoked.append((name, args))
                return HostFunction(name, record, returns_value=False)
            if name.casefold() == 'delete' and [c.name for c in table.columns.items] == ['Key', 'Amount']:
                real = original(table, name)
                def record_delete(*args):
                    invoked.append((name, args))
                    return real(*args)
                return HostFunction(name, record_delete, returns_value=False)
            return original(table, name)

        output = []
        with patch.object(BSLValueTable, 'get_method', get_method):
            Interpreter(output=output.append).execute(source())
        records = [line for line in output if line.startswith('table.ops.')
                   and not line.startswith('table.ops.checkpoint.')]
        self.assertEqual(len(invoked), 62)
        self.assertEqual(len(records), 62)
        for record in records:
            self.assertIn('  Status={"S","ok"}', record)
            self.assertNotIn('[serialize-error]', record)
            self.assertNotIn('[snapshot-error]', record)
        self.assertEqual(sum(name.casefold() in ('sort', 'сортировать') for name, _ in invoked), 24)
        self.assertIn(('Sort', ()), invoked)
        self.assertIn('Сортировать', [name for name, _ in invoked])
        self.assertIn('Свернуть', [name for name, _ in invoked])

    def test_operation_error_preserves_mutated_state(self):
        # A deliberate pre-error mutation distinguishes successful observation
        # from an outer catch that would erase partial native state.
        original = BSLValueTable.get_method
        def get_method(table, name):
            if name.casefold() in ('sort', 'сортировать', 'groupby', 'свернуть'):
                def fail(*args):
                    if table.rows:
                        table.delete(table.rows[0])
                    raise ValueError('instrumented failure after mutation')
                return HostFunction(name, fail, returns_value=False)
            return original(table, name)
        vm = Interpreter()
        # Load routines only, keeping the instrumented test independent of
        # the owner golden and the complete native comparison.
        helper_source = source().split('#Область МассивыИСтруктуры', 1)[0]
        vm.execute(helper_source)
        with patch.object(BSLValueTable, 'get_method', get_method):
            result = vm.execute('СверткаТаблицыПробы("base", "Key", "Amount")')
        self.assertEqual(result.get_member('Status'), 'error')
        self.assertEqual(result.get_member('After').get_member('Count'), 3)
        with patch.object(BSLValueTable, 'get_method', get_method):
            result = vm.execute('СортировкаТаблицыПробы("base", "Key")')
        self.assertEqual(result.get_member('Status'), 'error')
        self.assertEqual(result.get_member('Order').items, [2, 3, 4, 5, 6])
        self.assertEqual(result.get_member('FirstID'), '[error]')
        self.assertEqual(result.get_member('SameRow'), False)

    def test_real_current_runtime_records_all_unsupported_calls(self):
        output = []
        Interpreter(output=output.append).execute(source())
        records = [line for line in output if line.startswith('table.ops.')
                   and not line.startswith('table.ops.checkpoint.')]
        self.assertEqual(len(records), 62)
        # Do not assert native results. Before implementation, missing methods
        # must still leave useful state records instead of outer errors.
        for record in records:
            self.assertIn('  Status=', record)
            self.assertTrue('  Order=' in record or '  After.Count=' in record)
        self.assertEqual(output[-2:], ['table.ops.checkpoint.complete: [ok]', 'table.checkpoint.complete: [ok]'])


if __name__ == '__main__':
    unittest.main()
