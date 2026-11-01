"""Finite source-bound producer rejection diagnostics, never native success."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import test_native_data_hashing_family_profile as profile
import native_1c_data_hashing_family_contract as contract

tree, host, full = profile.tree, profile.host, profile.full
PROFILE = 'data-hashing-family-v1'


class HashingFailureTests(unittest.TestCase):
    def read(self, raw, sha=contract.SOURCE_SHA256):
        with tempfile.TemporaryDirectory(prefix='hash-failure-unit-') as tmp:
            path=Path(tmp)/'owned.json'; path.write_bytes(raw)
            return tree.read_hashing_native_result(path,sha)

    def observed(self, raw):
        with self.assertRaises(tree.ObservationFailure) as failure: self.read(raw)
        return failure.exception.diagnostic

    def test_ordinary_parser_unchanged_and_first(self):
        raw=b'{"messages":["fixed"],"error":""}'
        with mock.patch.object(tree.full,'parse_native_result',wraps=tree.full.parse_native_result) as parse:
            self.assertEqual(self.read(raw),(['fixed'],''));parse.assert_called_once_with(raw)
        with mock.patch.object(tree.full,'parse_native_result') as parse:
            with self.assertRaises(tree.full.FullError): self.read(raw,'0'*64)
            parse.assert_not_called()

    def test_finite_categories_and_owned_line_only(self):
        cases=[(b'{', 'result_json',None),
               (b'{"messages":0,"error":"private"}', 'result_shape',None),
               (b'{"messages":[],"error":3}', 'result_shape',None),
               (b'{"messages":["\\ud800"],"error":""}', 'result_encoding',None)]
        for text,line in (('private path/token not exported',None),
                ('{ВнешняяОбработка.TestModule.МодульОбъекта(38,3)}: private error',38),
                ('{ExternalDataProcessor.TestModule.ObjectModule(89,12)}: private',89),
                ('{ВнешняяОбработка.TestModule.МодульОбъекта(38)}: private error',38),
                ('{ExternalDataProcessor.TestModule.ObjectModule(90,12)}: private',None),
                ('{ExternalDataProcessor.Other.ObjectModule(1,1)}: private',None),
                ('file:///private/TestModule.ObjectModule(1,1) private',None)):
            cases.append((json.dumps({'messages':[],'error':text}).encode(),'result_error',line))
        for raw,category,line in cases:
            with self.subTest(category=category,line=line):
                result=self.observed(raw)
                self.assertEqual({k:v for k,v in result.items() if k!='calibration'},
                    dict(site='server',case=line,category=category))
                if category=='result_error': self.assertEqual(result['calibration']['kind'],'other')
                else: self.assertIsNone(result['calibration'])
                self.assertNotIn('private',json.dumps(result));self.assertNotIn('"token"',json.dumps(result))

    def test_secondary_inspection_bound_before_decode(self):
        raw=json.dumps({'messages':[],'error':'x'*contract.MAX_FAILURE_DIAGNOSTIC_BYTES}).encode()
        original=tree.full.strict_json
        with mock.patch.object(tree.full,'strict_json',wraps=original) as parse:
            result=self.observed(raw)
            self.assertEqual(parse.call_count,1)  # Only the unchanged first parser.
        self.assertEqual(result['category'],'result_limit');self.assertIsNone(result['case'])

    def test_fixed_error_kind_only_and_owned_launcher_details(self):
        launcher=(ROOT/'integrational_tests/launcher_1c/Launcher/Forms/Main/Ext/Form/Module.bsl').read_text(encoding='utf-8')
        self.assertIn('ОшибкаТеста = ПодробноеПредставлениеОшибки(ИнформацияОбОшибке());',launcher)
        for phrase,kind in (
                ('Ошибка инициализации модуля: Переменная не определена (private)', 'identifier'),
                ('Процедура или функция с указанным именем не определена (private)', 'function'),
                ('Тип не определен (private)', 'type'),
                ('Метод объекта не обнаружен (private)', 'method'),
                ('Ожидается имя private', 'syntax'),
                ('Module initialization error private', 'module'),
                ('Expected token private', 'syntax'),
                ('unexpected error private', 'other'),
                ('arbitrary private path/token', 'other')):
            value=self.observed(json.dumps(dict(messages=[],error=phrase)).encode())
            self.assertEqual(value['calibration']['kind'],kind);self.assertIsNone(value['case'])
            self.assertNotIn('private',json.dumps(value))
            host.validate_diagnostic(value,profile=PROFILE)

    def test_closed_validator_and_profile_isolation(self):
        valid=dict(site='server',case=1,category='result_error',calibration=None)
        for candidate in (valid,dict(valid,case=None),dict(valid,case=89)):
            tree.validate_diagnostic(candidate,profile=PROFILE);host.validate_diagnostic(candidate,profile=PROFILE)
        for candidate in (dict(valid,case=True),dict(valid,case=0),dict(valid,case=90),
                dict(valid,site='client'),dict(valid,category='free text'),
                dict(valid,calibration='private'),dict(valid,extra='private'),
                dict(valid,category='result_json')):
            with self.assertRaises(tree.full.FullError): tree.validate_diagnostic(candidate,profile=PROFILE)
            with self.assertRaises(host.TreeError): host.validate_diagnostic(candidate,profile=PROFILE)
        for other in ('data-io-family-v1','regex-family-v1','tree-v1'):
            with self.assertRaises(host.TreeError):host.validate_diagnostic(valid,profile=other)
        self.assertEqual(len((ROOT/'integrational_tests/measurements/data_hashing_family.bsl').read_text(encoding='utf-8').splitlines()),contract.SOURCE_LINE_COUNT)

    def test_allowlist_projection_redacts_unknown_quoted_path_uri_regions(self):
        canaries=('CANARY_OWNER_9381', 'CANARY_AUTH_918273', '/home/CANARY_OWNER_9381/DataHashing',
                  r'C:\Users\CANARY_OWNER_9381\HashFunction',
                  'https://CANARY_AUTH_918273.invalid/DataHashing',
                  '"DataHashing CANARY_AUTH_918273"', "'HashFunction'", '`AppendFile`',
                  '{CANARY_OWNER_9381 {inner} DataHashing}',
                  '(CANARY_OWNER_9381 HashFunction)',
                  '"https://x.invalid/private DataHashing"',
                  'prefix"CANARY_AUTH_918273 HashFunction"',
                  '« HashFunction CANARY_PRIVATE »', '“ HashFunction CANARY_PRIVATE ”',
                  '‘ HashFunction CANARY_PRIVATE ’', '„ HashFunction CANARY_PRIVATE “',
                  '‹ HashFunction CANARY_PRIVATE ›')
        for text in canaries:
            value=contract.failure_projection(text,[],'other')
            self.assertTrue(all(item==0 for item in value['tokens']),text)
            encoded=json.dumps(value)
            for marker in ('CANARY_', 'DataHashing', 'HashFunction', '/home', 'https:', 'Users'):
                self.assertNotIn(marker,encoded)
        value=contract.failure_projection('Ошибка: Переменная не определена (HashFunction)',[],'identifier')
        words=[contract.FAILURE_TOKEN_WORDS[item-1] if item else '*' for item in value['tokens']]
        self.assertEqual(words,['ошибка','переменная','не','определена','hashfunction'])

    def test_projection_phase_and_fixed_bounds(self):
        c1,c2=contract.CALIBRATION.decode('ascii').splitlines()
        value=contract.failure_projection('error',[c1,c2,'HF-01: [ok|S0:]'],'other')
        self.assertEqual(value['phase'],dict(messages=3,c1=True,c2=True,case=True))
        value=contract.failure_projection('error',['HF-C1: [private]','HF-00: [ok|S0:]','HF-01: [ok|S1:]'],'other')
        self.assertEqual(value['phase'],dict(messages=3,c1=False,c2=False,case=False))
        value=contract.failure_projection('error',['']*43,'other')
        self.assertEqual(value['phase'],dict(messages=None,c1=False,c2=False,case=False))
        long=contract.failure_projection('HashFunction '*200,[],'other')
        self.assertEqual(len(long['tokens']),64)
        self.assertLess(len(json.dumps(long).encode()),1024)
        for text in ('x'*16385,):
            with self.assertRaises(contract.ObservationError):contract.failure_projection(text,[],'other')
        with self.assertRaises(contract.ObservationError):contract.failure_projection('error',['x'*16385],'other')
        worst=dict(kind='identifier',tokens=[len(contract.FAILURE_TOKEN_WORDS)]*64,
                   phase=dict(messages=42,c1=False,c2=False,case=False))
        self.assertLess(len(json.dumps(worst).encode()),1024)
        for mutate in (lambda v:v['tokens'].append(0),lambda v:v.update(tokens=['private']),
                lambda v:v.update(tokens=[True]),lambda v:v.update(tokens=[len(contract.FAILURE_TOKEN_WORDS)+1]),
                lambda v:v.update(extra='private'),lambda v:v['phase'].update(extra='private'),
                lambda v:v['phase'].update(messages=43),lambda v:v['phase'].update(c1=1)):
            bad=json.loads(json.dumps(worst));mutate(bad)
            with self.assertRaises(contract.ObservationError):contract.validate_failure_projection(bad)

    def test_identifier_dictionary_is_only_exact_public_source_tokens(self):
        import re
        source=(ROOT/'integrational_tests/measurements/data_hashing_family.bsl').read_text(encoding='utf-8')
        stripped=re.sub(r'"(?:[^"]|"")*"|//[^\n]*',' ',source)
        words={word.casefold() for word in re.findall(r'[A-Za-z_][A-Za-z0-9_]*',stripped)}
        self.assertTrue(set(word.casefold() for word in contract.PUBLIC_SOURCE_IDENTIFIERS)<=words)
        self.assertEqual(len(contract.FAILURE_TOKEN_WORDS),len(set(contract.FAILURE_TOKEN_WORDS)))
        self.assertNotIn('CANARY_AUTH_918273'.casefold(),contract.FAILURE_TOKEN_WORDS)

    def test_failed_only_transport_rejects_success_or_outputs(self):
        encoded,hashes,modules=profile.envelope(profile.output())
        value=json.loads(encoded);report=value['report'];stage=report['stage3'];spec=profile.spec()
        report.update(status='stage3_failed',native_tests_completed=False)
        stage.update(status='failed',failure_kind='unsupported_observation',failed_case=spec.case,
            observation_diagnostic=dict(site='server',case=38,category='result_error',calibration=None))
        stage['cases'][0].update(status='failed',module_sha256=None,output_sha256=None,output_size=None,message_count=None)
        stage['client_tree']=tree.full.empty_dates_report();value['outputs']=[]
        def validate(candidate):
            return host.validate_envelope(json.dumps(candidate).encode(),profile.NONCE,hashes,modules,profile.smoke.validate_report,profile=PROFILE)
        with self.assertRaises(host.TreeError) as failure:validate(value)
        self.assertEqual(failure.exception.observation_diagnostic,stage['observation_diagnostic'])
        stage['observation_diagnostic']['calibration']=contract.failure_projection('error',[],'other')
        with self.assertRaises(host.TreeError) as failure:validate(value)
        self.assertEqual(failure.exception.observation_diagnostic,stage['observation_diagnostic'])
        # A diagnostic never admits a success, payload or source-identity mismatch.
        for mutate in (
                lambda v:v['report'].update(status='ok'),
                lambda v:v['report'].update(native_tests_completed=True),
                lambda v:v.update(outputs=[{'name':'private'}]),
                lambda v:v['report']['stage3'].update(status='ok'),
                lambda v:v['report']['stage3']['cases'][0].update(source_sha256='0'*64)):
            bad=json.loads(json.dumps(value));mutate(bad)
            with self.assertRaises(host.TreeError) as rejected:validate(bad)
            self.assertFalse(hasattr(rejected.exception,'observation_diagnostic'))


if __name__=='__main__':unittest.main()
