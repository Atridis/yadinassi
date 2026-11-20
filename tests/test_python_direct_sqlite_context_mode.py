"""SQLite attachment alone does not require full audits for pure BSL."""
from cProfile import Profile
from pathlib import Path
from pstats import Stats
from tempfile import TemporaryDirectory
import unittest

from sqlite_test_templates import copy_main_demo
from yadinassi import Interpreter
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.execution.direct.python_direct import make_boundary


def audit_calls(vm, source):
    plan = vm.prepare(source)
    profile = Profile()
    profile.runcall(vm.execute_prepared, plan)
    return sum(data[0] for (path, _, name), data in Stats(profile).stats.items()
               if name == '_check' and path == make_boundary.__code__.co_filename)


class SQLiteContextModeTests(unittest.TestCase):
    def make(self, *, allow_extensions=False):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'mode.sqlite'
        copy_main_demo(path)
        context = SQLiteDBContext(path)
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context, allow_extensions=allow_extensions)
        self.addCleanup(vm.close)
        return vm

    def test_pure_persisted_calls_and_tables_with_database_skip_full_audit(self):
        vm = self.make()
        vm.execute('Function Inc(Val X) Return X+1; EndFunction')
        pure = ('T=New ValueTable;T.Columns.Add("A");X=T.Add();X.A=47;'
                'R=0;For I=1 To 8 Do R=R+T.Get(0).A; EndDo;'
                'For I=1 To 8 Do R=Inc(R)+StrLen("abc"); EndDo;')
        self.assertEqual(audit_calls(vm, pure), 0)
        self.assertEqual(vm.variables['r'], 408)

    def test_query_checks_ownership_without_full_context_audit(self):
        vm = self.make()
        query = ('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады");'
                 'S=Q.Execute().Select();S.Next();R=S.N;')
        self.assertEqual(audit_calls(vm, query), 0)
        self.assertEqual(vm.variables['r'], 0)

    def test_server_handoff_still_uses_full_audit(self):
        vm = self.make()
        vm.execute('&AtServer\nFunction Inc(Val X) Return X+1; EndFunction')
        self.assertGreater(audit_calls(vm, 'R=Inc(3);'), 0)
        self.assertEqual(vm.variables['r'], 4)

    def test_database_dynamic_fragments_preserve_full_audit(self):
        vm = self.make()
        self.assertGreater(audit_calls(vm, 'R=Eval("1+2");Execute("R=R+2;");'), 0)
        self.assertEqual(vm.variables['r'], 5)

    def test_explicit_extensions_keep_strict_runtime(self):
        vm = self.make(allow_extensions=True)
        self.assertGreater(audit_calls(vm, 'For I=1 To 8 Do R=StrLen("abc"); EndDo;'), 0)
        self.assertEqual(vm.variables['r'], 3)
