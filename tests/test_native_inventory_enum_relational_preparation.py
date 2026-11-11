"""Offline source/transport checks, not native values or host parity."""
from pathlib import Path
from copy import deepcopy
import base64
import hashlib
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from inventory_enum_relational_behavior import fixture, route
import native_1c_inventory_enum_relational_profile as host

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/inventory_enum_relational_behavior'
NONCE = 'a' * 32


def wire(values=None):
    values = ['empty'] * 12 if values is None else values
    prefix = 'ERQ|' + NONCE + '|'
    return ('\n'.join([prefix + 'entered',
        *[prefix + str(n) + '|' + value for n, value in enumerate(values, 1)],
        prefix + 'completed']) + '\n').encode('ascii')


class EnumRelationalPreparationTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher = mock.patch.object(host.FULL, 'read_regular', side_effect=read_synthetic_file)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_twelve_new_groups_and_pinned_observer(self):
        self.assertEqual(route.COUNT, 12)
        self.assertEqual(route.source().count(b'For CaseNo = 1 To 12 Do'), 1)
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(), route.SOURCE_SHA256)
        self.assertNotEqual(route.SOURCE_SHA256,
            __import__('inventory_typed_filter_behavior.route', fromlist=['route']).SOURCE_SHA256)

    def test_pinned_assets_match_existing_enum_material(self):
        _, assets = fixture.load_saved()
        self.assertEqual(set(assets), set(fixture.ASSET_HASHES) | {'generated/observe.bsl'})
        for name in fixture.ASSET_HASHES:
            self.assertEqual((SOURCE / name).read_bytes(),
                (ROOT / 'scripts/inventory_enum_behavior' / name).read_bytes())

    def test_authored_runtime_source_matches_existing_enum_grant(self):
        def files(path):
            return {p.relative_to(path).as_posix(): p.read_bytes()
                    for p in path.rglob('*') if p.is_file()}
        actual = files(SOURCE / 'runtime_source')
        self.assertEqual(len(actual), 10)
        self.assertEqual(actual, files(ROOT / 'scripts/inventory_enum_behavior/runtime_source'))

    def test_program_is_parseable_nonce_bound_and_bounded(self):
        from yadinassi.syntax.parser import parse
        program = route.program(None, NONCE)
        parse(program.decode('utf-8'))
        self.assertLessEqual(len(program), 32768)
        for marker in ('entered', 'completed'):
            self.assertIn(('ERQ|' + NONCE + '|' + marker).encode(), program)

    def test_invalid_nonce_refused(self):
        for value in ('bad', 'g' * 32, 'a' * 31):
            with self.subTest(value=value), self.assertRaises(ValueError):
                route.program(None, value)

    def test_wire_preserves_finite_controls(self):
        values = ['unit-piece,1;|null,2;|execute-refused'] * 12
        self.assertEqual(route.parse_wire(wire(values), NONCE), values)
        observed, errors = route.parse_attempt(wire(values), NONCE)
        self.assertEqual(observed, list(map(list, enumerate(values, 1))))
        self.assertEqual(errors, [])

    def test_wire_nonce_order_and_completion_required(self):
        for raw in (wire().replace(b'|1|', b'|2|', 1), wire().replace(b'|completed', b'|missing'),
                    wire().replace(NONCE.encode(), b'b' * 32)):
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                route.parse_wire(raw, NONCE)

    def test_partial_observations_cannot_be_complete_output(self):
        prefix = 'ERQ|' + NONCE + '|'
        raw = (prefix + 'entered\n' + prefix + '1|empty\n' +
               prefix + 'error|2|query|' + json.dumps('private native value') + '\n' +
               prefix + 'completed\n').encode()
        observed, errors = route.parse_attempt(raw, NONCE)
        self.assertEqual(observed, [[1, 'empty']])
        self.assertEqual(errors, [(2, 'query', 'private native value')])
        with self.assertRaises(ValueError):
            route.parse_wire(raw, NONCE)
        with self.assertRaises(ValueError):
            route.canonical([value for _, value in observed])

    def test_output_count_size_and_alphabet_closed(self):
        for values in (['empty'] * 11, ['a' * 4097] * 12, ['execute_refused'] * 12,
                       ['private/path'] * 12, [''] * 12):
            with self.subTest(sample=values[0][:20]), self.assertRaises(ValueError):
                route.canonical(values)

    def test_export_binds_exact_ordered_observations(self):
        data = route.canonical(['empty'] * 12)
        stage = dict(record_count=12, incomplete=False,
                     partial_observations=[[n, 'empty'] for n in range(1, 13)])
        self.assertEqual(host.validate_observation_binding(stage, data), ['empty'] * 12)
        for key, value in (('record_count', 11), ('incomplete', True),
                           ('partial_observations', [[n, 'empty'] for n in range(1, 12)]),
                           ('partial_observations', [[n, 'execute-refused'] for n in range(1, 13)])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                host.validate_observation_binding(dict(stage, **{key: value}), data)

    def test_success_envelope_requires_every_current_witness(self):
        # Isolate the new stage validator; the unchanged stage-one/two report
        # validator has its own gates. These are synthetic values, not a golden.
        data = route.canonical(['empty'] * 12)
        hashes = {name: 'b' * 64 for name in host.staged_files()}
        hashes[host.SOURCE] = route.SOURCE_SHA256
        module = host.FULL.digest(host.FULL.generated_module(route.program(None, NONCE)))
        stage = dict(schema=host.STAGE_SCHEMA, profile=host.PROFILE, nonce=NONCE,
            status='ok', failure_kind='none', failure_phase='final', input_sha256=hashes,
            source_sha256=route.SOURCE_SHA256, module_sha256=module, module_verified_sha256=module,
            output_sha256=host.FULL.digest(data), output_size=len(data), record_count=12,
            process_diagnostics=dict(stage='after_exit', reason='none', unexpected_count=0,
                zombie_count=0, classes={k: 0 for k in ('native','display','session_bus','shell','python','other','unreadable')}),
            redump_diagnostic=[], configuration_validation=fixture.VALIDATION_MODE,
            native_error_category='none', native_error_details=None, install_diagnostics=[],
            partial_observations=[[n, 'empty'] for n in range(1, 13)], case_diagnostics=[], incomplete=False,
            **{name: True for name in host.FLAGS})
        value = dict(schema=host.SCHEMA, profile=host.PROFILE, nonce=NONCE,
            report=dict(status='ok', native_tests_completed=True, stage3=stage),
            outputs=[dict(name='inventory-enum-relational.out', size=len(data),
                sha256=host.FULL.digest(data), data_b64=base64.b64encode(data).decode('ascii'))])
        def validate(candidate):
            return host.validate_envelope(json.dumps(candidate).encode(), NONCE, hashes,
                validator=lambda raw, **kwargs: json.loads(raw))
        self.assertEqual(validate(value)[1], data)
        changes = [(name, False) for name in host.FLAGS] + [
            ('record_count', 11), ('incomplete', True), ('partial_observations', []),
            ('module_verified_sha256', 'c' * 64), ('input_sha256', {}),
            ('native_error_details', route.failure_details({'messages': [], 'error': 'private'}, NONCE))]
        for key, changed in changes:
            candidate = deepcopy(value)
            candidate['report']['stage3'][key] = changed
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(candidate)
        candidate = deepcopy(value)
        candidate['outputs'] = []
        with self.assertRaises(ValueError):
            validate(candidate)

    def test_failure_diagnostics_do_not_export_native_text(self):
        text = '{TestModule(12)}: Ошибка в запросе (Execute) private-secret-value'
        details = route.failure_details({'messages': [], 'error': text}, NONCE)
        self.assertTrue(route.valid_failure_details(details))
        self.assertNotIn('private-secret-value', json.dumps(details))
        diagnostic = route.install_diagnostic('password=private-secret-value\nUnknown Receipt', 'load')
        self.assertTrue(route.valid_install_diagnostic(diagnostic))
        self.assertNotIn('private-secret-value', json.dumps(diagnostic))

    def test_manifest_owns_only_new_observer_and_material(self):
        files = host.staged_files()
        self.assertIn('scripts/inventory_enum_relational_behavior/observe.bsl', files)
        for old in ('inventory_enum_behavior', 'inventory_typed_filter_behavior', 'inventory_filter_behavior'):
            self.assertNotIn('scripts/' + old + '/observe.bsl', files)
        for name in fixture.ASSET_HASHES:
            self.assertIn('scripts/inventory_enum_relational_behavior/' + name, files)
        self.assertLessEqual(len(files), 64)

    def test_staged_source_revalidated_after_copy(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            stage = Path(tmp).resolve() / 'stage'
            hashes = host.stage_inputs(ROOT, stage, host.SMOKE)
            host.validate_inputs(stage, hashes, host.SMOKE)
            (stage / 'bootstrap/inventory_enum_relational_behavior/observe.bsl').write_bytes(b'drift')
            with self.assertRaises(ValueError):
                host.validate_inputs(stage, hashes, host.SMOKE)

    def test_material_catalog_and_enum_targets_validated(self):
        raw = (SOURCE / 'Stock.xml').read_bytes()
        for before, after in ((b'cfg:CatalogRef.Products', b'cfg:CatalogRef.Warehouses'),
                              (b'cfg:EnumRef.Units', b'cfg:EnumRef.States')):
            self.assertIn(before, raw)
            self.assertNotEqual(fixture._owned_projection(raw, 'AccumulationRegister'),
                fixture._owned_projection(raw.replace(before, after), 'AccumulationRegister'))

    def test_enum_element_order_is_material(self):
        import xml.etree.ElementTree as ET
        raw = (SOURCE / 'Units.xml').read_bytes()
        root = ET.fromstring(raw)
        children = root.find('.//{http://v8.1c.ru/8.3/MDClasses}ChildObjects')
        first, _ = list(children)
        children.remove(first)
        children.append(first)
        self.assertNotEqual(fixture._owned_projection(raw, 'Enum'),
            fixture._owned_projection(ET.tostring(root), 'Enum'))

    def test_module_drift_and_unknown_files_refused(self):
        path = 'Documents/Receipt/Ext/ObjectModule.bsl'
        expected = {path: (SOURCE / 'ReceiptModule.bsl').read_bytes()}
        with self.assertRaises(ValueError):
            fixture.verify_redump(expected, {path: b'Procedure Changed()\nEndProcedure\n'})
        with self.assertRaises(ValueError):
            fixture.verify_redump({}, {'unknown.xml': b'<x/>'})

    def test_array_spellings_are_separate_from_singleton_scalar_control(self):
        source = route.source().split(b'ElsIf CaseNo=2 Then')[0]
        for token in (b'P.Unit IN (&One)', b'P.Unit IN (&Units)', b'P.Unit IN &Units',
                      b'New FixedArray(Params.Units)', b'P.Unit=&Unit'):
            self.assertIn(token, source)

    def test_null_empty_wrong_domain_and_nullable_inputs_are_observed(self):
        source = route.source()
        for token in (b'Params.Units=New Array', b'Params.Units.Add(Null)', b'Values(UE,Null)',
                      b'P.Unit NOT IN (&Units)', b'R.Unit NOT IN (&Units)',
                      b'Values(Enums.States.Draft,Enums.States.Approved)', b'Values(U,"owned")'):
            self.assertIn(token, source)

    def test_compound_outputs_and_empty_arm_controls_are_observed(self):
        source = route.source()
        for token in (b'CASE WHEN', b'ISNULL(R.Unit,P.Unit)', b'ISNULL(P.Unit,&OtherUnit)',
                      b'ISNULL(NULL,&Unit)', b'ELSE &State END', b'ELSE 5 END',
                      b'WrongEmpty', b'Empty+" UNION ALL "+WrongEmpty'):
            self.assertIn(token, source)

    def test_direct_compositions_cover_all_three_stock_tables(self):
        source = route.source()
        for token in (b'Stock.Balance(', b'Stock.Turnovers(', b'Stock.BalanceAndTurnovers(',
                      b'COUNT(DISTINCT T.Unit)', b'GROUP BY T.Unit', b'HAVING R.Unit IN',
                      b'LEFT JOIN (', b' UNION ALL ', b' UNION ', b'FROM (SELECT'):
            self.assertIn(token, source)

    def test_query_result_and_parameter_mutation_are_distinct_observations(self):
        source = route.source().split(b'ElsIf CaseNo=11 Then')[1].split(b'ElsIf CaseNo=12 Then')[0]
        self.assertLess(source.index(b'Params.Units.Add(U2)'), source.index(b'Old=Q.Execute()'))
        self.assertIn(b'Params.Units.Clear()', source)
        self.assertIn(b'Detached=Rows(Old)', source)
        self.assertIn(b'Q.SetParameter("Units",Params.Units)', source)

    def test_case12_observes_staged_rollback_repost_and_unpost(self):
        source = route.source().split(b'ElsIf CaseNo=12 Then')[1]
        self.assertIn(b'BeginTransaction()', source)
        self.assertEqual(source.count(b'RollbackTransaction()'), 2)
        self.assertIn(b'Target.Write(DocumentWriteMode.Posting)', source)
        self.assertIn(b'Target.Write(DocumentWriteMode.UndoPosting)', source)

    def test_control_catches_only_execute_not_setup_or_serialization(self):
        source = route.source().decode('utf-8')
        control = source.split('Function Control(', 1)[1].split('EndFunction', 1)[0]
        self.assertIn('Try R=Q.Execute(); Except Return "execute-refused"; EndTry;', control)
        self.assertIn('Return Rows(R);', control)
        self.assertLess(control.index('Q=Bound'), control.index('Try'))
        self.assertIn('AccumulationDiagnostic(CaseNo,Stage,', source)

    def test_rows_and_dates_bounded_without_closed_apis(self):
        source = route.source()
        self.assertIn(b'If Tokens.Count()>=32 Then Raise', source)
        for args in re.findall(rb'Date\(([^()]+)\)', source):
            self.assertIn(len(args.split(b',')), (3, 6))
        for token in (b'ExecuteBatch', b'TempTablesManager', b'.Unload()', b'Result.Columns', b'ORDER BY'):
            self.assertNotIn(token, source)

    def test_lf_pins_for_all_new_source_bound_paths(self):
        attrs = (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
        for path in ('scripts/inventory_enum_relational_behavior/**',
                     'scripts/native_1c_inventory_enum_relational_profile.py',
                     'scripts/native_1c_inventory_enum_relational_probe.sh',
                     'scripts/native_1c_bootstrap/inventory_enum_relational_suite.py',
                     'scripts/native_1c_enum_relational_ci_policy.py'):
            self.assertIn(path + ' text eol=lf', attrs)
        self.assertNotIn(b'\r', route.source())

    def test_isolation_cleanup_and_no_parity_claim_preserved(self):
        source = (ROOT / 'scripts/native_1c_inventory_enum_relational_profile.py').read_text(encoding='utf-8')
        for token in ("'--network', 'none'", "'--read-only'", 'DOCKER.run_owned',
                      "'private_cleanup_unverified'", 'validate_envelope(', 'export_artifact('):
            self.assertIn(token, source)
        self.assertIn("'runtime_parity_accepted':False", source.replace(' ', ''))
        self.assertLess(source.index('DOCKER.run_owned'), source.index('export_artifact(root,'))
        self.assertLess(source.index("require(not Path(directory).exists()"), source.index('export_artifact(root,'))

    def test_suite_requires_material_redump_exit_quiet_and_module_witness(self):
        source = (ROOT / 'scripts/native_1c_bootstrap/inventory_enum_relational_suite.py').read_text(encoding='utf-8')
        for token in ('fixture.verify_redump(expected,actual)', 'launcher.run_case(',
                      "report['process_exited']=True", "if not report['quiet']", 'module_verified_sha256',
                      'full.final_client_process_census(nonce)', 'if not quiet or bus_cleanup_failed'):
            self.assertIn(token, source)
        self.assertLess(source.index('fixture.verify_redump(expected,actual)'), source.index('launcher.run_case('))

    def test_probe_has_owned_export_and_no_raw_log_artifacts(self):
        workflow = (ROOT / '.github/workflows/native-1c-enum-relational.yml').read_text(encoding='utf-8')
        self.assertIn('inventory_enum_relational_outputs_ready', workflow)
        self.assertNotIn('*.log', workflow)
        self.assertIn('inventory-enum-relational-outputs/inventory-enum-relational.out', workflow)
        probe = (ROOT / 'scripts/native_1c_inventory_enum_relational_probe.sh').read_text(encoding='utf-8')
        self.assertIn('inventory_enum_relational_suite.py', probe)
        self.assertIn('finish_report', probe)
