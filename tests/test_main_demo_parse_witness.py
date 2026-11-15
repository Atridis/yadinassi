"""Pure parse memo does not cache source, schema or database authority."""
from dataclasses import replace
from unittest.mock import patch
import unittest
from test_main_demo_configuration import source
from yadinassi import configuration_main_demo as main

class MainDemoParseWitnessTests(unittest.TestCase):
    def setUp(self):
        main._parsed_source_witness.cache_clear()
        self.addCleanup(main._parsed_source_witness.cache_clear)
        self.config = main.import_main_demo_configuration(source(), profile=main.PROFILE)

    def test_one_private_parse_on_miss_and_none_on_hit(self):
        original = main.import_main_demo_configuration
        with patch.object(main, 'import_main_demo_configuration', wraps=original) as importer:
            first = main.canonical(self.config)
            second = main.canonical(self.config)
            self.assertEqual(importer.call_count, 1)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(main._parsed_source_witness.cache_info().maxsize, 1)
        self.assertEqual(main._parsed_source_witness.cache_info().currsize, 1)

    def test_every_source_file_is_rechecked_on_warm_cache(self):
        main.canonical(self.config)
        for path, raw in self.config.files:
            with self.subTest(path=path):
                files = tuple((p, b+b'\n' if p == path else b) for p,b in self.config.files)
                with self.assertRaises(ValueError): main.canonical(replace(self.config, files=files))
        self.assertEqual(main.canonical(self.config), self.config)

    def test_cold_and_warm_schema_grant_drift_is_rejected(self):
        for warm in (False, True):
            main._parsed_source_witness.cache_clear()
            if warm: main.canonical(self.config)
            for name in ('catalogs','documents','registers','handlers','enumerations','commands','reports','catalog_handlers','catalog_sources'):
                with self.subTest(warm=warm, field=name):
                    with self.assertRaises(ValueError): main.canonical(replace(self.config, **{name:()}))
            with self.assertRaises(ValueError):main.canonical(replace(self.config, source_digest='0'*64))
            with self.assertRaises(ValueError):main.canonical(replace(self.config, profile='inventory-enum-v1'))

    def test_returned_objects_cannot_poison_witness(self):
        first = main.canonical(self.config)
        object.__setattr__(first, 'name', 'forged')
        object.__setattr__(first.catalogs[0], 'name', 'forged nested')
        second = main.canonical(self.config)
        self.assertEqual(second, self.config)
        with self.assertRaises(ValueError):main.canonical(first)

    def test_failed_import_does_not_publish(self):
        with patch.object(main, 'import_main_demo_configuration', side_effect=ValueError('refused')):
            with self.assertRaises(ValueError):main.canonical(self.config)
        self.assertEqual(main._parsed_source_witness.cache_info().currsize, 0)
        self.assertEqual(main.canonical(self.config), self.config)

    def test_duplicate_missing_extra_and_subclass_source_rejected_before_lookup(self):
        class Bytes(bytes): pass
        first = self.config.files[0]
        variants = (self.config.files+(first,), self.config.files[:-1],
            self.config.files+(('extra.xml', b'<x/>'),),
            ((first[0], Bytes(first[1])),)+self.config.files[1:])
        with patch.object(main, '_parsed_source_witness', side_effect=AssertionError('lookup before admission')):
            for files in variants:
                with self.assertRaises(ValueError):main.canonical(replace(self.config, files=files))

    def test_oversized_source_rejected_before_hash_or_lookup(self):
        with patch.object(main.xml, 'MAX_FILE_BYTES', 1), patch.object(main, '_parsed_source_witness', side_effect=AssertionError('lookup before bound')):
            with self.assertRaises(ValueError):main.canonical(self.config)

    def test_foreign_schema_hooks_do_not_run_on_hit(self):
        class Foreign:
            def __eq__(self, other):raise AssertionError('foreign equality')
        main.canonical(self.config)
        with self.assertRaises(ValueError):main.canonical(replace(self.config, catalogs=(Foreign(),)))
