"""Strict Date/Null witness parity; fixtures are not new native execution."""
import copy
import inspect
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from infobase_preflight_test_support import offline_fixture
from unittest import mock

from test_native_1c_full_host import SyntheticFilesystemCase
from test_native_client_probe import full, suite, ROOT, stage_fixture, NONCE, process_diagnostics
from test_native_directive_witness import linux_fixture
import test_native_async_budget as budget

TOKEN = 'dn.v1:22222277'
PLAN = 'integrational_tests/directive_probes/date_null_measurement.json'
SOURCE = 'integrational_tests/directive_probes/date_null_core.bsl'


def marker(values=None, **changes):
    result = dict(schema=1, nonce=NONCE, phase='completed', witness='client',
                  values=list(full.CLIENT_VALUES) if values is None else values)
    result.update(changes)
    return result


class DateNullStrictWitnessTests(SyntheticFilesystemCase):
    def setUp(self):
        super().setUp()
        self.source = linux_fixture(ROOT / full.CLIENT_SOURCE)
        self.strict136 = full.infobase_shared_source(self.source)
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes',
                                      new=stage_fixture.portable_fixture_bytes)
            patch.start(); self.addCleanup(patch.stop)

    def read_marker(self, value):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / 'completed.json'
            path.write_bytes(json.dumps(value, ensure_ascii=False,
                                        separators=(',', ':'), allow_nan=False).encode())
            return suite.client_marker(path, NONCE, 'completed')

    def test_source_identity_and_strict136_equal_contract(self):
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)
        self.assertEqual(len(full.CLIENT_VALUES), 136)
        self.assertEqual(full.CLIENT_VALUES[-2:],
                         ['dual.v1:000032017000017041000032017', TOKEN])
        self.assertEqual(full.digest(self.strict136), full.DATE_NULL_SOURCE_SHA256)
        self.assertEqual(full.digest(suite.generated_module(self.strict136)), full.DATE_NULL_MODULE_SHA256)
        self.assertEqual(full.digest(linux_fixture(ROOT / SOURCE)), full.DATE_NULL_CORE_SHA256)
        self.assertEqual(self.read_marker(marker())['values'], full.CLIENT_VALUES)

    def test_every_value_and_type_is_required(self):
        for index, expected in enumerate(full.CLIENT_VALUES):
            with self.subTest(index=index):
                wrong = list(full.CLIENT_VALUES)
                wrong[index] = not expected if type(expected) is bool else None
                with self.assertRaises(suite.FullError): self.read_marker(marker(wrong))
                if type(expected) is int:
                    wrong[index] = float(expected)
                    with self.assertRaises(suite.FullError): self.read_marker(marker(wrong))
        for values in (full.CLIENT_VALUES[:-1], full.CLIENT_VALUES + [TOKEN], []):
            with self.assertRaises(suite.FullError): self.read_marker(marker(values))

    def test_changed_or_malformed_tokens_never_pass(self):
        for token in ('dn.v1:01201278', 'dn.v1:22222276', 'dn.v1:22222277 ',
                      'dn.v1:2222227', 'dn.v1:222222777', 'dn.v1:222222７7',
                      'dn.v1:22222288', True, None, 22222277):
            with self.subTest(token=token), self.assertRaises(suite.FullError):
                self.read_marker(marker(full.CLIENT_VALUES[:-1] + [token]))

    def test_nonce_phase_schema_witness_and_keys_fail_closed(self):
        for patch in ({'nonce':'0'*32}, {'phase':'error'}, {'schema':True},
                      {'witness':'server'}, {'extra':True}, {'values':None}):
            with self.subTest(patch=patch), self.assertRaises(suite.FullError):
                self.read_marker(dict(marker(), **patch))

    def test_private_marker_cap_and_json_guards_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / 'completed.json'
            for raw in (b' '*2049, b'{', b'{"schema":1,"schema":1}', b'{"values":[NaN]}'):
                path.write_bytes(raw)
                with self.assertRaises(suite.FullError): suite.client_marker(path, NONCE, 'completed')

    def test_capture_only_public_extension_is_rejected(self):
        value = dict(phase='completed', kind='count', ordinal=135, error_stage=0,
                     date_null=TOKEN)
        with self.assertRaises(ValueError): full.validate_marker_diagnostics(value)
        self.assertFalse(hasattr(suite, 'has_date_null_capture'))
        self.assertFalse(hasattr(suite, 'discard_date_null_capture'))
        self.assertFalse(hasattr(suite, 'date_null_client_marker'))
        self.assertNotIn('date_null_source', inspect.signature(suite.client_marker_diagnostics).parameters)

    def test_hash_bound_inverse_for_legacy_adapters_only(self):
        restored = suite.date_null_shared_source(self.strict136)
        self.assertEqual(full.date_null_shared_source(self.strict136), restored)
        self.assertEqual(full.digest(restored), full.DATE_NULL_BASE_SHA256)
        for mutated in (self.strict136+b'\n', self.strict136.replace(b'DNAppend(', b'DNOther(', 1)):
            with self.assertRaises(suite.FullError): suite.date_null_shared_source(mutated)
        plan = json.loads((ROOT/PLAN).read_text(encoding='utf-8'))
        for name, expected in plan['four_adapter_sha256'].items():
            scenario = linux_fixture(ROOT/f'integrational_tests/tests/{name}.bsl')
            self.assertEqual(full.digest(getattr(suite, f'client_{name}_module')(scenario, self.source)), expected)
        self.assertEqual(full.async_source_identity(linux_fixture(ROOT/'scripts/native_1c_bootstrap/full_suite.py')),
                         plan['async8_identity'])

    def test_current_preflight_passes_original_whole137_source(self):
        calls=[]
        with tempfile.TemporaryDirectory() as temporary, offline_fixture(full):
            path=Path(temporary).resolve()/'source.bsl'; path.write_bytes(self.source)
            def runner(command, cwd):
                calls.append(command)
                self.assertEqual(Path(command[-2]), path)
                self.assertEqual(path.read_bytes(), self.source)
                return 0, json.dumps(full.CLIENT_RUNTIME_VALUES, ensure_ascii=False, separators=(',',':')).encode(), b''
            full.verify_client_interpreter(ROOT,path,full.digest(self.source),runner=runner)
            self.assertEqual(len(calls),1)
            with self.assertRaises(full.FullError):
                full.verify_client_interpreter(ROOT,path,'0'*64,runner=runner)
            self.assertEqual(len(calls),1)

    @unittest.skipUnless(sys.platform == 'linux', 'fixed native fixture is Linux-only')
    def test_real_interpreter_computes_whole137_from_exact_native_source(self):
        full.verify_client_interpreter(ROOT, ROOT/full.CLIENT_SOURCE, full.digest(self.source))

    def test_compact_writer_kept_native_only_and_cap_not_increased(self):
        self.assertIn(suite.DATE_NULL_COMPACT_WRITER, self.source)
        self.assertIn('ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет, " ", Истина)',
                      self.source.decode('utf-8-sig'))
        self.assertEqual((full.MAX_STAGE_REPORT,suite.MAX_STAGE_REPORT,full.MAX_REPORT),
                         (8192,8192,32768))
        # Local serialization model only; actual native raw markers are private.
        raw=json.dumps(marker(),ensure_ascii=False,separators=(',',':')).encode()
        self.assertLessEqual(len(raw),2048)
        self.assertEqual(json.loads(raw)['values'],full.CLIENT_VALUES)

    def test_actual_public_serializers_keep_existing_caps(self):
        wires=[];reports=[]
        for early in (False,True):
            for case in (None,*range(8)):
                value=budget.majorant(early=early,marker_case=case)
                wire=budget.render_stage(value['stage3'])
                self.assertEqual(full.decode_stage3_wire(json.loads(wire)),value['stage3'])
                summary,_=budget.render_summary(value,error=True)
                wires.append(len(wire));reports.append(len(summary))
        self.assertLessEqual(max(wires),8192);self.assertLessEqual(max(reports),32768)
