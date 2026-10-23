"""Audited object transfer capture, now strict whole-source interpreter parity."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from decimal import Decimal
from test_native_client_probe import full, suite, ROOT, stage_fixture
from test_native_directive_witness import linux_fixture
from yadinassi import Interpreter

class ObjectTransferParityTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patch = mock.patch.object(suite, 'secure_bytes', new=stage_fixture.portable_fixture_bytes)
            patch.start(); self.addCleanup(patch.stop)
        self.capture = json.loads((ROOT/'integrational_tests/directive_probes/object_transfer_native.json').read_text())

    def test_captured_contract_and_source_identity(self):
        raw = full.module_context_shared_source(full.nocontext_shared_source(full.dual_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE))))
        self.assertEqual(full.digest(raw), self.capture['source_sha256'])
        self.assertEqual(full.digest(full.generated_module(raw)), self.capture['module_sha256'])
        self.assertEqual(self.capture['artifact_sha256'], '2f552e2620500c68823da3bba8bc06c3d9d9e082ca21d5bbfe0966d1404498ba')
        labels = re.findall(r'ObjectTransferRecord\("([^"]+)"', (ROOT/'integrational_tests/directive_probes/object_transfer_core.bsl').read_text())
        self.assertEqual(labels, self.capture['labels'])
        self.assertEqual(len(labels), 58)
        self.assertEqual(full.CLIENT_VALUES, suite.CLIENT_VALUES)
        self.assertEqual(full.CLIENT_VALUES[50:109], ['object.transfer.v1'] + self.capture['values'])

    def test_exact_restored_object_source_computes_every_captured_value(self):
        vm = Interpreter(lambda _: self.fail('unexpected output'))
        vm.execute(full.dual_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE)).decode('utf-8-sig'))
        values = list(vm.execute('ВычислитьПробу()'))
        normalized = [int(v) if type(v) is Decimal else v for v in values]
        self.assertEqual(normalized, full.CLIENT_VALUES)
        self.assertEqual([type(v) for v in normalized], [type(v) for v in full.CLIENT_VALUES])
        self.assertEqual(vm.execution_context, 'client')

    @unittest.skipIf(os.name == 'nt', 'bounded native preflight runner is POSIX-only')
    def test_exact_inverse_gate_rejects_changed_object_callee(self):
        raw = (ROOT/full.CLIENT_SOURCE).read_bytes()
        changed = raw.replace(b'P.N = 11;', b'Raise "changed";')
        self.assertNotEqual(raw, changed)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve()/'probe.bsl'; path.write_bytes(changed)
            with self.assertRaisesRegex(full.FullError, '^source_changed$'):
                full.verify_client_interpreter(ROOT, path, full.digest(changed))

    def test_strict_typed_native_contract_and_budgets(self):
        marker = dict(schema=1,nonce='a'*32,phase='completed',witness='client',values=suite.CLIENT_VALUES)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary).resolve()/'marker.json'
            path.write_bytes(json.dumps(marker).encode())
            self.assertEqual(suite.client_marker(path,'a'*32,'completed'),marker)
            for index in range(50,109):
                values=list(suite.CLIENT_VALUES); original=values[index]
                values[index] = not original if type(original) is bool else (original+1 if type(original) is int else 'wrong')
                path.write_bytes(json.dumps({**marker,'values':values}).encode())
                with self.assertRaises(suite.FullError):suite.client_marker(path,'a'*32,'completed')
                self.assertEqual(suite.client_marker_diagnostics(path,'a'*32)['ordinal'],index)
            for values in (suite.CLIENT_VALUES[:50],suite.CLIENT_VALUES[:-1],suite.CLIENT_VALUES+[0]):
                path.write_bytes(json.dumps({**marker,'values':values}).encode())
                with self.assertRaises(suite.FullError):suite.client_marker(path,'a'*32,'completed')
        self.assertLess(len(json.dumps(marker,indent=2).encode()),2048)
        self.assertEqual((suite.MAX_STAGE_REPORT,full.MAX_STAGE_REPORT,full.MAX_REPORT),(8192,8192,32768))

    def test_capture_only_metadata_and_shared_inverse_removed(self):
        self.assertFalse(hasattr(full,'client_interpreter_source'))
        for extra in ({'object_transfer':self.capture['values']},{'object_error_stage':1}):
            with self.assertRaises(ValueError):
                full.validate_marker_diagnostics(dict(phase='completed',kind='count',ordinal=50,error_stage=0,**extra))

    def test_all_probe_locals_explicit(self):
        from dataclasses import fields
        from yadinassi import ast
        from yadinassi.parser import parse
        def walk(node):
            if isinstance(node,ast.Node):
                yield node
                for f in fields(node):yield from walk(getattr(node,f.name))
            elif isinstance(node,(list,tuple)):
                for item in node:yield from walk(item)
        routines=[n for n in parse(full.module_context_shared_source(full.nocontext_shared_source(full.dual_shared_source(linux_fixture(ROOT/full.CLIENT_SOURCE)))).decode('utf-8-sig')) if isinstance(n,ast.Routine) and (n.name.startswith('ObjectTransfer') or n.name=='RunObjectTransferProbe')]
        self.assertEqual(len(routines),19)
        for routine in routines:
            declared={p.name.casefold() for p in routine.parameters}
            for n in walk(routine.body):
                if isinstance(n,ast.Var):declared.update(x.casefold() for x in n.names)
            assigned={n.target.name.casefold() for n in walk(routine.body) if isinstance(n,ast.Assign) and isinstance(n.target,ast.Name)}
            self.assertLessEqual(assigned,declared)
