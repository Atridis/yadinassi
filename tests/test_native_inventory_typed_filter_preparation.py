"""Offline gates for independent filter capture, never native expected values."""
from pathlib import Path
import hashlib
import os
import re
import tempfile
import unittest
from unittest import mock
from inventory_typed_filter_behavior import fixture, route
import native_1c_inventory_typed_filter_profile as host

ROOT=Path(__file__).resolve().parents[1]
NONCE='a'*32

class InventoryTypedFilterPreparationTests(unittest.TestCase):
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
        self.assertIn(b'Product IN (&Products) AND Unit IN (&Units)',route.source())
        self.assertIn(b'Target.Write(DocumentWriteMode.Posting)',route.source())
    def test_pinned_owned_assets(self):
        _,assets=fixture.load_saved()
        self.assertEqual(set(assets),set(fixture.ASSET_HASHES)|{'generated/observe.bsl'})
    def test_existing_enum_and_reference_assets_are_unchanged(self):
        for name in ('Products.xml','Warehouses.xml','Units.xml','States.xml'):
            self.assertEqual((ROOT/'scripts/inventory_enum_behavior'/name).read_bytes(),
                             (ROOT/'scripts/inventory_typed_filter_behavior'/name).read_bytes())
    def test_program_nonce_and_budget(self):
        program=route.program(None,NONCE)
        from yadinassi.syntax.parser import parse
        parse(program.decode('utf-8'))
        self.assertLessEqual(len(program),32768)
        self.assertIn(('TVP|'+NONCE+'|entered').encode(),program)
        self.assertIn(('TVP|'+NONCE+'|completed').encode(),program)
    def test_bad_nonce(self):
        with self.assertRaises(ValueError):route.program(None,'bad')
    def test_ordered_wire(self):
        prefix='TVP|'+NONCE+'|'
        raw=('\n'.join([prefix+'entered',*[prefix+str(n)+'|empty' for n in range(1,13)],prefix+'completed'])+'\n').encode()
        self.assertEqual(route.parse_wire(raw,NONCE),['empty']*12)
        controlled=raw.replace(b'|empty',b'|execute-refused')
        self.assertEqual(route.parse_wire(controlled,NONCE),['execute-refused']*12)
        values,errors=route.parse_attempt(controlled,NONCE)
        self.assertEqual(values,[[i,'execute-refused'] for i in range(1,13)])
        self.assertEqual(errors,[])
        with self.assertRaises(ValueError):route.parse_wire(raw,'b'*32)
    def test_missing_group_refused(self):
        with self.assertRaises(ValueError):route.canonical(['empty']*11)
    def test_oversized_group_refused(self):
        with self.assertRaises(ValueError):route.canonical(['a'*4097]*12)
    def test_manifest_owns_new_observer_only(self):
        files=host.staged_files()
        self.assertIn('scripts/inventory_typed_filter_behavior/observe.bsl',files)
        self.assertNotIn('scripts/inventory_reference_behavior/observe.bsl',files)
        self.assertNotIn('scripts/accumulation_register_behavior/observe.bsl',files)
        for name in fixture.ASSET_HASHES:self.assertIn('scripts/inventory_typed_filter_behavior/'+name,files)
    def test_staging_revalidates_inputs(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            stage=Path(tmp).resolve()/'stage'
            hashes=host.stage_inputs(ROOT,stage,host.SMOKE)
            host.validate_inputs(stage,hashes,host.SMOKE)
            (stage/'bootstrap/inventory_typed_filter_behavior/observe.bsl').write_bytes(b'drift')
            with self.assertRaises(ValueError):host.validate_inputs(stage,hashes,host.SMOKE)
    def test_workflow_exact_branch_and_no_dispatch(self):
        source=(ROOT/'.github/workflows/native-1c-inventory-typed-filter.yml').read_text(encoding='utf-8')
        self.assertIn("head.ref == 'codex/db-typed-virtual-dimensions'",source)
        self.assertNotIn('workflow_dispatch',source)
        self.assertIn('Observe twelve cases',source)
    def test_material_reference_target_validation(self):
        raw=(ROOT/'scripts/inventory_typed_filter_behavior/Stock.xml').read_bytes()
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
        for token in (b'EmptyRef()', b'GROUP BY', b'LEFT JOIN', b'HAVING', b'IN (&Units)',
                      b'IN &Units', b'New FixedArray', b'Params.Units.Add(Null)', b'Params.Units.Add(U2)'):
            self.assertIn(token,source)
        self.assertIn(b'GetRef(New UUID(',source)
        self.assertNotIn(b'ExecuteBatch()',source)
        self.assertNotIn(b'FROM (SELECT',source)
        self.assertNotIn(b'.Unload()',source)
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
        self.assertIn(b'Return Rows(Q.Execute()',source)
    def test_scalar_dimension_and_line_material_projection(self):
        for path,kind in (('Stock.xml','AccumulationRegister'),('Receipt.xml','Document'),('Issue.xml','Document')):
            raw=(ROOT/'scripts/inventory_typed_filter_behavior'/path).read_bytes()
            for field,before,after in (('Batch',b'<v8:Length>32</v8:Length>',b'<v8:Length>31</v8:Length>'),
                                      ('Grade',b'<v8:FractionDigits>2</v8:FractionDigits>',b'<v8:FractionDigits>1</v8:FractionDigits>'),
                                      ('Reserved',b'xs:boolean',b'xs:string'),
                                      ('LotDate',b'<v8:DateFractions>DateTime</v8:DateFractions>',b'<v8:DateFractions>Date</v8:DateFractions>')):
                with self.subTest(path=path,field=field):
                    blocks=re.findall(rb'<(?:Dimension|Attribute)\s+uuid="[^"]+">.*?</(?:Dimension|Attribute)>',raw,re.S)
                    block=next(value for value in blocks if ('<Name>'+field+'</Name>').encode() in value)
                    self.assertIn(before,block)
                    changed=raw.replace(block,block.replace(before,after))
                    self.assertNotEqual(fixture._owned_projection(raw,kind),fixture._owned_projection(changed,kind))

    def test_seven_admitted_dimensions_and_same_field_ids_in_both_sources(self):
        import xml.etree.ElementTree as ET
        md='{http://v8.1c.ru/8.3/MDClasses}'
        base=ROOT/'scripts/inventory_typed_filter_behavior'
        signatures=[]
        for path in (base/'Stock.xml',base/'runtime_source/AccumulationRegisters/Stock.xml'):
            dims=ET.fromstring(path.read_bytes()).findall('.//'+md+'Dimension')
            signatures.append([(n.get('uuid'),n.find(md+'Properties/'+md+'Name').text) for n in dims])
        self.assertEqual(signatures[0],signatures[1])
        self.assertEqual([v[1] for v in signatures[0]],['Product','Warehouse','Unit','Batch','Grade','Reserved','LotDate'])

    def test_handler_matches_runtime_and_copies_all_four_dimensions(self):
        base=ROOT/'scripts/inventory_typed_filter_behavior'
        for document in ('Receipt','Issue'):
            native=(base/(document+'Module.bsl')).read_bytes()
            self.assertEqual(native,(base/'runtime_source/Documents'/document/'Ext/ObjectModule.bsl').read_bytes())
            for field in ('Batch','Grade','Reserved','LotDate'):
                self.assertIn(('Row.'+field+' = Line.'+field+';').encode(),native)

    def test_enum_target_and_order_remain_material(self):
        base=ROOT/'scripts/inventory_typed_filter_behavior'
        raw=(base/'Stock.xml').read_bytes()
        self.assertNotEqual(fixture._owned_projection(raw,'AccumulationRegister'),
                            fixture._owned_projection(raw.replace(b'cfg:EnumRef.Units',b'cfg:EnumRef.States'),'AccumulationRegister'))
        raw=(base/'Units.xml').read_bytes()
        changed=raw.replace(b'<Name>Piece</Name>',b'<Name>Changed</Name>')
        self.assertNotEqual(fixture._owned_projection(raw,'Enum'),fixture._owned_projection(changed,'Enum'))

    def test_direct_native_controls_do_not_swallow_setup_or_row_failures(self):
        source=route.source().decode('utf-8')
        control=source.split('Function Control(',1)[1].split('EndFunction',1)[0]
        self.assertIn('Try R=Q.Execute(); Except Return "execute-refused"; EndTry;',control)
        self.assertIn('Return Rows(R);',control)
        self.assertNotIn('Try',control.split('Q=Bound',1)[0])
        self.assertIn('AccumulationDiagnostic(CaseNo,Stage,',source)

    def test_source_bound_packet_has_narrow_lf_checkout_pins(self):
        attrs=(ROOT/'.gitattributes').read_text(encoding='utf-8').splitlines()
        for path in ('scripts/inventory_typed_filter_behavior/**',
                     'scripts/native_1c_inventory_typed_filter_profile.py',
                     'scripts/native_1c_inventory_typed_filter_probe.sh',
                     'scripts/native_1c_bootstrap/inventory_typed_filter_suite.py'):
            self.assertIn(path+' text eol=lf',attrs)
        self.assertNotIn(b'\r',route.source())

    def test_harness_preserves_isolation_and_no_parity_claim(self):
        source=(ROOT/'scripts/native_1c_inventory_typed_filter_profile.py').read_text(encoding='utf-8')
        self.assertIn("'--network', 'none'",source)
        self.assertIn("'--read-only'",source)
        self.assertIn("'runtime_parity_accepted':False",source.replace(' ',''))
