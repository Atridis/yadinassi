"""Offline gates for independent filter capture, never native expected values."""
from pathlib import Path
import hashlib
import os
import re
import tempfile
import unittest
from unittest import mock
from inventory_filter_behavior import fixture, route
import native_1c_inventory_filter_profile as host

ROOT=Path(__file__).resolve().parents[1]
NONCE='a'*32

class InventoryFilterPreparationTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patcher.start();self.addCleanup(patcher.stop)
    def test_twelve_groups(self):
        self.assertEqual(route.COUNT,12)
        self.assertEqual(route.source().count(b'For CaseNo = 1 To 12 Do'),1)
    def test_observer_digest(self):
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(),route.SOURCE_SHA256)
        self.assertIn(b'Product=&Product AND Warehouse=&Warehouse',route.source())
        self.assertIn(b'Target.Write(DocumentWriteMode.Posting)',route.source())
    def test_pinned_owned_assets(self):
        _,assets=fixture.load_saved()
        self.assertEqual(set(assets),set(fixture.ASSET_HASHES)|{'generated/observe.bsl'})
    def test_previous_owned_material_is_unchanged(self):
        for name in fixture.ASSET_HASHES:
            self.assertEqual((ROOT/'scripts/inventory_reference_behavior'/name).read_bytes(),(ROOT/'scripts/inventory_filter_behavior'/name).read_bytes())
    def test_program_nonce_and_budget(self):
        program=route.program(None,NONCE)
        from yadinassi.syntax.parser import parse
        parse(program.decode('utf-8'))
        self.assertLessEqual(len(program),32768)
        self.assertIn(('FLT|'+NONCE+'|entered').encode(),program)
        self.assertIn(('FLT|'+NONCE+'|completed').encode(),program)
    def test_bad_nonce(self):
        with self.assertRaises(ValueError):route.program(None,'bad')
    def test_ordered_wire(self):
        prefix='FLT|'+NONCE+'|'
        raw=('\n'.join([prefix+'entered',*[prefix+str(n)+'|empty' for n in range(1,13)],prefix+'completed'])+'\n').encode()
        self.assertEqual(route.parse_wire(raw,NONCE),['empty']*12)
        with self.assertRaises(ValueError):route.parse_wire(raw,'b'*32)
    def test_missing_group_refused(self):
        with self.assertRaises(ValueError):route.canonical(['empty']*11)
    def test_oversized_group_refused(self):
        with self.assertRaises(ValueError):route.canonical(['a'*4097]*12)
    def test_manifest_owns_new_observer_only(self):
        files=host.staged_files()
        self.assertIn('scripts/inventory_filter_behavior/observe.bsl',files)
        self.assertNotIn('scripts/inventory_reference_behavior/observe.bsl',files)
        self.assertNotIn('scripts/accumulation_register_behavior/observe.bsl',files)
        for name in fixture.ASSET_HASHES:self.assertIn('scripts/inventory_filter_behavior/'+name,files)
    def test_staging_revalidates_inputs(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            stage=Path(tmp).resolve()/'stage'
            hashes=host.stage_inputs(ROOT,stage,host.SMOKE)
            host.validate_inputs(stage,hashes,host.SMOKE)
            (stage/'bootstrap/inventory_filter_behavior/observe.bsl').write_bytes(b'drift')
            with self.assertRaises(ValueError):host.validate_inputs(stage,hashes,host.SMOKE)
    def test_workflow_exact_branch_and_no_dispatch(self):
        source=(ROOT/'.github/workflows/native-1c-inventory-filter.yml').read_text(encoding='utf-8')
        self.assertIn("head.ref == 'codex/db-stock-filtered-virtual-tables'",source)
        self.assertNotIn('workflow_dispatch',source)
        self.assertIn('Observe twelve cases',source)
    def test_material_reference_target_validation(self):
        raw=(ROOT/'scripts/inventory_filter_behavior/Stock.xml').read_bytes()
        changed=raw.replace(b'cfg:CatalogRef.Products',b'cfg:CatalogRef.Warehouses')
        self.assertNotEqual(fixture._owned_projection(raw,'AccumulationRegister'),fixture._owned_projection(changed,'AccumulationRegister'))
    def test_module_drift_refused(self):
        expected={'Documents/Receipt/Ext/ObjectModule.bsl':b'Procedure X()\nEndProcedure\n'}
        with self.assertRaises(ValueError):fixture.verify_redump(expected,{next(iter(expected)):b'Procedure Y()\nEndProcedure\n'})
    def test_unknown_file_refused(self):
        with self.assertRaises(ValueError):fixture.verify_redump({}, {'new.xml':b'<x/>'})
    def test_optional_slots(self):
        source=route.source()
        self.assertIn(b'Args="&StartAt,&EndAt,"+Periodicity+","',source)
        self.assertIn(b'Kind="BalanceAndTurnovers" Then Args=Args+","',source)
        self.assertIn(b'"Turnovers","Day"',source)
        self.assertIn(b'"Turnovers","Month"',source)
        self.assertIn(b'"BalanceAndTurnovers","Day"',source)
        self.assertIn(b'"BalanceAndTurnovers","Month"',source)
    def test_reference_and_composition_observations(self):
        source=route.source()
        for token in (b'EmptyRef()',b'TypeOf(Empty)' ,b'GROUP BY',b'LEFT JOIN',b'ExecuteBatch()',b'FROM (SELECT'):
            self.assertIn(token,source)
        self.assertIn(b'GetRef(New UUID(', source)
        self.assertNotIn(b'R.Product AS Product', source)
        self.assertIn(b'C.ValueType.NumberQualifiers.Digits', source)
    def test_case12_has_transaction_rollback(self):
        source=route.source().split(b'ElsIf CaseNo=12 Then')[1]
        self.assertIn(b'BeginTransaction()',source)
        self.assertEqual(source.count(b'RollbackTransaction()'),2)
    def test_source_has_bounded_rows(self):
        source=route.source()
        self.assertIn(b'If Count>32 Then Raise',source)
        for arguments in re.findall(rb'Date\(([^()]+)\)',source):
            self.assertIn(len(arguments.split(b',')),(3,6))
        self.assertNotIn(b'Result.Columns',source)
        self.assertIn(b'Q.Execute().Unload()',source)
    def test_harness_preserves_isolation_and_no_parity_claim(self):
        source=(ROOT/'scripts/native_1c_inventory_filter_profile.py').read_text(encoding='utf-8')
        self.assertIn("'--network', 'none'",source)
        self.assertIn("'--read-only'",source)
        self.assertIn("'runtime_parity_accepted':False",source.replace(' ',''))
