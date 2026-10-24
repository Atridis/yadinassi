"""Synthetic bounded-shape protocol/source tests, never native compatibility proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_db_oracle'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract
import inputs
import protocol
import snapshots
from snapshots import OracleError
import test_native_1c_db_oracle_stage as fixtures

NONCE = fixtures.NONCE
TOKEN = 'd' * 32


def shape():
    return {'schema': 1, 'target': contract.TARGET, 'nesting': 'observed_value_tables_only',
        'tables': [{'parent': None, 'via_column': None,
                    'columns': [{'name': 'DiscoveredColumn', 'types': ['Строка']},
                                {'name': 'UnpredictedNested', 'types': []}]},
                   {'parent': 0, 'via_column': 1,
                    'columns': [{'name': 'AnotherName', 'types': ['Число']}]}]}


def identity():
    value = fixtures.provenance()
    value['sources'] = {source: 'c' * 64 for source in inputs.SOURCE_FILES}
    return value


def marker(token=TOKEN):
    return {'schema': 1, 'nonce': NONCE, 'token': token, 'operation': 'audit_contract',
        'status': 'ok', 'actual_version': protocol.VERSION, 'user': 'NativeOracleSetup',
        'role_verified': True, 'nonprivileged': True, 'users_verified': True,
        'metadata_version': 1, 'payload_length': 32, 'amount_digits': 9, 'amount_scale': 2,
        **{name: None for name in ('count', 'code', 'payload', 'amount', 'deletion_mark', 'same_reference')},
        'storage_shape': shape()}


class ShapeBackend(fixtures.FixtureNative):
    def audit_contract(self, identifier):
        self.event('audit_contract_clone', identifier)
        return marker()


def fixture(fail=None, cleanup=(True, True)):
    provenance = identity()
    report = contract.empty_report(NONCE, provenance)
    backend = ShapeBackend(provenance, fail); backend.clean = cleanup
    controller = fixtures.stage.Controller(backend, report); backend.controller = controller
    return controller.run(), backend


class ContractEnvelopeTests(unittest.TestCase):
    def check(self, report, final=False):
        return contract.validate_report(protocol.encode(report), nonce=NONCE,
                                        provenance=identity(), final=final)

    def test_exact_stage_snapshot_counts_and_baseline_only_launch(self):
        report, backend = fixture()
        self.check(report)
        self.assertEqual(len(report['stages']), 13)
        self.assertEqual(len(report['snapshots']), 11)
        self.assertEqual([x for x in backend.events if x[0].startswith('audit')],
                         [('audit_contract_clone', 'baseline'), ('audit_clone', 'restored')])
        self.assertEqual(report['storage_contract']['status'], 'shape_captured')
        self.assertEqual(report['reader_validation'], 'not_run')
        self.assertEqual(report['native_compatibility'], 'not_claimed')
        self.assertFalse(report['accepted'])
        report['cleanup'].update(container_removed=True, private_staging_removed=True)
        report['accepted'] = True
        self.check(report, True)

    def test_historical_v2_is_never_upgraded_or_accepted(self):
        old, _ = fixtures.fixture_report()
        with self.assertRaises(OracleError): self.check(old)
        protocol.validate_report(protocol.encode(old), nonce=NONCE, provenance=fixtures.provenance())

    def test_source_inventory_is_exact_not_a_tiny_expected_fixture(self):
        report, _ = fixture()
        report['provenance']['sources'] = {'synthetic': 'c' * 64}
        with self.assertRaises(OracleError):
            contract.validate_report(protocol.encode(report), nonce=NONCE,
                                     provenance=report['provenance'])

    def test_provenance_constants_remain_bounded_even_if_expected_is_forged(self):
        for key in ('image', 'platform', 'locale', 'timezone'):
            report, _ = fixture(); report['provenance'][key] = 'x' * 1000
            with self.subTest(key=key), self.assertRaises(OracleError):
                contract.validate_report(protocol.encode(report), nonce=NONCE,
                                         provenance=report['provenance'])

    def test_forged_stale_bindings_raw_keys_and_compatibility_claims_rejected(self):
        good, _ = fixture()
        edits = [lambda r: r.update(schema=2), lambda r: r.update(reader_validation='passed'),
            lambda r: r.update(native_compatibility='verified'),
            lambda r: r['storage_contract'].update(status='accepted'),
            lambda r: r['storage_contract'].update(schema=True),
            lambda r: r['storage_contract'].update(operation='audit'),
            lambda r: r['storage_contract'].update(token='stale'),
            lambda r: r['storage_contract'].update(nonce='b' * 32),
            lambda r: r['storage_contract'].update(source_manifest_sha256='b' * 64),
            lambda r: r['storage_contract'].update(snapshot='restored'),
            lambda r: r['storage_contract'].update(snapshot_sha256='b' * 64),
            lambda r: r['storage_contract'].update(actual_version='8.3.27.1'),
            lambda r: r['storage_contract'].update(raw_schema='PRIVATE'),
            lambda r: r.update(storage_contract=None)]
        for index, edit in enumerate(edits):
            with self.subTest(index=index):
                report = copy.deepcopy(good); edit(report)
                with self.assertRaises(OracleError): self.check(report)

    def test_each_failure_discards_capture_and_native_cleanup_cannot_be_accepted(self):
        for stage in protocol.STAGES[:-1]:
            with self.subTest(stage=stage):
                report, _ = fixture(stage)
                self.check(report)
                self.assertIsNone(report['storage_contract'])
                self.assertFalse(report['accepted'])
        for cleanup in ((False, True), (True, False), (False, False)):
            report, _ = fixture(cleanup=cleanup); self.check(report)
            self.assertIsNone(report['storage_contract'])
            self.assertEqual(report['failure_kind'], 'cleanup_unverified')
        good, _ = fixture()
        good['cleanup'].update(container_removed=False, private_staging_removed=True)
        with self.assertRaises(OracleError): self.check(good, True)

    def test_shape_cannot_survive_failed_report_even_if_it_preceded_failure(self):
        good, _ = fixture(); failed, _ = fixture('create')
        failed['storage_contract'] = good['storage_contract']
        with self.assertRaises(OracleError): self.check(failed)

    def test_strict_fresh_native_marker_identity_and_extra_fields(self):
        good = marker()
        protocol.marker(protocol.encode(good), nonce=NONCE, token=TOKEN, operation='audit_contract')
        edits = [lambda m: m.update(user='NativeOracleCRUD'), lambda m: m.update(nonprivileged=False),
                 lambda m: m.update(users_verified=False), lambda m: m.update(token='e' * 32),
                 lambda m: m.update(nonce='b' * 32), lambda m: m.update(operation='audit'),
                 lambda m: m.update(actual_version='8.3.0.0'), lambda m: m.update(metadata_version=2),
                 lambda m: m.update(count=1), lambda m: m.update(raw='PRIVATE')]
        for edit in edits:
            value = copy.deepcopy(good); edit(value)
            with self.assertRaises(OracleError):
                protocol.marker(protocol.encode(value), nonce=NONCE, token=TOKEN, operation='audit_contract')
        with self.assertRaises(OracleError):
            protocol.marker(protocol.encode(good), nonce=NONCE, token=TOKEN, operation='audit')


class ShapeValidationTests(unittest.TestCase):
    def test_unknown_names_declared_types_empty_types_and_unobserved_nesting_preserved(self):
        value = shape()
        self.assertIs(contract.validate_shape(value), value)
        value['tables'] = value['tables'][:1]
        self.assertEqual(contract.validate_shape(value)['nesting'], 'observed_value_tables_only')
        value['tables'][0]['columns'] = []
        contract.validate_shape(value)

    def test_invalid_shape_names_types_parent_links_and_raw_values(self):
        edits = [lambda s: s.update(schema=True), lambda s: s.update(target='Справочник.Other'),
            lambda s: s.update(nesting='exhaustive'), lambda s: s.update(rows=['PRIVATE']),
            lambda s: s['tables'][0].update(parent=0),
            lambda s: s['tables'][1].update(parent=1),
            lambda s: s['tables'][1].update(parent=True),
            lambda s: s['tables'][1].update(via_column=2),
            lambda s: s['tables'][0]['columns'][0].update(value='PRIVATE'),
            lambda s: s['tables'][0]['columns'][0].update(name=''),
            lambda s: s['tables'][0]['columns'][0].update(name='x\n'),
            lambda s: s['tables'][0]['columns'][0].update(name='\ud800'),
            lambda s: s['tables'][0]['columns'][0].update(name='\U0001f642'),
            lambda s: s['tables'][0]['columns'][0].update(types=['Строка', 'Строка']),
            lambda s: s['tables'][0]['columns'][0].update(types=[{'metadata': 'PRIVATE'}])]
        for index, edit in enumerate(edits):
            value = shape(); edit(value)
            with self.subTest(index=index), self.assertRaises(OracleError): contract.validate_shape(value)

    def test_every_independent_output_cap_fails_closed(self):
        values = []
        value = shape(); value['tables'] *= 9; values.append(value)
        value = shape(); value['tables'][0]['columns'][0]['name'] = 'x' * 65; values.append(value)
        value = shape(); value['tables'][0]['columns'][0]['types'] = ['x' + str(i) for i in range(9)]; values.append(value)
        value = shape(); value['tables'][0]['columns'] = [{'name': 'C'+str(i), 'types': []} for i in range(33)]; values.append(value)
        value = shape(); value['tables'] = [{'parent': None, 'via_column': None, 'columns': [{'name': 'C', 'types': []}]}]
        for i in range(4): value['tables'].append({'parent': i, 'via_column': 0, 'columns': [{'name': 'C', 'types': []}]})
        values.append(value)
        value = shape(); value['tables'] = [{'parent': None, 'via_column': None, 'columns': [{'name': 'C', 'types': []}]}]
        value['tables'] += [{'parent': 0, 'via_column': 0, 'columns': [{'name': chr(100+i), 'types': []} for i in range(32)]} for _ in range(2)]
        values.append(value)
        value = shape(); value['tables'][0]['columns'] = [{'name': 'C'+str(i), 'types': [chr(100+n) for n in range(8)]} for i in range(17)]; values.append(value)
        value = shape(); value['tables'][0]['columns'] = [{'name': str(i)+'x'*63, 'types': ['y'*64]} for i in range(7)]; values.append(value)
        for index, value in enumerate(values):
            with self.subTest(index=index), self.assertRaises(OracleError) as error: contract.validate_shape(value)
            self.assertEqual(error.exception.kind, 'artifact_limit')

    def test_encoded_shape_cap_is_checked_independently_no_truncation(self):
        with mock.patch.object(contract, 'MAX_SHAPE_BYTES', 10), self.assertRaises(OracleError) as error:
            contract.validate_shape(shape())
        self.assertEqual(error.exception.kind, 'artifact_limit')


class NativeShapeBoundaryTests(unittest.TestCase):
    # Reuse existing hardened file-boundary setup, not its create-specific tests.
    def setUp(self):
        fixtures.CommandCompletionBoundaryTests.setUp(self)
        self.native.begin_stage('baseline')

    def test_contract_missing_partial_stale_or_error_completion_rejected(self):
        cases = [('ok', 'complete', True, False), (None, 'complete', True, True),
                 ('ok', 'complete', False, True), ('ok', 'contract_scan', True, True),
                 ('error', 'contract_scan', True, True), ('error', 'contract_limit', True, True)]
        for status, phase, result, rejected in cases:
            commands = []
            def process(args, *unused, **kwargs):
                commands.append(args)
                control = json.loads((self.native.evidence/'control.json').read_text())
                self.assertEqual(set(control), {'schema', 'nonce', 'token', 'operation'})
                self.assertEqual(control['operation'], 'audit_contract')
                if status is not None:
                    (self.native.evidence/'completion.json').write_bytes(protocol.encode({**control, 'phase': phase, 'status': status}))
                if result:
                    (self.native.evidence/'result.json').write_bytes(protocol.encode(marker(control['token'])))
            with self.subTest(status=status, phase=phase, result=result), mock.patch.object(self.native, 'process', side_effect=process):
                if rejected:
                    with self.assertRaises(OracleError) as error: self.native.enterprise(self.db, 'audit_contract')
                    if phase == 'contract_limit': self.assertEqual(error.exception.kind, 'artifact_limit')
                else:
                    self.native.enterprise(self.db, 'audit_contract')
            self.assertEqual(len(commands), 1)
            self.assertIn('NativeOracleSetup', commands[0])
            self.assertEqual(list(self.native.evidence.iterdir()), [])

    def test_contract_stale_control_and_partial_publication_never_launch_or_accept(self):
        for name in ('control.json', 'result.json', 'completion.json', 'completion.pending.json'):
            path = self.native.evidence/name; path.write_text('PRIVATE')
            with self.subTest(name=name), mock.patch.object(self.native, 'process') as process:
                with self.assertRaises(OracleError): self.native.enterprise(self.db, 'audit_contract')
                process.assert_not_called()
            path.unlink()
        for partial in ('completion.json', 'result.json', 'completion.pending.json'):
            def process(*args, **kwargs):
                control = json.loads((self.native.evidence/'control.json').read_text())
                (self.native.evidence/'completion.json').write_bytes(protocol.encode({**control, 'status': 'ok', 'phase': 'complete'}))
                (self.native.evidence/'result.json').write_bytes(protocol.encode(marker(control['token'])))
                (self.native.evidence/partial).write_bytes(b'{')
            with self.subTest(partial=partial), mock.patch.object(self.native, 'process', side_effect=process):
                with self.assertRaises(OracleError): self.native.enterprise(self.db, 'audit_contract')
            self.assertEqual(list(self.native.evidence.iterdir()), [])

    def test_contract_audit_clone_scope_and_removal_required(self):
        self.native.begin_stage('baseline')
        with mock.patch.object(self.native, 'clone', return_value=self.db) as clone, \
             mock.patch.object(self.native, 'enterprise', return_value=marker()) as enter, \
             mock.patch.object(self.native, 'remove') as remove:
            self.native.audit_contract('baseline')
            clone.assert_called_once_with('baseline', 'auditor')
            enter.assert_called_once_with(self.db, 'audit_contract'); remove.assert_called_once_with(self.db)
        with mock.patch.object(self.native, 'clone') as clone, self.assertRaises(OracleError):
            self.native.audit_contract('restored')
        clone.assert_not_called()
        self.native.begin_stage('verify_restore')
        with self.assertRaises(OracleError): self.native.audit_contract('baseline')
        with mock.patch.object(self.native, 'process') as process, self.assertRaises(OracleError):
            self.native.enterprise(self.db, 'audit_contract')
        process.assert_not_called()


class ShapeSourceTests(unittest.TestCase):
    def test_one_filtered_call_no_scalar_rendering_or_guessed_nested_names(self):
        source = (ROOT/'scripts/native_1c_db_oracle/modules/NativeOracleServer.bsl').read_text()
        probe = source[source.index('// Shape-only diagnostic:'):source.index('Функция NativeНовыйРезультат')]
        self.assertEqual(probe.count('ПолучитьСтруктуруХраненияБазыДанных('), 1)
        self.assertIn('ПолучитьСтруктуруХраненияБазыДанных(Отбор)', probe)
        self.assertEqual(probe.count('Отбор.Добавить('), 1)
        self.assertIn('Отбор.Добавить("Справочник.NativeOracleItems")', probe)
        self.assertEqual(probe.count('Строка('), 1)
        self.assertIn('Строка(ОбъявленныйТип)', probe)
        for forbidden in ('ОписаниеОшибки', 'ИнформацияОбОшибке', 'Таблица.Fields', 'Таблица.Indexes',
                          'StorageTableName', 'StorageFieldName', 'Метаданные.', 'Выполнить('):
            self.assertNotIn(forbidden, probe)
        self.assertIn('ТипЗнч(СтрокаТаблицы[НомерКолонки]) = Тип("ТаблицаЗначений")', probe)
        self.assertEqual(protocol.COMMAND_STAGES['enterprise_audit_contract'], ('baseline',))
        self.assertIn('contract_limit', protocol.BSL_OPERATION_PHASES['audit_contract'])

    def test_native_and_python_caps_are_pinned_together(self):
        source = (ROOT/'scripts/native_1c_db_oracle/modules/NativeOracleServer.bsl').read_text()
        for snippet in ('Длина <= 64', 'Бюджет.units + Длина <= 768', 'Глубина <= 3',
                        'Форма.tables.Количество() < 16', 'ЧислоКолонок <= 32',
                        'Бюджет.columns + ЧислоКолонок <= 64', 'Бюджет.rows + ЧислоСтрок <= 256',
                        'Бюджет.cells + ЧислоСтрок * ЧислоКолонок <= 4096', 'Типы.Количество() <= 8',
                        'Бюджет.types + Типы.Количество() <= 128'):
            self.assertIn(snippet, source)
        self.assertEqual((contract.MAX_TEXT, contract.MAX_TEXT_UNITS, contract.MAX_DEPTH,
                          contract.MAX_TABLES, contract.MAX_COLUMNS, contract.MAX_TOTAL_COLUMNS,
                          contract.MAX_ROWS, contract.MAX_CELLS, contract.MAX_TYPES, contract.MAX_TOTAL_TYPES),
                         (64, 768, 3, 16, 32, 64, 256, 4096, 8, 128))


def shape_size_upper_bound():
    """Independent-maxima serialization, intentionally not an admissible shape.

    All 16 table containers use null links (longer than bounded indices). Pack
    columns/types to maximize separators, and put the entire 768-unit aggregate
    text allowance into one escaped BMP string. Individual limits/uniqueness
    only shrink real manifests. No native/private schema is used here.
    """
    value = {'schema': 1, 'target': contract.TARGET, 'nesting': 'observed_value_tables_only',
             'tables': [{'parent': None, 'via_column': None, 'columns': []}
                        for _ in range(contract.MAX_TABLES)]}
    for index in range(contract.MAX_TOTAL_COLUMNS):
        value['tables'][index // contract.MAX_COLUMNS]['columns'].append({'name': '', 'types': []})
    columns = [column for table in value['tables'] for column in table['columns']]
    for index in range(contract.MAX_TOTAL_TYPES):
        columns[index // contract.MAX_TYPES]['types'].append('')
    columns[0]['name'] = '\uffff' * contract.MAX_TEXT_UNITS
    return len(protocol.encode(value))


def whole_report_size_upper_bound():
    """Bound every field of the complete compact ASCII report plus newline.

    Deliberately combine mutually exclusive failure diagnostics, maximal stages,
    all 11 snapshots, 3 opaque artifacts, 5 comparisons, captured shape, and
    failed cleanup. All integers use a value with at least their maximum encoded
    width, even where that violates algebra. This is an upper bound, NOT a fake
    accepted report or assertion that all these facts can coexist.
    """
    longest = lambda values: max(values, key=lambda value: len(protocol.encode(value)))
    report = contract.empty_report(NONCE, identity())
    report.update(status='failed', failed_stage=longest(protocol.STAGES),
                  failure_kind=longest(protocol.FAILURES))
    report['provenance']['actual_version'] = protocol.VERSION
    # The stage names/check keys are exact; false/not_started are the longest.
    physical = {'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'f' * 64,
        'header': {'status': 'header_layout_match', 'version': [8, 2, 14, 0],
                   'page_size': 65536, 'page_count': (1 << 32)-1}, 'page_analysis': 'unsupported'}
    report['snapshots'] = [{'id': identifier, 'physical': copy.deepcopy(physical),
        'logical': protocol.expected_logical(identifier), 'quiescent': True, 'copy_verified': True}
        for identifier in protocol.SNAPSHOTS]
    report['artifacts'] = [{'id': name, 'source': source, 'status': 'ok',
        'physical': {'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'f'*64,
                     'header': 'unknown', 'page_analysis': 'unsupported'}}
        for name, source in protocol.ARTIFACTS.items()]
    counts = {key: snapshots.MAX_FILE_BYTES for key in ('changed_bytes', 'unchanged_bytes',
        'added_bytes', 'removed_bytes', 'changed_windows')}
    counts['size_delta'] = -snapshots.MAX_FILE_BYTES
    sample = [snapshots.MAX_FILE_BYTES] * snapshots.MAX_SAMPLES
    for name, (source, control, treatment) in protocol.COMPARISONS.items():
        pair = {'predecessor_bytes': snapshots.MAX_FILE_BYTES, 'treatment_bytes': snapshots.MAX_FILE_BYTES,
                'treatment': counts.copy()}
        windows = {'window_bytes': snapshots.WINDOW_BYTES, 'count': snapshots.MAX_FILE_BYTES}
        if control is None:
            pair['interpretation'] = 'observational_before_after_not_causation'
            windows.update(changed_count=snapshots.MAX_FILE_BYTES, changed_sample=sample.copy())
        else:
            pair.update(control_bytes=snapshots.MAX_FILE_BYTES, control=counts.copy(),
                        interpretation='physical_byte_differences_not_causation')
            for category in ('overlap', 'control_only', 'treatment_only'):
                windows[category+'_count'] = snapshots.MAX_FILE_BYTES
                windows[category+'_sample'] = sample.copy()
        pair['byte_windows'] = windows
        report['comparisons'].append({'id': name, 'kind': 'observational' if control is None else 'matched_control',
            'source': source, 'control': control, 'treatment': treatment, 'physical': pair})
    report['rejected_basename'] = '1Cv8' + 'X' * 48
    report['failure_context'] = {'operation': longest(protocol.COMMAND_STAGES),
        'site': longest(protocol.CONTEXT_SITES), 'bsl_phase': longest(protocol.BSL_PHASES),
        'region': longest(protocol.INVENTORY_REGIONS), 'reason': longest(protocol.INVENTORY_REASONS),
        'entry_class': longest(snapshots.ENTRY_CLASSES), 'entry_shape': longest(snapshots.ENTRY_SHAPES)}
    report['storage_contract'] = {'schema': 1, 'status': 'shape_captured', 'operation': 'audit_contract',
        'nonce': NONCE, 'token': TOKEN, 'source_manifest_sha256': 'f' * 64, 'snapshot': 'baseline',
        'snapshot_sha256': 'f' * 64, 'actual_version': protocol.VERSION, 'shape': None}
    # Replace the four-byte null with the independently enforced encoded shape
    # maximum, not a tiny successful fixture, then include the transport newline.
    return len(protocol.encode(report)) - len(b'null') + contract.MAX_SHAPE_BYTES + 1


class WholeReportBudgetTests(unittest.TestCase):
    def test_complete_encoded_report_has_proven_headroom_not_only_shape_budget(self):
        self.assertEqual(len(identity()['sources']), len(inputs.SOURCE_FILES))
        self.assertIn('scripts/native_1c_db_oracle/contract.py', identity()['sources'])
        self.assertEqual(shape_size_upper_bound(), 7350)
        self.assertLessEqual(shape_size_upper_bound(), contract.MAX_SHAPE_BYTES)
        self.assertEqual(whole_report_size_upper_bound(), 25875)
        self.assertLess(whole_report_size_upper_bound(), protocol.MAX_REPORT_BYTES)
        self.assertEqual(protocol.MAX_REPORT_BYTES, 32768)

    def test_source_binding_is_canonical_and_not_dictionary_order_dependent(self):
        first = identity(); second = copy.deepcopy(first)
        second['sources'] = dict(reversed(list(second['sources'].items())))
        self.assertEqual(contract.source_binding(first), contract.source_binding(second))

    def test_full_transport_limit_is_not_raised_and_exact_limit_fails_encoding(self):
        with self.assertRaises(OracleError) as error: protocol.encode('x' * (32768 - 2))
        self.assertEqual(error.exception.kind, 'artifact_limit')


class ExecutedShapeSourceTests(unittest.TestCase):
    """Execute exact BSL helpers under a controlled Python interpreter only."""
    def run_probe(self, setup):
        from yadinassi import Interpreter
        from yadinassi.native_targets import LINUX_8_3_27_1508
        from test_native_async_error_transport import encode as transport_encode
        vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
        vm.execute(setup)
        calls = []
        table = vm.execute('ТестоваяТаблица')
        def get_structure(selector):
            calls.append(selector)
            self.assertEqual(list(selector), [contract.TARGET])
            return table
        vm.register_function('ПолучитьСтруктуруХраненияБазыДанных', get_structure)
        source = (ROOT/'scripts/native_1c_db_oracle/modules/NativeOracleServer.bsl').read_text()
        helpers = source[source.index('// Shape-only diagnostic:'):source.index('Функция NativeНовыйРезультат')]
        vm.execute(helpers + '\nКонтекст = Новый Структура("phase", "dispatch");')
        try:
            vm.execute('Форма = NativeФормаХранения(Контекст);')
        except BaseException:
            self.assertEqual(len(calls), 1)
            return vm, None
        self.assertEqual(len(calls), 1)
        return vm, json.loads(transport_encode(vm.execute('Форма')))

    def test_real_helper_discovers_nested_tables_without_exporting_scalar_values(self):
        vm, result = self.run_probe('''
            ТестоваяТаблица = Новый ТаблицаЗначений;
            ТестоваяТаблица.Колонки.Добавить("Anything", Новый ОписаниеТипов("Строка"));
            ТестоваяТаблица.Колонки.Добавить("Unpredicted");
            СтрокаТеста = ТестоваяТаблица.Добавить();
            СтрокаТеста.Anything = "PRIVATE SCALAR MUST NEVER LEAVE";
            Вложенная = Новый ТаблицаЗначений;
            Вложенная.Колонки.Добавить("SecretColumn", Новый ОписаниеТипов("Число"));
            Вложенная.Добавить().SecretColumn = 123456;
            СтрокаТеста.Unpredicted = Вложенная;
        ''')
        self.assertIsNotNone(result)
        contract.validate_shape(result)
        self.assertEqual([table['columns'][0]['name'] for table in result['tables']], ['Anything', 'SecretColumn'])
        encoded = protocol.encode(result).decode()
        self.assertNotIn('PRIVATE', encoded); self.assertNotIn('123456', encoded)
        self.assertEqual(result['tables'][0]['columns'][0]['types'], ['Строка'])

    def test_real_helper_empty_rows_do_not_claim_exhaustive_nesting(self):
        _, result = self.run_probe('''ТестоваяТаблица = Новый ТаблицаЗначений;
            ТестоваяТаблица.Колонки.Добавить("MaybeNested");''')
        self.assertIsNotNone(result); contract.validate_shape(result)
        self.assertEqual(len(result['tables']), 1)
        self.assertEqual(result['nesting'], 'observed_value_tables_only')

    def test_real_helper_repeated_objects_cycles_rows_and_text_fail_closed(self):
        cases = [
            # A self-cycle is bounded by depth, without serializing row values.
            '''ТестоваяТаблица = Новый ТаблицаЗначений;
               ТестоваяТаблица.Колонки.Добавить("Cycle");
               ТестоваяТаблица.Добавить().Cycle = ТестоваяТаблица;''',
            # Each occurrence counts, including aliases of an empty table.
            '''ТестоваяТаблица = Новый ТаблицаЗначений;
               ТестоваяТаблица.Колонки.Добавить("Repeated"); Вложенная = Новый ТаблицаЗначений;
               Для Номер = 1 По 16 Цикл ТестоваяТаблица.Добавить().Repeated = Вложенная; КонецЦикла;''',
            '''ТестоваяТаблица = Новый ТаблицаЗначений;
               Для Номер = 1 По 257 Цикл ТестоваяТаблица.Добавить(); КонецЦикла;''',
            'ТестоваяТаблица = Новый ТаблицаЗначений; ТестоваяТаблица.Колонки.Добавить("' + 'x'*65 + '");',
            '''ТестоваяТаблица = Новый ТаблицаЗначений;
               Для Номер = 1 По 32 Цикл ТестоваяТаблица.Колонки.Добавить("C" + Строка(Номер)); КонецЦикла;
               Для Номер = 1 По 129 Цикл ТестоваяТаблица.Добавить(); КонецЦикла;''',
        ]
        for index, setup in enumerate(cases):
            with self.subTest(index=index):
                vm, result = self.run_probe(setup)
                self.assertIsNone(result)
                self.assertEqual(vm.execute('Контекст.phase'), 'contract_limit')
