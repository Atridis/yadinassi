"""Owned temporary-file workflows, never operate on user data."""
import codecs
from decimal import Decimal as D
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi import file_io as f


class FileIOTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yadinassi-file-io-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'a.txt'
        self.vm = Interpreter(lambda _: None)
        self.vm.variables['p'] = str(self.path)
        self.vm.variables['root'] = str(self.root)

    def test_bilingual_owned_workflow(self):
        for writer, reader, binary, file, write, close, read in (
                ('TextWriter', 'TextReader', 'BinaryData', 'File', 'WriteLine', 'Close', 'ReadLine'),
                ('ЗаписьТекста', 'ЧтениеТекста', 'ДвоичныеДанные', 'Файл', 'ЗаписатьСтроку', 'Закрыть', 'ПрочитатьСтроку')):
            self.vm.execute(f'w=New {writer}(p); w.{write}("Привет"); w.{close}();'
                            f'r=New {reader}(p); s=r.{read}(); e=r.{read}(); r.{close}();'
                            f'd=New {binary}(p); f=New {file}(p);')
            self.assertEqual(self.vm.execute('s'), 'Привет')
            self.assertIsNone(self.vm.execute('e'))
            self.assertTrue(self.vm.execute(f'(TypeOf(d)=Type("{binary}"))'))
            self.assertTrue(self.vm.execute('f.Exists()'))
            self.assertEqual(self.vm.execute('f.Size()'), D(len(self.path.read_bytes())))

    def test_file_metadata_find_copy_move_delete(self):
        self.path.write_bytes(b'abc')
        obj = f.BSLFile(str(self.path))
        for name, expected in [('Name','a.txt'),('BaseName','a'),('Extension','.txt'),
                               ('Path',str(self.root)+os.sep),('FullName',str(self.path))]:
            self.assertEqual(obj.get_member(name), expected)
        self.assertTrue(obj.exists()); self.assertTrue(obj.is_file()); self.assertFalse(obj.is_directory())
        copy = str(self.root/'b.txt'); moved = str(self.root/'c.txt')
        f.copy_file(str(self.path), copy); f.move_file(copy, moved)
        self.assertFalse(Path(copy).exists()); self.assertEqual(Path(moved).read_bytes(), b'abc')
        self.assertEqual(len(f.find_files(str(self.root), '*.txt').items), 2)
        self.assertEqual(len(f.find_files(str(self.path)).items), 1)
        self.assertEqual(len(f.find_files(copy).items), 0)
        f.delete_files(moved); f.delete_files(moved)
        child = str(self.root/'child'); f.create_directory(child); f.create_directory(child)
        self.assertTrue(f.BSLFile(child).is_directory()); f.delete_files(child)
        with self.assertRaises(ValueError): f.copy_file(str(self.path), str(self.path))
        self.assertEqual(self.path.read_bytes(), b'abc')

    def test_temp_name_is_not_created(self):
        a = f.temp_file_name('.txt'); b = f.temp_file_name('txt')
        self.assertNotEqual(a,b); self.assertTrue(a.endswith('.txt'))
        self.assertFalse(Path(a).exists()); self.assertTrue(f.temp_files_dir().endswith(os.sep))
        with self.assertRaises(ValueError): f.temp_file_name('../bad')

    def test_binary_string_base64_roundtrips(self):
        for enc in ('UTF-8','UTF-16','UTF-16BE','windows-1251',f.BSLTextEncoding.UTF8):
            for bom in (False, True):
                data = f.binary_from_string('Привет', enc, bom)
                self.assertEqual(f.string_from_binary(data, enc), 'Привет')
                self.assertEqual(f.base64_string(f.base64_value(f.base64_string(data))), f.base64_string(data))
                data.write(str(self.path)); self.assertEqual(f.BSLBinaryData(str(self.path))._data, data._data)
        with self.assertRaises(Exception): f.base64_value('!!')
        with self.assertRaises(TypeError): f.base64_string('abc')
        self.vm.execute('d=GetBinaryDataFromString("abc",,True);')
        self.assertEqual(self.vm.execute('Base64String(d)'), '77u/YWJj')

    def test_writer_append_and_custom_separator(self):
        w=f.BSLTextWriter(str(self.path),'UTF-8','|',False,'')
        w.write_line('a'); w.close()
        w.open(str(self.path),'UTF-8','|',True,''); w.write_line('b'); w.close(); w.close()
        self.assertEqual(self.path.read_bytes(), codecs.BOM_UTF8+b'a|b|')
        r=f.BSLTextReader(str(self.path),None,'|','')
        self.assertEqual(r.read_line(),'a'); self.assertEqual(r.read_line(),'b'); self.assertIsNone(r.read_line())
        r.close(); r.close()
        with self.assertRaises(ValueError): r.read()
        with self.assertRaises(ValueError): w.write('x')

    def test_unopened_write_line_is_catchable(self):
        with self.assertRaises(ValueError): f.BSLTextWriter().write_line("x")
        self.vm.execute('w=New TextWriter; caught=False; Try w.WriteLine("x"); Except caught=True; EndTry;')
        self.assertTrue(self.vm.execute("caught"))

    def test_same_file_reopen_flushes_old_bom_before_truncation(self):
        w = f.BSLTextWriter(str(self.path))
        w.open(str(self.path), "windows-1251")
        w.write("x"); w.close()
        self.assertEqual(self.path.read_bytes(), b"x")

    def test_reader_empty_lines_partial_and_eof(self):
        self.path.write_bytes(b'a\r\n\r\nbc\n')
        r=f.BSLTextReader(str(self.path),'UTF-8')
        self.assertEqual(r.read_line(),'a'); self.assertEqual(r.read_line(),'')
        self.assertEqual(r.read(D(1)),'b'); self.assertEqual(r.read(),'c\n'); self.assertIsNone(r.read())
        self.path.write_bytes(b''); r.open(str(self.path)); self.assertIsNone(r.read_line())
        for bad in (D(-1), D('NaN'), D('.5'), True):
            with self.assertRaises(TypeError): r.read(bad)

    def test_failed_open_preserves_previous_reader(self):
        self.path.write_bytes(b'abc'); r=f.BSLTextReader(str(self.path),'UTF-8')
        with self.assertRaises(ValueError): r.open(str(self.root/'absent'))
        self.assertEqual(r.read(),'abc')

    def test_invalid_writer_arguments_do_not_truncate(self):
        self.path.write_bytes(b'keep')
        for args in [('unrecognized',),('UTF-8',None,'yes'),('UTF-8',3)]:
            with self.assertRaises((TypeError,ValueError)): f.BSLTextWriter(str(self.path),*args)
            self.assertEqual(self.path.read_bytes(),b'keep')

    def test_writer_limit_is_atomic_per_write(self):
        with patch.object(f,'MAX_BYTES',8):
            w=f.BSLTextWriter(str(self.path))
            w.write('a')
            before=self.path.read_bytes()
            with self.assertRaises(ValueError): w.write('12345')
            self.assertEqual(self.path.read_bytes(),before); w.close()

    def test_base64_roundtrip_at_binary_limit(self):
        with patch.object(f, 'MAX_BYTES', 64):
            for size in (48, 49, 63, 64):
                data = f.BSLBinaryData.from_bytes(bytes(range(size)))
                self.assertEqual(f.base64_value(f.base64_string(data))._data, data._data)
            with self.assertRaises(ValueError): f.base64_value('A' * 200)

    def test_writer_expansion_bound_before_allocation_or_write(self):
        w = f.BSLTextWriter(str(self.path), 'UTF-8', None, False, 'x' * 100)
        with patch.object(f, 'MAX_BYTES', 64):
            before = self.path.read_bytes()
            with self.assertRaises(ValueError): w.write('a\n' * 32)
            with self.assertRaises(ValueError): w.write_line('a' * 64)
            self.assertEqual(self.path.read_bytes(), before)
        w.close()

    def test_reader_size_limit(self):
        self.path.write_bytes(b'123456789')
        with patch.object(f,'MAX_BYTES',8):
            with self.assertRaises(ValueError): f.BSLBinaryData(str(self.path))

    def test_nonregular_rejected_and_no_descriptor_leak(self):
        with self.assertRaises((ValueError, OSError)): f.BSLBinaryData(str(self.root))
        if hasattr(os,'mkfifo'):
            fifo=self.root/'fifo'; os.mkfifo(fifo)
            try:
                with self.assertRaises((ValueError,OSError)): f.BSLBinaryData(str(fifo))
            finally: fifo.unlink()

    def test_properties_and_host_attributes_not_writable(self):
        self.vm.execute('f=New File(p);')
        with self.assertRaises(BSLError): self.vm.execute('f.Name="bad";')
        with self.assertRaises(BSLError): self.vm.execute('f._filename')
        self.assertEqual(self.vm.execute('TextEncoding.UTF8'),f.BSLTextEncoding.UTF8)
        self.assertEqual(self.vm.execute('КодировкаТекста.Системная'),f.BSLTextEncoding.SYSTEM)
        self.vm.execute('w=New TextWriter(p,,,False);w.Close();r=New TextReader;r.Open(p,,,);r.Close();')

    def test_unsupported_recursive_cleanup_does_not_mutate(self):
        self.path.write_bytes(b'keep')
        with self.assertRaises(ValueError): f.delete_files(str(self.root),'*')
        with self.assertRaises(ValueError): f.delete_files(str(self.root))
        self.assertEqual(self.path.read_bytes(),b'keep')
        with self.assertRaises(ValueError): f.find_files(str(self.root),'*',True)
        with self.assertRaises(ValueError): f.BSLFile('https://example.com/file')

if __name__ == '__main__': unittest.main()
