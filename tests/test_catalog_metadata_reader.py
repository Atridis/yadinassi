"""Synthetic complete CONFIG images; no catalog records or native assumptions."""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

import test_native_1c_db_oracle_catalog_attribute_binding as fixture
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.database_context import FileDBContext
from yadinassi.storage import catalog_metadata as entry
from yadinassi.storage import filedb_catalog as catalog


def image(names=('InventedAlpha', 'InventedBeta'), keys=None):
    keys = keys or tuple(f'{index:08x}-1234-4321-9876-123456789abc' for index in range(1, len(names) + 1))
    payloads = []
    for key, name in zip(keys, names):
        prefix = fixture.matrix.names.document(name='"' + name + '"', code='7', kind='1',
                                               description='19', metadata_uuid=key)
        attributes = fixture.constructed.node('cf4abea7-37b2-11d4-940f-008048da11f9', '0')
        payloads.append(fixture.stored_literal(prefix[:-1] + b',0,0,0,0,' + attributes.encode() + b'}'))
    rows = fixture.entries(refs=keys, payload=payloads[0], tail=tuple(
        (key, payload, 0) for key, payload in zip(keys[1:], payloads[1:])))
    rows[0] = (keys[0], payloads[0], 0)
    return fixture.content_source(rows)


class CatalogMetadataReaderTests(unittest.TestCase):
    def test_dynamic_complete_identities_without_records(self):
        value = image()
        stages = []
        original = catalog._CatalogBindingGraph.stage
        def stage(graph, role, **kw):
            stages.append(role)
            return original(graph, role, **kw)
        with mock.patch.object(catalog._CatalogBindingGraph, 'stage', stage):
            result = entry.read_catalog_metadata(value.read_at, value.size)
        self.assertEqual(stages, ['config'])
        self.assertEqual(tuple(x.name for x in result), ('InventedAlpha', 'InventedBeta'))
        self.assertEqual(result[0].metadata_uuid, '00000001-1234-4321-9876-123456789abc')
        with self.assertRaises(FrozenInstanceError):
            result[0].name = 'Changed'

    def test_one_catalog_and_case_ambiguous_rejection(self):
        value = image(('ДругойСправочник',))
        self.assertEqual(entry.read_catalog_metadata(value.read_at, value.size)[0].name, 'ДругойСправочник')
        value = image(('Similar', 'SIMILAR'))
        with self.assertRaisesRegex(catalog.InvalidStructure, 'metadata_identity_ambiguous'):
            entry.read_catalog_metadata(value.read_at, value.size)

    def test_all_selected_entries_checked_before_return(self):
        value = image()
        # Missing/malformed bytes anywhere in the selected CONFIG must not yield
        # a successful partial first identity.
        def short(offset, length):
            return value.read_at(offset, length)[:-1]
        with self.assertRaises(catalog.CatalogError):
            entry.read_catalog_metadata(short, value.size)

    def test_bounds_before_source_reads_and_budget(self):
        reader = mock.Mock()
        for size in (-1, True, 67108865):
            with self.subTest(size=size), self.assertRaises(catalog.CatalogError):
                entry.read_catalog_metadata(reader, size)
        with self.assertRaisesRegex(catalog.InvalidStructure, 'metadata_limits'):
            entry.read_catalog_metadata(reader, 8192,
                limits=replace(catalog.CatalogLimits(), max_page_reads=100001))
        reader.assert_not_called()
        value = image()
        with self.assertRaises(catalog.CatalogError):
            entry.read_catalog_metadata(value.read_at, value.size,
                                        limits=replace(catalog.CatalogLimits(), max_read_bytes=1))


class CatalogMetadataPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / '1Cv8.1CD'
        self.context = FileDBContext(self.directory)

    def write(self):
        value = image()
        self.path.write_bytes(value.read_at(0, value.size))
        return value

    def test_real_file_returns_immutable_metadata_without_writes(self):
        self.write()
        before = self.path.read_bytes()
        result = self.context.catalog_metadata()
        self.assertEqual(tuple(x.name for x in result), ('InventedAlpha', 'InventedBeta'))
        self.assertEqual(self.path.read_bytes(), before)

    def test_actual_bsl_adapter_dynamic_config_without_catalog_rows(self):
        # This image contains CONFIG alone, deliberately no PARAMS/DBNames or
        # physical Catalog record tables. Both names and count come from bytes.
        value = image(('ТоварыПроверки', 'OtherInventory', 'ThirdInventory'))
        self.path.write_bytes(value.read_at(0, value.size))
        runtime = Interpreter(database_context=self.context)
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.execute('Metadata.Catalogs.Count()'), Decimal(3))
        self.assertEqual(runtime.execute('Метаданные.Справочники.ТоварыПроверки.Имя'), 'ТоварыПроверки')
        self.assertEqual(runtime.execute('Metadata.Catalogs.Find("otherinventory").FullName()'),
                         'Справочник.OtherInventory')
        self.assertEqual(runtime.execute('Метаданные.Справочники["ThirdInventory"].ПолноеИмя()'),
                         'Справочник.ThirdInventory')
        self.assertTrue(runtime.execute('(Metadata.Catalogs["OtherInventory"] = '
                                        'Метаданные.Справочники.OtherInventory)'))
        with self.assertRaises(BSLRuntimeError):
            runtime.execute('Metadata.Catalogs.OtherInventory.Name = "Changed";')
        self.assertEqual(runtime.execute('Metadata.Catalogs.OtherInventory.Name'), 'OtherInventory')

    def test_construction_lazy_missing_unsupported_and_nonregular(self):
        with self.assertRaisesRegex(ValueError, 'file_io_failed'):
            self.context.catalog_metadata()
        with mock.patch('os.open', side_effect=AssertionError('must not open')):
            bad = FileDBContext('//remote/database')
            with self.assertRaisesRegex(ValueError, 'unsupported file database directory'):
                bad.catalog_metadata()
        self.path.mkdir()
        with self.assertRaisesRegex(ValueError, 'not_regular_file|file_io_failed'):
            self.context.catalog_metadata()

    def test_descriptor_closed_on_success_and_decode_failure(self):
        self.write()
        original = os.close
        descriptors = []
        def close(fd):
            descriptors.append(fd)
            return original(fd)
        with mock.patch('os.close', side_effect=close):
            self.context.catalog_metadata()
            self.path.write_bytes(b'bad')
            with self.assertRaises(ValueError):
                self.context.catalog_metadata()
        self.assertEqual(len(descriptors), 2)
        for fd in descriptors:
            with self.assertRaises(OSError): os.fstat(fd)

    def test_changed_source_detected_even_if_projection_raises(self):
        self.write()
        for fail in (False, True):
            def change(*args, **kw):
                with self.path.open('ab') as stream:
                    stream.write(b'x')
                if fail:
                    raise catalog.InvalidStructure('earlier_error')
                return ()
            with mock.patch.object(entry, 'read_catalog_metadata', side_effect=change):
                with self.assertRaisesRegex(ValueError, 'source_changed'):
                    self.context.catalog_metadata()

    def test_oversize_file_rejected_without_read(self):
        with self.path.open('wb') as stream:
            stream.truncate(67108865)
        with mock.patch('os.read', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError, 'config_chain_image_bytes'):
                self.context.catalog_metadata()

    def test_private_seek_read_fallback(self):
        self.write()
        # Match Windows' lack of pread without altering the descriptor policy.
        if hasattr(os, 'pread'):
            pread = os.pread
            del os.pread
            try:
                result = self.context.catalog_metadata()
            finally:
                os.pread = pread
        else:
            result = self.context.catalog_metadata()
        self.assertEqual(len(result), 2)
