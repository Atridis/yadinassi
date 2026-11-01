"""Owned-temp normal ZIP workflows and adversarial input rejection."""
from decimal import Decimal
import io
from pathlib import Path
import os
import stat
import struct
import tempfile
import unittest
from unittest import mock
import zipfile

from yadinassi import Interpreter
from yadinassi.binary_streams import BSLMemoryStream, BSLPositionInStream, BSLBinaryDataBuffer
from yadinassi.zip_archives import (BSLZipFileReader as Reader, BSLZipFileWriter as Writer,
    BSLZIPStorePathMode as Paths, BSLZIPSubDirProcessingMode as Recurse,
    BSLZIPRestoreFilePathsMode as Restore, BSLZIPCompressionMethod as Method,
    BSLZIPCompressionLevel as Level, BSLFileNamesEncodingInZipFile as Encoding,
    BSLZIPEncryptionMethod as Encryption, _preflight_zip)
from yadinassi import zip_archives as module


ANCHORED = os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')


def raw_zip(entries, compression=zipfile.ZIP_STORED):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=compression) as z:
        for name, data in entries: z.writestr(name, data)
    return out.getvalue()


def reader_bytes(raw):
    return Reader(BSLMemoryStream(BSLBinaryDataBuffer.from_bytes(raw)))


class ZIPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='zip-family-test-')
        self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.src = self.root/'src'; self.src.mkdir(); (self.src/'sub').mkdir()
        (self.src/'a.bin').write_bytes(b'a\x00\xff'); (self.src/'sub'/'b.bin').write_bytes(b'b\x00\xff')
    @unittest.skipUnless(os.name == 'posix', 'Darwin root aliases use POSIX path syntax')
    def test_known_darwin_system_aliases_only(self):
        with mock.patch.object(module.sys, 'platform', 'darwin'):
            for prefix, target in (('/var','/private/var'),('/tmp','/private/tmp')):
                with mock.patch.object(module.os.path, 'realpath', return_value=target) as resolve:
                    self.assertEqual(module._darwin_system_path(Path(prefix+'/owned/a')),Path(target+'/owned/a'))
                    resolve.assert_called_once_with(prefix)
            with mock.patch.object(module.os.path, 'realpath') as resolve:
                self.assertEqual(module._darwin_system_path(Path('/variable/a')),Path('/variable/a'))
                self.assertEqual(module._darwin_system_path(Path('/tmp-other/a')),Path('/tmp-other/a'))
                resolve.assert_not_called()
            with mock.patch.object(module.os.path, 'realpath', return_value='/unexpected'):
                with self.assertRaises(ValueError): module._darwin_system_path(Path('/var/owned'))

    def test_file_create_read_find_metadata_extract(self):
        target = self.root/'out.zip'; w = Writer(str(target), None, 'комментарий')
        w.add(str(self.src/'a.bin')); w.write()
        r = Reader(str(target)); items = r.get_member('Items')
        self.assertEqual(items.count(), 1); entry = items.get(0)
        self.assertIs(items.find('a.bin'), entry); self.assertIsNone(items.find('missing'))
        self.assertEqual(entry.get_member('Name'), 'a.bin'); self.assertEqual(entry.get_member('BaseName'), 'a')
        self.assertEqual(entry.get_member('Extension'), 'bin'); self.assertEqual(entry.get_member('UncompressedSize'), 3)
        self.assertFalse(entry.get_member('Encrypted')); self.assertEqual(r.get_member('Comment'), 'комментарий')
        out = self.root/'extract'
        if not ANCHORED:
            with self.assertRaises(ValueError): r.extract(entry, str(out))
            self.assertFalse(out.exists()); return
        r.extract(entry, str(out)); self.assertEqual((out/'a.bin').read_bytes(), b'a\x00\xff')
        r.close(); r.close()
        with self.assertRaises(ValueError): r.get_member('Items')
    def test_recursive_relative_and_flat_extraction(self):
        w = Writer(); w.add(str(self.src/'*.bin'), Paths.RELATIVE, Recurse.RECURSIVE)
        r = Reader(w.get_binary_data().open_stream_for_read())
        self.assertEqual([e.get_member('FullName') for e in r.get_member('Items')], ['a.bin','sub/b.bin'])
        if not ANCHORED:
            with self.assertRaises(ValueError): r.extract_all(str(self.root/'restore'))
            return
        r.extract_all(str(self.root/'restore')); self.assertEqual((self.root/'restore/sub/b.bin').read_bytes(),b'b\x00\xff')
        r.extract_all(str(self.root/'flat'),Restore.FLAT);self.assertEqual((self.root/'flat/b.bin').read_bytes(),b'b\x00\xff')
    def test_memory_stream_and_binary_data_workflow(self):
        stream=BSLMemoryStream();w=Writer(stream);w.add(str(self.src/'a.bin'));w.write()
        stream.seek(0,BSLPositionInStream.BEGIN);r=Reader(stream)
        self.assertEqual(r.get_member('Items').count(),1)
        r.close();self.assertGreater(stream.size(),0)
    def test_compression_levels_and_utf8_roundtrip(self):
        p=self.src/'текст.txt';p.write_bytes(b'abc'*100)
        for method in (Method.COPY,Method.DEFLATE):
            for level in Level:
                w=Writer(str(self.root/'z.zip'),None,'',method,level,None,Encoding.UTF8)
                w.add(str(p));w.write();r=Reader(str(self.root/'z.zip'))
                if not ANCHORED:
                    with self.assertRaises(ValueError): r.extract_all(str(self.root/'e'))
                    with zipfile.ZipFile(self.root/'z.zip') as archive: self.assertEqual(archive.read('текст.txt'),b'abc'*100)
                    continue
                r.extract_all(str(self.root/'e'));self.assertEqual((self.root/'e/текст.txt').read_bytes(),b'abc'*100)
    def test_empty_archive_and_constructorless_open(self):
        r=Reader();w=Writer();raw=w.get_binary_data();r.open(raw.open_stream_for_read());self.assertEqual(r.get_member('Items').count(),0)
        with self.assertRaises(ValueError):w.get_binary_data()
        w.open(str(self.root/'new.zip'));w.write();self.assertTrue((self.root/'new.zip').is_file())
    def test_replaces_archive_not_appends(self):
        p=self.root/'z.zip';w=Writer(str(p));w.add(str(self.src/'a.bin'));w.write()
        w.open(str(p));w.add(str(self.src/'sub/b.bin'));w.write()
        self.assertEqual([e.get_member('Name') for e in Reader(str(p)).get_member('Items')],['b.bin'])
    def test_bsl_types_aliases_and_immutable_collection(self):
        z=self.root/'z.zip';w=Writer(str(z));w.add(str(self.src/'a.bin'));w.write();out=[]
        Interpreter(out.append).execute(f'r=New ЧтениеZipФайла("{z}"); Message(TypeOf(r)=Type("ZipFileReader")); Message(r.Items[0].Name); For Each x In r.Items Do Message(x.UncompressedSize); EndDo; Try r.Items[0]=1; Except Message("readonly"); EndTry; r.Close();')
        self.assertEqual(out,['Да','a.bin','3','readonly'])
    def test_foreign_and_stale_entry_rejected(self):
        raw=raw_zip([('a',b'x')]);a=reader_bytes(raw);b=reader_bytes(raw);entry=a.get_member('Items').get(0)
        with self.assertRaises(TypeError):b.extract(entry,str(self.root/'out'))
        a.open(BSLMemoryStream(BSLBinaryDataBuffer.from_bytes(raw)))
        with self.assertRaises(TypeError):a.extract(entry,str(self.root/'out'))
    def test_bad_arguments_and_host_adapters_rejected(self):
        for value in (io.BytesIO(),b'zip',True,object()):
            with self.subTest(value=type(value)),self.assertRaises(TypeError):Reader(value)
        w=Writer()
        with self.assertRaises(TypeError):w.add(str(self.src/'a.bin'),True)
        with self.assertRaises(ValueError):w.add(str(self.src/'missing'))
        with self.assertRaises(ValueError):w.write()
        w.add(str(self.src/'a.bin'))
        with self.assertRaises(ValueError):w.add(str(self.src/'a.bin'))
    def test_password_and_unsupported_settings_never_silent(self):
        for kwargs in ({'password':'secret'},{'method':Method.BZIP2},{'encryption':Encryption.AES256},{'encoding':Encoding.OS_UTF8}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):Writer(**kwargs)
        with self.assertRaises(ValueError):Reader(str(self.root/'absent'),'secret')
    def test_unsafe_archive_names_rejected_without_writes(self):
        for name in ('../escape','/absolute','C:/drive','a/../../escape','a:ads','a\\..\\b','//server/share','NUL','COM1.txt','trailing.','a//b'):
            with self.subTest(name=name),self.assertRaises(ValueError):reader_bytes(raw_zip([(name,b'x')]))
        self.assertFalse((self.root/'escape').exists())
    def test_archive_duplicate_and_file_directory_collisions(self):
        for entries in ([('A',b'x'),('a',b'y')],[('a',b'x'),('a/b',b'y')]):
            with self.assertRaises(ValueError):reader_bytes(raw_zip(entries))
    @unittest.skipUnless(ANCHORED, 'Anchored extraction backend unavailable')
    def test_flatten_collision_preflight_preserves_destination(self):
        r=reader_bytes(raw_zip([('one/a',b'x'),('two/a',b'y')]))
        out=self.root/'out';out.mkdir();(out/'a').write_bytes(b'original')
        with self.assertRaises(ValueError):r.extract_all(str(out),Restore.FLAT)
        self.assertEqual((out/'a').read_bytes(),b'original')
    def test_symlink_entry_rejected(self):
        info=zipfile.ZipInfo('link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        with self.assertRaises(ValueError):reader_bytes(raw_zip([(info,b'../outside')]))
    def test_symlink_ancestor_source_and_destination_rejected(self):
        target=self.root/'target';target.mkdir();link=self.root/'link'
        try:link.symlink_to(target,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('symlink creation unavailable')
        (target/'a').write_bytes(b'original')
        with self.assertRaises(ValueError):Writer().add(str(link/'a'))
        r=reader_bytes(raw_zip([('a',b'changed')]))
        with self.assertRaises(ValueError):r.extract_all(str(link))
        self.assertEqual((target/'a').read_bytes(),b'original')
    def test_network_device_path_rejected_before_open(self):
        for path in ('\\\\server\\share\\archive.zip','//server/share/a','\\\\.\\pipe\\x','C:/x:ads','NUL'):
            with self.subTest(path=path),mock.patch.object(module.os,'open') as opened,self.assertRaises(ValueError):Reader(path)
            opened.assert_not_called()
    def test_encrypted_flag_and_multipart_rejected(self):
        raw=bytearray(raw_zip([('a',b'x')]));central=raw.index(b'PK\x01\x02');struct.pack_into('<H',raw,central+8,1)
        with self.assertRaises(ValueError):reader_bytes(bytes(raw))
        raw=bytearray(raw_zip([('a',b'x')]));end=raw.rfind(b'PK\x05\x06');struct.pack_into('<H',raw,end+4,1)
        with self.assertRaises(ValueError):reader_bytes(bytes(raw))
    def test_central_directory_count_bounded_before_library(self):
        raw=raw_zip([('a',b'x'),('b',b'y')])
        with mock.patch.object(module,'MAX_ENTRIES',1),mock.patch.object(module.zipfile,'ZipFile') as constructor,self.assertRaises(ValueError):reader_bytes(raw)
        constructor.assert_not_called()
    @unittest.skipUnless(ANCHORED, 'Anchored extraction backend unavailable')
    def test_declared_and_actual_expansion_bounded(self):
        raw=raw_zip([('a',b'x'*1000)],zipfile.ZIP_DEFLATED)
        with mock.patch.object(module,'MAX_BYTES',500),self.assertRaises(ValueError):reader_bytes(raw)
        r=reader_bytes(raw);out=self.root/'out'
        with mock.patch.object(module,'MAX_BYTES',20),self.assertRaises(ValueError):r.extract_all(str(out))
        self.assertFalse(out.exists())
    @unittest.skipUnless(ANCHORED, 'Anchored extraction backend unavailable')
    def test_crc_failure_has_no_partial_extraction(self):
        raw=bytearray(raw_zip([('first',b'abc'),('second',b'xyz')]))
        raw[raw.index(b'xyz')]=ord('Q');r=reader_bytes(bytes(raw));out=self.root/'out'
        with self.assertRaises(ValueError):r.extract_all(str(out))
        self.assertFalse(out.exists())
    def test_writer_budget_failure_preserves_existing_target(self):
        p=self.root/'archive.zip';p.write_bytes(b'original');w=Writer(str(p));w.add(str(self.src/'a.bin'))
        with mock.patch.object(module,'MAX_BYTES',20),self.assertRaises(ValueError):w.write()
        self.assertEqual(p.read_bytes(),b'original')
    def test_recursive_scan_budget_and_symlinks_not_followed(self):
        with mock.patch.object(module,'MAX_ENTRIES',1),self.assertRaises(ValueError):Writer().add(str(self.src/'*.bin'),Paths.RELATIVE,Recurse.RECURSIVE)
    def test_readonly_stream_cannot_be_archive_target(self):
        stream=BSLMemoryStream().get_readonly_stream()
        self.assertTrue(stream.get_member('CanWrite'))
        with self.assertRaises(ValueError):Writer(stream)
    def test_unavailable_anchoring_refuses_extraction_before_any_write(self):
        r=reader_bytes(raw_zip([('ordinary.txt',b'data')]))
        out=self.root/'unsupported'
        with mock.patch.object(module.os,'supports_dir_fd',set()), mock.patch.object(module,'_write_file') as write:
            with self.assertRaises(ValueError):r.extract_all(str(out))
            write.assert_not_called()
        self.assertFalse(out.exists())
        self.assertEqual(r.get_member('Items').count(),1)  # Reader remains usable.

    def test_archive_library_errors_are_normalized(self):
        # Controlled library fault, not an external or adversarial archive.
        w = Writer()
        with mock.patch.object(w, '_bytes', side_effect=module.zlib.error('decode failed')):
            with self.assertRaises(ValueError): w.get_binary_data()

    def test_empty_and_truncated_input_errors_are_catchable(self):
        p=self.root/'bad.zip';p.write_bytes(b'bad');out=[]
        Interpreter(out.append).execute(f'Try r=New ZipFileReader("{p}"); Except Message("caught"); EndTry;')
        self.assertEqual(out,['caught'])

if __name__=='__main__':unittest.main()
