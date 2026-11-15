"""Real fixture storage behavior, independent of source formatting."""
from contextlib import closing
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import ast
import inspect
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('main_demo_qa_fixture', ROOT/'tests/browser_ui/main_demo_fixture.py')
fixture = module_from_spec(spec)
spec.loader.exec_module(fixture)


class MainDemoFixtureBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        fixture.seed(self.root)

    def test_fixture_has_no_direct_interpreter_or_document_write_calls(self):
        # Keep this architectural guard; execution coverage alone cannot forbid
        # an unexecuted alternate branch. AST is independent of whitespace.
        for fn in (fixture.seed, fixture.audit):
            tree = ast.parse(inspect.getsource(fn))
            calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
            names = {call.id if isinstance(call, ast.Name) else call.attr
                     for call in calls if isinstance(call, (ast.Name, ast.Attribute))}
            forbidden = {'Interpreter', 'execute_program', 'create_document'}
            if fn is fixture.seed:
                forbidden.add('execute')  # audit uses a readonly SQL SELECT.
            self.assertFalse(names & forbidden)

    def test_only_warehouse_choices_are_seeded_and_audit_is_readonly(self):
        database = self.root/fixture.DATABASE
        before = database.read_bytes()
        backend, connect = fixture.SQLiteCatalogBackend, fixture.sqlite3.connect
        with patch.object(fixture, 'SQLiteCatalogBackend', wraps=backend) as opened, patch.object(fixture.sqlite3, 'connect', wraps=connect) as connected:
            result = fixture.audit(self.root)
        self.assertTrue(result['readOnlyAudit'])
        self.assertEqual(result['documents'], {'Receipt': [], 'Issue': []})
        self.assertEqual(result['movementRows'], [])
        self.assertEqual(result['catalogs']['Номенклатура'], [])
        self.assertEqual(result['catalogs']['ВидыНоменклатуры'], [])
        rows = result['catalogs']['Склады']
        self.assertEqual(sorted((row['code'], row['description'], row['deletion_mark']) for row in rows),
                         [(f'W{i:03}', f'Warehouse {i:03}', False) for i in range(70)])
        self.assertTrue(opened.call_args_list)
        self.assertTrue(all(call.kwargs.get('read_only') is True for call in opened.call_args_list))
        self.assertTrue(connected.call_args_list)
        for call in connected.call_args_list:
            self.assertIn('mode=ro', call.args[0])
            self.assertTrue(call.kwargs.get('uri'))
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(fixture.audit(self.root), result)

    def test_audit_rejects_modified_authored_warehouse(self):
        with closing(fixture.SQLiteCatalogBackend(self.root/fixture.DATABASE)) as backend:
            schema = next(c for c in backend.accumulation_configuration.catalogs if c.name == 'Склады')
            with closing(backend.begin_read()) as view:
                row = view.select_catalog(schema.identity, fixture.CatalogSelection(limit=71))[0]
            with closing(backend.begin_write(UUID(int=99991))) as tx:
                tx.update(fixture.CatalogDraft(row.key, row.code, 'altered', False, ()), row.revision)
                tx.commit()
        before = (self.root/fixture.DATABASE).read_bytes()
        with self.assertRaisesRegex(ValueError, '^authored_warehouse_changed$'):
            fixture.audit(self.root)
        self.assertEqual((self.root/fixture.DATABASE).read_bytes(), before)

    def test_audit_rejects_source_mismatch_without_mutation(self):
        database = self.root/fixture.DATABASE
        before = database.read_bytes()
        with patch.object(fixture, 'read_configuration_directory', return_value=object()):
            with self.assertRaisesRegex(ValueError, '^source_changed$'):
                fixture.audit(self.root)
        self.assertEqual(database.read_bytes(), before)
