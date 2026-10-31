"""Executable structural majorants for tree-v1; never native evidence.

All optional fields and independent scalar maxima are retained simultaneously.
This intentionally includes unreachable combinations and is an upper bound, not
an accepted synthetic native report. No infobase, Docker, or shared fixture runs.
"""
import ast
import base64
import copy
import contextlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_bootstrap'))
sys.path.insert(0, str(ROOT / 'scripts'))
import full_suite as suite
import tree_suite as tree
spec = importlib.util.spec_from_file_location('tree_budget_host', ROOT / 'scripts/native_1c_tree_profile.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
full = host.FULL
smoke = host.sibling('native_1c_smoke')
d = smoke.DIAGNOSTICS
H = 'f' * 64
NONCE = 'f' * 32
STAGE_KEYS = {'schema', 'profile', 'nonce', 'status', 'failure_kind', 'failed_case',
              'input_sha256', 'cases', 'client_tree', 'observation_diagnostic'}
CLIENT_KEYS = {'status', 'failure_kind', 'process_diagnostics', 'source_sha256',
               'module_sha256', 'roundtrip_sha256', 'entered', 'completed',
               'process_exited', 'quiet', 'witness_verified', 'output_sha256',
               'output_size', 'message_count'}


@contextlib.contextmanager
def synthetic_inventory_reader():
    # This module loads its own host.FULL; patch that exact instance, not the
    # separately loaded alias in test_native_1c_full_host. Windows static-fixture
    # evidence is synthetic; production descriptor/no-follow guards are unchanged.
    from test_native_1c_full_host import read_synthetic_file
    if os.name == 'nt':
        with mock.patch.object(full, 'read_regular', side_effect=read_synthetic_file):
            yield
    else:
        yield


@contextlib.contextmanager
def synthetic_capture_reader():
    # Windows synthetic transport bytes are not Linux descriptor-race evidence.
    from test_native_1c_full_stage import portable_fixture_bytes
    if os.name == 'nt':
        with mock.patch.object(tree.full, 'secure_bytes', new=portable_fixture_bytes):
            yield
    else:
        yield


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def longest(values):
    return max(values, key=lambda v: len(wire(v)))


def diagnostic_majorant():
    # 64 tokens total: head-only costs one comma more than the 32/32 split.
    value = dict(category=longest(d.CATEGORIES), origin=longest(d.ORIGINS),
        module=longest(d.SOURCE_LINE_LIMITS), line=max(d.SOURCE_LINE_LIMITS.values()),
        identifier=longest(d.IDENTIFIERS), native_exit_code=None,
        source_frames=[dict(module=longest(d.SOURCE_LINE_LIMITS),
                            line=max(d.SOURCE_LINE_LIMITS.values()))] * d.MAX_SOURCE_FRAMES,
        source_frames_truncated=False, session_marker=longest(d.MARKER_STATES),
        managed_marker=longest(d.MARKER_STATES),
        rendered_context=dict(origin=longest(('session_marker', 'managed_marker')),
            representation='detailed_error_text', head=[longest(d.CONTEXT_TOKENS)] * d.MAX_CONTEXT_TOKENS,
            tail=[], omitted_middle=False))
    assert set(value) == set(d.empty_diagnostics())
    assert set(value['rendered_context']) == set(d.empty_rendered_context())
    return value


def stage_majorant():
    stage = tree.empty_report(NONCE)
    assert set(stage) == STAGE_KEYS and set(stage['client_tree']) == CLIENT_KEYS
    stage.update(status='not_started', failure_kind=longest(full.FAILURES | suite.FAILURE_KINDS | {'unsupported_observation'}),
                 failed_case=tree.CASE, input_sha256=dict.fromkeys(tree.INPUT_FILES, H),
                 observation_diagnostic=dict(site='server', case=None,
                     category=longest(tree.DIAGNOSTIC_CATEGORIES), calibration=None))
    # Null is four bytes, longer than ordinal32 (two) or quoted one-char (three).
    case = stage['cases'][0]
    case.update(status='not_started', source_sha256=H, module_sha256=H,
                output_sha256=H, output_size=8192, message_count=None)
    assert set(case) == full.CASE_KEYS
    client = stage['client_tree']
    client.update(status='not_started', failure_kind=longest(full.FAILURES | suite.FAILURE_KINDS | {'unsupported_observation'}),
                  **dict.fromkeys(full.CLIENT_HASHES, H), **dict.fromkeys(full.CLIENT_FLAGS, False),
                  output_sha256=H, output_size=8192, message_count=None)
    client['process_diagnostics'] = dict(stage='before_probe', reason='unexpected_processes',
        unexpected_count=256, zombie_count=256,
        classes=dict.fromkeys(('native', 'display', 'session_bus', 'shell', 'python', 'other', 'unreadable'), 256))
    # Deliberately charge seven three-digit counters, ignoring their sum<=256.
    # Optional inherited marker diagnostic is retained even when tree never emits it.
    client['marker_diagnostics'] = dict(phase='completed', kind='runtime_error', ordinal=141, error_stage=11)
    return stage


def native_majorant():
    stage2 = dict(schema=1, status='failed', failed_stage=longest(smoke.STAGES),
        failure_kind=longest(smoke.FAILURE_KINDS), actual_version='9999.9999.9999.9999',
        version_source='SystemInfo.AppVersion', simple_output_sha256=H,
        security_change_attempted=False, security_settings_state='not_attempted',
        diagnostics=diagnostic_majorant(), protection_observation=dict(stage='bootstrap',
            property_type=longest(d.PROTECTION_TYPES), warning_type=longest(d.PROTECTION_TYPES)),
        **dict.fromkeys(smoke.STAGE_FLAGS, False))
    fmt = dict(root='MetaDataObject', kind='Configuration', namespace='http://v8.1c.ru/8.3/MDClasses',
        schema_version='99.999.999.999', element_count=4096, sha256=H,
        known_elements=[longest(smoke.KNOWN_ELEMENTS)] * len(smoke.KNOWN_ELEMENTS),
        managed_application_module_present=False, session_module_present=False)
    # The reader permits repeated known elements; reserve all longest names.
    result = dict(schema=1, status=longest(smoke.STATUS | {'stage3_failed'}),
        python_version='99.99.999', runtime_version='9999.9999.9999.9999',
        runtime_version_source='SystemInfo.AppVersion', configuration_format=fmt,
        **dict.fromkeys(smoke.BOOL_KEYS, False), stage2=stage2, stage3=stage_majorant())
    return result


def host_majorant():
    # Runtime source digests have fixed width; reserve the admitted512 inventory
    # count rather than today's74, so a legitimate76-source follow-up fits too.
    interpreter = dict(python_version='99.99.999', dependencies=full.DEPENDENCIES.copy(),
        source_file_count=512, source_sha256=H, comparison_driver_sha256=H, map_contract_sha256=H)
    provenance = dict(commit='f'*40, tree='f'*40, github_run_id='9'*20, github_run_attempt='9'*20)
    identity_paths = ('scripts/native_1c_tree_profile.py', 'scripts/native_1c_tree_fill_contract.py',
                      'scripts/native_1c_tree_copy_contract.py', 'scripts/native_1c_tree_copy_diagnostics.py', 'scripts/native_1c_tree_access_probe.py',
                      'scripts/native_1c_tree_profiles.py', 'scripts/native_1c_smoke.py', 'scripts/native_1c_full_host.py')
    return dict(schema='native-1c-tree-host-v1', profile=tree.PROFILE, nonce=NONCE,
        image=smoke.IMAGE, platform='linux/amd64', configured_timezone='Etc/UTC',
        repository=provenance, interpreter=interpreter,
        host_source_sha256=dict.fromkeys(identity_paths, H),
        trusted_input_sha256=dict.fromkeys(tree.INPUT_FILES, H), native_report=native_majorant(),
        comparison=dict(schema='native-1c-tree-comparison-v1', profile=tree.PROFILE,
            status='invalid_interpreter_output', acceptance_status='rejected', native_sha256=H,
            native_size=8192, interpreter_sha256=H, interpreter_size=full.MAX_FILE),
        container_cleanup_verified=False, native_measurement_accepted=False,
        runtime_parity_accepted=False, private_payloads_removed=False)


def bounds():
    stage = stage_majorant(); native = native_majorant(); value = host_majorant()
    provenance = wire(value) + b'\n'
    value['native_artifact_sha256'] = dict.fromkeys((tree.CASE+'.out', 'provenance.json'), H)
    envelope = dict(schema=tree.WIRE_SCHEMA, profile=tree.PROFILE, nonce=NONCE,
        report=native, outputs=[dict(name=tree.CASE+'.out', size=8192, sha256=H,
        data_b64=base64.b64encode(b'x'*8192).decode())])
    failure = dict(schema='native-1c-tree-host-v1', profile=tree.PROFILE, status='failed',
        native_measurement_accepted=False, runtime_parity_accepted=False,
        observation_diagnostic=stage['observation_diagnostic'],
        envelope_phase=longest(host.ENVELOPE_PHASES),
        prerequisite_failure=dict(stage=longest(host.PREREQUISITE_STAGES),reason=longest(host.PREREQUISITE_REASONS)),
        failure_diagnostic=dict(stage=longest(host.FAILURE_STAGES+('unknown',)),
                                reason=longest(host.FAILURE_REASONS+('unexpected_failure',))),
        native_failure=dict(stage='tree',reason=longest(full.FAILURES|{'unsupported_observation'}),
                            case=host.CASE,process_stage='before_probe',process_reason='unexpected_processes'))
    return dict(stage=len(wire(stage)), native_report=len(wire(native)),
        transport=len(wire(envelope))+1, host_report=len(wire(value))+1,
        artifact_provenance=len(provenance), artifact_total=len(provenance)+8192,
        failure_report=len(wire(failure))+1)


def assignment_dict_keys(path, function, variable):
    """Close proof coverage over literal production builders, not size samples."""
    parsed=ast.parse(path.read_text(encoding='utf-8'))
    node=next(n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name==function)
    candidates=[n.value for n in ast.walk(node) if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id==variable for t in n.targets)
                and isinstance(n.value,ast.Dict)]
    assert len(candidates)==1
    value=candidates[0]
    assert all(isinstance(k,ast.Constant) and type(k.value) is str for k in value.keys)
    return {k.value for k in value.keys}


class TreeBudgetTests(unittest.TestCase):
    def test_all_structural_majorants_fit_unchanged_caps(self):
        value = bounds()
        self.assertEqual((tree.MAX_OUTPUT, tree.MAX_TRANSPORT, suite.MAX_STAGE_REPORT,
                          full.MAX_REPORT, smoke.MAX_OUTPUT), (8192,65536,8192,32768,32768))
        for key, cap in (('stage',8192),('native_report',32768),('transport',65536),
                         ('host_report',32768),('artifact_provenance',32768),('failure_report',32768)):
            with self.subTest(key=key): self.assertLessEqual(value[key],cap)
        self.assertEqual(tree.INPUT_FILES, host.staged_files(smoke))
        self.assertEqual(len(tree.INPUT_FILES),22)
        self.assertEqual(len(base64.b64encode(b'x'*8192)),4*((8192+2)//3))

    def test_diagnostic_finite_domains_and_escaping_are_accounted(self):
        self.assertEqual(set(diagnostic_majorant()),set(d.empty_diagnostics()))
        for value in d.IDENTIFIERS:
            self.assertLessEqual(len(wire(value)),len(wire(diagnostic_majorant()['identifier'])))
        for value in tree.DIAGNOSTIC_CATEGORIES:
            self.assertLessEqual(len(wire(value)),len(wire(stage_majorant()['observation_diagnostic']['category'])))
        # Independently upper-bound both admissible context layouts, including
        # the extra comma of64head values versus32head+32tail values.
        template=diagnostic_majorant()['rendered_context']
        split=copy.deepcopy(template);split.update(head=template['head'][:32],tail=template['head'][32:],omitted_middle=True)
        self.assertGreaterEqual(len(wire(template)),len(wire(split)))
        self.assertEqual(len(wire(template['head'])),1+64*len(wire(longest(d.CONTEXT_TOKENS)))+64)

    def test_production_stage_writer_keeps_complete_majorant(self):
        value=stage_majorant()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'stage.json';tree.write_report(path,value)
            self.assertEqual(path.read_bytes(),wire(value))

    def test_production_host_cli_keeps_optional_artifact_hashes_and_newline(self):
        value=host_majorant();value['native_artifact_sha256']=dict.fromkeys((tree.CASE+'.out','provenance.json'),H)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(host,'ROOT',Path(directory)),mock.patch.object(host,'run',return_value=value),\
                 mock.patch.object(sys,'argv',['tree','--execute-approved-image']),mock.patch.dict('os.environ',{},clear=True):
                self.assertEqual(host.main(),1)
            self.assertEqual((Path(directory)/'native-smoke/tree-report.json').read_bytes(),wire(value)+b'\n')

    def test_production_failure_serializer_is_finite_and_bounded(self):
        error=host.TreeError(longest(host.FAILURE_REASONS))
        error.envelope_phase=longest(host.ENVELOPE_PHASES)
        error.prerequisite_failure=dict(stage=longest(host.PREREQUISITE_STAGES),reason=longest(host.PREREQUISITE_REASONS))
        error.observation_diagnostic=dict(site='server',case=32,category='payload_contract',calibration=None)
        error.native_failure=dict(stage='tree',reason=longest(full.FAILURES|{'unsupported_observation'}),
                                  case=host.CASE,process_stage='before_probe',process_reason='unexpected_processes')
        def fail(*args,**kwargs):
            kwargs['failure_state']['stage']=longest(host.FAILURE_STAGES)
            raise error
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(host,'ROOT',Path(directory)),mock.patch.object(host,'run',side_effect=fail),\
                 mock.patch.object(sys,'argv',['tree','--execute-approved-image']),mock.patch.dict('os.environ',{},clear=True):
                self.assertEqual(host.main(),1)
            raw=(Path(directory)/'native-smoke/tree-report.json').read_bytes()
            self.assertLessEqual(len(raw),bounds()['failure_report'])
            value=json.loads(raw)
            self.assertFalse(value['native_measurement_accepted'])
            self.assertFalse(value['runtime_parity_accepted'])
            self.assertEqual(value['native_failure'],error.native_failure)
            self.assertEqual(value['observation_diagnostic'],error.observation_diagnostic)

    def test_majorant_covers_actual_host_builder_keys(self):
        path=ROOT/'scripts/native_1c_tree_profile.py'
        expected=set(host_majorant())-{'private_payloads_removed'}
        self.assertEqual(assignment_dict_keys(path,'run','result'),expected)
        failure={'schema','profile','status','native_measurement_accepted','runtime_parity_accepted','failure_diagnostic'}
        self.assertEqual(assignment_dict_keys(path,'main','report'),failure)
        self.assertEqual(set(stage_majorant())-set(tree.empty_report(NONCE)),set())

    def test_native_envelope_production_serializer_covers_capture_cap(self):
        # Structural maxima intentionally need not pass semantic acceptance.
        # Observation validation/census are stubbed; Windows also uses the
        # bounded static reader. Production serializer, hash checks, stage
        # shape, cap checks and base64 stay real.
        raw=b'x'*8192
        report=native_majorant();report['status']='ok'
        stage=report.pop('stage3');stage['status']='ok'
        stage['cases'][0].update(status='ok',output_size=len(raw),output_sha256=full.digest(raw))
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory).resolve(strict=True);capture=parent/'capture';capture.mkdir()
            (capture/(tree.CASE+'.out')).write_bytes(raw)
            tree.write_report(parent/'stage3-report.json',stage)
            with synthetic_capture_reader(), mock.patch.object(tree,'validate_observations'),mock.patch.object(tree.full,'final_client_process_census'):
                actual=tree.finish_report(report,NONCE,capture,quiet=True,bus_cleanup_failed=False)
            value=json.loads(actual)
            self.assertEqual(len(value['outputs']),1)
            self.assertEqual(value['outputs'][0]['data_b64'],base64.b64encode(raw).decode())
            self.assertLessEqual(len(actual),bounds()['transport'])
            self.assertTrue(actual.endswith(b'\n'))

    def test_capture_fixture_adapter_survives_descriptor_path_mismatch(self):
        from types import SimpleNamespace
        original_fstat = tree.full.os.fstat
        def mismatch(fd):
            info = original_fstat(fd)
            value = SimpleNamespace(**{name: getattr(info, name) for name in
                ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size',
                 'st_mtime_ns', 'st_ctime_ns')})
            value.st_ctime_ns += 1
            return value
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'output'
            path.write_bytes(b'x')
            with mock.patch.object(tree.full.os, 'fstat', side_effect=mismatch):
                with self.assertRaises(suite.FullError): tree.full.secure_bytes(path, 1)
                with mock.patch.dict(globals(), os=SimpleNamespace(name='nt')):
                    self.test_native_envelope_production_serializer_covers_capture_cap()

    def test_owned_temp_alias_is_canonicalized_without_weakening_reader(self):
        raw=b'x'*8192
        with tempfile.TemporaryDirectory() as directory:
            owned=Path(directory).resolve(strict=True)
            physical=owned/'physical';physical.mkdir()
            alias=owned/'alias'
            try:
                alias.symlink_to(physical,target_is_directory=True)
            except (OSError,NotImplementedError):
                self.skipTest('Creating directory symlinks is unavailable')
            capture=physical/'capture';capture.mkdir()
            (capture/(tree.CASE+'.out')).write_bytes(raw)
            stage=stage_majorant();stage['status']='ok'
            stage['cases'][0].update(status='ok',output_size=len(raw),output_sha256=full.digest(raw))
            tree.write_report(physical/'stage3-report.json',stage)
            # The production no-follow reader still rejects a symlink ancestor.
            with self.assertRaises(suite.FullError):
                suite.secure_bytes(alias/'capture'/(tree.CASE+'.out'),8192)
            for parent,expected in ((alias,False),(alias.resolve(strict=True),True)):
                report=native_majorant();report.pop('stage3');report['status']='ok'
                with synthetic_capture_reader(), mock.patch.object(tree,'validate_observations'),mock.patch.object(tree.full,'final_client_process_census'):
                    result=json.loads(tree.finish_report(report,NONCE,parent/'capture',quiet=True,bus_cleanup_failed=False))
                self.assertEqual(len(result['outputs']),1 if expected else 0)
                if expected:
                    self.assertEqual(result['outputs'][0]['data_b64'],base64.b64encode(raw).decode())
                else:
                    self.assertFalse(result['report']['native_tests_completed'])

    def test_client_marker_guard_budget(self):
        source=(ROOT/tree.SOURCE).read_text(encoding='utf-8').encode()
        template=(ROOT/suite.CLIENT_SOURCE).read_text(encoding='utf-8').encode()
        generated=tree.client_module(source,template).decode('utf-8-sig')
        # Fixed writer forbids line breaks. The exact alphabet contains neither
        # mandatory JSON escapes nor optional slash/HTML escapes. These source
        # guards and serializer calculations are not native behavior evidence.
        for fragment in ('Code >= 48 И Code <= 57', 'Code >= 65 И Code <= 90',
                         'Code >= 97 И Code <= 122', 'Code = 32', 'Code = 45',
                         'Code = 46', 'Code = 58', 'Code = 91', 'Code = 93', 'Code = 95'):
            self.assertIn(fragment,generated)
        expression=re.search(r'Allowed = (.*?);',generated,re.DOTALL)
        self.assertIsNotNone(expression)
        normalized=' '.join(expression[1].split())
        self.assertEqual(normalized, '(Code >= 48 И Code <= 57) Или (Code >= 65 И Code <= 90) '
            'Или (Code >= 97 И Code <= 122) Или Code = 32 Или Code = 45 Или Code = 46 '
            'Или Code = 58 Или Code = 91 Или Code = 93 Или Code = 95')
        self.assertIn('Если Не Allowed Тогда ВызватьИсключение',generated)
        self.assertIn('ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет, \" \", Истина)',generated)
        self.assertIn('TreeLaneCharacters + СтрДлина(Text) > 8158',generated)
        marker=dict(schema=tree.PROFILE,nonce=NONCE,phase='completed',witness='client',
                    values=['x'*(8192-34)]+['']*33)
        # Charge three BOM bytes and one optional space after EVERY JSON comma
        # and colon, even though the configured no-line-break writer is compact.
        encoded=wire(marker)
        upper=len(encoded)+encoded.count(b',')+encoded.count(b':')+3
        self.assertLessEqual(upper,16384)
        self.assertEqual(len(encoded),8373)

    def test_synthetic_inventory_reader_binds_exact_host_module(self):
        import types
        import test_native_1c_full_host as other
        original = full.read_regular
        other_original = other.full.read_regular
        self.assertIs(full, host.FULL)
        self.assertIsNot(full, other.full)
        # Replace only this test module's OS alias; do not change pathlib or
        # the real platform while exercising both conditional branches.
        for platform in ('nt', 'posix'):
            with mock.patch.dict(globals(), os=types.SimpleNamespace(name=platform)):
                with synthetic_inventory_reader():
                    self.assertIs(other.full.read_regular, other_original)
                    if platform == 'nt':
                        self.assertIs(full.read_regular.side_effect, other.read_synthetic_file)
                    else:
                        self.assertIs(full.read_regular, original)
                self.assertIs(full.read_regular, original)

    def test_source_physical_crlf_budget_and_runtime_inventory(self):
        raw=(ROOT/'scripts/native_1c_bootstrap/full_suite.py').read_bytes()
        canonical=raw.replace(b'\r\n',b'\n')
        self.assertLessEqual(len(canonical.replace(b'\n',b'\r\n')),294912)
        with synthetic_inventory_reader(), mock.patch.object(
                full.importlib.metadata,'version',side_effect=full.DEPENDENCIES.__getitem__):
            actual=full.interpreter_provenance(ROOT)
        self.assertLessEqual(len(wire(actual)),len(wire(host_majorant()['interpreter'])))
        self.assertLessEqual(actual['source_file_count'],512)
        self.assertEqual(set(actual),set(host_majorant()['interpreter']))


if __name__=='__main__':
    print(json.dumps(bounds(),sort_keys=True))
    unittest.main()
