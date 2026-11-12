"""Accepted source-bound period capture, with an explicit legacy writer exclusion."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter
from yadinassi.configuration_accumulation_references import PROFILE
from yadinassi.configuration_profile_import import prepare_directory,create_prepared

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/native_inventory_period'
ASSETS=ROOT/'scripts/inventory_period_behavior'


class InventoryPeriodEvidenceTests(unittest.TestCase):
    def test_original_acquisition_is_verified_and_not_rewritten_as_parity(self):
        evidence=json.loads((FIXTURE/'provenance.json').read_text(encoding='utf-8'))
        stage=evidence['native_report']['stage3']
        self.assertTrue(evidence['native_measurement_accepted'])
        self.assertFalse(evidence['runtime_parity_accepted'])
        self.assertEqual(evidence['repository'],dict(commit='669c00c3ac177f5626e0d68e350ff998cbaa4e53',
            tree='5a56176a329d5711eb0522e6d676733ca7a4cacc',github_run_attempt='1',github_run_id='43054182621'))
        self.assertEqual(evidence['interpreter']['source_file_count'],229)
        for key in ('completed','config_verified','entered','process_exited','witness_verified','quiet'):
            self.assertIs(stage[key],True)
        self.assertEqual(stage['record_count'],14)
        self.assertEqual(stage['case_diagnostics'],[])
        self.assertTrue(evidence['container_cleanup_verified'])
        self.assertTrue(evidence['private_payloads_removed'])
    def test_owned_native_source_and_capture_are_immutable(self):
        self.assertEqual(hashlib.sha256((FIXTURE/'provenance.json').read_bytes()).hexdigest(),
                         '50739558ab189457f59c21dc8a7304f416d977a9664bdfd84df1d20472e84675')
        self.assertEqual(hashlib.sha256((FIXTURE/'observations14.out').read_bytes()).hexdigest(),
                         'f511529186f44f8d6666001abac519dad9bd4f6b042c19221b1bb501737e5e31')
        evidence=json.loads((FIXTURE/'provenance.json').read_text(encoding='utf-8'))
        for name,digest in evidence['trusted_input_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
    def test_all_observed_queries_replay_without_claiming_extreme_writer_parity(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            prepared=prepare_directory(ROOT/'scripts/inventory_reference_behavior/runtime_source',profile=PROFILE)
            with closing(create_prepared(Path(temp)/'period.sqlite',prepared)) as context:
                with closing(Interpreter(database_context=context,output=lambda text:None)) as vm:
                    observed=[];diagnostics=[]
                    vm.register_function('ПодробноеПредставлениеОшибки',lambda info:info.get_member('Description'))
                    vm.register_function('AccumulationEmit',lambda n,value:observed.append((int(n),value)),returns_value=False)
                    vm.register_function('AccumulationDiagnostic',lambda n,stage,error:diagnostics.append((int(n),stage,error)),returns_value=False)
                    vm.execute((ASSETS/'observe.bsl').read_text(encoding='utf-8'),'accepted-native-period14-observer')
        self.assertEqual(diagnostics,[])
        self.assertEqual([n for n,_ in observed],list(range(1,15)))
        native=json.loads((FIXTURE/'observations14.out').read_text(encoding='ascii'))
        self.assertEqual([value for _,value in observed[:13]],native[:13])
        # The host's pre-existing Date9999 write grant is unchanged. The probe
        # always rolls that transaction back, so the three query-only outcomes
        # have identical ordinary-date input. Do not label the writer as parity.
        self.assertEqual(native[13],'write:refused|query-refused|query-refused|query-refused')
        self.assertEqual(observed[13][1].split('|')[0],'write:accepted')
        self.assertEqual(observed[13][1].split('|')[1:],native[13].split('|')[1:])
