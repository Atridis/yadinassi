"""Closed full-source admission and fresh physical13 variant boundaries."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import UUID

from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_posting_application import import_posting_application, canonical, PROFILE
from yadinassi.configuration_posting import import_posting_configuration, PROFILE as CORE_PROFILE
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from posting_application_fixture import source, FORM_MODULE

ROOT = Path(__file__).resolve().parents[1]


class PostingApplicationSourceTests(unittest.TestCase):
    def load(self, files=None):
        return import_posting_application(source() if files is None else files, posting_runtime=PROFILE)

    def test_full_original_source_and_digest_retained(self):
        files=source();config=self.load(files)
        self.assertEqual(dict(config.files),files);self.assertEqual(canonical(config),config)
        digest=sha256(b''.join(p.encode()+b'\0'+sha256(raw).digest() for p,raw in sorted(files.items()))).hexdigest()
        self.assertEqual(config.source_digest,digest)
        self.assertNotEqual(config.source_digest,config.core_projection_digest)

    def test_explicit_profile_required(self):
        with self.assertRaises(ValueError):import_posting_application(source())

    def test_old_scalar_importer_is_not_widened(self):
        with self.assertRaises(ValueError):import_posting_configuration(source(),posting_runtime=CORE_PROFILE)

    def test_commands_bind_exact_form_name_id_and_mode(self):
        grants=self.load().commands
        self.assertEqual([(g.command,g.command_id,g.mode) for g in grants],[('DoWrite',1,'Write'),('DoPost',2,'Post'),('DoUndo',3,'UndoPosting')])

    def test_missing_host_manifest_refused(self):
        files=source();del files['PostingApplication.xml']
        with self.assertRaises(ValueError):self.load(files)

    def test_unknown_host_manifest_fields_refused(self):
        files=source();files['PostingApplication.xml']=files['PostingApplication.xml'].replace(b'version="1"',b'version="1" unknown="true"')
        with self.assertRaises(ValueError):self.load(files)

    def test_wrong_command_id_refused(self):
        files=source();files['PostingApplication.xml']=files['PostingApplication.xml'].replace(b'id="2"',b'id="99"')
        with self.assertRaises(ValueError):self.load(files)

    def test_wrong_command_name_refused(self):
        files=source();files['PostingApplication.xml']=files['PostingApplication.xml'].replace(b'name="DoPost"',b'name="Post"')
        with self.assertRaises(ValueError):self.load(files)

    def test_duplicate_mode_refused(self):
        files=source();files['PostingApplication.xml']=files['PostingApplication.xml'].replace(b'mode="Post"',b'mode="Write"')
        with self.assertRaises(ValueError):self.load(files)

    def test_wrong_namespace_refused(self):
        files=source();files['PostingApplication.xml']=files['PostingApplication.xml'].replace(b'posting-application:1',b'posting-application:2')
        with self.assertRaises(ValueError):self.load(files)

    def test_nonempty_host_command_handler_refused(self):
        files=source();files[FORM_MODULE]=files[FORM_MODULE].replace(b'DoPostCommand(Command)\n',b'DoPostCommand(Command)\nMessage("not empty");\n')
        with self.assertRaises(ValueError):self.load(files)

    def test_unknown_executable_file_refused(self):
        files=source();files['Ext/ManagedApplicationModule.bsl']=b'// no implicit grant'
        with self.assertRaises(ValueError):self.load(files)

    def test_forged_full_configuration_refused(self):
        with self.assertRaises(ValueError):canonical(replace(self.load(),source_digest='0'*64))

    def test_forged_commands_refused(self):
        with self.assertRaises(ValueError):canonical(replace(self.load(),commands=()))

    def test_duplicate_form_and_register_field_identity_refused(self):
        files=source();p='Documents/Order/Forms/Card.xml';files[p]=files[p].replace(str(UUID(int=30)).encode(),str(UUID(int=4)).encode())
        with self.assertRaises(ValueError):self.load(files)

    def test_fresh_create_stores_full_source_and_distinct_marker(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            path=Path(tmp)/'app.sqlite';config=self.load()
            with closing(SQLiteDBContext.create_posting(path,config)) as context:
                self.assertEqual(context.backend.export_configuration(),dict(config.files))
                self.assertEqual((context.backend.format_version,context.backend.storage_version),(13,7))
            with closing(sqlite3.connect(path)) as c:
                self.assertEqual(c.execute('SELECT profile,source_digest FROM posting_profile').fetchone(),(PROFILE,config.source_digest))
            with closing(SQLiteCatalogBackend(path)) as backend:self.assertEqual(backend.posting_configuration,config)

    def test_new_source_under_old_marker_refused(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            path=Path(tmp)/'app.sqlite'
            SQLiteDBContext.create_posting(path,self.load()).close()
            with closing(sqlite3.connect(path)) as c:c.execute('UPDATE posting_profile SET profile=?',(CORE_PROFILE,));c.commit()
            with self.assertRaises(BackendError):SQLiteCatalogBackend(path)

    def test_manifest_tamper_with_updated_file_hash_refused_on_open(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            path=Path(tmp)/'app.sqlite';config=self.load();SQLiteDBContext.create_posting(path,config).close()
            raw=dict(config.files)['PostingApplication.xml'].replace(b'mode="Post"',b'mode="Write"')
            with closing(sqlite3.connect(path)) as c:c.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',(raw,sha256(raw).hexdigest(),'PostingApplication.xml'));c.commit()
            with self.assertRaises(BackendError):SQLiteCatalogBackend(path)

    def test_inverse_document_name_uuid_order_is_canonical(self):
        files=source()
        for path,raw in tuple(files.items()):
            if path.startswith('Documents/Order'):
                for old,new in ((2,99),(20,120),(21,121),(22,122),(30,130)):
                    raw=raw.replace(str(UUID(int=old)).encode(),str(UUID(int=new)).encode())
                files[path.replace('Order','Alpha')]=raw.replace(b'Order',b'Alpha')
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Document>Alpha</Document></ChildObjects>')
        manifest=files['PostingApplication.xml'];start=manifest.index(b'<Form ');end=manifest.index(b'</Form>')+len(b'</Form>')
        files['PostingApplication.xml']=manifest[:end]+manifest[start:end].replace(b'Document.Order.',b'Document.Alpha.')+manifest[end:]
        config=self.load(files)
        self.assertEqual([d.name for d in config.documents],['Order','Alpha'])
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
            with closing(SQLiteDBContext.create_posting(Path(tmp)/'app.sqlite',config)) as context:
                from yadinassi.document_posting_host import RootPostingOperations
                host=RootPostingOperations(context,config);host.verify_source();host.close()
