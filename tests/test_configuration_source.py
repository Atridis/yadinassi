"""Generic source admission is not a metadata activation grant."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from yadinassi.configuration_source import (import_source, load_source_directory,
    load_source_archive, save_source_archive)
from yadinassi.configuration_import import read_configuration_directory


CONFIG = b'''<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Configuration uuid="11111111-1111-1111-1111-111111111111"><Properties><Name>Example</Name></Properties><ChildObjects/></Configuration></MetaDataObject>'''
TASK = b'''<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Task uuid="22222222-2222-2222-2222-222222222222"><Properties><Name>Workflow</Name><UnknownBehavior>Something</UnknownBehavior></Properties><ChildObjects/></Task></MetaDataObject>'''


class GeneralSourceTests(unittest.TestCase):
    def test_empty_configuration_without_catalogs(self):
        source = import_source({'Configuration.xml': CONFIG})
        self.assertEqual(source.name, 'Example')
        self.assertFalse(source.report()['storage_activated'])

    def test_unknown_metadata_preserved_without_runtime_claim(self):
        source = import_source({'Configuration.xml': CONFIG, 'Tasks/Workflow.xml': TASK})
        self.assertEqual(source.metadata[1].family, 'Task')
        self.assertIn('storage_not_activated', [d.code for d in source.diagnostics])

    def test_uncompiled_unknown_modules_are_preserved(self):
        raw = b'not supported syntax \xff'
        source = import_source({'Configuration.xml': CONFIG, 'CommonModules/X/Ext/Module.bsl': raw})
        self.assertEqual(source.files[0].content, raw)
        self.assertEqual(source.files[0].kind, 'module')

    def test_binary_resources_are_retained(self):
        source = import_source({'Configuration.xml': CONFIG, 'CommonPictures/Logo/Ext/Picture.bin': b'\x00\xff'})
        self.assertEqual(source.files[0].kind, 'resource')

    def test_archive_round_trip_all_bytes(self):
        source = import_source({'Configuration.xml': CONFIG, 'Tasks/Workflow.xml': TASK,
                                'CommonTemplates/X/Ext/Template.bin': b'\x00\xff'})
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'source.zip'
            save_source_archive(target, source)
            self.assertEqual(load_source_archive(target), source)

    def test_archive_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'db.sqlite'
            target.write_bytes(b'precious')
            with self.assertRaises(FileExistsError):
                save_source_archive(target, import_source({'Configuration.xml': CONFIG}))
            self.assertEqual(target.read_bytes(), b'precious')

    def test_archive_rejects_changed_source_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'source.zip'
            save_source_archive(target, import_source({'Configuration.xml': CONFIG}))
            with zipfile.ZipFile(target) as original:
                entries = {i.filename: original.read(i) for i in original.infolist()}
            entries['source/Configuration.xml'] = CONFIG.replace(b'Example', b'Changed')
            with zipfile.ZipFile(target, 'w') as changed:
                for name, raw in entries.items(): changed.writestr(name, raw)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_source_archive(target)

    def test_source_rejects_traversal(self):
        for path in ('../x.xml', '/x.xml', 'a//x.xml', 'a/./x.xml', 'a\\x.xml', 'a:x.xml'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                import_source({'Configuration.xml': CONFIG, path: b''})

    def test_source_rejects_case_collisions(self):
        with self.assertRaisesRegex(ValueError, 'colliding'):
            import_source({'Configuration.xml': CONFIG, 'x.bsl': b'', 'X.bsl': b''})

    def test_source_rejects_duplicate_metadata_identity(self):
        with self.assertRaisesRegex(ValueError, 'UUID'):
            import_source({'Configuration.xml': CONFIG, 'Tasks/Workflow.xml': TASK.replace(b'22222222-2222-2222-2222-222222222222', b'11111111-1111-1111-1111-111111111111')})

    def test_source_rejects_malformed_xml(self):
        with self.assertRaisesRegex(ValueError, 'malformed'):
            import_source({'Configuration.xml': CONFIG, 'Ext/Unknown.xml': b'<oops>'})

    def test_source_rejects_entities(self):
        with self.assertRaisesRegex(ValueError, 'DTD'):
            import_source({'Configuration.xml': b'<!DOCTYPE x [<!ENTITY x "expanded">]>'+CONFIG})

    def test_source_requires_configuration_root(self):
        with self.assertRaisesRegex(ValueError, 'Configuration.xml'):
            import_source({'Configuration.xml': TASK})

    def test_source_rejects_file_budget(self):
        with patch('yadinassi.configuration_source.MAX_FILES', 1), self.assertRaises(ValueError):
            import_source({'Configuration.xml': CONFIG, 'x.bsl': b''})

    def test_source_rejects_total_byte_budget(self):
        with patch('yadinassi.configuration_source.MAX_TOTAL_BYTES', 1), self.assertRaises(ValueError):
            import_source({'Configuration.xml': CONFIG})

    def test_directory_and_archive_have_identical_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)/'source'; directory.mkdir()
            (directory/'Configuration.xml').write_bytes(CONFIG)
            (directory/'unknown.bin').write_bytes(b'\x00')
            loaded = load_source_directory(directory)
            target = Path(temp)/'source.zip'
            save_source_archive(target, loaded)
            self.assertEqual(loaded, load_source_archive(target))

    def test_directory_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)/'source'; directory.mkdir()
            (directory/'Configuration.xml').write_bytes(CONFIG)
            outside = Path(temp)/'outside'; outside.write_bytes(b'private')
            try: (directory/'linked.bin').symlink_to(outside)
            except OSError: self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError): load_source_directory(directory)

    def test_reader_limits_explicit_and_bounded(self):
        for options in ({'max_files': True}, {'max_depth': 33}, {'max_total_bytes': -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                read_configuration_directory('.', **options)

    def test_legacy_default_limits_still_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'Configuration.xml').write_bytes(CONFIG)
            (Path(temp)/'large.bin').write_bytes(b'x'*(1024*1024+1))
            with self.assertRaises(ValueError): read_configuration_directory(temp)
            self.assertEqual(len(load_source_directory(temp).files), 2)

    def test_archive_unknown_entries_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'bad.zip'
            with zipfile.ZipFile(target, 'w') as archive:
                archive.writestr('manifest.json', json.dumps({'format':'yadinassi.configuration-source.v1','files':{}}))
                archive.writestr('../escape', 'bad')
            with self.assertRaises(ValueError): load_source_archive(target)
