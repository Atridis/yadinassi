"""Synthetic private locator/reference proof; no native semantic-root claim."""
from dataclasses import FrozenInstanceError, asdict, fields
import ast
import hashlib
import itertools
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'), str(ROOT / 'yadinassi/storage')]
import config_framing_reader as core
from filedb_catalog import CatalogError, UnsupportedSharing
from test_native_1c_db_oracle_config_blob_chain_reader import DECLARATIONS, P, blob_calls, chain_nodes, row, source
from test_native_1c_db_oracle_config_content_decode_reader import (
    ABC_FIXED, EMPTY, RECIPE as CONTENT_RECIPE, content_source, decoder, packed)

# Synthetic fixed literals are not captured native names/bytes or expected UUIDs.
GUID = b'01234567-89Ab-cDeF-0123-456789aBCdEf'
KEY = GUID.decode('ascii').lower()
LOCATOR = b'\xef\xbb\xbf{2,' + GUID + b'}'
# Independent raw-DEFLATE stored-block framing, no production encoder/parser.
ROOT_STORED = b'\x01\x2b\x00\xd4\xff' + LOCATOR
RECIPE = dict(CONTENT_RECIPE,
    identifier='config_root_reference_8380_8192_v1',
    phases='all_selected_guards_then_root_target_remaining_once_v1',
    locator_selector='root',
    locator_grammar='initial_utf8_bom_ws_lbrace_2_comma_bare_guid_rbrace_ws_eof_v1',
    locator_whitespace=(32, 9, 13, 10),
    locator_guid='ascii_hex_8_4_4_4_12_case_fold_no_semantic_constraints_v1',
    locator_limit=1024,
    locator_limit_stage='after_unchanged_content_decode_before_syntax_scan_v1',
    reference_resolution='private_selected_name_map_exactly_one_positive_target_v1',
    reference_order='root_then_target_then_remaining_insertion_order_no_cache_reread_v1',
    reference_attempt='single_use_poison_shared_decoder_and_chains_on_any_failure_v1',
    reference_map_weights=(512, 8, 4, 32), reference_parser_weights=(1024, 4, 128, 512),
    reference_lookup_weights=(256, 128), reference_observation_weight=4096,
    reference_relation='fixed_key_guid_reference_resolved_v1')
RECIPE_SHA256 = 'df07907176f55bb17c3ed086173da9549f05a0d44a63a934faee12e3829467c5'


def profile(): return core.ConfigRootReferenceProfile(DECLARATIONS, '0', 0)


def root_source(entries=None, **kwargs):
    return content_source([('root', ROOT_STORED, 0), (KEY, ABC_FIXED, 0)] if entries is None else entries, **kwargs)


def operation(value, *, catalog_limits=None, root_limits=None):
    reader = core.CatalogReader(value.read_at, value.size, limits=catalog_limits)
    reader._budget.charge('output_bytes', 1024)
    return core._ConfigRootReferenceOperation(reader, profile(), core.ConfigFramingLimits(),
        core.ConfigBlobChainLimits(), core.ConfigContentDecodeLimits(), root_limits or core.ConfigRootReferenceLimits())


class ConfigRootParserTests(unittest.TestCase):
    def parse(self, value, **kwargs):
        context, _, _, _ = decoder()
        return core._parse_config_root_reference(value, context.budget, core.ConfigRootReferenceLimits(**kwargs))

    def test_literal_minimum_case_fold_and_all_hex_values(self):
        self.assertEqual(len(LOCATOR), 43)
        self.assertEqual(self.parse(LOCATOR), KEY)
        for value in (b'0' * 8 + b'-' + b'0' * 4 + b'-' + b'0' * 4 + b'-' + b'0' * 4 + b'-' + b'0' * 12,
                      b'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF'):
            self.assertEqual(self.parse(b'\xef\xbb\xbf{2,' + value + b'}'), value.decode().lower())

    def test_each_ascii_whitespace_every_position_and_exact_cap(self):
        for whitespace in (b' ', b'\t', b'\r', b'\n', b' \t\r\n'):
            value = b'\xef\xbb\xbf' + whitespace + b'{' + whitespace + b'2' + whitespace + b',' + whitespace + GUID + whitespace + b'}' + whitespace
            self.assertEqual(self.parse(value), KEY)
        value = LOCATOR + b' ' * (1024 - len(LOCATOR))
        self.assertEqual(self.parse(value), KEY)
        self.assertEqual(self.parse(LOCATOR, max_input_bytes=43), KEY)
        for value, limit in ((value + b' ', 1024), (LOCATOR, 42)):
            with self.assertRaisesRegex(core.ResourceLimit, '^config_root_input_bytes$'):
                self.parse(value, max_input_bytes=limit)

    def test_all_truncations_fail_and_diagnostics_are_closed(self):
        codes = {'config_root_bom', 'config_root_grammar', 'config_root_tag', 'config_root_guid'}
        for end in range(len(LOCATOR)):
            with self.subTest(end=end), self.assertRaises(CatalogError) as caught:
                self.parse(LOCATOR[:end])
            self.assertIn(str(caught.exception), codes)

    def test_initial_bom_absent_partial_wrong_duplicate_interior(self):
        for prefix in (b'', b'\xef', b'\xef\xbb', b'\xef\xbb\x00', b'\xff\xfe', b' '):
            with self.assertRaisesRegex(core.UnsupportedLayout, '^config_root_bom$'):
                self.parse(prefix + LOCATOR[3:])
        for offset, code in ((3, 'grammar'), (4, 'tag'), (5, 'tag'), (6, 'guid'), (42, 'guid'), (43, 'trailing')):
            value = LOCATOR[:offset] + b'\xef\xbb\xbf' + LOCATOR[offset:]
            with self.assertRaisesRegex(CatalogError, '^config_root_' + code + '$'):
                self.parse(value)

    def test_exact_tag_not_old_or_alternate_decimal(self):
        for tag in (b'1', b'0', b'3', b'02', b'+2', b'-2', b'2.0', b'22', b'2e0', b'"2"', b'', b'\xff'):
            with self.assertRaisesRegex(core.UnsupportedLayout, '^config_root_tag$'):
                self.parse(b'\xef\xbb\xbf{' + tag + b',' + GUID + b'}')
        with self.assertRaisesRegex(core.UnsupportedLayout, '^config_root_tag$'):
            self.parse(b'\xef\xbb\xbf{1,' + GUID + b',0}')

    def test_guid_exact_width_bare_ascii_and_every_character_position(self):
        for value in (b'"' + GUID + b'"', b'{' + GUID + b'}', GUID[:-1], GUID + b'0', GUID.replace(b'-', b''), b''):
            with self.assertRaisesRegex(core.InvalidStructure, '^config_root_guid$'):
                self.parse(b'\xef\xbb\xbf{2,' + value + b'}')
        for index in range(36):
            for invalid in (b'G', b'\0', b'\xff', b' ', b'_', b'\xc2\xa0'):
                with self.subTest(index=index, invalid=invalid), self.assertRaisesRegex(core.InvalidStructure, '^config_root_guid$'):
                    self.parse(b'\xef\xbb\xbf{2,' + GUID[:index] + invalid + GUID[index+1:] + b'}')

    def test_structure_separators_nested_extra_fields_and_tail(self):
        for value in (b'\xef\xbb\xbf[2,' + GUID + b']', b'\xef\xbb\xbf{2}',
                      b'\xef\xbb\xbf{2 ' + GUID + b'}', LOCATOR[:-1] + b',}',
                      LOCATOR[:-1] + b',0}', LOCATOR[:-1] + b',{}'):
            with self.assertRaisesRegex(core.InvalidStructure, '^config_root_grammar$'): self.parse(value)
        for tail in (b'\0', b'\xff', b'\xc2\xa0', b'\xef\xbb\xbf', LOCATOR, b'// comment'):
            with self.assertRaisesRegex(core.InvalidStructure, '^config_root_trailing$'): self.parse(LOCATOR + tail)
        for ws in (b'\v', b'\f', b'\xc2\xa0'):
            with self.assertRaises(CatalogError): self.parse(b'\xef\xbb\xbf' + ws + LOCATOR[3:])

    def test_type_length_bom_syntax_precedence(self):
        class Bytes(bytes): pass
        for value in (None, True, 'text', bytearray(LOCATOR), memoryview(LOCATOR), Bytes(LOCATOR)):
            with self.assertRaisesRegex(core.InvalidStructure, '^config_root_input$'): self.parse(value)
        with self.assertRaisesRegex(core.ResourceLimit, '^config_root_input_bytes$'): self.parse(b'X' * 1025)
        for value, code in ((b'X', 'bom'), (b'\xef\xbb\xbf[1,bad', 'grammar'),
                            (b'\xef\xbb\xbf{1,bad', 'tag'), (b'\xef\xbb\xbf{2 bad', 'grammar'),
                            (b'\xef\xbb\xbf{2,bad}tail', 'guid')):
            with self.assertRaisesRegex(CatalogError, '^config_root_' + code + '$'): self.parse(value)

    def test_limits_exact_lower_only_and_preallocation_work(self):
        for value in (False, True, 0, -1, 1025, 1.0, '43'):
            with self.assertRaises(ValueError): core.ConfigRootReferenceLimits(max_input_bytes=value)
        for value in (1, 43, 1024): self.assertEqual(core.ConfigRootReferenceLimits(value).max_input_bytes, value)
        for field, needed in (('output_bytes', 512), ('bytes_processed', 4 * len(LOCATOR) + 128)):
            context, _, _, _ = decoder()
            budget = context.budget
            remaining = getattr(budget.limits, 'max_' + field) - budget.counts[field]
            budget.charge(field, remaining - needed + 1)
            before = dict(budget.counts)
            with mock.patch.object(core, 'bytearray', side_effect=AssertionError('allocation before budget'), create=True):
                with self.assertRaises(core.ResourceLimit):
                    core._parse_config_root_reference(LOCATOR, budget, core.ConfigRootReferenceLimits())
            self.assertTrue(all(budget.counts[k] >= v for k, v in before.items()))
        context, _, _, _ = decoder(); before = context.budget.usage()
        with self.assertRaises(core.ResourceLimit):
            core._parse_config_root_reference(LOCATOR, context.budget, core.ConfigRootReferenceLimits(42))
        self.assertEqual(context.budget.usage(), before)


class ConfigRootReferenceReaderTests(unittest.TestCase):
    def read(self, value, **kwargs):
        return core.observe_config_root_reference(value.read_at, value.size, profile=profile(), **kwargs)

    def test_previous_complete_prefix_ast_and_profiles_unchanged(self):
        value = (ROOT / 'scripts/native_1c_db_oracle/config_framing_reader.py').read_bytes()
        self.assertEqual(hashlib.sha256(value[:60997]).hexdigest(), '3b2c78ceac98cddf7220d0a5c956d8c742e59b5c7c57a1bc1ee4d562fe19c096')
        tree = ast.parse(value)
        old = ast.Module(body=tree.body[:36], type_ignores=[])
        self.assertEqual(hashlib.sha256(ast.dump(old, include_attributes=False).encode()).hexdigest(), 'f12b71c6e6384b4881f1c332e1bb6771c14d83fe48ae74043a5015bc7b8eb3b6')
        self.assertFalse(any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in tree.body[36:]))
        p = profile(); self.assertEqual(p.recipe(), RECIPE); self.assertEqual(p.recipe_sha256, RECIPE_SHA256)
        self.assertEqual(hashlib.sha256(json.dumps(RECIPE, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), RECIPE_SHA256)
        with self.assertRaises(FrozenInstanceError): p.identifier = 'x'

    def test_profile_arguments_and_every_global_limit_never_widen(self):
        for kind in (core.ConfigFramingProfile, core.ConfigMarkerCensusProfile, core.ConfigZeroMarkerFilenameProfile,
                     core.ConfigEntryReferenceProfile, core.ConfigBlobChainProfile, core.ConfigContentDecodeProfile):
            value = root_source()
            with self.assertRaises(ValueError): core.observe_config_root_reference(value.read_at, value.size, profile=kind(DECLARATIONS, '0', 0))
            self.assertEqual(value.calls, [])
        for key in ('limits', 'chain_limits', 'content_limits', 'root_limits', 'catalog_limits'):
            value = root_source()
            with self.assertRaises(ValueError): self.read(value, **{key: {}})
            self.assertEqual(value.calls, [])
        for f in fields(core.CatalogLimits):
            value = root_source(); default = getattr(core.CatalogLimits(), f.name)
            with self.assertRaises(ValueError): self.read(value, catalog_limits=core.CatalogLimits(**{f.name: default + 1}))
            self.assertEqual(value.calls, [])

    def test_all_permutations_root_target_then_remaining_once_same_budget(self):
        entries = [('RoOt', ROOT_STORED, 0), (KEY.upper(), ABC_FIXED, 0), ('before.inf', b'plain', 0), ('empty', EMPTY, 0)]
        for sequence in itertools.permutations(entries):
            value = root_source(sequence); seen, stores, budgets, catalogs = [], [], [], []
            original_read, original_decode, original_catalog = core._ConfigBlobChains.read, core._ConfigContentDecoder.decode, core.CatalogReader.read_catalog
            def read(chains, start, length):
                seen.append(start); stores.append(chains); return original_read(chains, start, length)
            def decode(context, stored, kind):
                budgets.append(context.budget); return original_decode(context, stored, kind)
            def catalog(reader):
                catalogs.append(reader); return original_catalog(reader)
            with mock.patch.object(core._ConfigBlobChains, 'read', read), mock.patch.object(core._ConfigContentDecoder, 'decode', decode), mock.patch.object(core.CatalogReader, 'read_catalog', catalog), mock.patch.object(core, 'observe_config_content_decode', side_effect=AssertionError('second traversal')):
                result = self.read(value)
            root = sequence.index(entries[0]) + 1; target = sequence.index(entries[1]) + 1
            self.assertEqual(seen, [root, target] + [i for i in range(1, 5) if i not in (root, target)])
            self.assertEqual(len(catalogs), 1); self.assertTrue(all(x is stores[0] for x in stores))
            self.assertTrue(all(x is stores[0].budget is catalogs[0]._budget for x in budgets))
            self.assertEqual(len(blob_calls(value)), 8)
            self.assertEqual((result.completed_chain_count, result.deflate_entry_count, result.positive_decoded_entry_count), (4, 3, 2))
            self.assertEqual(result.inflated_content_bytes, 46); self.assertEqual(result.plain_content_bytes, 5)
            self.assertEqual(result.total_stored_bytes_read, sum(len(e[1]) for e in sequence))
            self.assertEqual((result.parsed_locator_count, result.resolved_positive_target_count), (1, 1))
            self.assertEqual(result.relation_validation, 'fixed_key_guid_reference_resolved_v1')
            self.assertEqual((result.file_identity, result.root_identity, result.applied_state, result.native_acceptance), ('not_observed', 'not_observed', 'not_observed', 'pending'))
            self.assertFalse(value.closed)
            text = repr(asdict(result)); self.assertNotIn(KEY, text); self.assertNotIn(repr(LOCATOR), text); self.assertNotIn('before.inf', text)
            self.assertFalse({'names', 'target', 'payload', 'root_bytes', 'target_bytes', 'payload_hash', 'contents'} & (set(asdict(result)) - {'target'}))

    def test_all_guards_and_duplicate_anywhere_before_any_selected_read(self):
        bads = [('ROOT', ABC_FIXED, 0), (KEY.upper(), ABC_FIXED, 0), ('tail.NEW', ABC_FIXED, 0),
                ('tail_DynUpdate_x', ABC_FIXED, 0), ('nonascii_Ω', ABC_FIXED, 0), ('part', ABC_FIXED, 1)]
        for bad in bads:
            for index in (0, 1, 2):
                entries = [('root', ROOT_STORED, 0), (KEY, ABC_FIXED, 0)]; entries.insert(index, bad)
                value = root_source(entries)
                with self.assertRaises(CatalogError): self.read(value)
                self.assertEqual(blob_calls(value), [])
        value = root_source([('root', packed(b'bad grammar'), 0), (KEY, ABC_FIXED, 0), ('bad.new', ABC_FIXED, 0)])
        with self.assertRaisesRegex(core.UnsupportedLayout, 'config_content_dynamic_name'): self.read(value)
        self.assertEqual(blob_calls(value), [])

    def test_missing_and_excluded_fixed_root_and_target(self):
        for rows in ([], [row('root', start=0)], [row('root', marker=1)], [row('root', marker=2)]):
            value = root_source([(KEY, ABC_FIXED, 0)], trailing_rows=rows)
            with self.assertRaisesRegex(core.UnsupportedLayout, '^config_root_missing_selected_root$'): self.read(value)
            self.assertEqual(blob_calls(value), [])
        for rows in ([], [row(KEY, start=0)], [row(KEY, marker=1)], [row(KEY, marker=2)]):
            value = root_source([('root', ROOT_STORED, 0)], trailing_rows=rows)
            with self.assertRaisesRegex(core.UnsupportedLayout, '^config_root_missing_selected_target$'): self.read(value)
            self.assertEqual(len(blob_calls(value)), 2)
        value = root_source([], trailing_rows=[row('root', start=0)])
        with self.assertRaisesRegex(core.UnsupportedLayout, '^config_root_missing_selected_root$'): self.read(value)
        self.assertEqual(blob_calls(value), [])

    def test_content_guid_actually_selects_target_not_position_or_name_census(self):
        other = 'ffffffff-ffff-ffff-ffff-ffffffffffff'
        entries = [(KEY, EMPTY, 0), ('root', packed(b'\xef\xbb\xbf{2,' + other.encode() + b'}'), 0), (other, ABC_FIXED, 0)]
        result = self.read(root_source(entries))
        self.assertEqual((result.deflate_entry_count, result.positive_decoded_entry_count), (3, 2))
        entries[1] = ('root', ROOT_STORED, 0)
        with self.assertRaisesRegex(core.UnsupportedLayout, '^config_root_empty_target$'): self.read(root_source(entries))

    def test_empty_target_after_complete_decode_and_late_failures_discard(self):
        for stored, code in ((EMPTY, 'config_root_empty_target'), (EMPTY + b'\0', 'config_content_trailing_data'), (ABC_FIXED[:-1], 'config_content_truncated_deflate')):
            value = root_source([('root', ROOT_STORED, 0), (KEY, stored, 0), ('later', ABC_FIXED, 0)])
            with self.assertRaisesRegex(CatalogError, '^' + code + '$'): self.read(value)
            self.assertEqual(len(blob_calls(value)), 4)
        for stored in (ABC_FIXED[:-1], ABC_FIXED + b'\0'):
            value = root_source([('bad', stored, 0), ('root', ROOT_STORED, 0), (KEY, ABC_FIXED, 0), ('unread', ABC_FIXED, 0)])
            with self.assertRaises(CatalogError): self.read(value)
            self.assertEqual(len(blob_calls(value)), 6)

    def test_parse_lookup_target_and_late_failure_poison_single_attempt(self):
        cases = [([('root', packed(b'bad'), 0), (KEY, ABC_FIXED, 0)], 'config_root_bom'),
                 ([('root', ROOT_STORED, 0)], 'config_root_missing_selected_target'),
                 ([('root', ROOT_STORED, 0), (KEY, EMPTY, 0)], 'config_root_empty_target'),
                 ([('root', ROOT_STORED, 0), (KEY, ABC_FIXED, 0), ('bad', ABC_FIXED + b'\0', 0)], 'config_content_trailing_data')]
        for entries, code in cases:
            value = root_source(entries); op = operation(value)
            with self.assertRaisesRegex(CatalogError, '^' + code + '$'): op.run()
            self.assertTrue(op.used); self.assertTrue(op.chains.failed); self.assertTrue(op.decoder.failed)
            usage, calls, owners = op.reader.usage, list(value.calls), set(op.chains.owners)
            for fn, code in ((op.run, 'config_root_failed_attempt'),
                (lambda: op.chains.read(1, len(ROOT_STORED)), 'config_chain_failed_attempt'),
                (lambda: op.decoder.decode(ABC_FIXED, 'raw_deflate'), 'config_content_failed_attempt')):
                with self.assertRaisesRegex(CatalogError, '^' + code + '$'): fn()
            self.assertEqual(op.reader.usage, usage); self.assertEqual(value.calls, calls); self.assertEqual(op.chains.owners, owners)
        value = root_source(); op = operation(value); op.run(); calls = list(value.calls)
        with self.assertRaisesRegex(CatalogError, '^config_root_failed_attempt$'): op.run()
        self.assertEqual(value.calls, calls)

    def test_parser_cap_after_full_decoder_not_early_inflation_cap(self):
        value = root_source([('root', packed(LOCATOR + b' ' * 982), 0), (KEY, ABC_FIXED, 0)])
        op = operation(value)
        with self.assertRaisesRegex(core.ResourceLimit, '^config_root_input_bytes$'): op.run()
        self.assertEqual(op.decoder.total_content_bytes, 1025); self.assertEqual(op.completed, 1)
        self.assertTrue(op.decoder.failed); self.assertTrue(op.chains.failed)
        result = self.read(root_source(), root_limits=core.ConfigRootReferenceLimits(43))
        self.assertEqual(result.parsed_locator_count, 1)

    def test_same_page_distinct_logical_blocks_valid_zero_used_tail_checked(self):
        nodes = {1: (3, ROOT_STORED), 3: (0, b''), 2: (0, ABC_FIXED)}
        rows = [row(marker=1), row(KEY, start=2, length=5), row('root', start=1, length=len(ROOT_STORED))]
        value = source(rows=rows, nodes=nodes); self.assertEqual(len(value.blob_pages), 1)
        result = self.read(value)
        self.assertEqual((result.completed_chain_count, result.total_chain_blocks, result.zero_payload_block_count), (2, 3, 1))
        nodes[3] = (3, b''); value = source(rows=rows, nodes=nodes)
        with self.assertRaisesRegex(CatalogError, '^config_chain_cycle$'): self.read(value)
        self.assertEqual([n for _, n in blob_calls(value)], [6, 48, 6])

    def test_selected_logical_overlap_and_late_declared_length_mismatch(self):
        for rows, nodes, code in (
            ([row(marker=1), row('root', length=48), row(KEY, start=2, length=5), row('late', start=2, length=5)],
             {1: (0, ROOT_STORED), 2: (0, ABC_FIXED)}, 'config_chain_overlap'),
            ([row(marker=1), row('root', length=48), row(KEY, start=2, length=5), row('late', start=3, length=4)],
             {1: (0, ROOT_STORED), 2: (0, ABC_FIXED), 3: (0, ABC_FIXED)}, 'config_chain_length'),
            ([row(marker=1), row('root', length=48), row(KEY, start=2, length=5), row('late', start=3, length=5)],
             {1: (0, ROOT_STORED), 2: (0, ABC_FIXED), 3: (3, ABC_FIXED)}, 'config_chain_cycle')):
            value = source(rows=rows, nodes=nodes); op = operation(value)
            with self.assertRaisesRegex(CatalogError, '^' + code + '$'): op.run()
            self.assertTrue(op.decoder.failed); self.assertTrue(op.chains.failed)

    def test_physical_catalog_descriptor_mapping_and_data_role_overlap_reject(self):
        # BLOB map points at each previously owned physical role. This is not the
        # valid co-residence of distinct logical BLOB blocks on their own page.
        for page in (2, 3, 8, 9, 10):
            value = root_source(); value.page(8)[24:28] = page.to_bytes(4, 'little')
            with self.subTest(page=page), self.assertRaisesRegex(UnsupportedSharing, '^physical_page_role_overlap$'):
                self.read(value)
        value = root_source(); value.page(8)[24:28] = value.data_pages[0].to_bytes(4, 'little')
        with self.assertRaisesRegex(UnsupportedSharing, '^physical_page_role_overlap$'): self.read(value)

    def test_inherited_constructor_io_charged_before_new_operation_allocation(self):
        value = root_source(); original = core._ConfigRootReferenceOperation.__init__; seen = []
        def construct(context, reader, *args):
            # Exactly inherited header/root-map setup, no catalog scan/selected IO.
            self.assertEqual(value.calls, [(0, 24), (2 * P, P)])
            self.assertEqual(reader.usage.read_bytes, 24 + P)
            self.assertGreaterEqual(reader.usage.bytes_processed, 24 + P)
            seen.append(reader.usage.output_bytes)
            original(context, reader, *args)
            self.assertFalse(context.used)
        with mock.patch.object(core._ConfigRootReferenceOperation, '__init__', construct):
            self.read(value)
        baseline = root_source(); reader = core.CatalogReader(baseline.read_at, baseline.size)
        self.assertEqual(seen, [reader.usage.output_bytes + 1024])
        value = root_source(); op = operation(value); original_catalog = core.CatalogReader.read_catalog
        def catalog(reader):
            self.assertTrue(op.used)
            # Re-entrancy fails without work or prior budget reset.
            usage = reader.usage; calls = list(value.calls)
            with self.assertRaisesRegex(CatalogError, '^config_root_failed_attempt$'): op.run()
            self.assertEqual(reader.usage, usage); self.assertEqual(value.calls, calls)
            return original_catalog(reader)
        with mock.patch.object(core.CatalogReader, 'read_catalog', catalog): op.run()

    def test_second_map_key_work_reservation_precedes_fold_and_lookup_work_precedes_pop(self):
        # Abort immediately after successful classifier allocation and before the
        # additional folded-key map work. Actual callbacks remain bounded.
        value = root_source(); original = core._config_content_name
        def name(text, units, budget, keys):
            result = original(text, units, budget, keys)
            available = budget.limits.max_bytes_processed - budget.counts['bytes_processed']
            budget.charge('bytes_processed', available - (4 * units + 31))
            return result
        with mock.patch.object(core, '_config_content_name', name), self.assertRaisesRegex(core.ResourceLimit, '^bytes_processed$'):
            self.read(value)
        self.assertEqual(blob_calls(value), [])
        value = root_source(); op = operation(value); original_take = core._ConfigRootReferenceOperation._take
        class Untouched(dict):
            def pop(self, *args): raise AssertionError('lookup before work/output reservation')
        for field, amount in (('bytes_processed', 255), ('output_bytes', 127)):
            value = root_source(); op = operation(value); budget = op.reader._budget
            available = getattr(budget.limits, 'max_' + field) - budget.counts[field]
            budget.charge(field, available - amount); before = dict(budget.counts)
            with self.assertRaisesRegex(core.ResourceLimit, '^' + field + '$'):
                original_take(op, Untouched(root=(1, 48, 'raw_deflate')), 'root', 'config_root_missing_selected_root')
            self.assertTrue(all(budget.counts[k] >= v for k, v in before.items()))

    def test_all_selected_maximum_names_map_and_intersected_global_budgets(self):
        entries = [(f'p{i}.inf', b'x', 0) for i in range(4093)] + [('root', ROOT_STORED, 0), (KEY, ABC_FIXED, 0)]
        result = self.read(root_source(entries))
        self.assertEqual((result.candidate_slots, result.selected_reference_count, result.completed_chain_count), (4096, 4095, 4095))
        self.assertEqual(result.positive_decoded_entry_count, 2)
        value = root_source(entries, trailing_rows=[row('excluded', start=0)])
        with self.assertRaisesRegex(core.ResourceLimit, '^config_slots$'): self.read(value)
        self.assertEqual(blob_calls(value), [])
        result = self.read(root_source())
        for field in ('page_reads', 'read_bytes', 'bytes_processed', 'blob_visits', 'total_blob_bytes', 'output_bytes'):
            used = getattr(result.usage, field)
            self.read(root_source(), catalog_limits=core.CatalogLimits(**{'max_' + field: used}))
            with self.assertRaises(core.ResourceLimit): self.read(root_source(), catalog_limits=core.CatalogLimits(**{'max_' + field: used - 1}))

    def test_new_map_parser_lookup_final_reservations_and_no_refund(self):
        # Locate exact cumulative budget boundaries with method instrumentation,
        # then lower the real global ceiling by one at each new output phase.
        seen = []; original_name = core._config_content_name
        def name(value, units, budget, keys):
            result = original_name(value, units, budget, keys)
            seen.append((budget.counts['output_bytes'], 512 + 8 * units))
            return result
        with mock.patch.object(core, '_config_content_name', name): self.read(root_source())
        for used, needed in seen:
            value = root_source()
            with self.assertRaises(core.ResourceLimit): self.read(value, catalog_limits=core.CatalogLimits(max_output_bytes=used + needed - 1))
            self.assertEqual(blob_calls(value), [])
        for site, remaining in (('_take', 127), ('parse', 511), ('final', 4095)):
            value = root_source(); op = operation(value); original_take = core._ConfigRootReferenceOperation._take
            original_parse = core._parse_config_root_reference; original_consume = core._ConfigRootReferenceOperation._consume
            def drain(budget, amount):
                available = budget.limits.max_output_bytes - budget.counts['output_bytes']
                budget.charge('output_bytes', available - amount)
            def take(context, refs, key, code):
                if key != 'root': drain(context.reader._budget, remaining)
                return original_take(context, refs, key, code)
            def parse(content, budget, limits):
                drain(budget, remaining); return original_parse(content, budget, limits)
            def consume(context, reference):
                content = original_consume(context, reference)
                if context.completed == 2: drain(context.reader._budget, remaining)
                return content
            patch = mock.patch.object(core._ConfigRootReferenceOperation, '_take', take) if site == '_take' else mock.patch.object(core, '_parse_config_root_reference', parse) if site == 'parse' else mock.patch.object(core._ConfigRootReferenceOperation, '_consume', consume)
            with patch, self.assertRaisesRegex(core.ResourceLimit, '^output_bytes$'): op.run()
            self.assertTrue(op.decoder.failed); self.assertTrue(op.chains.failed)
            usage = op.reader.usage
            with self.assertRaisesRegex(CatalogError, '^config_root_failed_attempt$'): op.run()
            self.assertEqual(op.reader.usage, usage)
        value = root_source()
        with mock.patch.object(core, '_ConfigRootReferenceOperation', side_effect=AssertionError('state constructed before reservation')):
            with self.assertRaises(core.ResourceLimit): self.read(value, catalog_limits=core.CatalogLimits(max_output_bytes=1023))
        self.assertEqual(value.calls, [(0, 24), (2 * P, P)])


if __name__ == '__main__': unittest.main()
