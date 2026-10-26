"""Private synthetic content proof; neither native equivalence nor applied state."""
from dataclasses import FrozenInstanceError, asdict, fields
import ast
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'), str(ROOT / 'yadinassi/storage')]
import config_framing_reader as core
from filedb_catalog import CatalogError, UnsupportedSharing
from test_native_1c_db_oracle_config_blob_chain_reader import (
    DECLARATIONS, P, RECIPE as CHAIN_RECIPE, blob_calls, chain_nodes, primitive, row, source)

# These complete stream fixtures are literal, independent of the production
# decoder. Stored-block LEN/NLEN bytes and the split final-bit case are explicit.
EMPTY = bytes.fromhex('0300')
ABC_FIXED = bytes.fromhex('4b4c4a0600')
ABC_STORED = bytes.fromhex('010300fcff616263')
ABC_MULTIBLOCK = bytes.fromhex('000100feff61010200fdff6263')
DYNAMIC = bytes.fromhex(
    'edc9471180300000302b582b7b6f68413d3ab84bbe0979515675d376fd304ef3b26efb715e774ccf'
    '9b05a594524a29a594524a29a594524a29a594524a29a594524a29f5fffa00')
DYNAMIC_PAYLOAD = b'abcdefghijklmnopqrstuvwxyz ' * 400

RECIPE = dict(CHAIN_RECIPE,
    identifier='config_content_decode_8380_8192_v1',
    phases='all_selected_name_part_guards_then_exact_chain_content_v1',
    selected_name='printable_ascii_1_128_units_ascii_fold_unique_v1',
    selected_parts='every_selected_part_zero_required_v1',
    dynamic_names='reject_final_new_and_any_ascii_fold_dynupdate_marker_v1',
    plain_names=('dynamicallyupdated', 'sprscndinfo', 'dbnamesversion', 'siversions'),
    plain_patterns='leading_left_brace_or_fo_version_substring_or_final_inf_pf_v1',
    compression='selected_singlepart_ascii_name_rule_raw_deflate_v1',
    inflate='raw_minus15_eof_full_consumption_no_flush_no_fallback_v1',
    content_limits=(4194304, 8388608, 4096, 16384), inflate_chunks=(32768, 65536),
    representation_weights=(512, 2, 128, 128, 3, 128),
    content_weights=(512, 8, 4, 256, 131072, 2, 2),
    inflate_output_probe='min_chunk_remaining_plus_one_strictly_positive_v1',
    content_assembly='plain_alias_or_reserved_final_immutable_decoded_copy_v1',
    content_budget='identical_chain_budget_cumulative_poison_on_failure_v1',
    positive_decoded_witness='one_complete_raw_stream_positive_output_required_v1')
RECIPE_SHA256 = '2afa62880be57cae787c9eafb4ccc0dc3022f1560e2becc418bc5e64efb31a3e'


def packed(payload, *, level=6, strategy=zlib.Z_DEFAULT_STRATEGY):
    """Independent synthetic encoder for size and chunk-boundary cases only."""
    encoder = zlib.compressobj(level, zlib.DEFLATED, -15, strategy=strategy)
    return encoder.compress(payload) + encoder.flush()


def profile():
    return core.ConfigContentDecodeProfile(DECLARATIONS, '0', 0)


def content_source(entries=None, *, trailing_rows=(), **kwargs):
    """Each (name, stored bytes, part) has disjoint logical blocks, even per page."""
    entries = [('opaque', ABC_FIXED, 0)] if entries is None else entries
    rows, nodes, start = [row(marker=1)], {}, 1
    for name, stored, part in entries:
        rows.append(row(name, start=start, length=len(stored), part=part))
        new = chain_nodes(stored, start)
        nodes.update(new)
        start = max(new, default=start) + 1
    return source(rows=rows + list(trailing_rows), nodes=nodes, **kwargs)


def decoder(*, limits=None, catalog_limits=None):
    value = source()
    chains, reader = primitive(value, catalog_limits=catalog_limits)
    result = core._ConfigContentDecoder(chains, limits or core.ConfigContentDecodeLimits())
    return result, chains, reader, value


class TracedInflater:
    """Observe the real zlib contract without changing any bytes or progress."""
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.calls = []

    def decompress(self, data, max_length=0):
        previous_tail = self.wrapped.unconsumed_tail
        self.calls.append((data, max_length, previous_tail))
        if not 1 <= max_length <= 65536:
            raise AssertionError('unbounded output request')
        if len(data) > 32768 or (previous_tail and data != previous_tail):
            raise AssertionError('new input appended to pending tail')
        return self.wrapped.decompress(data, max_length)

    @property
    def eof(self): return self.wrapped.eof
    @property
    def unused_data(self): return self.wrapped.unused_data
    @property
    def unconsumed_tail(self): return self.wrapped.unconsumed_tail
    def flush(self, *args): raise AssertionError('flush is not a hard cap')


class ConfigContentDecodeCoreTests(unittest.TestCase):
    def read(self, value, **kwargs):
        return core.observe_config_content_decode(value.read_at, value.size, profile=profile(), **kwargs)

    def test_old_module_ast_and_eager_imports_unchanged(self):
        path = ROOT / 'scripts/native_1c_db_oracle/config_framing_reader.py'
        tree = ast.parse(path.read_text())
        old = ast.Module(body=tree.body[:30], type_ignores=[])
        self.assertEqual(hashlib.sha256(ast.dump(old, include_attributes=False).encode()).hexdigest(),
                         '8201d15d926649e23f3a7e809e959f7993f412b2637eb88e5bc3314edfbf0767')
        eager = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any('zlib' in ast.dump(node) or 'filedb_named_file' in ast.dump(node)
                             for node in eager))
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr in ('flush', 'casefold')
                             for node in ast.walk(ast.Module(body=tree.body[30:], type_ignores=[]))))

    def test_profiles_limits_exact_types_and_no_default_budget_widening(self):
        p = profile()
        self.assertEqual(p.recipe(), RECIPE)
        self.assertEqual(p.recipe_sha256, RECIPE_SHA256)
        self.assertEqual(hashlib.sha256(json.dumps(RECIPE, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), RECIPE_SHA256)
        self.assertEqual(p.identifier, 'config_content_decode_8380_8192_v1')
        self.assertEqual((p.candidate_stride, p.filename_offset, p.binarydata_offset, p.partno_offset),
                         (301, 1, 287, 295))
        with self.assertRaises(FrozenInstanceError): p.identifier = 'changed'
        for kind in (core.ConfigFramingProfile, core.ConfigMarkerCensusProfile,
                     core.ConfigZeroMarkerFilenameProfile, core.ConfigEntryReferenceProfile,
                     core.ConfigBlobChainProfile):
            with self.assertRaises(ValueError):
                core.observe_config_content_decode(lambda a, n: b'', 0, profile=kind(DECLARATIONS, '0', 0))
        for key in ('limits', 'chain_limits', 'content_limits', 'catalog_limits'):
            with self.assertRaises(ValueError): self.read(content_source(), **{key: {}})
        for name, ceiling in (('max_content_bytes', 4194304), ('max_total_content_bytes', 8388608),
                              ('max_inflate_calls', 4096), ('max_total_inflate_calls', 16384)):
            for invalid in (False, True, 0, -1, ceiling + 1, 1.0, '1'):
                with self.assertRaises(ValueError): core.ConfigContentDecodeLimits(**{name: invalid})
        for f in fields(core.CatalogLimits):
            value = content_source()
            with self.assertRaises(ValueError):
                self.read(value, catalog_limits=core.CatalogLimits(**{f.name: getattr(core.CatalogLimits(), f.name) + 1}))
            self.assertEqual(value.calls, [])

    def test_literal_complete_stream_byte_equality(self):
        self.assertEqual((DYNAMIC[0] >> 1) & 3, 2)
        vectors = ((EMPTY, b''), (ABC_FIXED, b'abc'), (ABC_STORED, b'abc'),
                   (ABC_MULTIBLOCK, b'abc'), (DYNAMIC, DYNAMIC_PAYLOAD),
                   (bytes.fromhex('010500faff00ff80fe7f'), b'\x00\xff\x80\xfe\x7f'))
        for stored, expected in vectors:
            with self.subTest(stored=stored[:4]):
                context, chains, _, _ = decoder()
                self.assertIs(context.budget, chains.budget)
                actual = context.decode(stored, 'raw_deflate')
                self.assertIs(type(actual), bytes)
                self.assertEqual(actual, expected)
                self.assertEqual(context.total_content_bytes, len(expected))
                self.assertGreaterEqual(context.total_calls, 1)
                self.assertFalse(context.failed)

    def test_plain_alias_is_exact_and_stream_like_bytes_not_inflated(self):
        context, chains, _, _ = decoder()
        for stored in (ABC_FIXED, b'\x78\x9c\x00\xff', b'\x1f\x8b\xff', b'\xff\0not text'):
            before = chains.budget.usage()
            with mock.patch.object(zlib, 'decompressobj', side_effect=AssertionError('plain decoded')):
                self.assertIs(context.decode(stored, 'plain'), stored)
            self.assertEqual(chains.budget.usage(), before)
        self.assertEqual(context.total_calls, 0)
        self.assertEqual(context.total_content_bytes, sum(map(len, (ABC_FIXED, b'\x78\x9c\x00\xff', b'\x1f\x8b\xff', b'\xff\0not text'))))

    def test_each_source_informed_plain_name_rule_and_negation(self):
        plain = ('DynamicallyUpdated', 'dYnAmIcAlLyUpDaTeD', 'SprScndInfo', 'sPrScNdInFo',
                 'DBNamesVersion', 'DBNAMESVERSION', 'siVersions', 'SIVERSIONS', '{', '{abc}',
                 'fo_version', 'aFO_VERSIONb', 'x.inf', 'X.InF', '.INF', 'x.old.pF', 'a..PF', ' .inf', 'x.new.inf')
        raw = ('root', 'metadata', 'PF', 'INF', 'x', 'DynamicallyUpdated ', ' SprScndInfo',
               'DBNamesVersions', 'xsiVersions', 'x{', 'FO-VERSION', 'x.inf.foo', 'x.PF.',
               'x.inf ', ' .inf ', ' foo_version', '../plain', 'C:\\private')
        for expected, names in (('plain', plain), ('raw_deflate', raw)):
            for name in names:
                with self.subTest(name=name):
                    _, chains, _, _ = decoder()
                    keys = set()
                    self.assertEqual(core._config_content_name(name, len(name), chains.budget, keys), expected)
                    self.assertEqual(keys, {name.lower()})

    def test_selected_name_ascii_policy_and_name_budget_before_keys(self):
        for name in ('\x00x', '\x1fx', 'x\x7f', 'Ω', 'é', 'e\u0301', 'ſiVersions', '\uff33prScndInfo', '😀'):
            value = content_source([('good', ABC_FIXED, 0), (name, ABC_FIXED, 0)])
            with self.assertRaisesRegex(core.UnsupportedLayout, 'config_content_name'):
                self.read(value)
            self.assertEqual(blob_calls(value), [])
        # A printable space is significant, not trim-to-empty or a pathname.
        result = self.read(content_source([(' ', ABC_FIXED, 0), ('x', ABC_FIXED, 0), ('x ', ABC_FIXED, 0)]))
        self.assertEqual(result.completed_chain_count, 3)
        for name in ('x', 'x' * 128):
            _, chains, _, _ = decoder()
            keys, before = set(), chains.budget.usage()
            core._config_content_name(name, len(name), chains.budget, keys)
            after = chains.budget.usage()
            self.assertEqual(after.output_bytes - before.output_bytes, 512 + 8 * len(name))
            self.assertEqual(after.bytes_processed - before.bytes_processed, 4 * len(name))
        _, chains, _, _ = decoder()
        remaining = chains.budget.limits.max_output_bytes - chains.budget.counts['output_bytes']
        chains.budget.charge('output_bytes', remaining - 519)
        keys = set()
        with self.assertRaisesRegex(core.ResourceLimit, 'output_bytes'):
            core._config_content_name('x', 1, chains.budget, keys)
        self.assertEqual(keys, set())

    def test_dynamic_name_guards_precede_all_chain_and_decoder_work(self):
        for name in ('x.new', 'x.NeW', '.NEW', 'name.inf.new', '{plain.new',
                     '_dynupdate_', 'x_DyNuPdAtE_y', 'x_dynupdate_.inf', 'fo_version_dynupdate_'):
            value = content_source([('good', ABC_FIXED, 0), (name, ABC_FIXED, 0)])
            with mock.patch.object(core._ConfigBlobChains, 'read', side_effect=AssertionError('early chain')):
                with mock.patch.object(zlib, 'decompressobj', side_effect=AssertionError('early inflater')):
                    with self.assertRaisesRegex(core.UnsupportedLayout, 'config_content_dynamic'):
                        self.read(value)
            self.assertEqual(blob_calls(value), [])
        # No dynamic-name resolution or environment override; opaque special bytes
        # are admitted but cannot stand in for an applied-state selection.
        with mock.patch.dict('os.environ', {'TOOL1CD_NODYNUP': '1'}):
            result = self.read(content_source([('DynamicallyUpdated', b'not parsed', 0), ('x', ABC_FIXED, 0)]))
        self.assertEqual(result.plain_entry_count, 1)
        self.assertEqual(result.applied_state, 'not_observed')

    def test_late_duplicate_and_all_nonzero_parts_reject_before_first_chain(self):
        for name in ('same', 'SAME', 'SaMe'):
            value = content_source([('same', ABC_FIXED, 0), (name, ABC_FIXED, 0)])
            with self.assertRaisesRegex(core.UnsupportedLayout, 'config_content_duplicate'):
                self.read(value)
            self.assertEqual(blob_calls(value), [])
        for parts in ((1,), (0, 2), (1, 0), (1, 1), (0, 4095)):
            value = content_source([(f'name{i}', ABC_FIXED, part) for i, part in enumerate(parts)])
            with self.assertRaisesRegex(core.UnsupportedLayout, 'config_content_nonzero_part'):
                self.read(value)
            self.assertEqual(blob_calls(value), [])
        # Same canonical part for different unique names is not a collision.
        result = self.read(content_source([('name1', ABC_FIXED, 0), ('name2', ABC_FIXED, 0)]))
        self.assertEqual((result.selected_part_zero_count, result.selected_part_nonzero_count), (2, 0))

    def test_exclusions_keep_part_opaque_but_all_zero_marker_utf16_validates(self):
        extras = [row('Ω', start=0, part_raw=b'\xff' * 6), row('', part_raw=b'\xff' * 6),
                  b'\xff' + b'\xff' * 300, b'\x01' + b'\xff' * 300]
        value = content_source(trailing_rows=extras)
        result = self.read(value)
        self.assertEqual((result.reference_excluded_count, result.empty_name_excluded_count,
                          result.later_one_count, result.later_other_count), (1, 1, 1, 1))
        for index in (2, 3):
            offset = index * 301 + 295
            physical = value.data_pages[offset // P] * P + offset % P
            self.assertFalse(any(a <= physical < a + n for a, n in value.calls))
        for extra, code in ((row(raw=b'\x00\xd8', units=1, start=0), 'config_filename_encoding'),
                            (row(units=129, start=0), 'config_filename_length')):
            value = content_source(trailing_rows=[extra])
            with self.assertRaisesRegex(CatalogError, code): self.read(value)
            self.assertEqual(blob_calls(value), [])

    def test_all_selected_exact_private_bytes_single_graph_and_finite_result(self):
        binary = bytes(range(256)) * 7
        stored = packed(binary, level=0)
        entries = [('private.inf', b'\xff\0raw', 0), ('opaque', stored, 0), ('empty', EMPTY, 0)]
        value = content_source(entries)
        actual, budgets, chains_seen = [], [], []
        original_decode, original_read = core._ConfigContentDecoder.decode, core._ConfigBlobChains.read
        def inspect_decode(context, payload, kind):
            result = original_decode(context, payload, kind)
            actual.append((kind, result))
            budgets.append(context.budget)
            return result
        def inspect_read(chains, start, length):
            chains_seen.append(chains)
            return original_read(chains, start, length)
        with mock.patch.object(core._ConfigContentDecoder, 'decode', inspect_decode):
            with mock.patch.object(core._ConfigBlobChains, 'read', inspect_read):
                with mock.patch.object(core, 'observe_config_blob_chains', side_effect=AssertionError('public reread')):
                    result = self.read(value)
        self.assertEqual(actual, [('plain', b'\xff\0raw'), ('raw_deflate', binary), ('raw_deflate', b'')])
        self.assertEqual(len({id(item) for item in chains_seen}), 1)
        self.assertTrue(all(item is chains_seen[0].budget for item in budgets))
        self.assertEqual((result.plain_entry_count, result.deflate_entry_count, result.positive_decoded_entry_count), (1, 2, 1))
        self.assertEqual((result.plain_content_bytes, result.inflated_content_bytes), (5, len(binary)))
        self.assertEqual(result.total_stored_bytes_read, sum(len(stored) for _, stored, _ in entries))
        self.assertEqual(result.completed_chain_count, 3)
        self.assertEqual(result.compression_validation, 'selected_singlepart_ascii_name_rule_raw_deflate_v1')
        self.assertEqual((result.file_identity, result.root_identity, result.applied_state, result.native_acceptance),
                         ('not_observed', 'not_observed', 'not_observed', 'pending'))
        self.assertEqual(len(blob_calls(value)), 2 * result.total_chain_blocks)
        self.assertFalse(value.closed)
        public = repr(asdict(result))
        self.assertNotIn('private.inf', public)
        self.assertFalse({'names', 'payload', 'payload_hash', 'parts', 'pointers', 'contents'} & set(asdict(result)))
        with self.assertRaises(FrozenInstanceError): result.inflated_content_bytes = 0

    def test_positive_decoded_witness_not_plain_or_empty_streams(self):
        for entries in ([('x.inf', b'plain', 0)], [('empty', EMPTY, 0)],
                        [('empty', EMPTY, 0), ('plain.inf', b'plain', 0)]):
            with self.assertRaisesRegex(core.UnsupportedLayout, 'config_content_no_positive'):
                self.read(content_source(entries))
        result = self.read(content_source([('empty', EMPTY, 0), ('positive', ABC_FIXED, 0)]))
        self.assertEqual((result.deflate_entry_count, result.positive_decoded_entry_count), (2, 1))

    def test_invalid_wrapped_dictionary_and_truncated_streams_never_fallback(self):
        wrapped = zlib.compress(b'abc')
        gzip_encoder = zlib.compressobj(wbits=31)
        gzip = gzip_encoder.compress(b'abc') + gzip_encoder.flush()
        cases = (wrapped, gzip, b'\x07', b'\xff\xff', b'\x03\x02\x00',
                 ABC_FIXED[:-1], ABC_STORED[:-1], ABC_MULTIBLOCK[:-1], DYNAMIC[:-1], b'\x00')
        for stored in cases:
            context, _, _, _ = decoder()
            with self.subTest(stored=stored[:4]):
                with self.assertRaises(CatalogError) as caught:
                    context.decode(stored, 'raw_deflate')
                self.assertNotIn(repr(stored), str(caught.exception))
                self.assertTrue(context.failed)
                usage = context.budget.usage()
                with self.assertRaisesRegex(CatalogError, 'config_content_failed'):
                    context.decode(ABC_FIXED, 'raw_deflate')
                self.assertEqual(context.budget.usage(), usage)

    def test_trailing_zero_bytes_concatenation_and_unread_source_eof_reject(self):
        for stored in (ABC_FIXED + b'x', ABC_FIXED + b'\x00', ABC_FIXED + EMPTY,
                       EMPTY + ABC_FIXED, ABC_FIXED + b'\x00' * 32768):
            context, _, _, _ = decoder()
            with self.assertRaisesRegex(CatalogError, 'config_content_trailing'):
                context.decode(stored, 'raw_deflate')
            self.assertTrue(context.failed)
        # A late decode failure invalidates the observation, with no third read.
        value = content_source([('ok', ABC_FIXED, 0), ('bad', ABC_FIXED + b'\0', 0), ('later', ABC_FIXED, 0)])
        with self.assertRaisesRegex(CatalogError, 'config_content_trailing'): self.read(value)
        self.assertEqual(len(blob_calls(value)), 4)

    def test_input_chunks_pending_tail_positive_max_length_and_no_flush(self):
        data = random.Random(17).randbytes(80000) + b'A' * 400000
        stored = packed(data)
        original, instances = zlib.decompressobj, []
        def factory(*args, **kwargs):
            self.assertEqual(args or tuple(kwargs.values()), (-15,))
            self.assertFalse('zdict' in kwargs)
            result = TracedInflater(original(*args, **kwargs)); instances.append(result); return result
        with mock.patch.object(zlib, 'decompressobj', factory):
            with mock.patch.object(zlib, 'decompress', side_effect=AssertionError('one-shot')):
                context, _, _, _ = decoder()
                self.assertEqual(context.decode(stored, 'raw_deflate'), data)
        self.assertEqual(len(instances), 1)
        calls = instances[0].calls
        self.assertTrue(any(tail for _, _, tail in calls))
        self.assertGreater(len(calls), 3)
        self.assertEqual(context.total_calls, len(calls))
        self.assertTrue(all(0 < cap <= 65536 and len(chunk) <= 32768 for chunk, cap, _ in calls))

    def test_per_entry_and_aggregate_exact_content_caps_plus_one(self):
        for kind, stored, content in (('plain', b'abc', b'abc'), ('raw_deflate', ABC_FIXED, b'abc')):
            context, _, _, _ = decoder(limits=core.ConfigContentDecodeLimits(max_content_bytes=3))
            self.assertEqual(context.decode(stored, kind), content)
            context, _, _, _ = decoder(limits=core.ConfigContentDecodeLimits(max_content_bytes=2))
            with self.assertRaisesRegex(core.ResourceLimit, 'config_content_bytes'):
                context.decode(stored, kind)
            self.assertTrue(context.failed)
        context, _, _, _ = decoder(limits=core.ConfigContentDecodeLimits(max_total_content_bytes=4))
        self.assertEqual(context.decode(b'x', 'plain'), b'x')
        self.assertEqual(context.decode(ABC_FIXED, 'raw_deflate'), b'abc')
        self.assertEqual(context.decode(EMPTY, 'raw_deflate'), b'')
        self.assertEqual(context.total_content_bytes, 4)
        with self.assertRaisesRegex(core.ResourceLimit, 'config_content_total_bytes'):
            context.decode(b'x', 'plain')
        context, _, _, _ = decoder(limits=core.ConfigContentDecodeLimits(max_total_content_bytes=3))
        context.decode(b'x', 'plain')
        with self.assertRaisesRegex(core.ResourceLimit, 'config_content_total_bytes'):
            context.decode(ABC_FIXED, 'raw_deflate')

    def test_hard_content_cap_bomb_and_total_cap_without_refunds(self):
        data = b'X' * 4194304
        compressed = packed(data)
        context, _, _, _ = decoder()
        self.assertEqual(context.decode(compressed, 'raw_deflate'), data)
        self.assertEqual(context.decode(compressed, 'raw_deflate'), data)
        self.assertEqual(context.total_content_bytes, 8388608)
        with self.assertRaises(core.ResourceLimit): context.decode(ABC_FIXED, 'raw_deflate')
        context, _, _, _ = decoder()
        with self.assertRaisesRegex(core.ResourceLimit, 'config_content_bytes'):
            context.decode(packed(data + b'X'), 'raw_deflate')
        self.assertTrue(context.failed)

    def test_call_limits_are_cumulative_and_checked_before_zlib(self):
        class Producing:
            eof = False
            unused_data = b''
            unconsumed_tail = b''
            def __init__(self): self.calls = 0
            def decompress(self, data, max_length):
                self.calls += 1
                self.unconsumed_tail = data
                return b'x'
        fake = Producing()
        context, _, _, _ = decoder(limits=core.ConfigContentDecodeLimits(max_inflate_calls=2))
        with mock.patch.object(zlib, 'decompressobj', return_value=fake):
            with self.assertRaisesRegex(core.ResourceLimit, 'config_content_inflate_calls'):
                context.decode(ABC_FIXED, 'raw_deflate')
        self.assertEqual((fake.calls, context.total_calls), (2, 2))
        context, _, _, _ = decoder(limits=core.ConfigContentDecodeLimits(max_total_inflate_calls=2))
        context.decode(ABC_FIXED, 'raw_deflate')
        context.decode(ABC_FIXED, 'raw_deflate')
        forbidden = mock.Mock()
        forbidden.decompress.side_effect = AssertionError('call after total call ceiling')
        with mock.patch.object(zlib, 'decompressobj', return_value=forbidden):
            with self.assertRaisesRegex(core.ResourceLimit, 'config_content_total_inflate_calls'):
                context.decode(ABC_FIXED, 'raw_deflate')
        forbidden.decompress.assert_not_called()
        self.assertEqual(context.total_calls, 2)
        self.assertTrue(context.failed)

    def test_empty_input_drain_truncation_and_nonprogress_are_finite(self):
        class Fake:
            eof = False
            unused_data = b''
            unconsumed_tail = b''
            def __init__(self, mode): self.mode, self.calls = mode, []
            def decompress(self, data, max_length):
                self.calls.append((data, max_length))
                if self.mode == 'drain':
                    if data: return b'a'
                    self.eof = True
                    return b'b'
                if self.mode == 'stuck': self.unconsumed_tail = data
                return b''
        for mode in ('drain', 'stuck', 'truncated'):
            fake = Fake(mode)
            context, _, _, _ = decoder()
            with mock.patch.object(zlib, 'decompressobj', return_value=fake):
                if mode == 'drain':
                    self.assertEqual(context.decode(b'x', 'raw_deflate'), b'ab')
                    self.assertEqual(fake.calls[-1][0], b'')
                else:
                    code = 'config_content_nonprogress' if mode == 'stuck' else 'config_content_truncated_deflate'
                    with self.assertRaisesRegex(CatalogError, '^' + code + '$'):
                        context.decode(b'x', 'raw_deflate')
                    self.assertEqual(len(fake.calls), 1 if mode == 'stuck' else 2)
                    self.assertEqual(context.total_calls, len(fake.calls))
                    self.assertTrue(context.failed)
            self.assertTrue(all(cap > 0 for _, cap in fake.calls))

    def test_shared_budget_rejections_before_constructor_and_decompress(self):
        context, chains, _, _ = decoder()
        remaining = context.budget.limits.max_output_bytes - context.budget.counts['output_bytes']
        context.budget.charge('output_bytes', remaining - 131071)
        with mock.patch.object(zlib, 'decompressobj', side_effect=AssertionError('construction before reservation')):
            with self.assertRaisesRegex(core.ResourceLimit, 'output_bytes'):
                context.decode(ABC_FIXED, 'raw_deflate')
        self.assertTrue(context.failed)
        for remaining in (131072, 131072 + len(ABC_FIXED), 131072 + len(ABC_FIXED) + 2 * len(ABC_FIXED)):
            context, chains, _, _ = decoder()
            available = context.budget.limits.max_output_bytes - context.budget.counts['output_bytes']
            context.budget.charge('output_bytes', available - remaining)
            fake = mock.Mock()
            fake.decompress.side_effect = AssertionError('decompress before reservation')
            with mock.patch.object(zlib, 'decompressobj', return_value=fake):
                with self.assertRaisesRegex(core.ResourceLimit, 'output_bytes'):
                    context.decode(ABC_FIXED, 'raw_deflate')
            self.assertFalse(fake.decompress.called)
            self.assertTrue(context.failed)

    def test_final_immutable_copy_reservation_and_processing_before_return(self):
        context, _, _, _ = decoder()
        self.assertEqual(context.decode(ABC_FIXED, 'raw_deflate'), b'abc')
        total_output = context.budget.usage().output_bytes
        context, _, _, _ = decoder(catalog_limits=core.CatalogLimits(max_output_bytes=total_output - 1))
        actual_calls = []
        original = zlib.decompressobj
        def factory(*args, **kwargs):
            result = TracedInflater(original(*args, **kwargs)); actual_calls.append(result); return result
        with mock.patch.object(zlib, 'decompressobj', factory):
            with self.assertRaisesRegex(core.ResourceLimit, 'output_bytes'):
                context.decode(ABC_FIXED, 'raw_deflate')
        self.assertEqual(len(actual_calls[0].calls), 1)
        self.assertTrue(actual_calls[0].eof)
        self.assertTrue(context.failed)
        context, _, _, _ = decoder()
        remaining = context.budget.limits.max_bytes_processed - context.budget.counts['bytes_processed']
        context.budget.charge('bytes_processed', remaining)
        with mock.patch.object(zlib, 'decompressobj', wraps=original):
            with self.assertRaisesRegex(core.ResourceLimit, 'bytes_processed'):
                context.decode(ABC_FIXED, 'raw_deflate')
        self.assertTrue(context.failed)

    def test_all_existing_shared_gates_intersect_and_no_reread(self):
        baseline = self.read(content_source())
        for field in ('page_reads', 'read_bytes', 'bytes_processed', 'blob_visits', 'total_blob_bytes', 'output_bytes'):
            used = getattr(baseline.usage, field)
            self.read(content_source(), catalog_limits=core.CatalogLimits(**{'max_' + field: used}))
            with self.assertRaises(core.ResourceLimit):
                self.read(content_source(), catalog_limits=core.CatalogLimits(**{'max_' + field: used - 1}))
        self.read(content_source(), catalog_limits=core.CatalogLimits(max_mapping_pages=3))
        value = content_source()
        with self.assertRaisesRegex(core.ResourceLimit, 'mapping_pages'):
            self.read(value, catalog_limits=core.CatalogLimits(max_mapping_pages=2))
        self.assertEqual(blob_calls(value), [])

    def test_decode_failure_poison_on_same_successful_chain_and_sanitized_error(self):
        value = content_source()
        chains, _ = primitive(value)
        stored, _, _ = chains.read(1, len(ABC_FIXED))
        context = core._ConfigContentDecoder(chains, core.ConfigContentDecodeLimits())
        fake = mock.Mock()
        fake.decompress.side_effect = zlib.error('PRIVATE_FILENAME and raw payload bytes')
        with mock.patch.object(zlib, 'decompressobj', return_value=fake):
            with self.assertRaises(CatalogError) as caught: context.decode(stored, 'raw_deflate')
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertNotIn('payload', str(caught.exception))
        self.assertTrue(context.failed)
        self.assertTrue(chains.failed)
        calls, usage = list(value.calls), chains.budget.usage()
        with self.assertRaisesRegex(CatalogError, 'config_content_failed'):
            context.decode(stored, 'plain')
        self.assertEqual(value.calls, calls)
        self.assertEqual(chains.budget.usage(), usage)
        with self.assertRaisesRegex(CatalogError, 'config_chain_failed_attempt'):
            chains.read(1, len(ABC_FIXED))
        self.assertEqual(value.calls, calls)

    def test_shared_chain_policy_zero_tail_and_same_page_ownership_remain(self):
        value = source(rows=[row(marker=1), row('one', start=1, length=5), row('two', start=2, length=5)],
                       nodes={1: (3, ABC_FIXED), 3: (0, b''), 2: (0, ABC_FIXED)})
        result = self.read(value)
        self.assertEqual((result.completed_chain_count, result.total_chain_blocks, result.zero_payload_block_count), (2, 3, 1))
        value = source(rows=[row(marker=1), row('one', start=1, length=5), row('two', start=1, length=5)],
                       nodes={1: (0, ABC_FIXED)})
        with self.assertRaisesRegex(UnsupportedSharing, 'config_chain_overlap'): self.read(value)
        for length in (4, 6):
            value = source(rows=[row(marker=1), row('one', length=length)], nodes={1: (0, ABC_FIXED)})
            with self.assertRaisesRegex(CatalogError, 'config_chain_length'): self.read(value)

    def test_all_4095_selected_unique_names_with_one_actual_decoder_witness(self):
        entries = [(f'x{i}.inf', b'x', 0) for i in range(4094)] + [('packed', ABC_FIXED, 0)]
        value = content_source(entries)
        result = self.read(value)
        self.assertEqual((result.candidate_slots, result.selected_reference_count,
                          result.selected_part_zero_count, result.completed_chain_count),
                         (4096, 4095, 4095, 4095))
        self.assertEqual((result.plain_entry_count, result.deflate_entry_count,
                          result.positive_decoded_entry_count, result.inflate_call_count),
                         (4094, 1, 1, 1))
        self.assertEqual((result.plain_content_bytes, result.inflated_content_bytes,
                          result.total_stored_bytes_read), (4094, 3, 4099))
        self.assertEqual(result.total_chain_blocks, 4095)
        self.assertFalse(value.closed)
        value = content_source(entries, trailing_rows=[row('too_many', start=0)])
        with self.assertRaisesRegex(core.ResourceLimit, 'config_slots'):
            self.read(value)
        self.assertEqual(blob_calls(value), [])

    def test_private_input_exact_types_and_existing_poison_are_not_retried(self):
        class StringSubclass(str): pass
        class BytesSubclass(bytes): pass
        for stored, kind in ((b'', 'raw_deflate'), (bytearray(ABC_FIXED), 'raw_deflate'),
                             (memoryview(ABC_FIXED), 'raw_deflate'), (BytesSubclass(ABC_FIXED), 'raw_deflate'),
                             (ABC_FIXED, StringSubclass('plain')), (ABC_FIXED, True), (ABC_FIXED, 'gzip')):
            context, chains, _, _ = decoder()
            with self.assertRaisesRegex(CatalogError, 'config_content_input'):
                context.decode(stored, kind)
            self.assertTrue(context.failed)
            self.assertTrue(chains.failed)
        for chains, limits in ((object(), core.ConfigContentDecodeLimits()), (None, {})):
            with self.assertRaises(ValueError): core._ConfigContentDecoder(chains, limits)
        context, chains, _, value = decoder()
        chains.failed = True
        usage, calls = chains.budget.usage(), list(value.calls)
        with self.assertRaisesRegex(CatalogError, 'config_content_failed_attempt'):
            context.decode(ABC_FIXED, 'raw_deflate')
        self.assertEqual(chains.budget.usage(), usage)
        self.assertEqual(value.calls, calls)

    def test_remaining_zero_uses_one_byte_probe_and_poisoned_overflow_is_not_refunded(self):
        class ExactThenFinish:
            eof = False
            unused_data = b''
            unconsumed_tail = b''
            def __init__(self, overflow): self.overflow, self.caps = overflow, []
            def decompress(self, data, max_length):
                self.caps.append(max_length)
                if len(self.caps) == 1: return b'x'
                self.eof = True
                return b'y' if self.overflow else b''
        for overflow in (False, True):
            context, chains, _, _ = decoder(limits=core.ConfigContentDecodeLimits(max_content_bytes=1))
            fake = ExactThenFinish(overflow)
            with mock.patch.object(zlib, 'decompressobj', return_value=fake):
                if overflow:
                    with self.assertRaisesRegex(core.ResourceLimit, 'config_content_bytes'):
                        context.decode(b'x', 'raw_deflate')
                    self.assertTrue(context.failed)
                    self.assertTrue(chains.failed)
                else:
                    self.assertEqual(context.decode(b'x', 'raw_deflate'), b'x')
            self.assertEqual(fake.caps, [2, 1])
            self.assertEqual(context.total_content_bytes, 1)
            self.assertEqual(context.total_calls, 2)

    def test_eof_requires_both_tail_fields_empty_and_late_failure_keeps_charges(self):
        class End:
            eof = True
            def __init__(self, unused, tail): self.unused_data, self.unconsumed_tail = unused, tail
            def decompress(self, data, max_length): return b'x'
        for unused, tail in ((b'x', b''), (b'', b'x'), (b'x', b'x')):
            context, _, _, _ = decoder()
            before = context.budget.usage()
            with mock.patch.object(zlib, 'decompressobj', return_value=End(unused, tail)):
                with self.assertRaisesRegex(CatalogError, 'config_content_trailing_data'):
                    context.decode(b'x', 'raw_deflate')
            self.assertEqual(context.total_content_bytes, 1)
            self.assertEqual(context.total_calls, 1)
            self.assertGreater(context.budget.usage().output_bytes, before.output_bytes)
            usage = context.budget.usage()
            with self.assertRaisesRegex(CatalogError, 'config_content_failed_attempt'):
                context.decode(ABC_FIXED, 'plain')
            self.assertEqual(context.budget.usage(), usage)

    def test_decoder_constructor_error_sanitized_and_final_processing_reserved(self):
        context, _, _, _ = decoder()
        with mock.patch.object(zlib, 'decompressobj', side_effect=zlib.error('PRIVATE error text')):
            with self.assertRaisesRegex(CatalogError, '^config_content_invalid_deflate$') as caught:
                context.decode(ABC_FIXED, 'raw_deflate')
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertTrue(context.failed)
        context, _, _, _ = decoder()
        context.decode(ABC_FIXED, 'raw_deflate')
        total = context.budget.usage().bytes_processed
        context, _, _, _ = decoder(catalog_limits=core.CatalogLimits(max_bytes_processed=total - 1))
        real, instances = zlib.decompressobj, []
        def factory(*args, **kwargs):
            result = TracedInflater(real(*args, **kwargs)); instances.append(result); return result
        with mock.patch.object(zlib, 'decompressobj', factory):
            with self.assertRaisesRegex(core.ResourceLimit, 'bytes_processed'):
                context.decode(ABC_FIXED, 'raw_deflate')
        self.assertEqual(len(instances[0].calls), 1)
        self.assertTrue(instances[0].eof)
        self.assertTrue(context.failed)

    def test_name_processing_budget_before_key_and_image_cap_before_io(self):
        _, chains, _, _ = decoder()
        remaining = chains.budget.limits.max_bytes_processed - chains.budget.counts['bytes_processed']
        chains.budget.charge('bytes_processed', remaining - 3)
        keys = set()
        with self.assertRaisesRegex(core.ResourceLimit, 'bytes_processed'):
            core._config_content_name('x', 1, chains.budget, keys)
        self.assertEqual(keys, set())
        calls = []
        with self.assertRaisesRegex(core.ResourceLimit, 'config_chain_image_bytes'):
            core.observe_config_content_decode(lambda a, n: calls.append((a, n)), 67108865, profile=profile())
        self.assertEqual(calls, [])
        value = content_source([('x' * 128, ABC_FIXED, 0)])
        self.assertEqual(self.read(value).max_filename_units, 128)
        value = content_source(trailing_rows=[row('x', units=129)])
        with self.assertRaisesRegex(CatalogError, 'config_filename_length'): self.read(value)
        self.assertEqual(blob_calls(value), [])

    def test_cold_stdlib_complete_observation_and_old_import_without_zlib(self):
        code = """import sys
sys.path[:0] = sys.argv[1:]
class Guard:
 def find_spec(self, fullname, path=None, target=None):
  if fullname == 'zlib': raise ImportError('forbidden eager zlib')
sys.meta_path.insert(0, Guard())
import config_framing_reader
assert 'zlib' not in sys.modules
assert not any(n == 'yadinassi' or n.startswith('yadinassi.') for n in sys.modules)
"""
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code,
                                 str(ROOT / 'scripts/native_1c_db_oracle'), str(ROOT / 'yadinassi/storage')],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        code = ('import sys,json,dataclasses;sys.path[:0]=sys.argv[1:];import config_framing_reader as c;'
                'raw=sys.stdin.buffer.read();p=c.ConfigContentDecodeProfile(c.DECLARATIONS,"0",0);'
                'o=c.observe_config_content_decode(lambda a,n:raw[a:a+n],len(raw),profile=p);'
                'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
                'assert "filedb_named_file" not in sys.modules;print(json.dumps(dataclasses.asdict(o),sort_keys=True))')
        value = content_source()
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code,
                                 str(ROOT / 'scripts/native_1c_db_oracle'), str(ROOT / 'yadinassi/storage')],
                                input=value.full_bytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), asdict(self.read(value)))


if __name__ == '__main__': unittest.main()
