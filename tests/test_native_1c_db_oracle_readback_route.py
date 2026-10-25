"""Offline row-route plumbing; synthetic/mocked transport is not native proof."""
from __future__ import annotations

import contextlib
import copy
import importlib
import importlib.machinery
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / 'scripts/native_1c_db_oracle'
NONCE = 'a' * 32
APPROVED = ['--execute-approved-image', '--file-db-oracle']
MODES = ({}, {'record_metadata': True}, {'record_reader': True})
FLAGS = ([], ['--record-metadata-observation'], ['--record-reader-validation'])


def allowed_module_origin(name, location, module, *, staged, stdlib, extension_root):
    """Test-only import census; the Windows exception is one exact DLLs root."""
    if {'site-packages','dist-packages'}.intersection(part.casefold() for part in location.parts):
        return False
    if staged in location.parents or stdlib in location.parents:
        return True
    loader=getattr(module,'__loader__',None); spec=getattr(module,'__spec__',None)
    return (extension_root is not None and location.parent==extension_root
        and name in sys.stdlib_module_names
        and type(loader) is importlib.machinery.ExtensionFileLoader
        and getattr(spec,'loader',None) is loader and getattr(spec,'name',None)==name
        and loader.name==name and type(getattr(spec,'origin',None)) is str
        and Path(loader.path).resolve()==location and Path(spec.origin).resolve()==location
        and location.name in {name.rsplit('.',1)[-1]+suffix
                             for suffix in importlib.machinery.EXTENSION_SUFFIXES})


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_saved_path = sys.path[:]
_saved_bytecode = sys.dont_write_bytecode
_names = ('comparison', 'filedb_catalog', 'contract', 'protocol', 'snapshots',
          'inputs', 'native_1c_smoke', 'filedb', 'record_observation', 'record_validation')
_saved_modules = {name: sys.modules.get(name) for name in _names}
try:
    sys.path[:0] = [str(HELPERS), str(ROOT / 'scripts'), str(ROOT / 'yadinassi/storage')]
    for _name in _names:
        sys.modules.pop(_name, None)
    host = load('readback_route_host_under_test', ROOT / 'scripts/native_1c_db_oracle.py')
    inputs = importlib.import_module('inputs')
    protocol = importlib.import_module('protocol')
    record_policy = importlib.import_module('record_validation')
    OracleError = importlib.import_module('snapshots').OracleError
    _test_modules = {name: sys.modules[name] for name in _names if name in sys.modules}
finally:
    sys.path[:] = _saved_path
    sys.dont_write_bytecode = _saved_bytecode
    for _name, _module in _saved_modules.items():
        if _module is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _module


def identity(sources):
    return {'commit': 'a' * 40, 'tree': 'b' * 40, 'sources': sources,
        'image': protocol.IMAGE, 'platform': 'linux/amd64', 'actual_version': None,
        'locale': 'ru_RU.UTF-8', 'timezone': 'Etc/UTC'}


def writable(root):
    for path in (root, *root.rglob('*')):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)


class RouteCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: writable(self.root))
        patch = mock.patch.dict(sys.modules, _test_modules)
        patch.start(); self.addCleanup(patch.stop)

    def reject(self, action):
        with self.assertRaises(OracleError) as caught:
            action()
        self.assertEqual(caught.exception.kind, 'invalid_input')


class InputRouteTests(RouteCase):
    def setUp(self):
        super().setUp()
        self.repo = self.root / 'synthetic-repository'; self.repo.mkdir()
        # All files are placeholders: new policy/reader implementation is not
        # required to test the exact source manifest and bounded staging route.
        for relative in inputs.ROW_SOURCE_FILES:
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# synthetic input: ' + relative + '\n', encoding='ascii')

    def stage(self, index):
        options = MODES[index]
        value = identity(inputs.source_hashes(self.repo, **options))
        target = self.root / ('stage-' + str(index))
        inputs.stage_inputs(self.repo, target, NONCE, value, **options)
        return target, value

    def test_exact_distinct_inventories(self):
        self.assertEqual(tuple(map(len, (inputs.LEGACY_V3_SOURCE_FILES,
            inputs.SOURCE_FILES, inputs.RECORD_SOURCE_FILES, inputs.ROW_SOURCE_FILES))), (18, 20, 21, 23))
        self.assertEqual(inputs.ROW_SOURCE_FILES, {**inputs.RECORD_SOURCE_FILES,
            'yadinassi/storage/filedb_records.py': 'filedb_records.py',
            'scripts/native_1c_db_oracle/record_validation.py': 'record_validation.py'})
        self.assertEqual(inputs.ROW_LANE, 'owned_record_readback_v1')
        for options, inventory in zip(MODES, (inputs.SOURCE_FILES, inputs.RECORD_SOURCE_FILES, inputs.ROW_SOURCE_FILES)):
            self.assertIs(inputs.inventory(**options), inventory)

    def test_three_invocations_are_closed_and_all_cross_lane_reads_reject(self):
        for index, options in enumerate(MODES):
            with self.subTest(mode=index):
                target, value = self.stage(index)
                self.assertEqual(inputs.verify_inputs(target, NONCE, **options), value)
                invocation = json.loads((target / 'invocation.json').read_text(encoding='ascii'))
                expected = {'schema': index + 1, 'nonce': NONCE, 'provenance': value}
                if index: expected['lane'] = inputs.RECORD_LANE if index == 1 else inputs.ROW_LANE
                self.assertEqual(invocation, expected)
                self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()},
                    set(inputs.inventory(**options).values()) | {'invocation.json'})
                for other, alternate in enumerate(MODES):
                    if other == index: continue
                    with self.assertRaises(OracleError): inputs.verify_inputs(target, NONCE, **alternate)
                    with self.assertRaises(OracleError): inputs.staged_hashes(target, **alternate)

    def test_ambiguous_or_nonboolean_selection_rejects_before_read_or_write(self):
        for options in ({'record_metadata': True, 'record_reader': True},
                        {'record_reader': 1}, {'record_reader': None}, {'record_metadata': 1}):
            with self.subTest(options=options), mock.patch.object(inputs, 'read_source') as read:
                destination = self.root / 'must-not-exist'
                self.reject(lambda: inputs.inventory(**options))
                self.reject(lambda: inputs.source_hashes(self.repo, **options))
                self.reject(lambda: inputs.staged_hashes(self.repo, **options))
                self.reject(lambda: inputs.stage_inputs(self.repo, destination, NONCE, {}, **options))
                self.reject(lambda: inputs.verify_inputs(self.repo, NONCE, **options))
                self.assertFalse(destination.exists()); read.assert_not_called()

    def test_row_invocation_schema_lane_nonce_and_extra_fields_are_exact(self):
        target, _ = self.stage(2); writable(target)
        original = (target / 'invocation.json').read_bytes()
        edits = (lambda v: v.pop('lane'), lambda v: v.update(lane=inputs.RECORD_LANE),
                 lambda v: v.update(schema=2), lambda v: v.update(schema=True),
                 lambda v: v.update(nonce='b' * 32), lambda v: v.update(extra='private'))
        for edit in edits:
            value = json.loads(original); edit(value)
            (target / 'invocation.json').write_text(json.dumps(value), encoding='ascii')
            with self.assertRaises(OracleError): inputs.verify_inputs(target, NONCE, record_reader=True)

    def test_row_modules_are_hash_bound_and_unexpected_files_reject(self):
        target, _ = self.stage(2); writable(target)
        for name in ('filedb_records.py', 'record_validation.py'):
            path = target / name; original = path.read_bytes()
            path.write_bytes(original + b'# changed\n')
            with self.assertRaises(OracleError): inputs.verify_inputs(target, NONCE, record_reader=True)
            path.write_bytes(original)
            path.unlink()
            with self.assertRaises(OracleError): inputs.staged_hashes(target, record_reader=True)
            path.write_bytes(original)
        (target / 'unexpected.py').write_bytes(b'# unreviewed\n')
        self.reject(lambda: inputs.staged_hashes(target, record_reader=True))

    def test_container_changes_only_staging_path_and_explicit_flag(self):
        targets = [self.stage(index)[0] for index in range(3)]
        commands = [host.container_command(target, 'onec-db-oracle-' + NONCE, NONCE, **options)
                    for target, options in zip(targets, MODES)]
        for index in (1, 2):
            expected = [part.replace(str(targets[0]), str(targets[index])) for part in commands[0]] + FLAGS[index]
            self.assertEqual(commands[index], expected)
        self.assertEqual(commands[2][commands[2].index('--network') + 1], 'none')
        self.assertEqual(commands[2][commands[2].index('--log-driver') + 1], 'none')
        self.reject(lambda: host.container_command(targets[2], 'onec-db-oracle-' + NONCE,
            NONCE, record_metadata=True, record_reader=True))


class HostRouteTests(RouteCase):
    def test_row_staged_runtime_initializes_isolated_with_one_catalog_identity(self):
        value = identity(inputs.source_hashes(ROOT, record_reader=True))
        target = self.root / 'row-runtime'
        inputs.stage_inputs(ROOT, target, NONCE, value, record_reader=True)
        code = """
import sys
from pathlib import Path
import sysconfig
import importlib.machinery
stdlib = Path(sysconfig.get_path('stdlib')).resolve()
extension_root = (Path(sys.base_prefix) / 'DLLs').resolve() if sys.platform == 'win32' else None
""" + inspect.getsource(allowed_module_origin) + """
staged = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(staged))
import inputs, run, filedb_catalog, record_validation
provenance = inputs.verify_inputs(staged, 'a' * 32, record_reader=True)
native = run.Native('a' * 32, provenance, record_reader=True)
assert native.record_policy is record_validation
assert native.record_module is sys.modules['_owned_record_storage.filedb_records']
assert sys.modules['_owned_record_storage.filedb_catalog'] is filedb_catalog
for name in ('CatalogReader', 'CatalogLimits', 'PhysicalTable', 'UnsupportedLayout', 'InvalidStructure'):
    assert getattr(native.record_module, name) is getattr(filedb_catalog, name), name
assert Path(native.record_module.__file__).resolve() == staged / 'filedb_records.py'
assert 'enterprise_audit_record_metadata' in native.command_stages()
assert not any(name == 'yadinassi' or name.startswith('yadinassi.') or 'interpreter' in name.lower()
               for name in sys.modules)
for name, module in tuple(sys.modules.items()):
    location = getattr(module, '__file__', None)
    if not location or location.startswith('<'):
        continue
    location = Path(location).resolve()
    assert allowed_module_origin(name, location, module, staged=staged, stdlib=stdlib,
                                 extension_root=extension_root), (name, location)
"""
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(target)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertEqual(result.stdout, b'')

    def test_interpreter_extension_exception_is_exact_and_not_a_search_root(self):
        base=self.root/'interpreter'; extension_root=base/'DLLs'
        staged=self.root/'staged'; stdlib=base/'Lib'
        name='_hashlib'; suffix=importlib.machinery.EXTENSION_SUFFIXES[0]
        def module(path, *, kind=importlib.machinery.ExtensionFileLoader):
            loader=kind(name,str(path))
            return SimpleNamespace(__loader__=loader,
                __spec__=importlib.machinery.ModuleSpec(name,loader,origin=str(path)))
        def allowed(path, value, root=extension_root):
            return allowed_module_origin(name,path,value,staged=staged,stdlib=stdlib,extension_root=root)
        path=extension_root/(name+suffix)
        self.assertTrue(allowed(path,module(path)))
        self.assertFalse(allowed(path,module(path),None))  # No non-Windows exception.
        for other in (self.root/'DLLs',base,extension_root/'nested',
                      extension_root/'site-packages',extension_root/'DIST-Packages',
                      stdlib/'Site-Packages',staged/'dist-packages'):
            wrong=other/path.name
            self.assertFalse(allowed(wrong,module(wrong)),str(wrong))
        for filename in (name+'.py',name+'.pyc',name+'.dll','unrelated'+suffix):
            wrong=extension_root/filename
            self.assertFalse(allowed(wrong,module(wrong)),filename)
        class Forged(importlib.machinery.ExtensionFileLoader): pass
        for kind in (importlib.machinery.SourceFileLoader,Forged):
            self.assertFalse(allowed(path,module(path,kind=kind)))
        edits=(lambda m:setattr(m,'__loader__',None),
               lambda m:setattr(m.__spec__,'loader',None),
               lambda m:setattr(m.__spec__,'name','wrong'),
               lambda m:setattr(m.__loader__,'name','wrong'),
               lambda m:setattr(m.__loader__,'path',str(base/path.name)),
               lambda m:setattr(m.__spec__,'origin',str(base/path.name)))
        for edit in edits:
            value=module(path);edit(value)
            self.assertFalse(allowed(path,value))
        foreign='not_a_standard_library_module'
        wrong=extension_root/(foreign+suffix)
        loader=importlib.machinery.ExtensionFileLoader(foreign,str(wrong))
        value=SimpleNamespace(__loader__=loader,
            __spec__=importlib.machinery.ModuleSpec(foreign,loader,origin=str(wrong)))
        self.assertFalse(allowed_module_origin(foreign,wrong,value,staged=staged,
            stdlib=stdlib,extension_root=extension_root))

    def test_older_staged_runtimes_import_without_row_modules_or_interpreter(self):
        for index, options in enumerate(MODES[:2]):
            value = identity(inputs.source_hashes(ROOT, **options))
            target = self.root / ('older-runtime-' + str(index))
            inputs.stage_inputs(ROOT, target, NONCE, value, **options)
            code = ("import sys;sys.path.insert(0,sys.argv[1]);"
                    "sys.modules['record_validation']=None;sys.modules['filedb_records']=None;"
                    "import run;observed=sys.argv[2]=='1';"
                    "n=run.Native('a'*32,{},record_metadata=observed);"
                    "assert (n.observation is not None)==observed;"
                    "assert ('enterprise_audit_record_metadata' in n.command_stages())==observed;"
                    "assert 'yadinassi' not in sys.modules")
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(target), str(index)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            self.assertEqual(result.stdout, b'')

    def test_cli_explicitly_selects_each_lane_and_rejects_combined_flags(self):
        for options, flags in zip(MODES, FLAGS):
            with self.subTest(options=options), mock.patch.object(host, 'ROOT', self.root), \
                 mock.patch.object(host, 'run_oracle', return_value={'accepted': False}) as run, \
                 mock.patch.object(host, 'export_report') as export, \
                 mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(host.main(APPROVED + flags), 1)
                self.assertEqual(run.call_args.kwargs, options); export.assert_called_once()
        for flags in (FLAGS[1] + FLAGS[2], FLAGS[2] + FLAGS[1], ['--record-reader']):
            with mock.patch.object(host, 'run_oracle') as run, mock.patch.object(host, 'export_report') as export, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught: host.main(APPROVED + flags)
                self.assertEqual(caught.exception.code, 2)
                run.assert_not_called(); export.assert_not_called()

    def test_ambiguous_host_selection_precedes_external_calls_and_credentials(self):
        with mock.patch.object(host.smoke.FULL, 'repository_provenance') as repository, \
             mock.patch.dict(os.environ, {'GHCR_TOKEN': 'synthetic-token', 'GHCR_USER': 'Atridis'}, clear=True):
            for options in ({'record_reader': True, 'record_metadata': True}, {'record_reader': 1}):
                self.reject(lambda: host.provenance(**options))
                self.reject(lambda: host.run_oracle(self.root, **options))
            self.assertEqual(os.environ['GHCR_TOKEN'], 'synthetic-token')
            repository.assert_not_called()

    def invoke_row(self, *, container_bad=False, source_changed=False):
        value = identity({name: 'c' * 64 for name in inputs.ROW_SOURCE_FILES})
        report = protocol.empty_report(NONCE, copy.deepcopy(value))
        report.update(schema=6, lane=inputs.ROW_LANE, status='ok', failed_stage=None,
            failure_kind='none', record_readback={'schema': 7, 'synthetic': True})
        report['cleanup'].update(native_processes_stopped=True, raw_files_removed=True)
        calls = []

        def make_report(nonce, provenance):
            result = protocol.empty_report(nonce, provenance)
            result.update(schema=6, lane=inputs.ROW_LANE, record_readback=None)
            return result

        def validate(raw, **kwargs):
            self.assertEqual(kwargs['nonce'], NONCE)
            self.assertEqual(kwargs['provenance'], value)
            return protocol.decode(raw)

        def discard(result, *, final=False):
            self.assertTrue(final)
            result['record_readback'] = None

        policy = SimpleNamespace(empty_report=mock.Mock(side_effect=make_report),
            validate_report=mock.Mock(side_effect=validate), discard_capture=mock.Mock(side_effect=discard))

        def provenance(**options):
            self.assertEqual(options, {'record_reader': True})
            self.assertNotIn('GHCR_TOKEN', os.environ); self.assertNotIn('GHCR_USER', os.environ)
            calls.append('provenance')
            result = copy.deepcopy(value)
            if source_changed and calls.count('provenance') > 1: result['tree'] = 'd' * 40
            return result

        def bounded(args, *_args):
            calls.append(args[1])
            if args[1] == 'image': return 0, b'linux/amd64|0'
            if args[1] == 'ps': return 0, b'still-live' if container_bad else b''
            self.assertEqual(args, ['docker', 'run', '--record-reader-validation'])
            return 0, protocol.encode(report)

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(sys.modules, {'record_validation': policy}))
            stack.enter_context(mock.patch.dict(os.environ, {'GHCR_TOKEN': 'synthetic-token', 'GHCR_USER': 'Atridis'}, clear=True))
            stack.enter_context(mock.patch.object(host.uuid, 'uuid4', return_value=SimpleNamespace(hex=NONCE)))
            stack.enter_context(mock.patch.object(host, 'provenance', side_effect=provenance))
            stage = stack.enter_context(mock.patch.object(host, 'stage_inputs'))
            command = stack.enter_context(mock.patch.object(host, 'container_command', return_value=['docker', 'run', '--record-reader-validation']))
            stack.enter_context(mock.patch.object(host.smoke, 'run_silent'))
            stack.enter_context(mock.patch.object(host.smoke, 'bounded_run', side_effect=bounded))
            popen = stack.enter_context(mock.patch.object(host.smoke.subprocess, 'Popen', side_effect=AssertionError('native process forbidden')))
            old_validate = stack.enter_context(mock.patch.object(host, 'validate_report', side_effect=AssertionError('old validator selected')))
            old_discard = stack.enter_context(mock.patch.object(host, 'discard_capture', side_effect=AssertionError('old discard selected')))
            result = host.run_oracle(self.root, record_reader=True)
            self.assertEqual(stage.call_args.kwargs, {'record_reader': True})
            self.assertEqual(command.call_args.kwargs, {'record_reader': True})
            popen.assert_not_called(); old_validate.assert_not_called(); old_discard.assert_not_called()
        self.assertEqual(policy.empty_report.call_count, 1)
        self.assertEqual(policy.validate_report.call_count, 2)
        self.assertEqual(policy.validate_report.call_args.kwargs['final'], True)
        self.assertEqual(list(self.root.iterdir()), [])
        return result, policy

    def test_row_host_selects_only_row_policy(self):
        result, policy = self.invoke_row()
        self.assertTrue(result['accepted']); self.assertTrue(all(result['cleanup'].values()))
        self.assertEqual(result['record_readback']['schema'], 7)
        policy.discard_capture.assert_not_called()

    def test_row_host_late_failures_discard_using_row_policy(self):
        for options in ({'container_bad': True}, {'source_changed': True}):
            with self.subTest(options=options):
                result, policy = self.invoke_row(**options)
                self.assertFalse(result['accepted']); self.assertIsNone(result['record_readback'])
                policy.discard_capture.assert_called_once_with(result, final=True)
                self.assertEqual(result['artifacts'], [])


class RealPolicyHostCleanupTests(RouteCase):
    def invoke(self, *, container_bad=False, staging_bad=False, source_changed=False):
        value = identity({name: 'c' * 64 for name in inputs.ROW_SOURCE_FILES})
        report = record_policy.empty_report(NONCE, copy.deepcopy(value))
        report['provenance']['actual_version'] = protocol.VERSION
        report.update(failed_stage='baseline', failure_kind=record_policy.FAILURE_KIND,
            record_validation='failed', record_readback={'schema': 7, 'status': 'failed',
                'category': 'unsupported_layout', 'code': 'format_string_zero'})
        for stage in report['stages'][:2]:
            stage.update(status='ok', checks={key: True for key in stage['checks']})
        report['stages'][2]['status'] = 'failed'
        report['cleanup'].update(native_processes_stopped=True, raw_files_removed=True)
        report['stages'][-1].update(status='ok', checks={key: True for key in protocol.CHECKS['cleanup']})
        # The real policy admits this finite failure before any mocked transport.
        record_policy.validate_report(protocol.encode(report), nonce=NONCE, provenance=value)
        provenance_calls = []

        def provenance(**options):
            self.assertEqual(options, {'record_reader': True})
            self.assertNotIn('GHCR_TOKEN', os.environ); self.assertNotIn('GHCR_USER', os.environ)
            provenance_calls.append(options)
            result = copy.deepcopy(value)
            if source_changed and len(provenance_calls) > 1: result['tree'] = 'd' * 40
            return result

        def bounded(args, *_args):
            if args[1] == 'image': return 0, b'linux/amd64|0'
            if args[1] == 'ps': return 0, b'still-live' if container_bad else b''
            self.assertEqual(args, ['docker', 'run', '--record-reader-validation'])
            return 1, protocol.encode(report)

        class LeftoverDirectory:
            def __init__(self, **options): self.name = tempfile.mkdtemp(**options)
            def __enter__(self): return self.name
            def __exit__(self, *args): return False

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {'GHCR_TOKEN': 'synthetic-token', 'GHCR_USER': 'Atridis'}, clear=True))
            stack.enter_context(mock.patch.object(host.uuid, 'uuid4', return_value=SimpleNamespace(hex=NONCE)))
            stack.enter_context(mock.patch.object(host, 'provenance', side_effect=provenance))
            stack.enter_context(mock.patch.object(host, 'stage_inputs'))
            stack.enter_context(mock.patch.object(host, 'container_command', return_value=['docker', 'run', '--record-reader-validation']))
            stack.enter_context(mock.patch.object(host.smoke, 'run_silent'))
            stack.enter_context(mock.patch.object(host.smoke, 'bounded_run', side_effect=bounded))
            processes = stack.enter_context(mock.patch.object(host.smoke.subprocess, 'Popen', side_effect=AssertionError('native process forbidden')))
            validate = stack.enter_context(mock.patch.object(record_policy, 'validate_report', wraps=record_policy.validate_report))
            discard = stack.enter_context(mock.patch.object(record_policy, 'discard_capture', wraps=record_policy.discard_capture))
            if staging_bad: stack.enter_context(mock.patch.object(host.tempfile, 'TemporaryDirectory', LeftoverDirectory))
            result = host.run_oracle(self.root, record_reader=True)
            processes.assert_not_called()
            self.assertEqual(validate.call_count, 2)
            self.assertIs(validate.call_args.kwargs['final'], True)
            if container_bad or staging_bad or source_changed:
                discard.assert_called_once_with(result, final=True)
            else:
                discard.assert_not_called()
        record_policy.validate_report(protocol.encode(result), nonce=NONCE, provenance=value, final=True)
        self.assertFalse(result['accepted']); self.assertEqual(result['artifacts'], [])
        return result

    def test_finite_row_failure_survives_only_verified_final_cleanup(self):
        result = self.invoke()
        self.assertTrue(all(result['cleanup'].values()))
        self.assertEqual(result['record_readback'], {'schema': 7, 'status': 'failed',
            'category': 'unsupported_layout', 'code': 'format_string_zero'})
        self.assertEqual(result['failure_kind'], record_policy.FAILURE_KIND)
        self.assertEqual(result['failed_stage'], 'baseline')

    def test_each_unverified_host_cleanup_gate_discards_real_finite_failure(self):
        for options in ({'container_bad': True}, {'staging_bad': True}):
            with self.subTest(options=options):
                result = self.invoke(**options)
                self.assertIsNone(result['record_readback'])
                self.assertEqual(result['failure_kind'], record_policy.FAILURE_KIND)
                self.assertEqual(result['failed_stage'], 'baseline')
                self.assertEqual(result['stages'][-1]['status'], 'failed')
                writable(self.root)
                for path in self.root.iterdir(): shutil.rmtree(path)

    def test_changed_source_discards_real_finite_failure(self):
        result = self.invoke(source_changed=True)
        self.assertIsNone(result['record_readback'])
        self.assertEqual(result['failure_kind'], 'provenance_mismatch')
        self.assertEqual(result['failed_stage'], 'cleanup')


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'requires POSIX bash, never native 1C')
class ProbeRouteTests(RouteCase):
    def setUp(self):
        super().setUp()
        stub = self.root / 'python3'
        stub.write_text('#!' + sys.executable + '\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n', encoding='utf-8')
        stub.chmod(0o755)

    def probe(self, args):
        return subprocess.run([shutil.which('bash'), str(HELPERS / 'probe.sh'), *args],
            env={'PATH': str(self.root) + os.pathsep + os.defpath},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)

    def test_probe_forwards_only_the_explicit_whitelisted_lane(self):
        for flags in FLAGS:
            result = self.probe(['--invocation-nonce', NONCE] + flags)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ['-B', '/oracle/run.py', '--invocation-nonce', NONCE] + flags)

    def test_probe_rejects_combined_unknown_missing_and_malformed_inputs(self):
        for args in ([], ['--invocation-nonce'], ['--invocation-nonce', NONCE, '--unknown'],
                     ['--invocation-nonce', NONCE] + FLAGS[1] + FLAGS[2],
                     ['--invocation-nonce', NONCE, '--record-reader'],
                     ['--invocation-nonce', NONCE.upper()] + FLAGS[2],
                     ['--other', NONCE] + FLAGS[2]):
            with self.subTest(args=args):
                result = self.probe(args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b''); self.assertEqual(result.stderr, b'')


if __name__ == '__main__':
    unittest.main()
