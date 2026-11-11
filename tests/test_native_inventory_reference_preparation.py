"""Offline acquisition gates; no native semantic expected values and no Docker."""
from pathlib import Path
import tempfile
import unittest
from inventory_reference_behavior import fixture, route, native_source, runtime_source
import native_1c_inventory_reference_profile as host

ROOT=Path(__file__).resolve().parents[1]
NONCE='a'*32

class InventoryReferencePreparationTests(unittest.TestCase):
    def test_twelve_numbered_groups(self):
        self.assertEqual(route.COUNT,12)
        self.assertEqual(route.source().count(b'For CaseNo = 1 To 12 Do'),1)
    def test_native_assets_reproducible(self):
        for name,raw in native_source.derive().items():self.assertEqual((ROOT/'scripts/inventory_reference_behavior'/name).read_bytes(),raw)
    def test_runtime_assets_reproducible(self):
        for name,raw in runtime_source.derive().items():self.assertEqual((ROOT/'scripts/inventory_reference_behavior/runtime_source'/name).read_bytes(),raw)
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
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp)/'stage';hashes=host.stage_inputs(ROOT,stage,host.SMOKE)
            host.validate_inputs(stage,hashes,host.SMOKE)
            (stage/'bootstrap/inventory_reference_behavior/observe.bsl').write_bytes(b'drift')
            with self.assertRaises(ValueError):host.validate_inputs(stage,hashes,host.SMOKE)
    def test_workflow_is_separate_branch_and_no_dispatch(self):
        source=(ROOT/'.github/workflows/native-1c-inventory-reference.yml').read_text()
        self.assertIn("head.ref == 'codex/db-inventory-references'",source)
        self.assertNotIn('workflow_dispatch',source)
        self.assertIn('Observe twelve cases',source)

    def test_no_polymorphic_recorder_binding_in_sources(self):
        root=ROOT/'scripts/inventory_reference_behavior'
        for name in ('observe.bsl','ReceiptModule.bsl','IssueModule.bsl'):
            raw=(root/name).read_text()
            self.assertNotIn('R.Recorder',raw)
            self.assertNotIn('WHERE R.Recorder',raw)
        for name,kind in (('ReceiptModule.bsl','receipt'),('IssueModule.bsl','issue')):
            raw=(root/name).read_text()
            self.assertIn('Row.Note = "'+kind+':" + Number;',raw)
            self.assertIn('Q.SetParameter("Tag", "'+kind+':" + Number);',raw)
