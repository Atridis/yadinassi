"""Local recursive search contract; no native-recursion parity claim."""
from pathlib import Path
import os
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi import file_io as f


class RecursiveFindFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='yadinassi-recursive-find-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def touch(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'owned fixture')
        return path

    def names(self, mask='*.txt', recursive=True):
        return {str(Path(item.get_member('FullName')).relative_to(self.root))
                for item in f.find_files(str(self.root), mask, recursive).items}

    def test_nested_search_descends_through_nonmatching_directories(self):
        self.touch('root.txt'); self.touch('branch/deep/товар.txt')
        self.touch('branch/ignore.csv')
        self.assertEqual(self.names(), {'root.txt', str(Path('branch/deep/товар.txt'))})

    def test_matching_directories_are_returned_and_still_traversed(self):
        self.touch('branch.txt/inside.txt')
        self.assertEqual(self.names(), {'branch.txt', str(Path('branch.txt/inside.txt'))})

    def test_false_and_omission_keep_nonrecursive_search(self):
        self.touch('top.txt'); self.touch('nested/child.txt')
        self.assertEqual(self.names(recursive=False), {'top.txt'})
        self.assertEqual(self.names(recursive=None), {'top.txt'})

    def test_without_mask_true_still_checks_only_exact_path(self):
        file = self.touch('nested/item.txt')
        for path in (file, self.root, self.root / 'missing'):
            with self.subTest(path=path):
                values = f.find_files(str(path), None, True).items
                self.assertEqual([item.get_member('FullName') for item in values],
                                 [str(path)] if path.exists() else [])

    def test_empty_tree_and_empty_mask(self):
        self.assertEqual(self.names(), set())
        self.touch('nested/item.txt')
        self.assertEqual(self.names(mask=''), set())

    def test_bilingual_bsl_aliases_and_omitted_arguments(self):
        self.touch('nested/товар.txt')
        vm = Interpreter(lambda _: None); vm.variables['root'] = str(self.root)
        for expression in ('НайтиФайлы(root,"*.txt",Истина)',
                           'fInDfIlEs(root,"*.txt",True)'):
            with self.subTest(expression=expression):
                self.assertEqual(len(vm.execute(expression).items), 1)
        self.assertEqual(vm.execute('FindFiles(root,,True)[0].FullName'), str(self.root))
        with self.assertRaises(BSLError):
            vm.execute('FindFiles(root,"*",1)')

    def test_invalid_arguments_reject_before_scanning(self):
        with patch.object(f.os, 'scandir', side_effect=AssertionError('unexpected scan')):
            for mask, recursive in (('../*', True), ('a/b', True), ('a\\b', True),
                                     ('*', 1), ('*', 'true'), (3, True)):
                with self.subTest(mask=mask, recursive=recursive):
                    with self.assertRaises((TypeError, ValueError)):
                        f.find_files(str(self.root), mask, recursive)

    def test_entry_budget_is_global_and_includes_nonmatches(self):
        self.touch('one/a.txt'); self.touch('two/b.txt')
        for mask in ('*.txt', '*.missing'):
            with self.subTest(mask=mask), patch.object(f, 'MAX_FILES', 3):
                with self.assertRaisesRegex(ValueError, 'предел числа файлов'):
                    self.names(mask)
        with patch.object(f, 'MAX_FILES', 4):
            self.assertEqual(len(self.names()), 2)

    def test_deep_search_uses_no_recursive_python_calls(self):
        relative = Path(*(['d'] * 80)) / 'last.txt'
        self.touch(relative)
        self.assertEqual(self.names(), {str(relative)})

    def test_links_are_listed_but_never_descended_into(self):
        outside = self.root / 'outside'; outside.mkdir()
        (outside / 'hidden.txt').write_bytes(b'owned')
        base = self.root / 'base'; base.mkdir()
        try:
            (base / 'linked.txt').symlink_to(outside, target_is_directory=True)
            (base / 'loop.txt').symlink_to(base, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('directory symlinks unavailable')
        found = f.find_files(str(base), '*.txt', True).items
        self.assertEqual({item.get_member('Name') for item in found}, {'linked.txt', 'loop.txt'})

    def test_recursive_root_link_rejects(self):
        target = self.root / 'target'; target.mkdir()
        link = self.root / 'link'
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('directory symlinks unavailable')
        suffixes = ('', os.sep, os.sep * 3, os.sep + '.', os.sep + '.' + os.sep,
                    os.sep + '.' + os.sep + '.' + os.sep)
        for suffix in suffixes:
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, 'обычный каталог'):
                f.find_files(str(link) + suffix, '*', True)

    def test_root_normalization_preserves_roots_and_interior_components(self):
        root = os.path.abspath(os.sep)
        for path in (root, root + '.', root + '.' + os.sep):
            self.assertEqual(f._search_root(path), root)
        self.assertEqual(f._search_root('.' + os.sep), '.')
        relative = os.path.join('linked', '..', 'directory')
        self.assertEqual(f._search_root(relative + os.sep + '.'), relative)
        if os.name == 'nt':
            for path in ('C:\\', '\\\\server\\share\\'):
                self.assertEqual(f._search_root(path), path)

    def test_windows_reparse_entry_is_not_descended(self):
        entry = SimpleNamespace(name='junction', path=str(self.root / 'junction'),
                                stat=lambda **kw: SimpleNamespace(st_mode=stat.S_IFDIR,
                                                                  st_file_attributes=0x400))
        class Scan:
            def __enter__(self): return iter((entry,))
            def __exit__(self, *args): pass
        with patch.object(f.os, 'scandir', return_value=Scan()) as scan:
            result = f.find_files(str(self.root), '*', True)
        self.assertEqual(len(result.items), 1)
        scan.assert_called_once_with(str(self.root))

    def test_failure_closes_scanner_and_returns_no_partial_result(self):
        state = []
        def failure(**kwargs): raise PermissionError('owned simulated unreadable entry')
        entry = SimpleNamespace(name='matched.txt', path=str(self.root / 'matched.txt'), stat=failure)
        class Scan:
            def __enter__(self): return iter((entry,))
            def __exit__(self, *args): state.append('closed')
        with patch.object(f.os, 'scandir', return_value=Scan()):
            with self.assertRaisesRegex(ValueError, 'Файлы:'):
                f.find_files(str(self.root), '*.txt', True)
        self.assertEqual(state, ['closed'])

    def test_missing_root_and_file_root_are_catchable_errors(self):
        file = self.touch('item.txt')
        for path in (self.root / 'missing', file):
            with self.subTest(path=path), self.assertRaises(ValueError):
                f.find_files(str(path), '*', True)


if __name__ == '__main__':
    unittest.main()
