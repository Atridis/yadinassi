"""Execute exact generated BSL request routines against a controlled token double.
Offline harness logic only: no native JSONReader, API, filesystem, or Async evidence.
"""
from decimal import Decimal
import itertools
import json
from pathlib import Path
import unittest

from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.structures import BSLStructure
from yadinassi.values import BSLObject, HostFunction
import test_native_async_execution as execution

suite = execution.suite
class Pairs(list):
    pass

# Source-bound, exact-spelling doubles only, not a native API alias inventory.
# Keep the internal JSON token grammar separate from the exposed enum members.
TOKENS = frozenset(('ObjectStart', 'ObjectEnd', 'PropertyName', 'String',
                    'Number', 'Boolean', 'Null', 'ArrayStart', 'ArrayEnd'))

SOURCE_EN_MEMBERS = frozenset(('ObjectStart', 'PropertyName', 'String', 'Number'))


class TokenNames(BSLObject):
    def get_member(self, name):
        if name not in SOURCE_EN_MEMBERS:
            raise ValueError('Unknown controlled English enum member')
        return name


class RussianTokenNames(BSLObject):
    def get_member(self, name):
        if name != 'КонецОбъекта':
            raise ValueError('Unknown controlled Russian enum member')
        return 'ObjectEnd'


def stream_tokens(raw):
    """Generic JSON tokenizer, never the request validator. Preserve duplicates."""
    def walk(value):
        if isinstance(value, Pairs):
            yield ('ObjectStart', None)
            for key, item in value:
                yield ('PropertyName', key)
                yield from walk(item)
            yield ('ObjectEnd', None)
        elif isinstance(value, list):
            yield ('ArrayStart', None)
            for item in value:
                yield from walk(item)
            yield ('ArrayEnd', None)
        elif type(value) is bool:
            yield ('Boolean', value)
        elif value is None:
            yield ('Null', None)
        elif type(value) is Decimal:
            yield ('Number', value)
        else:
            assert type(value) is str
            yield ('String', value)
    # Raw-decode each root, so trailing valid JSON reaches the BSL EOF guard.
    text = raw.decode('utf-8')
    decoder = json.JSONDecoder(object_pairs_hook=Pairs, parse_int=Decimal,
                               parse_float=Decimal,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite')))
    result = []
    while text.strip():
        text = text.lstrip()
        value, end = decoder.raw_decode(text)
        result.extend(walk(value))
        text = text[end:]
    return result


class ControlledReader(BSLObject):
    def __init__(self, tokens, expected_path, fault=None):
        self.tokens, self.expected_path, self.fault = tokens, expected_path, fault
        self.position = -1
        self.opened = self.closed = False
        self.read_calls = 0

    def open_file(self, path):
        assert path == self.expected_path, 'LaunchParameter changed'
        if self.fault == 'request_open':
            raise ValueError('Controlled failure')
        self.opened = True

    def read(self):
        assert self.opened and not self.closed
        self.position += 1
        self.read_calls += 1
        if self.position < len(self.tokens):
            kind = self.tokens[self.position][0]
            stage = {'ObjectStart': 'request_object', 'PropertyName': 'request_key',
                     'String': 'request_value', 'Number': 'request_value',
                     'ObjectEnd': 'request_end'}.get(kind)
            if stage == self.fault:
                raise ValueError('Controlled failure')
            return True
        return False

    def close(self):
        self.closed = True

    def get_member(self, name):
        if name == 'CurrentValueType':
            return self.tokens[self.position][0]
        if name == 'CurrentValue':
            kind, value = self.tokens[self.position]
            assert kind not in ('ObjectStart', 'ObjectEnd', 'ArrayStart', 'ArrayEnd')
            return value
        method = {'OpenFile': self.open_file, 'Read': self.read, 'Close': self.close}.get(name)
        if method is None:
            raise ValueError('Unknown controlled reader member')
        return HostFunction(name, method, returns_value=(name == 'Read'))


class ControlledStructure(BSLStructure):
    def __init__(self, fault):
        super().__init__()
        self.fault = fault
        self.property_calls = 0

    def property(self, name, output=None):
        self.property_calls += 1
        if self.fault == 'request_fields' and self.property_calls == 6:
            raise ValueError('Controlled failure')
        return super().property(name, output)

    def get_member(self, name):
        if ((self.fault == 'request_nonce' and name == 'nonce') or
                (self.fault == 'request_paths' and name == 'entered')):
            raise ValueError('Controlled failure')
        return super().get_member(name)


def exercise(raw, launch_path='/tmp/offline/request.json', fault=None, tokens=None, case_id=0):
    # No source rewrite: these bytes come directly from the generated case module.
    module = suite.async_client_module(case_id).decode('utf-8-sig')
    start = module.index('&AtClient\nProcedure AsyncExpectToken')
    end = module.index('&НаКлиенте\nПроцедура АсинхЗаписатьВход')
    source = module[start:end]
    reader = ControlledReader(stream_tokens(raw) if tokens is None else tokens, launch_path, fault)
    vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
    vm.register_type('JSONReader', lambda: reader)
    if fault in ('request_fields', 'request_nonce', 'request_paths'):
        vm.register_type('Structure', lambda: ControlledStructure(fault))
    vm.execute('Var JSONValueType, ТипЗначенияJSON, LaunchParameter;')
    vm.variables['jsonvaluetype'] = TokenNames()
    vm.variables['типзначенияjson'] = RussianTokenNames()
    vm.variables['launchparameter'] = launch_path
    vm.execute(source)
    vm.execute('Stage = "request"; Caught = False; '
               'Try Result = AsyncReadRequest(Stage); Except Caught = True; EndTry;')
    return vm, reader


def canonical(**changes):
    value = dict(schema=1, version=1, nonce='a' * 32,
                 entered='/tmp/offline/entered.json', completed='/tmp/offline/completed.json')
    value.update(changes)
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


class GeneratedRequestReaderTests(unittest.TestCase):
    def test_enum_doubles_separate_source_members_from_token_grammar(self):
        english, russian = TokenNames(), RussianTokenNames()
        self.assertEqual(russian.get_member('КонецОбъекта'), 'ObjectEnd')
        self.assertIn('ObjectEnd', TOKENS)
        for name in SOURCE_EN_MEMBERS:
            self.assertEqual(english.get_member(name), name)
        # Reject unused spellings in this source-bound test double only. This
        # does not claim that native enum names are case-sensitive, nor that
        # the original English ObjectEnd alias is generally unsupported.
        for name in (*sorted(TOKENS - SOURCE_EN_MEMBERS), 'КонецОбъекта', 'Unknown'):
            with self.subTest(namespace='English', member=name), self.assertRaises(ValueError):
                english.get_member(name)
        for name in (*sorted(TOKENS), 'КонецМассива', 'Unknown'):
            with self.subTest(namespace='Russian', member=name), self.assertRaises(ValueError):
                russian.get_member(name)

    def test_canonical_request_runs_actual_bsl(self):
        vm, reader = exercise(canonical())
        self.assertFalse(vm.execute('Caught'))
        self.assertEqual(vm.execute('Result.Count()'), Decimal(5))
        self.assertEqual(vm.execute('Result.schema'), Decimal(1))
        self.assertEqual(vm.execute('Result.version'), Decimal(1))
        self.assertEqual(vm.execute('Stage'), 'request_paths')
        self.assertTrue(reader.opened and reader.closed)
        self.assertEqual(reader.read_calls, 13)  # 12 tokens plus EOF.

    def test_all_key_orders_preserve_values(self):
        items = list(json.loads(canonical()).items())
        for case_id in range(8):
            for ordered in itertools.permutations(items):
                with self.subTest(case=case_id, order=[key for key, _ in ordered]):
                    vm, reader = exercise(json.dumps(dict(ordered), separators=(',', ':')).encode(),
                                          case_id=case_id)
                    self.assertFalse(vm.execute('Caught'))
                    self.assertEqual(vm.execute('Result.Count()'), Decimal(5))
                    for key, value in ordered:
                        self.assertEqual(vm.execute('Result.' + key), value)
                    self.assertEqual(reader.read_calls, 13)
                    self.assertTrue(reader.closed)

    def test_strict_negatives_reach_actual_bsl_guards(self):
        good = canonical()
        bad = [b'[]', b'null', b'{}', good + b'{}',
               good.replace(b'"schema":1', b'"schema":1,"schema":1'),
               good.replace(b'"version":1', b'"schema":1'),
               good.replace(b'"schema":1', b'"extra":1'),
               good.replace(b'"schema":1', b'"schema":{}'),
               good.replace(b'"schema":1', b'"schema":[]')]
        for key in ('schema', 'version'):
            for value in (True, False, '1', None, 0, 2, 1.5):
                bad.append(canonical(**{key: value}))
        for key in ('nonce', 'entered', 'completed'):
            for value in (True, False, 1, None, {}, []):
                bad.append(canonical(**{key: value}))
        for value in ('', 'a' * 31, 'a' * 33, 'A' * 32, 'g' * 32):
            bad.append(canonical(nonce=value))
        for key in ('entered', 'completed'):
            for value in ('', 'a' * 513):
                bad.append(canonical(**{key: value}))
        bad.append(canonical(completed='/tmp/offline/entered.json'))
        for case_id in range(8):
            for index, raw in enumerate(bad):
                with self.subTest(case=case_id, invalid=index):
                    vm, _ = exercise(raw, case_id=case_id)
                    self.assertTrue(vm.execute('Caught'))
                    self.assertNotIn('result', vm.variables)

    def test_lexical_numbers_are_value_checks_not_integer_spelling(self):
        # Native reader converts numbers. Canonical writer uses 1, but the BSL
        # routine intentionally checks numeric value, not original JSON spelling.
        for spelling in (b'1.0', b'1e0', b'1.000'):
            vm, _ = exercise(canonical().replace(b'"schema":1', b'"schema":' + spelling))
            self.assertFalse(vm.execute('Caught'))

    def test_numeric_guard_rejects_boolean_even_under_number_token(self):
        tokens = stream_tokens(canonical())
        at = tokens.index(('PropertyName', 'schema')) + 1
        tokens[at] = ('Number', True)
        vm, _ = exercise(canonical(), tokens=tokens)
        self.assertTrue(vm.execute('Caught'))
        self.assertEqual(vm.execute('Stage'), 'request_value')

    def test_all_eight_faults_preserve_byref_stage_after_exception(self):
        for part in ('open', 'object', 'key', 'value', 'end', 'fields', 'nonce', 'paths'):
            stage = 'request_' + part
            with self.subTest(stage=stage):
                vm, _ = exercise(canonical(), fault=stage)
                self.assertTrue(vm.execute('Caught'))
                self.assertEqual(vm.execute('Stage'),
                                 {'key': 'request_key_read_first',
                                  'end': 'request_end_read'}.get(part, stage))
                self.assertNotIn('result', vm.variables)


class ActualSerializerRequestTests(unittest.TestCase):
    argument = staticmethod(execution.AsyncExecutionTests.argument)
    fake_native = execution.AsyncExecutionTests.fake_native
    run_async = execution.AsyncExecutionTests.run_async

    def setUp(self):
        execution.AsyncExecutionTests.setUp(self)
        self.request_replays = 0

    def fake_async(self, command, directory, log, timeout, *, require_clean_tree=False):
        if '/Execute' in command:
            self.assertEqual(command.count('/C'), 1)
            path = Path(self.argument(command, '/C'))
            raw = path.read_bytes()
            self.assertEqual(path, directory / 'request.json')
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
            obj = json.loads(raw.decode('utf-8'))
            self.assertEqual(list(obj), ['completed', 'entered', 'nonce', 'schema', 'version'])
            self.assertIs(type(obj['schema']), int)
            self.assertIs(type(obj['version']), int)
            self.assertEqual(obj['schema'], 1)
            self.assertEqual(obj['version'], 1)
            self.assertTrue(all(type(obj[name]) is str for name in ('nonce', 'entered', 'completed')))
            self.assertEqual(obj['nonce'], execution.NONCE)
            self.assertIn(b'"schema":1', raw)
            self.assertIn(b'"version":1', raw)
            self.assertEqual(raw, json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8'))
            self.assertEqual(obj['entered'], str(directory / 'entered.json'))
            self.assertEqual(obj['completed'], str(directory / 'completed.json'))
            vm, reader = exercise(raw, str(path), case_id=int(directory.name.split('-')[-1]))
            self.assertFalse(vm.execute('Caught'))
            self.assertEqual(vm.execute('Result.nonce'), obj['nonce'])
            self.assertEqual(vm.execute('Result.entered'), obj['entered'])
            self.assertEqual(vm.execute('Result.completed'), obj['completed'])
            self.assertTrue(reader.closed)
            self.request_replays += 1
        return execution.AsyncExecutionTests.fake_async(self, command, directory, log, timeout,
                                                        require_clean_tree=require_clean_tree)

    def test_actual_writer_and_command_replayed_for_all_eight_cases(self):
        self.work = self.root / 'async path ё'
        value = self.run_async()
        self.assertEqual(value['status'], 'ok', value)
        self.assertEqual(self.request_replays, 8)


if __name__ == '__main__':
    unittest.main()
