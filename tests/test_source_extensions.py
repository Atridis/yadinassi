from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from test_source_manager_modules import configuration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError


class SourceExtensionTests(unittest.TestCase):
    def app(self, call='Message(ConfigurationExtensions.Get().Count());', scratch=True, server=True):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        a=SourceApplication(configuration(call,session=server),output=lambda _:None,
                            scratch_database=Path(temp.name)/'fresh.sqlite' if scratch else None)
        self.addCleanup(a.close)
        return a

    def test_fresh_database_inventory_is_empty(self):
        a=self.app()
        self.assertTrue(a.start())

    def test_all_session_sources_and_issues(self):
        a=self.app('Message(ConfigurationExtensions.Get(,).Count()); Message(ConfigurationExtensions.Get(Undefined,).Count()); Message(ConfigurationExtensions.Get(, ConfigurationExtensionsSource.Database).Count()); Message(ConfigurationExtensions.Get(, ConfigurationExtensionsSource.SessionApplied).Count()); Message(ConfigurationExtensions.Get(, ConfigurationExtensionsSource.SessionDisabled).Count()); Message(ConfigurationExtensions.GetSessionApplicationIssuesInformation().Count());')
        self.assertTrue(a.start())

    def test_missing_scratch_database_not_empty(self):
        with self.assertRaisesRegex(BSLError,'explicitly created'):self.app(scratch=False).start()

    def test_populated_registry_is_not_hidden(self):
        a=self.app()
        with closing(sqlite3.connect(a.constant_store.path)) as db, db:
            db.execute('INSERT INTO source_extension_registry VALUES(?,?)',('x',b'data'))
        with self.assertRaisesRegex(BSLError,'populated extension registry'):a.start()

    def test_missing_registry_is_not_empty(self):
        a=self.app()
        with closing(sqlite3.connect(a.constant_store.path)) as db, db:db.execute('DROP TABLE source_extension_registry')
        with self.assertRaisesRegex(BSLError,'file/schema integrity'):a.start()

    def test_issues_are_not_hidden(self):
        a=self.app()
        with closing(sqlite3.connect(a.constant_store.path)) as db, db:db.execute('INSERT INTO source_extension_issues VALUES(?,?)',('x','broken'))
        with self.assertRaisesRegex(BSLError,'populated extension registry'):a.start()

    def test_client_access_not_granted(self):
        with self.assertRaisesRegex(BSLError,'synchronous server'):self.app(server=False).start()

    def test_safe_mode_blocks_database_read(self):
        with self.assertRaises(BSLError):self.app('SetSafeMode(True); ConfigurationExtensions.Get();').start()

    def test_mutation_explicitly_unsupported(self):
        with self.assertRaisesRegex(BSLError,'attachment and mutation'):self.app('ConfigurationExtensions.Create();').start()

    def test_invalid_source_not_coerced(self):
        with self.assertRaisesRegex(BSLError,'ConfigurationExtensionsSource required'):self.app('ConfigurationExtensions.Get(, "SessionApplied");').start()

    def test_filter_not_ignored(self):
        with self.assertRaisesRegex(BSLError,'filter is not yet supported'):self.app('ConfigurationExtensions.Get(New Structure);').start()

    def test_local_name_keeps_precedence(self):
        with self.assertRaises(BSLError):self.app('ConfigurationExtensions=7; ConfigurationExtensions.Get(, ConfigurationExtensionsSource.Database);').start()
