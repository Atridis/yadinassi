"""Explicit full-source format16 grant and host-family isolation contracts."""
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest

from inventory_enum_application_fixture import source
from yadinassi.configuration_inventory_enum_application import (
    PROFILE, import_inventory_application, canonical, validated_core)
from yadinassi.configuration_inventory_enums import canonical as core_canonical
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalog_backend import BackendError
from yadinassi.inventory_host_operations import _source_configuration
from yadinassi.configuration_profile_import import prepare_files, create_prepared


class InventoryEnumApplicationProfileTests(unittest.TestCase):
    def config(self):
        return import_inventory_application(source(), inventory_runtime=PROFILE)

    def test_explicit_source_profile_only(self):
        for grant in (None, 'inventory-enum-v1', True):
            with self.assertRaises(ValueError):
                import_inventory_application(source(), inventory_runtime=grant)

    def test_original_source_and_core_projection(self):
        config = self.config()
        self.assertEqual(dict(config.files), source())
        core = validated_core(config)
        self.assertEqual(core.enumerations, config.enumerations)
        self.assertEqual(core.documents, config.documents)
        self.assertNotIn('InventoryApplication.xml', dict(core.files))
        self.assertEqual(config.core_projection_digest, core.source_digest)
        self.assertEqual(canonical(config), config)

    def test_tampered_grant_rejected(self):
        config = self.config()
        for forged in (replace(config, profile='inventory-enum-v1'),
                       replace(config, enumerations=()), replace(config, commands=()),
                       replace(config, core_projection_digest='0'*64)):
            with self.assertRaises(ValueError): canonical(forged)

    def test_core_creator_remains_closed(self):
        config = self.config()
        with self.assertRaises(ValueError): core_canonical(config)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'db.sqlite'
            with self.assertRaises(BackendError): SQLiteDBContext.create_inventory_enum(path, config)
            self.assertFalse(path.exists())

    def test_full_source_reopens_with_exact_marker(self):
        config = self.config()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'db.sqlite'
            with SQLiteDBContext.create_inventory_enum_application(path, config) as context:
                self.assertEqual(context.backend.format_version, 16)
                self.assertEqual(_source_configuration(context.backend), config)
                self.assertEqual(context.backend.export_configuration(), source())
            with SQLiteDBContext(path) as context:
                self.assertEqual(_source_configuration(context.backend), config)

    def test_preflight_is_explicit_and_creates_full_source(self):
        prepared = prepare_files(source(), profile=PROFILE)
        self.assertEqual(prepared.format_version, 16)
        with tempfile.TemporaryDirectory() as folder:
            with create_prepared(Path(folder)/'db.sqlite', prepared) as context:
                self.assertEqual(context.backend.export_configuration(), source())

    def test_launch_snapshot_requires_full_forms_grant(self):
        config = self.config()
        with tempfile.TemporaryDirectory() as folder:
            with SQLiteDBContext.create_inventory_enum_application(Path(folder)/'ui.sqlite', config) as context:
                snap = context.backend.launch_snapshot()
                self.assertEqual((snap.profile, snap.route), (PROFILE, 'inventory-enum'))
            with SQLiteDBContext.create_inventory_enum(Path(folder)/'core.sqlite', validated_core(config)) as context:
                with self.assertRaises(BackendError): context.backend.launch_snapshot()

    def test_catalog_session_owns_enum_family_and_close_retires_it(self):
        from yadinassi.inventory_application_sessions import InventoryCatalogSession
        from yadinassi.inventory_enum_runtime import binding
        config = self.config()
        schema = next(s for s in config.catalogs if s.name == 'Products')
        with tempfile.TemporaryDirectory() as folder:
            with SQLiteDBContext.create_inventory_enum_application(Path(folder)/'db.sqlite', config) as context:
                session = InventoryCatalogSession(context, schema, config)
                bridge = binding(session._interpreter._metadata)
                field = next(f for f in schema.fields if f.kind == 'enum_ref')
                value = session.object.get_member(field.name)
                key = bridge.key(value, field.target_enum_id)
                self.assertEqual(key.value_id.int, 0)
                session.close()
                with self.assertRaises(BackendError): bridge.key(value, field.target_enum_id)

    def test_document_session_uses_owned_enum_manager(self):
        from yadinassi.inventory_application_sessions import InventoryDocumentSession
        from yadinassi.inventory_enum_runtime import binding
        config = self.config()
        schema = next(s for s in config.documents if s.name == 'Receipt')
        with tempfile.TemporaryDirectory() as folder:
            with SQLiteDBContext.create_inventory_enum_application(Path(folder)/'db.sqlite', config) as context:
                session = InventoryDocumentSession(context, schema, config, 'Document.Receipt.Form.Card')
                bridge = binding(session.operations._interpreter._metadata)
                field = next(f for f in schema.fields if f.kind == 'enum_ref')
                value = session.object.get_member(field.name)
                self.assertEqual(bridge.key(value, field.target_enum_id).value_id.int, 0)
                session.close()
                with self.assertRaises(BackendError): bridge.key(value, field.target_enum_id)

    def test_marker_cannot_turn_forms_into_core(self):
        import sqlite3
        config = self.config()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'db.sqlite'
            SQLiteDBContext.create_inventory_enum_application(path, config).close()
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE inventory_profile SET profile='inventory-enum-v1'")
            with self.assertRaises(BackendError): SQLiteDBContext(path)
