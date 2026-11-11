"""Offline acquisition gates; no native semantic expected values and no Docker."""
from pathlib import Path
import importlib
import os
import tempfile
import unittest
from unittest import mock
from xml.etree import ElementTree as ET
from inventory_reference_behavior import fixture, route, native_source, runtime_source
import native_1c_inventory_reference_profile as host

ROOT=Path(__file__).resolve().parents[1]
NONCE='a'*32

class InventoryReferencePreparationTests(unittest.TestCase):
    def setUp(self):
        # Static Windows fixture adapter only, not native containment proof.
        if os.name == 'nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patcher.start();self.addCleanup(patcher.stop)
    def test_twelve_numbered_groups(self):
        self.assertEqual(route.COUNT,12)
        self.assertEqual(route.source().count(b'For CaseNo = 1 To 12 Do'),1)
    def test_native_assets_reproducible(self):
        for name,raw in native_source.derive().items():self.assertEqual((ROOT/'scripts/inventory_reference_behavior'/name).read_bytes(),raw)
    def test_runtime_assets_reproducible(self):
        for name,raw in runtime_source.derive().items():self.assertEqual((ROOT/'scripts/inventory_reference_behavior/runtime_source'/name).read_bytes(),raw)
    def test_runtime_generator_preserves_process_namespace_map(self):
        before=ET._namespace_map.copy()
        importlib.reload(runtime_source)
        self.assertEqual(ET._namespace_map,before)
        runtime_source.derive()
        self.assertEqual(ET._namespace_map,before)
    def test_runtime_generator_restores_namespace_map_after_serialization_failure(self):
        before=ET._namespace_map.copy()
        with mock.patch.object(ET,'tostring',side_effect=ValueError('owned failure')):
            with self.assertRaises(ValueError):runtime_source.derive()
        self.assertEqual(ET._namespace_map,before)
    def test_exact_pinned_assets(self):
        _,assets=fixture.load_saved()
        self.assertEqual(set(assets),set(fixture.ASSET_HASHES)|{'generated/observe.bsl'})
    def test_generated_program_is_bounded_and_nonce_bound(self):
        program=route.program(None,NONCE)
        self.assertLessEqual(len(program),32768)
        self.assertIn(('INV|'+NONCE+'|entered').encode(),program)
        self.assertIn(('INV|'+NONCE+'|completed').encode(),program)
    def test_bad_nonce_refused(self):
        with self.assertRaises(ValueError):route.program(None,'not-a-nonce')
    def test_wire_order_and_nonce(self):
        prefix='INV|'+NONCE+'|'
        raw=('\n'.join([prefix+'entered',*[prefix+str(n)+'|0' for n in range(1,13)],prefix+'completed'])+'\n').encode()
        self.assertEqual(route.parse_wire(raw,NONCE),['0']*12)
        with self.assertRaises(ValueError):route.parse_wire(raw,'b'*32)
    def test_wire_cannot_omit_case(self):
        with self.assertRaises(ValueError):route.canonical(['0']*11)
    def test_native_reference_targets_material(self):
        raw=(ROOT/'scripts/inventory_reference_behavior/Stock.xml').read_bytes()
        changed=raw.replace(b'cfg:CatalogRef.Products',b'cfg:CatalogRef.Warehouses')
        self.assertNotEqual(fixture._owned_projection(raw,'AccumulationRegister'),fixture._owned_projection(changed,'AccumulationRegister'))
    def test_document_section_reference_material(self):
        raw=(ROOT/'scripts/inventory_reference_behavior/Receipt.xml').read_bytes()
        changed=raw.replace(b'cfg:CatalogRef.Products',b'cfg:CatalogRef.Warehouses')
        self.assertNotEqual(fixture._owned_projection(raw,'Document'),fixture._owned_projection(changed,'Document'))
    def test_reference_qname_prefix_is_semantic(self):
        raw=(ROOT/'scripts/inventory_reference_behavior/Receipt.xml').read_bytes()
        changed=raw.replace(b'xmlns:cfg=',b'xmlns:local=').replace(b'cfg:CatalogRef.',b'local:CatalogRef.')
        self.assertEqual(fixture._owned_projection(raw,'Document'),fixture._owned_projection(changed,'Document'))
    def test_changed_module_refused(self):
        expected={'Documents/Receipt/Ext/ObjectModule.bsl':b'Procedure X()\nEndProcedure\n'}
        with self.assertRaises(ValueError):fixture.verify_redump(expected,{next(iter(expected)):b'Procedure Y()\nEndProcedure\n'})
    def test_unknown_file_refused(self):
        with self.assertRaises(ValueError):fixture.verify_redump({}, {'new.xml':b'<x/>'})
    def test_manifest_has_every_owned_asset_and_no_old_observer(self):
        files=host.staged_files()
        for name in fixture.ASSET_HASHES:self.assertIn('scripts/inventory_reference_behavior/'+name,files)
        self.assertIn('scripts/inventory_reference_behavior/observe.bsl',files)
        self.assertNotIn('scripts/accumulation_register_behavior/observe.bsl',files)
    def test_staging_revalidates_source(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            stage=Path(tmp).resolve()/'stage';hashes=host.stage_inputs(ROOT,stage,host.SMOKE)
            host.validate_inputs(stage,hashes,host.SMOKE)
            (stage/'bootstrap/inventory_reference_behavior/observe.bsl').write_bytes(b'drift')
            with self.assertRaises(ValueError):host.validate_inputs(stage,hashes,host.SMOKE)
    def test_workflow_is_separate_branch_and_no_dispatch(self):
        source=(ROOT/'.github/workflows/native-1c-inventory-reference.yml').read_text(encoding='utf-8')
        condition=source.split('    if: >-\n',1)[1].split('    permissions:',1)[0]
        expected=("github.repository == 'Atridis/yadinassi' && github.repository_id == '359770628' && "
            "github.repository_owner_id == '30860798' && github.actor == 'Atridis' && "
            "github.actor_id == '30860798' && github.triggering_actor == 'Atridis' && "
            "github.event.pull_request.head.repo.full_name == 'Atridis/yadinassi' && "
            "(github.event.pull_request.head.ref == 'codex/db-inventory-references' || "
            "github.event.pull_request.head.ref == 'codex/explicit-profile-import') && "
            "github.event.pull_request.base.ref == 'main'")
        self.assertEqual(' '.join(condition.split()),expected)
        self.assertIn('ref: ${{ github.sha }}',source)
        self.assertIn('persist-credentials: false',source)
        self.assertIn('fetch-depth: 2',source)
        self.assertLess(source.index('python3 -I -B scripts/native_1c_ci_policy.py bind'),
                        source.index('GHCR_TOKEN:'))
        self.assertNotIn('workflow_dispatch',source)
        self.assertIn('Observe twelve cases',source)

    def test_no_polymorphic_recorder_binding_in_sources(self):
        root=ROOT/'scripts/inventory_reference_behavior'
        for name in ('observe.bsl','ReceiptModule.bsl','IssueModule.bsl'):
            raw=(root/name).read_text(encoding='utf-8')
            self.assertNotIn('R.Recorder',raw)
            self.assertNotIn('WHERE R.Recorder',raw)
        for name,kind in (('ReceiptModule.bsl','receipt'),('IssueModule.bsl','issue')):
            raw=(root/name).read_text(encoding='utf-8')
            self.assertIn('Row.Note = "'+kind+':" + Number;',raw)
            self.assertIn('Q.SetParameter("Tag", "'+kind+':" + Number);',raw)
