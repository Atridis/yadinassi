"""Synthetic partial-reference cases; never evidence of native CONFIG validity."""
from dataclasses import asdict, fields, FrozenInstanceError
import ast
import hashlib
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'yadinassi/storage')]
import config_framing_reader as core
import config_root_projection as projector
import filedb_catalog as catalog
from test_native_1c_db_oracle_config_blob_chain_reader import source as chain_source, row, chain_nodes
from test_native_1c_db_oracle_config_content_decode_reader import (
    content_source, ABC_FIXED, EMPTY, DECLARATIONS)

GUID = '01234567-89ab-cdef-0123-456789abcdef'
PREFIX = b'\xef\xbb\xbf{2,' + GUID.encode() + b','


def stored_literal(content):
    assert len(content) <= 65535
    n = len(content)
    return b'\x01' + n.to_bytes(2, 'little') + (65535-n).to_bytes(2, 'little') + content


def entries(*, root=PREFIX+b'not-a-valid-tail\xff', target=ABC_FIXED):
    return [('other', ABC_FIXED, 0), (GUID.upper(), target, 0), ('RoOt', stored_literal(root), 0)]


def successful_source(**kwargs):
    return content_source(entries(**kwargs))


def profile():
    return core.ConfigRootReferenceProjectionProfile(DECLARATIONS, '0', 0)


class ConfigRootProjectionReaderTests(unittest.TestCase):
    def read(self, source, **kwargs):
        return core.observe_config_root_reference_projection(source.read_at, source.size,
            profile=profile(), **kwargs)

    def test_complete_observation_is_partial_and_contains_no_private_names(self):
        result = self.read(successful_source())
        self.assertEqual((result.projected_root_count, result.resolved_target_count,
                          result.positive_target_count), (1, 1, 1))
        self.assertEqual(result.completed_chain_count, 3)
        self.assertEqual(result.root_document_validation, 'not_performed')
        self.assertEqual(result.root_suffix_validation, 'not_performed')
        self.assertEqual(result.root_identity, 'not_observed')
        self.assertEqual(result.file_identity, 'not_observed')
        self.assertEqual(result.applied_state, 'not_observed')
        self.assertNotIn(GUID, repr(asdict(result)))
        self.assertNotIn('not-a-valid-tail', repr(asdict(result)))
        with self.assertRaises(FrozenInstanceError): result.projected_root_count = 2

    def test_root_target_and_remaining_decoded_once_on_one_graph(self):
        calls, readers, decoders = [], [], []
        old_init, old_decode, old_read = core.CatalogReader.__init__, core._ConfigContentDecoder.__init__, core._ConfigBlobChains.read
        def init(obj, *args, **kwargs):
            old_init(obj, *args, **kwargs); readers.append(obj)
        def decode_init(obj, *args, **kwargs):
            old_decode(obj, *args, **kwargs); decoders.append(obj)
        def read(obj, start, length):
            calls.append((id(obj), start)); return old_read(obj, start, length)
        with mock.patch.object(core.CatalogReader, '__init__', init), \
             mock.patch.object(core._ConfigContentDecoder, '__init__', decode_init), \
             mock.patch.object(core._ConfigBlobChains, 'read', read):
            result = self.read(successful_source())
        self.assertEqual(len(readers), 1); self.assertEqual(len(decoders), 1)
        self.assertIs(decoders[0].budget, readers[0]._budget)
        self.assertEqual(len(set(i for i, _ in calls)), 1)
        self.assertEqual([s for _, s in calls], [3, 2, 1])
        self.assertEqual(result.completed_chain_count, len(calls))

    def test_suffix_bytes_are_intentionally_not_validated(self):
        for suffix in (b'', b'\xff', b'{{{', b'"unterminated', b'\x00'*2000):
            self.assertEqual(self.read(successful_source(root=PREFIX+suffix)).projected_root_count, 1)
        self.assertEqual(self.read(successful_source(root=PREFIX[:-1]+b'}garbage')).resolved_target_count, 1)

    def test_no_expected_uuid_header_or_target_contents(self):
        zero = '00000000-0000-0000-0000-000000000000'
        value = content_source([('root', stored_literal(b'\xef\xbb\xbf{0,'+zero.encode()+b'}tail'), 0),
                                (zero, stored_literal(b'opaque\xff'), 0)])
        self.assertEqual(self.read(value).positive_target_count, 1)

    def test_missing_root_and_target(self):
        for source, code in ((content_source([(GUID, ABC_FIXED, 0)]), 'config_projection_root_missing'),
                (content_source([('root', stored_literal(PREFIX), 0)]), 'config_projection_target_missing')):
            with self.assertRaises(core.UnsupportedLayout) as caught: self.read(source)
            self.assertEqual(caught.exception.code, code)

    def test_names_are_ascii_folded_not_trimmed(self):
        value = entries(); value[-1] = (' root ', value[-1][1], 0)
        with self.assertRaises(core.UnsupportedLayout) as caught: self.read(content_source(value))
        self.assertEqual(caught.exception.code, 'config_projection_root_missing')
        value = entries(); value[1] = (' '+GUID, ABC_FIXED, 0)
        with self.assertRaises(core.UnsupportedLayout) as caught: self.read(content_source(value))
        self.assertEqual(caught.exception.code, 'config_projection_target_missing')

    def test_duplicate_names_rejected_before_any_chain_read(self):
        for duplicate in ('ROOT', GUID):
            with mock.patch.object(core._ConfigBlobChains, 'read', side_effect=AssertionError('too early')):
                with self.assertRaises(core.UnsupportedLayout) as caught:
                    self.read(content_source(entries()+[(duplicate, ABC_FIXED, 0)]))
            self.assertEqual(caught.exception.code, 'config_content_duplicate_name')

    def test_every_selected_name_and_part_guard_precedes_root(self):
        for name, part, code in (('file.new', 0, 'config_content_dynamic_name'),
                ('x_dynupdate_y', 0, 'config_content_dynamic_name'),
                ('x', 1, 'config_content_nonzero_part'), ('x\x00', 0, 'config_content_name_policy')):
            with mock.patch.object(core._ConfigBlobChains, 'read', side_effect=AssertionError('too early')):
                with self.assertRaises(core.UnsupportedLayout) as caught:
                    self.read(content_source(entries()+[(name, ABC_FIXED, part)]))
            self.assertEqual(caught.exception.code, code)

    def test_all_bad_prefixes_fail_finitely_and_do_not_echo_input(self):
        for value in (b'', b'{2,'+GUID.encode()+b'}', PREFIX[:-2], b'PRIVATE',
                      b'\xef\xbb\xbf{2,"'+GUID.encode()+b'"}'):
            with self.assertRaises(core.InvalidStructure) as caught:
                self.read(successful_source(root=value))
            self.assertEqual(caught.exception.code, 'config_projection_prefix')
            self.assertNotIn('PRIVATE', str(caught.exception))

    def test_prefix_limit_on_shared_budget(self):
        with self.assertRaises(core.ResourceLimit) as caught:
            self.read(successful_source(root=b'\xef\xbb\xbf'+b' '*1024+PREFIX[3:]))
        self.assertEqual(caught.exception.code, 'config_projection_prefix_bytes')

    def test_empty_target_rejected(self):
        with self.assertRaises(core.UnsupportedLayout) as caught:
            self.read(successful_source(target=EMPTY))
        self.assertEqual(caught.exception.code, 'config_projection_target_empty')

    def test_bad_target_and_later_unrelated_entry_fail_whole_observation(self):
        for value in (entries(target=b'bad-deflate'), entries()+[('later', b'bad-deflate', 0)]):
            with self.assertRaises(core.InvalidStructure): self.read(content_source(value))

    def test_failure_poisons_shared_decoder_and_chain_without_refund(self):
        decoders = []; original = core._ConfigContentDecoder.__init__
        def init(obj, *args, **kwargs): original(obj, *args, **kwargs); decoders.append(obj)
        for source in (successful_source(root=b'PRIVATE'), successful_source(target=EMPTY),
                       content_source(entries()+[('later', b'bad-deflate', 0)])):
            with mock.patch.object(core._ConfigContentDecoder, '__init__', init):
                with self.assertRaises((core.InvalidStructure, core.UnsupportedLayout)): self.read(source)
            decoder = decoders[-1]
            self.assertTrue(decoder.failed); self.assertTrue(decoder.chains.failed)
            usage = dict(decoder.budget.counts)
            with self.assertRaises(core.InvalidStructure): decoder.decode(ABC_FIXED, 'raw_deflate')
            self.assertEqual(decoder.budget.counts, usage)

    def test_exact_types_and_no_budget_widening(self):
        for value in (None, {}, core.ConfigContentDecodeProfile(DECLARATIONS, '0', 0)):
            with self.assertRaises(ValueError):
                core.observe_config_root_reference_projection(lambda a,n:b'', 0, profile=value)
        for field in fields(core.CatalogLimits):
            source = successful_source()
            with self.assertRaises(ValueError): self.read(source, catalog_limits=core.CatalogLimits(
                **{field.name: getattr(core.CatalogLimits(), field.name)+1}))
            self.assertEqual(source.calls, [])

    def test_shared_budget_exact_boundary_and_one_less(self):
        baseline=self.read(successful_source())
        for name in ('output_bytes', 'bytes_processed', 'read_bytes', 'page_reads'):
            amount=getattr(baseline.usage, name)
            limits=core.CatalogLimits(**{'max_'+name: amount})
            self.assertEqual(self.read(successful_source(),catalog_limits=limits).usage, baseline.usage)
            limits=core.CatalogLimits(**{'max_'+name: amount-1})
            with self.assertRaises(core.ResourceLimit): self.read(successful_source(),catalog_limits=limits)

    def test_final_output_reservation_failure_also_poisons(self):
        baseline=self.read(successful_source()); decoders=[]
        original=core._ConfigContentDecoder.__init__
        def init(obj,*args,**kwargs): original(obj,*args,**kwargs); decoders.append(obj)
        with mock.patch.object(core._ConfigContentDecoder,'__init__',init):
            with self.assertRaises(core.ResourceLimit): self.read(successful_source(),
                catalog_limits=core.CatalogLimits(max_output_bytes=baseline.usage.output_bytes-1))
        self.assertTrue(decoders[-1].failed); self.assertTrue(decoders[-1].chains.failed)

    def test_projection_reservation_charged_exactly_before_parse(self):
        reserve=projector.reserve_root_projection
        parse=projector.project_root_reference_prefix
        charge=catalog._Budget.charge
        events=[]; active=[False]; reservation=[None]
        def observed_reserve(data,**kwargs):
            result=reserve(data,**kwargs)
            if not active[0]:
                active[0]=True; events.clear(); reservation[0]=result
            return result
        def observed_charge(obj,name,amount):
            if active[0]: events.append((name,amount))
            return charge(obj,name,amount)
        def observed_parse(data,**kwargs):
            expected=reservation[0]
            self.assertEqual(events,[('output_bytes',2048),('bytes_processed',expected.bytes_processed)])
            return parse(data,**kwargs)
        with mock.patch.object(projector,'reserve_root_projection',observed_reserve), \
             mock.patch.object(catalog._Budget,'charge',observed_charge), \
             mock.patch.object(projector,'project_root_reference_prefix',observed_parse):
            self.read(successful_source())

    def test_exact_prefix_ceiling_includes_delimiter_not_suffix(self):
        content=b'\xef\xbb\xbf'+b' '*981+b'{0,'+GUID.encode()+b','
        self.assertEqual(len(content),1024)
        self.assertEqual(self.read(successful_source(root=content+b'PRIVATE')).projected_root_count,1)
        with self.assertRaises(core.ResourceLimit) as caught:
            self.read(successful_source(root=content[:3]+b' '+content[3:]))
        self.assertEqual(caught.exception.code,'config_projection_prefix_bytes')

    def test_root_target_alias_and_later_alias_reject_complete_observation(self):
        root=stored_literal(PREFIX)
        same=chain_source(rows=[row(marker=1), row('root',start=1,length=len(root)),
            row(GUID,start=1,length=len(root))], nodes=chain_nodes(root,1))
        later=content_source(entries(),trailing_rows=[row('alias',start=2,length=len(ABC_FIXED))])
        for value in (same,later):
            with self.assertRaises(catalog.UnsupportedSharing) as caught: self.read(value)
            self.assertEqual(caught.exception.code,'config_chain_overlap')

    def test_later_invalid_chain_prevents_early_success(self):
        root=stored_literal(PREFIX)
        value=chain_source(rows=[row(marker=1), row('other',start=1,length=len(ABC_FIXED)),
            row(GUID,start=2,length=len(ABC_FIXED)), row('root',start=3,length=len(root)),
            row('later',start=4,length=1)],
            nodes={1:(0,ABC_FIXED),2:(0,ABC_FIXED),3:(0,root),4:(4,b'x')})
        with self.assertRaises(core.InvalidStructure) as caught: self.read(value)
        self.assertEqual(caught.exception.code,'config_chain_cycle')

    def test_old_full_reader_source_is_exact_prefix(self):
        # Git checkout may use CRLF on Windows; compare normalized source text.
        raw = (ROOT/'scripts/native_1c_db_oracle/config_framing_reader.py').read_text(encoding='utf-8').encode('utf-8')
        prefix = raw.split(b'\n\n# Explicit partial-reference lane.')[0]
        self.assertEqual(hashlib.sha256(prefix).hexdigest(), '3b2c78ceac98cddf7220d0a5c956d8c742e59b5c7c57a1bc1ee4d562fe19c096')

if __name__ == '__main__': unittest.main()
