"""Offline two-phase driver tests; mocks are never native export evidence."""
import ast as pyast
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_native_1c_full_stage as stage
from scripts import native_1c_full_host as host
from scripts.native_historical_replay import without_exported_postcreate_probes
from yadinassi import Interpreter
from yadinassi.values import BSLObject, BSLArray, HostFunction
from yadinassi.structures import BSLStructure

ROOT = Path(__file__).resolve().parents[1]
launcher = stage.load_launcher(ROOT / 'integrational_tests/test_launcher.py')
DIRECTIVE = launcher.POST_CREATE_DIRECTIVE
FORM = ROOT / 'integrational_tests/launcher_1c/Launcher/Forms/Main/Ext/Form/Module.bsl'


def host_directive_parser():
    tree = pyast.parse(host.EXECUTE_SCRIPT)
    nodes = [node for node in tree.body if
             (isinstance(node, pyast.FunctionDef) and node.name == 'post_create_requested')
             or (isinstance(node, pyast.Assign) and any(isinstance(t, pyast.Name) and
                 t.id == 'POST_CREATE_DIRECTIVE' for t in node.targets))]
    namespace = {'re': re}
    exec(compile(pyast.Module(body=nodes, type_ignores=[]), '<driver-parser>', 'exec'), namespace)
    return namespace['post_create_requested']


class DirectiveProtocolTests(unittest.TestCase):
    def test_identical_fail_closed_grammar(self):
        host_parser = host_directive_parser()
        accepted = [('', False), ('Message("// NativePostCreate: Unknown");', False)]
        for bom in ('', '\ufeff'):
            for ending in ('\n', '\r\n'):
                accepted.extend([(bom + DIRECTIVE + ending + 'Message(1);', True),
                                 (bom + 'Message(1);' + ending, False)])
        for source, expected in accepted:
            self.assertIs(launcher.post_create_requested(source), expected)
            self.assertIs(host_parser(source), expected)
        rejected = [DIRECTIVE + '\n' + DIRECTIVE,
                    '\n' + DIRECTIVE, ' ' + DIRECTIVE,
                    DIRECTIVE.replace('ExportProbeAfterCreate', 'Unknown'),
                    DIRECTIVE + '();', DIRECTIVE + ' ', '//NativePostCreate: ExportProbeAfterCreate',
                    '// NativePostCreateUnknown', 'Message(1);\n' + DIRECTIVE]
        for source in rejected:
            for ending in ('\n', '\r\n'):
                transported = source.replace('\n', ending)
                with self.subTest(source=source), self.assertRaises(launcher.LaunchError):
                    launcher.post_create_requested(transported)
                with self.assertRaises(ValueError):
                    host_parser(transported)

    def test_read_once_and_reject_before_module_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'test.bsl'
            source.write_text(DIRECTIVE + '\nMessage(1);', encoding='utf-8')
            original = Path.read_text
            reads = []
            def reader(path, *args, **kwargs):
                if path == source:
                    reads.append(path)
                return original(path, *args, **kwargs)
            def fake_process(command, directory, log, timeout):
                request = json.loads((directory / 'request.json').read_text())
                self.assertIs(request['post_create'], True)
                (directory / 'result.json').write_text('{"messages":[],"error":""}')
            with mock.patch.object(Path, 'read_text', reader), mock.patch.object(launcher, 'build_epf'), \
                 mock.patch.object(launcher, 'run_process', side_effect=fake_process):
                launcher.run_case(launcher.Platform(Path('native'), root), source, root/'launcher.epf',
                                  root/'case', root/'result.out')
            self.assertEqual(reads, [source])
            source.write_text(DIRECTIVE + '\n' + DIRECTIVE, encoding='utf-8')
            with mock.patch.object(launcher, 'build_epf') as build, self.assertRaises(launcher.LaunchError):
                launcher.run_case(launcher.Platform(Path('native'), root), source, root/'launcher.epf',
                                  root/'rejected', root/'bad.out')
            build.assert_not_called()
            self.assertFalse((root/'rejected').exists())

    def test_request_binding_and_boolean_types(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            command = ['native', 'ENTERPRISE', '/C', str(root/'request.json')]
            expected = {'module': str(root/'TestModule.epf'), 'result': str(root/'result.json'),
                        'post_create': True}
            for changed in (expected, {**expected, 'post_create': False}, {**expected, 'post_create': 1},
                            {**expected, 'post_create': 'true'}, {**expected, 'module': '/wrong'},
                            {**expected, 'result': '/wrong'}, {**expected, 'extra': True},
                            {key:value for key,value in expected.items() if key != 'post_create'}):
                (root/'request.json').write_text(json.dumps(changed), encoding='utf-8')
                if changed is expected:
                    stage.suite.validate_case_request(command, root, True)
                else:
                    with self.assertRaises(stage.suite.FullError):
                        stage.suite.validate_case_request(command, root, True)
            (root/'request.json').write_text(json.dumps(expected), encoding='utf-8')
            for args in (['native','ENTERPRISE'], command+['/C',str(root/'request.json')],
                         ['native','ENTERPRISE','/C',str(root/'other.json')]):
                with self.assertRaises(stage.suite.FullError):
                    stage.suite.validate_case_request(args, root, True)

    def test_request_tamper_rejected_at_actual_launch_boundary(self):
        harness = stage.FullSuiteHarness()
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        write = Path.write_text
        mutated = []
        def tamper(path, text, *args, **kwargs):
            if path.name == 'request.json':
                request = json.loads(text)
                request['post_create'] = not request['post_create']
                text = json.dumps(request)
                mutated.append(path)
            return write(path, text, *args, **kwargs)
        with mock.patch.object(Path, 'write_text', tamper):
            report = harness.run_suite()
        self.assertTrue(mutated)
        self.assertEqual(report['failure_kind'], 'invalid_input')
        self.assertEqual(harness.events, [('collections', 'build')])

    def test_host_literal_call_order_with_offline_mock_receiver(self):
        # A mock package checks driver ordering, not any 1C/runtime semantics.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'yadinassi').mkdir()
            (root/'yadinassi/__init__.py').write_text("""
class BSLError(Exception):
    def __init__(self, message):
        self.message = message
class Interpreter:
    def __init__(self, output, **options):
        self.output = output
        self.started = False
    def execute(self, source, label):
        if not self.started:
            self.started = True
            self.fail = 'callback-failure' in source
            self.output('mock-initial')
        else:
            assert source == 'ThisObject.ExportProbeAfterCreate(ThisObject);'
            assert label == '<post-create>'
            self.output('mock-probe')
            if self.fail:
                raise BSLError('controlled private callback text')
""", encoding='utf-8')
            source = root/'case.bsl'
            for failure in (False, True):
                source.write_text(DIRECTIVE + '\n// ' + ('callback-failure' if failure else 'success'),
                                  encoding='utf-8')
                result = subprocess.run([sys.executable, '-c', host.EXECUTE_SCRIPT, str(root), str(source)],
                                        capture_output=True, check=False)
                self.assertEqual(result.stderr, b'')
                self.assertEqual(result.returncode, 3 if failure else 0)
                expected = ['mock-initial', 'export-phase.post-create: [begin]', 'mock-probe',
                            'export-phase.post-create: [error;kind=other;named={"B",0}]' if failure
                            else 'export-phase.post-create: [ok]']
                self.assertEqual(result.stdout.decode().splitlines(), expected)

    def test_host_real_checkpoint_is_bounded_failure_not_green(self):
        source = ROOT/'integrational_tests/tests/functions.bsl'
        result = subprocess.run([sys.executable, '-c', host.EXECUTE_SCRIPT, str(ROOT), str(source),
                                 'linux-8.3.27.1508'], capture_output=True, check=False)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stderr, b'')
        expected = []
        Interpreter(expected.append, native_target='linux-8.3.27.1508').execute(
            without_exported_postcreate_probes(source.read_text(encoding='utf-8')))
        lines = result.stdout.decode().splitlines()
        self.assertEqual(lines[:136], expected)
        self.assertEqual(lines[136:], ['export-phase.post-create: [begin]',
            'export-phase.post-create: [error;kind=other;named={"B",0}]'])
        with tempfile.TemporaryDirectory() as folder:
            historical = Path(folder)/'old.bsl'
            historical.write_text('Message("unchanged");', encoding='utf-8')
            result = subprocess.run([sys.executable, '-c', host.EXECUTE_SCRIPT, str(ROOT), str(historical)],
                                    capture_output=True, check=False)
            self.assertEqual((result.returncode,result.stdout,result.stderr), (0,b'unchanged\n',b''))


class NativeDriverOfflineTests(unittest.TestCase):
    def run_server(self, mode, enabled=True):
        pending, events = [], []
        interpreter = Interpreter(pending.append)
        class Public(BSLObject):
            def get_method(self, name):
                if name != 'ExportProbeAfterCreate':
                    raise AssertionError(name)
                if mode == 'missing':
                    raise ValueError('Метод объекта не обнаружен (ExportProbeAfterCreate)')
                def callback(receiver):
                    events.append('callback')
                    self_test.assertIs(receiver, public)
                    pending.append('controlled-probe')
                    if mode == 'callback-failure':
                        raise ValueError('controlled callback failure')
                return HostFunction(name, callback)
        class Manager(BSLObject):
            def get_method(self, name):
                if name.casefold() != 'создать':
                    raise AssertionError(name)
                def create(path, safe):
                    events.append('create')
                    if mode == 'create-failure':
                        raise ValueError('controlled create failure')
                    return public
                return HostFunction(name, create)
        self_test = self
        public = Public()
        interpreter.variables['внешниеобработки'] = Manager()
        interpreter.module_names.add('внешниеобработки')
        interpreter.register_function('ПодробноеПредставлениеОшибки', lambda info: 'offline captured error')
        def collect(clear):
            array = BSLArray()
            array.items.extend(BSLStructure('Текст', message) for message in pending)
            pending.clear()
            return array
        interpreter.register_function('ПолучитьСообщенияПользователю', collect)
        source = FORM.read_text(encoding='utf-8')
        # Offline control-flow simulation only: the standalone test VM has no server context.
        # This removes exactly one compilation annotation, never edits a native input.
        self.assertEqual(source.count('&НаСервереБезКонтекста\n'), 1)
        interpreter.execute(source.replace('&НаСервереБезКонтекста\n', '', 1))
        interpreter.variables['enabled'] = enabled
        interpreter.execute('Result = ЗапуститьТестНаСервере("controlled", Enabled);')
        result = interpreter.variables['result']
        return list(result.get('messages')), result.get('error'), events

    def test_literal_call_receiver_and_success_order(self):
        messages, error, events = self.run_server('success')
        self.assertEqual(messages, ['export-phase.post-create: [begin]', 'controlled-probe',
                                    'export-phase.post-create: [ok]'])
        self.assertEqual(error, '')
        self.assertEqual(events, ['create', 'callback'])

    def test_missing_entrypoint_and_callback_failure_are_bounded(self):
        messages, error, events = self.run_server('missing')
        self.assertEqual(messages, ['export-phase.post-create: [begin]',
            'export-phase.post-create: [error;kind=method-missing;named={"B",1}]'])
        self.assertEqual(error, '')
        self.assertEqual(events, ['create'])
        messages, error, events = self.run_server('callback-failure')
        self.assertEqual(messages[:2], ['export-phase.post-create: [begin]', 'controlled-probe'])
        self.assertTrue(messages[-1].startswith('export-phase.post-create: [error;kind=other;'))
        self.assertNotIn('controlled callback failure', ''.join(messages))
        self.assertEqual(error, '')

    def test_no_phase_after_create_failure_or_without_directive(self):
        messages, error, events = self.run_server('create-failure')
        self.assertEqual(messages, [])
        self.assertTrue(error)
        self.assertEqual(events, ['create'])
        self.assertEqual(self.run_server('success', False), ([], '', ['create']))

    def test_invalid_boolean_rejected_before_create(self):
        from yadinassi import BSLError
        with self.assertRaisesRegex(BSLError, 'Invalid post-create request'):
            self.run_server('success', 'true')

if __name__ == '__main__':
    unittest.main()
