"""The layout and prepared-admission blocks retain the same complete source grant."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from yadinassi.catalog_backend import BackendError
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


def grouped(files, path):
    source = dict(files); raw = source[path]
    if b'<ChildItems>' not in raw or b'</ChildItems>' not in raw:
        raise AssertionError('fixture must contain declared form items')
    source[path] = raw.replace(b'<ChildItems>',
        b'<ChildItems><UsualGroup name="PreparedGroup" id="128"><Visible>true</Visible><ChildItems>', 1).replace(
        b'</ChildItems>', b'</ChildItems></UsualGroup></ChildItems>', 1)
    return source


class PreparedLayoutAdmissionTests(unittest.TestCase):
    def check_profile(self, files, path, create):
        source = grouped(files, path)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)/'layout.sqlite'
            with closing(create(database, source)) as backend:
                with patch('yadinassi.configuration_forms.compile_form_module') as compiler:
                    for _ in range(3):
                        with closing(backend.begin_read()): pass
                        self.assertEqual(backend.export_configuration(), source)
                    compiler.assert_not_called()
                changed = source[path].replace(b'<Visible>true</Visible>', b'<Visible>false</Visible>', 1)
                self.assertNotEqual(changed, source[path])
                with closing(sqlite3.connect(database)) as db:
                    db.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                        (changed, sha256(changed).hexdigest(), path)); db.commit()
                with self.assertRaises(BackendError): backend.begin_read()

    def test_business_layout_source_reused_without_widening_admission(self):
        from business_configuration_fixture import sources
        self.check_profile(sources(), 'CommonForms/Welcome/Ext/Form.xml',
            SQLiteCatalogBackend.create_business_application)

    def test_reference_layout_retains_full_typed_profile_and_tamper_guard(self):
        from test_configuration_reference_profile import sources
        self.check_profile(sources(), 'Catalogs/Products/Forms/Card/Ext/Form.xml',
            SQLiteCatalogBackend.create_reference_application)
