"""Immutable independent native12 capture and exact public-query replay."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter
from yadinassi.configuration_accumulation_references import PROFILE
from yadinassi.configuration_profile_import import prepare_directory, create_prepared

ROOT=Path(__file__).resolve().parents[1]
CAPTURE=ROOT/'tests/fixtures/native_inventory_filter'


class InventoryFilterReplayTests(unittest.TestCase):
    def test_capture_is_source_bound_complete_and_not_a_host_verdict(self):
        evidence=json.loads((CAPTURE/'provenance.json').read_bytes())
        self.assertEqual(evidence['repository'],dict(commit='0a3af8377ad618b625b147e9be58881b626e9e01',
            tree='8480486101e6e4a2f5b548150866e6a1c96c11f0',github_run_id='43070878852',github_run_attempt='1'))
        self.assertEqual(evidence['interpreter']['source_file_count'],229) # Historical capture, not current inventory.
        self.assertTrue(evidence['native_measurement_accepted'])
        self.assertFalse(evidence['runtime_parity_accepted'])
        stage=evidence['native_report']['stage3']
        self.assertEqual(stage['record_count'],12)
        self.assertEqual(stage['case_diagnostics'],[])
        for key in ('completed','config_verified','process_exited','witness_verified','quiet'):
            self.assertIs(stage[key],True)
        self.assertTrue(evidence['container_cleanup_verified'])
        self.assertTrue(evidence['private_payloads_removed'])

    def test_original_observer_assets_and_capture_bytes_are_immutable(self):
        for name,digest in (('provenance.json','4c20d0f97c9fb37901c571fd760c1d5c96738cc075e9d03967a8c573fb82738b'),
                            ('observations12.out','8ef3817d616cfcf7892477882652b25ed52b0dc42e77b9ca0ca6ad0f112744a9')):
            self.assertEqual(hashlib.sha256((CAPTURE/name).read_bytes()).hexdigest(),digest)
        evidence=json.loads((CAPTURE/'provenance.json').read_bytes())
        for name,digest in evidence['trusted_input_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
        self.assertIn('tests/fixtures/native_inventory_filter/* -text',(ROOT/'.gitattributes').read_text(encoding='utf-8'))

    def test_all_twelve_native_groups_replay_through_public_bsl(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            prepared=prepare_directory(ROOT/'scripts/inventory_reference_behavior/runtime_source',profile=PROFILE)
            with closing(create_prepared(Path(temp)/'filters.sqlite',prepared)) as context:
                with closing(Interpreter(database_context=context,output=lambda text:None)) as vm:
                    observed=[];diagnostics=[]
                    vm.register_function('ПодробноеПредставлениеОшибки',lambda info:info.get_member('Description'))
                    vm.register_function('AccumulationEmit',lambda n,v:observed.append((int(n),v)),returns_value=False)
                    vm.register_function('AccumulationDiagnostic',lambda n,s,e:diagnostics.append((int(n),s,e)),returns_value=False)
                    vm.execute((ROOT/'scripts/inventory_filter_behavior/observe.bsl').read_text(encoding='utf-8'),'native-filter12-replay')
        self.assertEqual(diagnostics,[])
        self.assertEqual([n for n,_ in observed],list(range(1,13)))
        self.assertEqual([v for _,v in observed],json.loads((CAPTURE/'observations12.out').read_bytes()))
