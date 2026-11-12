"""Immutable two-Enterprise capture and unchanged two-process host replay."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_native_async_fixture import historical_source_bytes
from inventory_enum_behavior import route
from yadinassi.configuration_inventory_enums import PROFILE,import_inventory_enum_configuration
from yadinassi.database_context import SQLiteDBContext
from test_configuration_inventory_enums import source

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/native_inventory_enum'

class InventoryEnumAcquisitionTests(unittest.TestCase):
    def test_original_capture_boundaries_and_cleanup_are_immutable(self):
        raw=(FIXTURE/'inventory-enum.out').read_bytes();proof=(FIXTURE/'provenance.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'755ffb03217bb01318932adbd78933f4d9a77fbd9376be2ad9359ef319fa3527')
        self.assertEqual(hashlib.sha256(proof).hexdigest(),'047518ceb188ff2e808a3c812e18eccf3595f83f9f5738d0e627a1c6ab0f1c66')
        d=json.loads(proof);stage=d['native_report']['stage3']
        self.assertEqual(d['repository']['tree'],'859b834a0badea7abd2300e4a582282f3e3a1c2c')
        self.assertEqual(d['repository']['commit'],'723c8ece2e78c55fcc9c5b4ca3cc2a3d8ee241e4')
        self.assertEqual(d['repository']['github_run_id'],'43086960484')
        self.assertTrue(d['native_measurement_accepted']);self.assertFalse(d['runtime_parity_accepted'])
        for key in ('container_cleanup_verified','docker_cli_reap_verified','private_payloads_removed'):self.assertTrue(d[key])
        self.assertTrue(stage['restart_verified']);self.assertEqual(stage['record_count'],12)
        self.assertEqual([p['record_count'] for p in stage['phases']],[11,1])
        for phase in stage['phases']:
            for key in ('entered','completed','quiet','process_exited'):self.assertTrue(phase[key])
            self.assertEqual(phase['module_sha256'],phase['module_verified_sha256'])
        self.assertNotEqual(*[p['module_sha256'] for p in stage['phases']])
        self.assertEqual(stage['partial_observations'],list(map(list,enumerate(json.loads(raw),1))))

    def test_original_acquisition_inputs_still_match(self):
        d=json.loads((FIXTURE/'provenance.json').read_bytes())
        for group in ('trusted_input_sha256','host_source_sha256'):
            for path,digest in d[group].items():
                with self.subTest(path=path):self.assertEqual(hashlib.sha256(historical_source_bytes(path, (ROOT/path).read_bytes(), digest)).hexdigest(),digest)

    def test_unchanged_observer_replays_after_actual_host_process_restart(self):
        expected=json.loads((FIXTURE/'inventory-enum.out').read_bytes())
        nonce='c'*32
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root=Path(directory);database=root/'owned.sqlite'
            context=SQLiteDBContext.create_inventory_enum(database,import_inventory_enum_configuration(source(),inventory_runtime=PROFILE));context.close()
            actual=[]
            for phase in (1,2):
                program=root/('phase'+str(phase)+'.bsl');program.write_bytes(route.program(None,nonce,phase))
                # Each subprocess must exit successfully before the next one
                # opens this same database. Phase2 never repeats the seed.
                result=subprocess.run([sys.executable,'-m','yadinassi','--f',str(database),str(program)],cwd=ROOT,
                    env=dict(os.environ,PYTHONPATH=str(ROOT),PYTHONIOENCODING='utf-8'),capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr.decode('utf-8','replace'))
                actual.extend(route.parse_wire(result.stdout,nonce,phase))
            self.assertEqual(actual,expected)
