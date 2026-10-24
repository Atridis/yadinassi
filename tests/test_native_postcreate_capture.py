"""Offline capture gates only; synthetic native rows never establish 1C semantics."""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import test_native_1c_output_artifact as artifact
import test_native_1c_map_contract as map_fixtures
from test_native_1c_output_artifact import accepted_report, PAYLOAD
from test_native_1c_full_host import full, smoke, SyntheticFilesystemCase
from test_native_postcreate_protocol import (
    host_directive_parser, launcher, unavailable_postcreate_entrypoint,
)

ROOT = Path(__file__).resolve().parents[1]
BEGIN = b'export-phase.post-create: [begin]'
OK = b'export-phase.post-create: [ok]'
ERROR = b'export-phase.post-create: [error;kind=method-missing;named={"B",1}]'


def native_payload(*, ending=b'\n', failure=None):
    """A 156-line framing fixture, not native output or expected runtime values."""
    lines = [b'offline historical row'] * 136 + [BEGIN]
    if failure is None:
        lines += [label.encode('ascii') + b': opaque offline value' for label in full.POST_CREATE_LABELS]
    lines += [OK if failure is None else failure]
    return ending.join(lines) + ending


class PostCreateCaptureTests(SyntheticFilesystemCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.original_source = (ROOT / 'integrational_tests/tests/functions.bsl').read_text(encoding='utf-8')
        cls.failure_source = unavailable_postcreate_entrypoint(cls.original_source)
        with tempfile.TemporaryDirectory() as folder:
            failure_path = Path(folder) / 'missing-entrypoint.bsl'
            failure_path.write_text(cls.failure_source, encoding='utf-8')
            responses = []
            for source in (ROOT / 'integrational_tests/tests/functions.bsl', failure_path):
                result = subprocess.run(
                    [sys.executable, '-I', '-B', '-c', full.EXECUTE_SCRIPT, str(ROOT),
                     str(source), full.LINUX_TARGET],
                    cwd=ROOT, env=full.child_environment(), capture_output=True, timeout=full.CASE_SECONDS,
                    check=False)
                responses.append((result.returncode, result.stdout, result.stderr))
        cls.success_response, cls.actual_response = responses

    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'integrational_tests/tests').mkdir(parents=True)
        self.report = accepted_report()
        self.inputs = self.report['stage3']['input_sha256']
        for name in full.SCENARIOS:
            source = self.root / f'integrational_tests/tests/{name}.bsl'
            source.write_bytes(self.failure_source.encode('utf-8')
                               if name == 'functions' else b'// offline fixture\n')
            self.inputs[f'integrational_tests/tests/{name}.bsl'] = full.digest(source.read_bytes())
        self.report['trusted_input_sha256'] = dict(self.inputs)
        self.payloads = dict.fromkeys(full.ARTIFACT_FILES[:-1], PAYLOAD)
        self.payloads['functions.out'] = native_payload()
        self.capture = full.quarantine_outputs(self.root,
            {name: self.payloads[name + '.out'] for name in full.SCENARIOS})
        for case in self.report['stage3']['cases']:
            name = case['name']
            source = (self.root / f'integrational_tests/tests/{name}.bsl').read_bytes()
            case.update(source_sha256=full.digest(source), module_sha256=full.digest(full.generated_module(source)))
        self.bind_native(self.payloads['functions.out'])

    def bind_native(self, payload):
        self.payloads['functions.out'] = payload
        path = self.capture / 'functions.out'
        path.chmod(0o600)
        path.write_bytes(payload)
        self.report['stage3']['cases'][2].update(output_sha256=full.digest(payload),
            output_size=len(payload), message_count=payload.count(b'\n'))

    def set_source(self, source):
        (self.root / 'integrational_tests/tests/functions.bsl').write_bytes(source)
        key = 'integrational_tests/tests/functions.bsl'
        self.inputs[key] = full.digest(source)
        self.report['trusted_input_sha256'][key] = full.digest(source)
        self.report['stage3']['cases'][2].update(source_sha256=full.digest(source),
            module_sha256=full.digest(full.generated_module(source)))

    def compare(self, response=None, *, real=False):
        def runner(args, cwd):
            if Path(args[-2]).stem != 'functions':
                return 0, PAYLOAD, b''
            if real:
                # Execute the exact missing-export test fixture against the real package.
                args = list(args)
                args[-3] = str(ROOT)
                result = subprocess.run(args, cwd=cwd, env=full.child_environment(), capture_output=True,
                                        timeout=full.CASE_SECONDS, check=False)
                return result.returncode, result.stdout, result.stderr
            if isinstance(response, Exception):
                raise response
            return self.actual_response if response is None else response
        result = full.compare_outputs(self.root, self.capture, self.report['stage3'], self.inputs,
                                      runner=runner)
        self.report['comparison'] = result
        return result['cases'][2]

    def artifacts(self):
        return full.output_artifact_files(self.payloads, self.report, smoke.IMAGE)

    def assert_rejected_host(self, case, kind=full.POST_CREATE_FAILURE):
        self.assertEqual(case['status'], 'timeout' if kind == 'interpreter_timeout' else 'error')
        self.assertEqual(case['failure_kind'], kind)
        self.assertEqual(case['acceptance_status'], 'rejected')
        for key in ('interpreter_sha256', 'interpreter_size', 'mismatch', 'semantic'):
            self.assertIsNone(case[key])
        self.assertEqual(self.report['comparison']['status'], 'failed')
        self.assertEqual(self.report['comparison']['acceptance_status'], 'rejected')

    def test_complete_source_keeps_success_and_measurement_before_postcreate(self):
        code, actual, stderr = self.success_response
        self.assertEqual((code, stderr), (0, b''))
        rows = actual.splitlines()
        self.assertEqual(len(rows), 157)
        self.assertRegex(rows[136], rb'^omit\.v1:(?:[SE][0-9]{4}){9}$')
        self.assertEqual(rows[137], BEGIN)
        self.assertEqual(tuple(row.split(b':', 1)[0].decode() for row in rows[138:156]),
                         full.POST_CREATE_LABELS)
        self.assertEqual(rows[-1], OK)
        self.assertNotEqual(self.failure_source, self.original_source)

    def test_actual_missing_export_exit3_keeps_measurement_and_seven_file_packaging(self):
        code, actual, stderr = self.actual_response
        self.assertEqual((code, stderr), (3, b''))
        self.assertEqual(len(actual.splitlines()), 139)
        self.assertEqual(actual.splitlines()[-2:], [BEGIN, ERROR])
        self.assert_rejected_host(self.compare())
        files = self.artifacts()
        self.assertEqual(tuple(files), full.ARTIFACT_FILES)
        self.assertEqual(files['functions.out'], self.payloads['functions.out'])
        provenance = json.loads(files['provenance.json'])
        case = provenance['cases'][2]
        self.assertEqual(case['comparison_status'], 'error')
        self.assertEqual(case['acceptance_status'], 'rejected')
        self.assertNotIn('failure_kind', case)  # Specific classification remains in the summary.
        for key in ('interpreter_sha256', 'interpreter_size', 'mismatch', 'semantic'):
            self.assertIsNone(case[key])
        self.assertEqual(provenance['acceptance_status'], 'rejected')
        self.assertEqual(provenance['schema'], 'native-1c-outputs-v2')

    def test_real_lf_crlf_and_bom_sources_and_native_bytes_are_preserved(self):
        source = self.failure_source.encode('utf-8').replace(b'\r\n', b'\n')
        for bom in (b'', b'\xef\xbb\xbf'):
            for ending in (b'\n', b'\r\n'):
                with self.subTest(bom=bom, ending=ending):
                    self.set_source(bom + source.replace(b'\n', ending))
                    self.bind_native(native_payload(ending=ending))
                    self.assert_rejected_host(self.compare(real=True))
                    self.assertEqual(self.artifacts()['functions.out'], self.payloads['functions.out'])

    def test_directive_grammar_matches_both_existing_drivers(self):
        embedded = host_directive_parser()
        directive = full.POST_CREATE_DIRECTIVE
        valid = [('', False), ('Message("// NativePostCreate: Unknown");', False)]
        for bom in ('', '\ufeff'):
            for ending in ('\n', '\r\n'):
                valid += [(bom + directive + ending + 'Message(1);', True)]
        for source, expected in valid:
            for parser in (full.post_create_requested, embedded, launcher.post_create_requested):
                self.assertIs(parser(source), expected)
        malformed = [directive + '\n' + directive, '\n' + directive, ' ' + directive,
                     directive + ' ', directive + '();', directive.replace('AfterCreate', 'Other'),
                     '//NativePostCreate: ExportProbeAfterCreate', '// NativePostCreateUnknown',
                     'Message(1);\n' + directive]
        for source in malformed:
            for ending in ('\n', '\r\n'):
                transported = source.replace('\n', ending)
                for parser, error in ((full.post_create_requested, ValueError), (embedded, ValueError),
                                      (launcher.post_create_requested, launcher.LaunchError)):
                    with self.subTest(source=transported, parser=parser), self.assertRaises(error):
                        parser(transported)
                self.set_source(transported.encode('utf-8'))
                self.assert_rejected_host(self.compare(), 'interpreter_failed')
                with self.assertRaises(full.FullError):
                    self.artifacts()
        self.set_source(b'// no directive\n')
        self.assert_rejected_host(self.compare(), 'interpreter_failed')
        self.assertFalse(full.interpreter_post_create_failed(b'\xff\n' + directive.encode(),
                                                           *self.actual_response))

    def test_exit_stderr_and_host_phase_mutations_fail_closed(self):
        _, actual, _ = self.actual_response
        mutations = [actual.replace(BEGIN + b'\n', b''), actual.replace(ERROR + b'\n', b''),
                     actual.replace(BEGIN, BEGIN + b'\n' + BEGIN), actual + ERROR + b'\n',
                     actual.replace(ERROR, OK), actual.replace(ERROR, ERROR + b' suffix'),
                     actual.replace(BEGIN, b'prefix ' + BEGIN), actual + b'extra\n', actual + b'\n',
                     actual.replace(ERROR, b'export-phase.post-create: [error;kind=unknown;named={"B",0}]'),
                     actual.replace(ERROR, ERROR.replace(b'{"B",1}', b'{"B",2}')),
                     actual.replace(BEGIN + b'\n' + ERROR, ERROR + b'\n' + BEGIN), actual[:-1]]
        responses = [(1, actual, b''), (2, actual, b''), (3, actual, b'private stderr'),
                     (0, actual, b'private stderr')] + [(3, mutation, b'') for mutation in mutations]
        for response in responses:
            with self.subTest(response=response):
                self.assert_rejected_host(self.compare(response), 'interpreter_failed')
                with self.assertRaises(full.FullError):
                    self.artifacts()
        for kind in ('interpreter_timeout', 'interpreter_output_limit', 'interpreter_unavailable'):
            self.assert_rejected_host(self.compare(full.FullError(kind)), kind)
            with self.assertRaises(full.FullError):
                self.artifacts()

    def test_bounded_phase_error_enums_and_line_endings(self):
        for kind in ('other', 'method-missing'):
            for named in (0, 1):
                final = f'export-phase.post-create: [error;kind={kind};named={{"B",{named}}}]'.encode()
                for ending in (b'\n', b'\r\n'):
                    response = (3, ending.join([b'offline host', BEGIN, final]) + ending, b'')
                    self.bind_native(native_payload(ending=ending, failure=final))
                    self.assert_rejected_host(self.compare(response))
                    self.assertEqual(self.artifacts()['functions.out'], self.payloads['functions.out'])

    def test_source_and_capture_tampering_never_get_narrow_classification(self):
        source = self.root / 'integrational_tests/tests/functions.bsl'
        source.write_bytes(source.read_bytes() + b'// tampered\n')
        self.assert_rejected_host(self.compare(), 'source_changed')
        with self.assertRaises(full.FullError):
            self.artifacts()
        self.set_source(source.read_bytes())
        path = self.capture / 'functions.out'
        path.write_bytes(b'tampered')
        self.assert_rejected_host(self.compare(), 'native_capture_changed')
        with self.assertRaises(full.FullError):
            self.artifacts()

    def test_native_phase_and_probe_inventory_mutations_are_independently_rejected(self):
        good = native_payload()
        rows = good.splitlines()
        first, second = rows[137:139]
        mutations = [good.replace(BEGIN + b'\n', b''), good.replace(OK + b'\n', b''),
                     good.replace(BEGIN, BEGIN + b'\n' + BEGIN), good + OK + b'\n',
                     good + b'extra\n', good + b'\n', good.replace(OK, ERROR),
                     good.replace(OK, b'export-phase.post-create: [error;kind=unknown;named={"B",0}]'),
                     good.replace(first + b'\n', b''), good.replace(first, first + b'\n' + first),
                     good.replace(first + b'\n' + second, second + b'\n' + first),
                     good.replace(first, first.replace(b'object-context', b'unknown')),
                     good.replace(first, first.partition(b': ')[0]),
                     first + b'\n' + good, good.replace(BEGIN, b'prefix ' + BEGIN),
                     b'\n'.join([BEGIN, first, ERROR]) + b'\n',
                     good.replace(b'\n', b'\r'), good[:-1], b'old capture\n']
        for payload in mutations:
            with self.subTest(payload=payload):
                self.bind_native(payload)  # Hash-consistent malformed bytes must still be rejected.
                self.assert_rejected_host(self.compare())
                with self.assertRaisesRegex(full.FullError, '^native_artifact_evidence_invalid$'):
                    self.artifacts()

    def test_probe_inventory_is_exactly_committed_callback_labels_not_values(self):
        source = (ROOT / 'integrational_tests/tests/functions.bsl').read_text(encoding='utf-8-sig')
        callback = source.split('Procedure ExportProbeAfterCreate(', 1)[1].split('EndProcedure', 1)[0]
        labels = re.findall(r'ObserveExportProbe\("([^"]+)"', callback)
        self.assertEqual(tuple('export-variable.' + label for label in labels), full.POST_CREATE_LABELS)
        self.assertEqual(len(labels), 18)
        self.bind_native(native_payload().replace(b'opaque offline value', b'any unasserted result'))
        self.assert_rejected_host(self.compare())
        self.artifacts()

    def test_new_failure_domain_cannot_claim_success_or_synthetic_host_evidence(self):
        self.compare()
        for update in ({'status': 'timeout'}, {'status': 'matched'}, {'acceptance_status': 'accepted'},
                       {'interpreter_sha256': 'a' * 64}, {'interpreter_size': 0}, {'mismatch': {}},
                       {'semantic': {}}, {'failure_kind': 'interpreter_failed'},
                       {'failure_kind': 'source_changed'}, {'failure_kind': 'arbitrary'}):
            original = copy.deepcopy(self.report)
            self.report['comparison']['cases'][2].update(update)
            with self.subTest(update=update), self.assertRaises(full.FullError):
                self.artifacts()
            self.report = original

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Atomic export uses Linux renameat2')
    def test_mocked_native_run_and_real_comparison_export_main_stay_rejected(self):
        harness = artifact.OrchestrationTests()
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        for mode in (full.BYTE_EXACT, full.MAP_MODE):
            # The actual semantic verifier checks these synthetic typed records;
            # no mocked verdict or invented native observation is used.
            collections = map_fixtures.encode(map_fixtures.records()) if mode == full.MAP_MODE else None
            for changed in (False, True):
                with self.subTest(mode=mode, changed=changed):
                    result, exported, retained = harness.invoke(post_create=(native_payload(), self.actual_response),
                        through_main=True, final_changed=changed, comparison_mode=mode,
                        collections_payload=collections)
                    self.assertEqual((len(exported), len(retained)), (1, 1))
                    self.assertEqual(result['exit_code'], 1)
                    self.assertEqual(result['final_verifications'], 1)
                    self.assertEqual(result['ready'], '' if changed else 'native_outputs_ready=true\n')
                    summary = result['summary']
                    self.assertFalse(summary['smoke_completed'])
                    self.assertFalse(summary['interpreter_comparison_completed'])
                    self.assertFalse(summary['interpreter_acceptance_completed'])
                    probe = summary['probe']
                    self.assertIs(probe['native_output_artifact_ready'], not changed)
                    self.assertEqual(probe['comparison']['acceptance_status'], 'rejected')
                    self.assertEqual(probe['comparison']['comparison_mode'], mode)
                    self.assertEqual(probe['comparison']['cases'][2]['failure_kind'], full.POST_CREATE_FAILURE)
                    self.assertTrue(probe['native_evidence_accepted'])
                    self.assertTrue(probe['private_payloads_removed'])
                    self.assertEqual(exported[0]['functions.out'], native_payload())
                    if mode == full.MAP_MODE:
                        semantic = probe['comparison']['cases'][0]['semantic']
                        self.assertEqual((semantic['status'], semantic['records']), ('equivalent', 854))
                        self.assertIsNone(probe['comparison']['cases'][2]['semantic'])
