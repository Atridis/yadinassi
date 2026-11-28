"""Existing databases validate their current layout, not a discarded new layout."""
from contextlib import closing
from dataclasses import replace
import unittest
from unittest.mock import patch
from uuid import UUID

import test_sqlite_transaction_source as fixture
from yadinassi.db.sqlite import sqlite_main_demo_profile as profile
from yadinassi.db.catalog.catalog_backend import BackendError, FieldSchema


class ExistingShapeValidationTests(unittest.TestCase):
    setUp = fixture.TransactionSourceTests.setUp
    mutate = fixture.TransactionSourceTests.mutate

    def test_live_validation_generates_each_expected_ddl_once(self):
        config, domain = self.backend.accumulation_configuration, self.backend._enum_domain
        storage = profile._storage()
        with closing(self.backend.begin_read()) as view:
            with patch.object(storage, 'build_layout', side_effect=AssertionError('unused new layout')), \
                 patch.object(storage, 'build_section_layout', side_effect=AssertionError('unused new sections')), \
                 patch.object(profile, '_require_config', wraps=profile._require_config) as canonical, \
                 patch.object(storage, 'catalog_ddl', wraps=storage.catalog_ddl) as catalog, \
                 patch.object(storage, 'section_ddl', wraps=storage.section_ddl) as section:
                profile.validate_main_demo_ddl(view._connection, config, domain)
                self.assertEqual(canonical.call_count, 1)
                self.assertEqual(catalog.call_count, len(config.catalogs))
                self.assertEqual(section.call_count, sum(len(c.tabular_sections) for c in config.catalogs))

    def test_current_codec_roundtrip_is_still_required(self):
        with closing(self.backend.begin_read()) as view:
            with patch.object(profile._storage(), '_schema', return_value=None):
                with self.assertRaises(BackendError):
                    profile.validate_main_demo_ddl(view._connection, self.backend.accumulation_configuration, self.backend._enum_domain)

    def test_catalog_codec_serializes_only_once_per_catalog(self):
        config, domain = self.backend.accumulation_configuration, self.backend._enum_domain
        storage = profile._storage()
        with patch.object(storage, '_json', wraps=storage._json) as encode, \
             patch.object(storage, '_schema', wraps=storage._schema) as decode:
            profile._validate_catalogs(config.catalogs, domain)
        self.assertEqual(encode.call_count, len(config.catalogs))
        self.assertEqual(decode.call_count, len(config.catalogs))

    def test_overlong_serialization_rejects_before_decode(self):
        catalog = self.backend.accumulation_configuration.catalogs[0]
        fields = tuple(FieldSchema(UUID(int=i + 1), '😀' * 124 + f'{i:04d}', 'boolean', ())
                       for i in range(64))
        candidate = replace(catalog, fields=fields)
        storage, domain = profile._storage(), self.backend._enum_domain
        data = storage._schema_data(candidate, enforce_serialized_limit=False, enum_domain=domain)
        self.assertGreater(len(storage._json(data)), 65536)
        with patch.object(storage, '_schema', side_effect=AssertionError('decode over limit')):
            with self.assertRaisesRegex(BackendError, '^invalid_input$'):
                profile._validate_catalogs((candidate,), domain)

    def test_catalog_serialized_aggregate_bound_is_retained(self):
        config, domain = self.backend.accumulation_configuration, self.backend._enum_domain
        with patch.object(profile._storage(), '_MAX_CONFIG_BYTES', 1):
            with self.assertRaisesRegex(BackendError, '^unsupported$'):
                profile._validate_catalogs(config.catalogs, domain)

    def test_forged_config_and_domain_still_reject(self):
        config = self.backend.accumulation_configuration
        with closing(self.backend.begin_read()) as view:
            for candidate, domain in ((replace(config, catalogs=()), self.backend._enum_domain), (config, object())):
                with self.subTest(config=candidate is config), self.assertRaises(BackendError):
                    profile.validate_main_demo_ddl(view._connection, candidate, domain)

    def test_persisted_layout_change_is_not_cached(self):
        with closing(self.backend.begin_read()): pass
        self.mutate("UPDATE catalog_storage_map SET physical_name='catalog_wrong' WHERE catalog_id=(SELECT catalog_id FROM catalog_storage_map LIMIT 1)")
        with self.assertRaises(BackendError): self.backend.begin_read()
