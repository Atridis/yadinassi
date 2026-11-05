"""Source-to-storage local numbering contract, not native-numbering parity."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.configuration_xml import import_configuration
from yadinassi.cli import main
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from sqlite_catalog_fixture import configuration_files


def numbered_files():
    files = configuration_files()
    path = 'Catalogs/Categories.xml'
    files[path] = files[path].replace(b'<Autonumbering>false', b'<Autonumbering>true')
    return files


class ConfigurationNumberingImportTests(unittest.TestCase):
    def test_default_remains_closed_and_policy_is_exact(self):
        with self.assertRaises(ValueError):
            import_configuration(numbered_files())
        for policy in (None, True, '', 'native', 'DECIMAL_V1', ['decimal_v1']):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                import_configuration(numbered_files(), numbering_policy=policy)

    def test_opt_in_preserves_source_and_only_enables_flagged_catalog(self):
        files = numbered_files()
        imported = import_configuration(files, numbering_policy='decimal_v1')
        self.assertEqual(imported.activation_issues, ())
        self.assertEqual({f.path: f.content for f in imported.files}, files)
        self.assertEqual([c.numbering for c in imported.catalogs], ['decimal_v1', 'explicit'])
        self.assertEqual(import_configuration(configuration_files()).catalogs[0].numbering, 'explicit')

    def test_semantic_and_width_gates_remain_closed(self):
        for old, new in ((b'<CodeLength>8', b'<CodeLength>10'),
                         (b'<Hierarchical>false', b'<Hierarchical>true'),
                         (b'<CheckUnique>true', b'<CheckUnique>false'),
                         (b'<CodeType>String', b'<CodeType>Number'),
                         (b'<Autonumbering>true', b'<Autonumbering>True'),
                         (b'<Autonumbering>true', b'<Autonumbering>1'),
                         (b'</Properties>', b'<CodeSeries>WithinOwner</CodeSeries></Properties>'),
                         (b'</Properties>', b'<Owners><Item>Other</Item></Owners></Properties>')):
            files = numbered_files()
            files['Catalogs/Categories.xml'] = files['Catalogs/Categories.xml'].replace(old, new)
            with self.subTest(new=new), self.assertRaises(ValueError):
                import_configuration(files, numbering_policy='decimal_v1')

    def test_other_activation_issues_cannot_be_bypassed(self):
        for path, content in (('Catalogs/Categories/Ext/ObjectModule.bsl', b'Procedure BeforeWrite(Cancel)\nCancel=True;\nEndProcedure'),
                              ('Catalogs/Categories/Forms/Card.xml', b'<unsupported/>')):
            files = numbered_files(); files[path] = content
            imported = import_configuration(files, numbering_policy='decimal_v1')
            self.assertTrue(imported.activation_issues)
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'refused.sqlite'
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    SQLiteCatalogBackend.create(target, imported)
                self.assertFalse(target.exists())

    def test_active_import_committed_outcome_export_reopen_and_receipt(self):
        files = numbered_files()
        imported = import_configuration(files, numbering_policy='decimal_v1')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'owned.sqlite'
            backend = SQLiteCatalogBackend.create(target, imported)
            try:
                self.assertEqual(backend.storage_version, 4)
                draft = CatalogDraft(CatalogKey(backend.database_id, imported.catalogs[0].identity, uuid4()), '', 'saved', False, (), auto_number=True)
                operation = uuid4()
                tx = backend.begin_write(operation)
                try:
                    tx.create(draft)
                    outcome = tx.commit_outcomes()[0]
                finally: tx.close()
                self.assertEqual(outcome.code, '00000001')
            finally: backend.close()
            backend = SQLiteCatalogBackend(target)
            try:
                self.assertEqual(backend.resolve_write_outcome(operation, draft), outcome)
                self.assertEqual(backend.export_configuration(), files)
                view = backend.begin_read()
                try: self.assertEqual(view.read_catalog(draft.key).description, 'saved')
                finally: view.close()
            finally: backend.close()

    def test_cli_import_then_real_bsl_write_and_reopen(self):
        def run(args):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(args)
            return code, out.getvalue(), err.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; source.mkdir()
            for path, content in numbered_files().items():
                target = source / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
            database = root / 'app.sqlite'
            args = ['--create-db', str(database), '--import-xml', str(source)]
            self.assertEqual(run(args)[0], 1)
            self.assertFalse(database.exists())
            result = run(args + ['--numbering-policy', 'decimal_v1'])
            self.assertEqual(result[0], 0, result)
            result = run(['--f', str(database), '-c', 'O=Catalogs.Categories.CreateItem();O.Description="saved";O.Write();Message(O.Code);'])
            self.assertEqual(result[:2], (0, '00000001\n'), result)
            result = run(['--f', str(database), '-c', 'Message(Catalogs.Categories.FindByCode("00000001").Description);'])
            self.assertEqual(result[:2], (0, 'saved\n'), result)
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                main(['--numbering-policy', 'decimal_v1', '-c', 'Message(1);'])
            self.assertEqual(error.exception.code, 2)
