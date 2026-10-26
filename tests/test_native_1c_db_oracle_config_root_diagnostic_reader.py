"""Failure-only synthetic root syntax diagnosis, never a native relation witness."""
from dataclasses import FrozenInstanceError, fields
import ast
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'), str(ROOT / 'yadinassi/storage')]
import config_framing_reader as core
import filedb_catalog as catalog
from test_native_1c_db_oracle_config_blob_chain_reader import DECLARATIONS, P, blob_calls, row, source
from test_native_1c_db_oracle_config_content_decode_reader import ABC_FIXED, EMPTY, RECIPE as CONTENT_RECIPE, packed
from test_native_1c_db_oracle_config_root_reference_reader import GUID, KEY, LOCATOR, ROOT_STORED, root_source

RECIPE = dict(CONTENT_RECIPE,
    identifier='config_root_diagnostic_8380_8192_v1',
    selected_part_zero_witness='fixed_root_chain_only_no_all_selected_witness_v1',
    chain_ownership='visited_root_chain_only_no_sharing_stricter_local_hypothesis_v1',
    phases='all_selected_guards_then_fixed_root_diagnostic_stop_v1',
    positive_decoded_witness='not_claimed_diagnostic_failure_only_v1',
    locator_selector='root',
    locator_grammar='initial_utf8_bom_ws_lbrace_2_comma_bare_guid_rbrace_ws_eof_v1',
    locator_whitespace=(32, 9, 13, 10),
    locator_guid='ascii_hex_8_4_4_4_12_no_key_materialization_v1',
    locator_limit=1024,
    locator_limit_stage='after_unchanged_content_decode_before_syntax_scan_v1',
    diagnostic_resolution='not_run',
    diagnostic_order='root_once_then_stop_no_target_or_remaining_reads_v1',
    diagnostic_attempt='single_use_poison_shared_decoder_and_chains_on_any_stop_v1',
    diagnostic_result='failed_nonaccepted_three_delimiter_classes_or_complete_stop_v1',
    diagnostic_map_weights=(512, 8, 4, 32),
    diagnostic_parser_weights=(1024, 4, 128, 512), diagnostic_lookup_weights=(256, 128),
    diagnostic_context_weights=(1024, 256, 128), diagnostic_failure_weight=4096)
RECIPE_SHA256 = '200fad1e58775d99e94b5d3b649aff6fcd042b5d1aad71639f4f8b55f12cb131'
COMPLETE = 'config_root_diagnostic_complete'
GATES = {'config_root_open_brace', 'config_root_comma', 'config_root_close_brace'}


def profile(): return core.ConfigRootDiagnosticProfile(DECLARATIONS, '0', 0)


def budget(): return catalog._Budget(core.CatalogLimits())


def operation(value, **kwargs):
    reader = core.CatalogReader(value.read_at, value.size, limits=kwargs.get('catalog_limits'))
    for field, amount in (('output_bytes', 1024), ('output_bytes', 256),
                          ('bytes_processed', 128), ('output_bytes', 4096)):
        reader._budget.charge(field, amount)
    return core._ConfigRootDiagnosticOperation(reader, profile(), core.ConfigFramingLimits(),
        core.ConfigBlobChainLimits(), core.ConfigContentDecodeLimits(),
        kwargs.get('root_limits') or core.ConfigRootReferenceLimits())


class ConfigRootDiagnosticScannerTests(unittest.TestCase):
    def scan(self, value, **kwargs):
        return core._diagnose_config_root_syntax(value, budget(), core.ConfigRootReferenceLimits(**kwargs))

    def outcome(self, value, function=None):
        try:
            result = (function or core._diagnose_config_root_syntax)(value, budget(), core.ConfigRootReferenceLimits())
        except catalog.CatalogError as error:
            return type(error), error.code
        return str, result

    def test_each_gate_and_eof_are_fixed_codes_not_token_kinds(self):
        cases = ((b'\xef\xbb\xbf', 'open_brace'), (b'\xef\xbb\xbf[2,x]', 'open_brace'),
            (b'\xef\xbb\xbf{2', 'comma'), (b'\xef\xbb\xbf{2}', 'comma'),
            (b'\xef\xbb\xbf{2 ' + GUID + b'}', 'comma'),
            (LOCATOR[:-1], 'close_brace'), (LOCATOR[:-1] + b',0}', 'close_brace'))
        for value, gate in cases:
            with self.subTest(value=value), self.assertRaisesRegex(core.InvalidStructure, '^config_root_' + gate + '$'):
                self.scan(value)
        for ws in (b' ', b'\t', b'\r', b'\n', b' \t\r\n'):
            for prefix, gate in ((b'\xef\xbb\xbf', 'open_brace'), (b'\xef\xbb\xbf{2', 'comma'),
                                 (LOCATOR[:-1], 'close_brace')):
                with self.assertRaisesRegex(core.InvalidStructure, '^config_root_' + gate + '$'):
                    self.scan(prefix + ws)

    def test_complete_language_always_exact_private_stop_without_key(self):
        for whitespace in (b'', b' ', b'\t', b'\r', b'\n', b' \t\r\n'):
            value = b'\xef\xbb\xbf' + whitespace + b'{' + whitespace + b'2' + whitespace + b',' + whitespace + GUID + whitespace + b'}' + whitespace
            with mock.patch.object(core, 'bytearray', side_effect=AssertionError('private key allocated'), create=True):
                with self.assertRaises(core._ConfigRootDiagnosticComplete) as caught: self.scan(value)
            self.assertIs(type(caught.exception), core._ConfigRootDiagnosticComplete)
            self.assertIsInstance(caught.exception, catalog.CatalogError)
            self.assertEqual(caught.exception.code, COMPLETE)
            self.assertEqual(caught.exception.args, (COMPLETE,))
            self.assertEqual(vars(caught.exception), {'code': COMPLETE})
        for value in (b'00000000-0000-0000-0000-000000000000', b'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF'):
            with self.assertRaises(core._ConfigRootDiagnosticComplete): self.scan(b'\xef\xbb\xbf{2,' + value + b'}')
        with self.assertRaises(TypeError): core._ConfigRootDiagnosticComplete('arbitrary')

    def test_original_failure_precedence_and_exact_types(self):
        class Bytes(bytes): pass
        for value in (None, False, 'text', bytearray(LOCATOR), memoryview(LOCATOR), Bytes(LOCATOR)):
            with self.assertRaisesRegex(core.InvalidStructure, '^config_root_input$'): self.scan(value)
        for value, code in ((b'X'*1025, 'input_bytes'), (b'X', 'bom'),
            (b'\xef\xbb\xbf[1,bad', 'open_brace'), (b'\xef\xbb\xbf{1,bad', 'tag'),
            (b'\xef\xbb\xbf{22,x}', 'tag'), (b'\xef\xbb\xbf{2 bad', 'comma'),
            (b'\xef\xbb\xbf{2,bad}tail', 'guid'), (LOCATOR + b'\0', 'trailing')):
            with self.assertRaisesRegex(catalog.CatalogError, '^config_root_' + code + '$'): self.scan(value)
        for end in range(len(LOCATOR)):
            kind, code = self.outcome(LOCATOR[:end])
            self.assertIn(code, GATES | {'config_root_bom', 'config_root_tag', 'config_root_guid'})
            self.assertIsNot(kind, core._ConfigRootDiagnosticComplete)

    def test_exhaustive_single_byte_and_seeded_differential_equivalence(self):
        # The original local parser is a comparator, not used in production or
        # used to claim that its grammar is universal native format knowledge.
        values = [LOCATOR, LOCATOR + b' ' * 981]
        values += [LOCATOR[:i] for i in range(len(LOCATOR))]
        values += [LOCATOR[:i] + bytes([v]) + LOCATOR[i+1:] for i in range(len(LOCATOR)) for v in range(256)]
        values += [LOCATOR[:i] + bytes([v]) + LOCATOR[i:] for i in range(len(LOCATOR)+1) for v in (0, 9, 10, 13, 32, 44, 123, 125, 255)]
        rng = random.Random(20261026)
        values += [bytes(rng.randrange(256) for _ in range(rng.randrange(100))) for _ in range(500)]
        for value in values:
            old_kind, old_code = self.outcome(value, core._parse_config_root_reference)
            new_kind, new_code = self.outcome(value)
            if old_kind is str:
                self.assertIs(new_kind, core._ConfigRootDiagnosticComplete)
                self.assertEqual(new_code, COMPLETE)
            elif old_code == 'config_root_grammar':
                self.assertIs(new_kind, core.InvalidStructure); self.assertIn(new_code, GATES)
            else:
                self.assertIs(new_kind, old_kind); self.assertEqual(new_code, old_code)
        self.assertEqual(len(values), 11949)

    def test_cap_and_exact_parser_preallocation_no_refund(self):
        with self.assertRaises(core._ConfigRootDiagnosticComplete): self.scan(LOCATOR + b' ' * 981)
        with self.assertRaisesRegex(core.ResourceLimit, '^config_root_input_bytes$'): self.scan(LOCATOR + b' ' * 982)
        with self.assertRaises(core._ConfigRootDiagnosticComplete): self.scan(LOCATOR, max_input_bytes=43)
        with self.assertRaisesRegex(core.ResourceLimit, '^config_root_input_bytes$'): self.scan(LOCATOR, max_input_bytes=42)
        for field, needed in (('output_bytes', 512), ('bytes_processed', 4 * len(LOCATOR) + 128)):
            for available in (needed-1, needed):
                b = budget(); remaining = getattr(b.limits, 'max_' + field) - b.counts[field]
                b.charge(field, remaining-available); before=dict(b.counts)
                expected = core.ResourceLimit if available < needed else core._ConfigRootDiagnosticComplete
                with self.assertRaises(expected): core._diagnose_config_root_syntax(LOCATOR, b, core.ConfigRootReferenceLimits())
                self.assertTrue(all(b.counts[k] >= v for k,v in before.items()))


class ConfigRootDiagnosticReaderTests(unittest.TestCase):
    def read(self, value, **kwargs):
        return core.observe_config_root_diagnostic(value.read_at, value.size, profile=profile(), **kwargs)

    def test_exact_old_prefix_ast_and_new_failure_only_recipe(self):
        raw = (ROOT/'scripts/native_1c_db_oracle/config_framing_reader.py').read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(hashlib.sha256(raw[:77214]).hexdigest(), '6856e08726deaf0453bf8a0e72450d3b695997fc358780f5e3dd1e16ef98621d')
        oldtree = ast.parse(raw[:77214]); newtree = ast.parse(raw)
        self.assertEqual(ast.dump(ast.Module(body=newtree.body[:len(oldtree.body)],type_ignores=[])),ast.dump(oldtree))
        self.assertFalse(any(isinstance(n,(ast.Import,ast.ImportFrom)) for n in newtree.body[len(oldtree.body):]))
        p=profile(); self.assertEqual(p.recipe(), RECIPE); self.assertEqual(p.recipe_sha256, RECIPE_SHA256)
        self.assertEqual(hashlib.sha256(json.dumps(RECIPE,sort_keys=True,separators=(',',':')).encode()).hexdigest(),RECIPE_SHA256)
        self.assertNotIn('reference_relation',p.recipe()); self.assertEqual(p.recipe()['diagnostic_resolution'],'not_run')
        with self.assertRaises(FrozenInstanceError): p.identifier='x'

    def test_all_permutations_guard_all_but_read_root_once_no_target_lookup(self):
        entries=[('RoOt',ROOT_STORED,0),(KEY,b'invalid raw stream',0),('other',b'also invalid',0)]
        for sequence in itertools.permutations(entries):
            value=root_source(sequence); seen=[]; decoders=[]; keys=[]; contexts=[]
            original_read=core._ConfigBlobChains.read; original_decode=core._ConfigContentDecoder.decode
            original_take=core._ConfigRootDiagnosticOperation._take; original_catalog=core.CatalogReader.read_catalog
            def take(op, refs, key, missing):
                self.assertEqual(len(refs),3); keys.append(key); return original_take(op,refs,key,missing)
            def read(chains,start,length): seen.append((chains,start)); return original_read(chains,start,length)
            def decode(context,payload,kind): decoders.append(context); return original_decode(context,payload,kind)
            def catalog_read(context): contexts.append(context); return original_catalog(context)
            with mock.patch.object(core._ConfigRootDiagnosticOperation,'_take',take), mock.patch.object(core._ConfigBlobChains,'read',read), mock.patch.object(core._ConfigContentDecoder,'decode',decode), mock.patch.object(core.CatalogReader,'read_catalog',catalog_read), mock.patch.object(core,'_parse_config_root_reference',side_effect=AssertionError('second parser')), mock.patch.object(core,'observe_config_root_reference',side_effect=AssertionError('old observer')):
                with self.assertRaises(core._ConfigRootDiagnosticComplete): self.read(value)
            self.assertEqual(keys,['root']); self.assertEqual([start for _,start in seen],[sequence.index(entries[0])+1])
            self.assertEqual(len(blob_calls(value)),2); self.assertEqual(len(contexts),1); self.assertEqual(len(decoders),1)
            self.assertIs(seen[0][0].budget,contexts[0]._budget); self.assertIs(decoders[0].budget,contexts[0]._budget)
            self.assertTrue(seen[0][0].failed); self.assertTrue(decoders[0].failed); self.assertFalse(value.closed)

    def test_root_only_requires_no_target_or_positive_target_or_remaining_transport(self):
        for entries in ([('root',ROOT_STORED,0)], [('root',ROOT_STORED,0),(KEY,EMPTY,0)],
                        [('root',ROOT_STORED,0),(KEY,ABC_FIXED+b'\0',0)]):
            value=root_source(entries)
            with self.assertRaises(core._ConfigRootDiagnosticComplete): self.read(value)
            self.assertEqual(len(blob_calls(value)),2)
        # Unvisited sharing/cycles are not ruled out, and no such claim is made.
        value=source(rows=[row(marker=1),row('root',start=1,length=48),row(KEY,start=2,length=5),row('other',start=2,length=5)],nodes={1:(0,ROOT_STORED),2:(2,ABC_FIXED)})
        with self.assertRaises(core._ConfigRootDiagnosticComplete): self.read(value)
        self.assertEqual(len(blob_calls(value)),2)

    def test_every_late_selected_guard_precedes_root_chain(self):
        bads=[('ROOT',ABC_FIXED,0),(KEY.upper(),ABC_FIXED,0),('tail.NEW',ABC_FIXED,0),
              ('tail_DynUpdate_x',ABC_FIXED,0),('nonascii_Ω',ABC_FIXED,0),('part',ABC_FIXED,1)]
        for bad in bads:
            for index in (0,1,2):
                entries=[('root',ROOT_STORED,0),(KEY,ABC_FIXED,0)]; entries.insert(index,bad)
                value=root_source(entries)
                with self.assertRaises(catalog.CatalogError): self.read(value)
                self.assertEqual(blob_calls(value),[])
        for entries in ([(KEY,ABC_FIXED,0)], [('root',ROOT_STORED,0)]):
            value=root_source(entries, trailing_rows=[row('bad',start=2**31,length=1)])
            with self.assertRaisesRegex(core.InvalidStructure,'^config_reference_bounds$'): self.read(value)
            self.assertEqual(blob_calls(value),[])
        value=root_source([(KEY,ABC_FIXED,0)],trailing_rows=[row('root',start=0,length=1)])
        with self.assertRaisesRegex(core.UnsupportedLayout,'^config_root_missing_selected_root$'): self.read(value)
        self.assertEqual(blob_calls(value),[])

    def test_every_stop_poisoned_and_no_second_action_or_budget_reset(self):
        cases=[(ROOT_STORED,COMPLETE),(packed(b'bad'),'config_root_bom'),
            (packed(b'\xef\xbb\xbf['),'config_root_open_brace'),(packed(b'\xef\xbb\xbf{2}'),'config_root_comma'),
            (packed(LOCATOR[:-1]),'config_root_close_brace'),(ROOT_STORED+b'\0','config_content_trailing_data')]
        for stored,code in cases:
            value=root_source([('root',stored,0)]);op=operation(value)
            with self.assertRaisesRegex(catalog.CatalogError,'^'+code+'$'):op.run()
            self.assertTrue(op.used);self.assertTrue(op.chains.failed);self.assertTrue(op.decoder.failed)
            usage,calls,owners=op.reader.usage,list(value.calls),set(op.chains.owners)
            for fn,code2 in ((op.run,'config_root_failed_attempt'),
                (lambda:op.chains.read(1,len(stored)),'config_chain_failed_attempt'),
                (lambda:op.decoder.decode(ABC_FIXED,'raw_deflate'),'config_content_failed_attempt')):
                with self.assertRaisesRegex(catalog.CatalogError,'^'+code2+'$'):fn()
            self.assertEqual(op.reader.usage,usage);self.assertEqual(value.calls,calls);self.assertEqual(op.chains.owners,owners)

    def test_real_decode_finishes_before_syntax_cap_not_smaller_inflate_limit(self):
        for length,kind in ((1024,core._ConfigRootDiagnosticComplete),(1025,core.ResourceLimit),(4194304,core.ResourceLimit)):
            value=root_source([('root',packed(LOCATOR+b' '*(length-43)),0)]);op=operation(value)
            with self.assertRaises(kind):op.run()
            self.assertEqual(op.decoder.total_content_bytes,length);self.assertTrue(op.decoder.failed);self.assertTrue(op.chains.failed)
        value=root_source([('root',packed(LOCATOR+b' '*(4194305-43)),0)]);op=operation(value)
        with self.assertRaisesRegex(core.ResourceLimit,'^config_content_bytes$'):op.run()
        self.assertTrue(op.decoder.failed);self.assertTrue(op.chains.failed)

    def test_root_zero_used_tail_cycle_length_and_physical_ownership(self):
        rows=[row(marker=1),row(KEY,start=2,length=5),row('root',start=1,length=48)]
        nodes={1:(3,ROOT_STORED),3:(0,b''),2:(0,ABC_FIXED)}
        value=source(rows=rows,nodes=nodes);self.assertEqual(len(value.blob_pages),1)
        with self.assertRaises(core._ConfigRootDiagnosticComplete):self.read(value)
        self.assertEqual([n for _,n in blob_calls(value)],[6,48,6])
        nodes[3]=(3,b'');value=source(rows=rows,nodes=nodes)
        with self.assertRaisesRegex(core.InvalidStructure,'^config_chain_cycle$'):self.read(value)
        value=source(rows=[row(marker=1),row('root',start=1,length=47)],nodes={1:(0,ROOT_STORED)})
        with self.assertRaisesRegex(core.InvalidStructure,'^config_chain_length$'):self.read(value)
        for page in (2,3,8,9,10):
            value=root_source();value.page(8)[24:28]=page.to_bytes(4,'little')
            with self.assertRaisesRegex(catalog.UnsupportedSharing,'^physical_page_role_overlap$'):self.read(value)

    def test_all_caps_exact_lowerable_and_profile_types_not_widened(self):
        for kind in (core.ConfigFramingProfile,core.ConfigContentDecodeProfile,core.ConfigRootReferenceProfile):
            value=root_source()
            with self.assertRaises(ValueError):core.observe_config_root_diagnostic(value.read_at,value.size,profile=kind(DECLARATIONS,'0',0))
            self.assertEqual(value.calls,[])
        for key in ('limits','chain_limits','content_limits','root_limits','catalog_limits'):
            value=root_source()
            with self.assertRaises(ValueError):self.read(value,**{key:{}})
            self.assertEqual(value.calls,[])
        for field in fields(core.CatalogLimits):
            value=root_source()
            with self.assertRaises(ValueError):self.read(value,catalog_limits=core.CatalogLimits(**{field.name:getattr(core.CatalogLimits(),field.name)+1}))
            self.assertEqual(value.calls,[])
        entries=[(f'p{i}.inf',b'x',0) for i in range(4094)]+[('root',ROOT_STORED,0)]
        with self.assertRaises(core._ConfigRootDiagnosticComplete):self.read(root_source(entries))
        value=root_source(entries,trailing_rows=[row('excluded',start=0)])
        with self.assertRaisesRegex(core.ResourceLimit,'^config_slots$'):self.read(value)
        self.assertEqual(blob_calls(value),[])

    def test_file_ceiling_and_lower_root_content_chain_limits(self):
        for size in (None,False,True,-1,1.0,'10'):
            value=root_source()
            with self.assertRaises(ValueError):core.observe_config_root_diagnostic(value.read_at,size,profile=profile())
            self.assertEqual(value.calls,[])
        value=root_source()
        with self.assertRaisesRegex(core.ResourceLimit,'^config_chain_image_bytes$'):
            core.observe_config_root_diagnostic(value.read_at,67108865,profile=profile())
        self.assertEqual(value.calls,[])
        with self.assertRaises(core._ConfigRootDiagnosticComplete):
            self.read(root_source(),root_limits=core.ConfigRootReferenceLimits(43),
                chain_limits=core.ConfigBlobChainLimits(max_chain_bytes=48),
                content_limits=core.ConfigContentDecodeLimits(max_content_bytes=43))
        for options,code in (({'root_limits':core.ConfigRootReferenceLimits(42)},'config_root_input_bytes'),
                ({'chain_limits':core.ConfigBlobChainLimits(max_chain_bytes=47)},'config_chain_bytes'),
                ({'content_limits':core.ConfigContentDecodeLimits(max_content_bytes=42)},'config_content_bytes')):
            with self.assertRaisesRegex(core.ResourceLimit,'^'+code+'$'):self.read(root_source(),**options)

    def test_constructor_reads_charged_and_new_state_final_record_prepaid(self):
        baseline=root_source();r=core.CatalogReader(baseline.read_at,baseline.size);before=r.usage
        value=root_source();original=core._ConfigRootDiagnosticOperation.__init__;seen=[]
        def construct(op,reader,*args):
            self.assertEqual(value.calls,[(0,24),(2*P,P)])
            self.assertEqual(reader.usage.read_bytes,24+P)
            self.assertEqual(reader.usage.output_bytes,before.output_bytes+1024+256+4096)
            self.assertEqual(reader.usage.bytes_processed,before.bytes_processed+128)
            seen.append(reader);original(op,reader,*args);self.assertFalse(op.used)
        with mock.patch.object(core._ConfigRootDiagnosticOperation,'__init__',construct):
            with self.assertRaises(core._ConfigRootDiagnosticComplete):self.read(value)
        self.assertEqual(len(seen),1)
        for extra in (1023,1024+255,1024+256+4095):
            value=root_source()
            with mock.patch.object(core,'_ConfigRootDiagnosticOperation',side_effect=AssertionError('unpaid operation')):
                with self.assertRaises(core.ResourceLimit):self.read(value,catalog_limits=core.CatalogLimits(max_output_bytes=before.output_bytes+extra))
            self.assertEqual(value.calls,[(0,24),(2*P,P)])
        value=root_source()
        with mock.patch.object(core,'_ConfigRootDiagnosticOperation',side_effect=AssertionError('unpaid work')):
            with self.assertRaises(core.ResourceLimit):self.read(value,catalog_limits=core.CatalogLimits(max_bytes_processed=before.bytes_processed+127))
        self.assertEqual(value.calls,[(0,24),(2*P,P)])

    def test_exact_context_boundaries_admit_construction_not_one_less(self):
        value=root_source();r=core.CatalogReader(value.read_at,value.size);before=r.usage
        class Reached(Exception): pass
        for field,amount in (('output_bytes',1024+256+4096),('bytes_processed',128)):
            for available in (amount-1,amount):
                value=root_source()
                with mock.patch.object(core,'_ConfigRootDiagnosticOperation',side_effect=Reached):
                    expected=core.ResourceLimit if available<amount else Reached
                    with self.assertRaises(expected):
                        self.read(value,catalog_limits=core.CatalogLimits(**{'max_'+field:getattr(before,field)+available}))
                self.assertEqual(value.calls,[(0,24),(2*P,P)])

    def test_map_output_reservation_before_duplicate_key_work(self):
        seen=[];original=core._config_content_name
        def name(text,units,b,keys):
            result=original(text,units,b,keys);seen.append((b.counts['output_bytes'],512+8*units));return result
        with mock.patch.object(core,'_config_content_name',name):
            with self.assertRaises(core._ConfigRootDiagnosticComplete):self.read(root_source())
        self.assertEqual(len(seen),2)
        for used,needed in seen:
            value=root_source()
            with self.assertRaisesRegex(core.ResourceLimit,'^output_bytes$'):
                self.read(value,catalog_limits=core.CatalogLimits(max_output_bytes=used+needed-1))
            self.assertEqual(blob_calls(value),[])

    def test_used_state_before_catalog_and_prepaid_failure_no_extra_charge(self):
        value=root_source();op=operation(value);original=core.CatalogReader.read_catalog
        def read(reader):
            self.assertTrue(op.used);before=reader.usage;calls=list(value.calls)
            with self.assertRaisesRegex(core.InvalidStructure,'^config_root_failed_attempt$'):op.run()
            self.assertEqual(reader.usage,before);self.assertEqual(value.calls,calls)
            return original(reader)
        with mock.patch.object(core.CatalogReader,'read_catalog',read):
            with self.assertRaises(core._ConfigRootDiagnosticComplete):op.run()
        # Full used ceilings exactly reproduce this failure; reducing each by one
        # must exhaust the same shared budget, never grant a replacement budget.
        usage=op.reader.usage
        for field in ('page_reads','read_bytes','bytes_processed','blob_visits','total_blob_bytes','output_bytes'):
            used=getattr(usage,field)
            with self.assertRaises(core._ConfigRootDiagnosticComplete):self.read(root_source(),catalog_limits=core.CatalogLimits(**{'max_'+field:used}))
            with self.assertRaises(core.ResourceLimit):self.read(root_source(),catalog_limits=core.CatalogLimits(**{'max_'+field:used-1}))

    def test_map_lookup_parser_charge_before_work_no_refund(self):
        value=root_source();original=core._config_content_name
        def name(text,units,b,keys):
            result=original(text,units,b,keys);available=b.limits.max_bytes_processed-b.counts['bytes_processed']
            b.charge('bytes_processed',available-(4*units+31));return result
        with mock.patch.object(core,'_config_content_name',name):
            with self.assertRaisesRegex(core.ResourceLimit,'^bytes_processed$'):self.read(value)
        self.assertEqual(blob_calls(value),[])
        class Untouched(dict):
            def pop(self,*args):raise AssertionError('unpaid lookup')
        for field,amount in (('bytes_processed',255),('output_bytes',127)):
            op=operation(root_source());b=op.reader._budget;available=getattr(b.limits,'max_'+field)-b.counts[field]
            b.charge(field,available-amount);before=dict(b.counts)
            with self.assertRaisesRegex(core.ResourceLimit,'^'+field+'$'):op._take(Untouched(root=(1,48,'raw_deflate')),'root','config_root_missing_selected_root')
            self.assertTrue(all(b.counts[k]>=v for k,v in before.items()))
        value=root_source();op=operation(value);scan=core._diagnose_config_root_syntax
        def drained(content,b,limits):
            available=b.limits.max_output_bytes-b.counts['output_bytes'];b.charge('output_bytes',available-511)
            return scan(content,b,limits)
        with mock.patch.object(core,'_diagnose_config_root_syntax',drained):
            with self.assertRaisesRegex(core.ResourceLimit,'^output_bytes$'):op.run()
        self.assertTrue(op.decoder.failed);self.assertTrue(op.chains.failed)


if __name__=='__main__':unittest.main()
