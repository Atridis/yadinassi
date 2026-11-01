"""Small ordinary checksum workflows; no authentication/security claims."""
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zlib

from yadinassi import Interpreter, serialization
from yadinassi import data_hashing as api
from yadinassi.data_hashing import BSLDataHashing as Hash, BSLHashFunction as Function
from yadinassi.binary_streams import (BSLMemoryStream as Memory, BSLFileStream as File,
    BSLBinaryDataBuffer as Buffer, BSLFileOpenMode as Mode, BSLFileAccess as Access,
    BSLPositionInStream as Origin)
from yadinassi.file_io import BSLBinaryData as Binary
from yadinassi.type_values import type_of
from yadinassi.values import BSLType


def digest(value):
    result = value.get_member('HashSum')
    return result if type(result) is Decimal else result._data


def reference(function, data):
    if function is Function.CRC32: return Decimal(zlib.crc32(data) & 0xffffffff)
    return hashlib.new(function.name.lower(), data, usedforsecurity=False).digest()


class DataHashingTests(unittest.TestCase):
    def test_all_algorithms_empty_incremental_and_snapshot(self):
        for function in Function:
            with self.subTest(function=function):
                value = Hash(function)
                self.assertEqual(digest(value), reference(function,b''))
                value.append('a'); snapshot = value.get_member('HashSum')
                value.append(Binary.from_bytes(b'bc'))
                self.assertEqual(digest(value), reference(function,b'abc'))
                self.assertEqual(digest(value), reference(function,b'abc'))
                self.assertEqual(snapshot if type(snapshot) is Decimal else snapshot._data,
                                 reference(function,b'a'))
                self.assertIs(value.get_member('HashFunction'),function)

    def test_known_ordinary_vectors(self):
        value = Hash(Function.CRC32); value.append('123456789')
        self.assertEqual(digest(value),Decimal(3421780262))
        value = Hash(Function.SHA256); value.append('abc')
        self.assertEqual(digest(value).hex(),
            'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

    def test_unicode_utf8_no_bom_or_implicit_normalization(self):
        for text in ('Я😀','e\u0301','é','a\0b','\r\n'):
            value=Hash(Function.SHA512); value.append(text)
            self.assertEqual(digest(value),reference(Function.SHA512,text.encode('utf-8')))

    def test_stream_count_cursor_eof_and_borrowed_lifetime(self):
        stream=Memory(Buffer.from_bytes(b'abcde')); stream.seek(1,Origin.BEGIN)
        value=Hash(Function.SHA256); value.append(stream,2)
        self.assertEqual(stream.current_position(),3)
        value.append(stream,0); self.assertEqual(stream.current_position(),3)
        value.append(stream,9); self.assertEqual(stream.current_position(),5)
        value.append(stream); self.assertEqual(stream.current_position(),5)
        self.assertEqual(digest(value),reference(Function.SHA256,b'bcde'))
        stream.seek(0,Origin.BEGIN); self.assertEqual(stream._read_bytes(1),b'a')

    def test_readonly_stream_and_independent_returned_binary(self):
        stream=Binary.from_bytes(b'abc').open_stream_for_read()
        value=Hash(Function.MD5); value.append(stream)
        first=value.get_member('HashSum'); second=value.get_member('HashSum')
        self.assertIsNot(first,second)
        self.assertEqual(first._data,second._data)
        self.assertEqual(stream.current_position(),3)

    def test_owned_file_and_file_stream_workflow(self):
        with tempfile.TemporaryDirectory(prefix='hashing-test-') as directory:
            path=Path(directory)/'owned.bin'; path.write_bytes(b'a\0bc')
            value=Hash(Function.CRC32); value.append('prefix'); value.append_file(str(path))
            self.assertEqual(digest(value),reference(Function.CRC32,b'prefixa\0bc'))
            stream=File(str(path),Mode.OPEN,Access.READ)
            try:
                value=Hash(Function.SHA1); value.append(stream,2)
                self.assertEqual(stream.current_position(),2)
                self.assertEqual(digest(value),reference(Function.SHA1,b'a\0'))
            finally: stream.close()
            self.assertEqual(path.read_bytes(),b'a\0bc')
            path.unlink()  # Also exercises owned AppendFile handle closure on Windows.

    def test_file_failure_preserves_hash_and_closes_owned_handle(self):
        with tempfile.TemporaryDirectory(prefix='hashing-test-') as directory:
            path=Path(directory)/'owned.bin'; path.write_bytes(b'abcd')
            value=Hash(Function.SHA256); value.append('x'); before=digest(value)
            with mock.patch.object(api,'MAX_TOTAL_BYTES',3), self.assertRaises(ValueError):
                value.append_file(str(path))
            self.assertEqual(digest(value),before); path.unlink()
            with self.assertRaises(ValueError): value.append_file(str(path))
            self.assertEqual(digest(value),before)

    def test_local_file_boundary_rejects_before_open(self):
        for path in ('https://example.invalid/a','\\\\host\\share\\a','//host/share/a',
                     '\\\\.\\pipe\\a','name:stream','NUL'):
            with mock.patch('yadinassi.binary_streams.os.open') as opened:
                with self.assertRaises((TypeError,ValueError)): Hash(Function.CRC32).append_file(path)
                opened.assert_not_called()

    def test_invalid_types_and_counts_preserve_state(self):
        value=Hash(Function.SHA256); before=digest(value)
        stream=Memory(Buffer.from_bytes(b'ab'))
        for count in (-1,True,'1',Decimal('1.5'),Decimal('NaN')):
            with self.assertRaises((TypeError,ValueError)): value.append(stream,count)
            self.assertEqual(stream.current_position(),0)
        for item in (None,True,1,Buffer(1),object()):
            with self.assertRaises(TypeError): value.append(item)
        for function in ('SHA256',None,1,True):
            with self.assertRaises(TypeError): Hash(function)
        with self.assertRaises(TypeError): value.append('a',1)
        self.assertEqual(digest(value),before)

    def test_exact_type_admission_and_readonly_properties(self):
        class Text(str): pass
        class BinaryChild(Binary): pass
        class StreamChild(Memory): pass
        value=Hash(Function.CRC32)
        for item in (Text('x'),BinaryChild.from_bytes(b'x'),StreamChild()):
            with self.assertRaises(TypeError): value.append(item)
        for name in ('HashSum','ХешФункция'):
            with self.assertRaises((TypeError,ValueError)): value.set_member(name,1)

    def test_budget_before_encoding_read_or_hash_mutation(self):
        value=Hash(Function.SHA256); value.append('a'); before=digest(value)
        stream=Memory(Buffer.from_bytes(b'bcde'))
        with mock.patch.object(api,'MAX_TOTAL_BYTES',4):
            with mock.patch.object(api,'_encoded') as encoded:
                with self.assertRaises(ValueError): value.append('😀')
                encoded.assert_not_called()
            with mock.patch.object(stream,'_read_bytes', wraps=stream._read_bytes) as read:
                with self.assertRaises(ValueError): value.append(stream)
                read.assert_not_called()
        self.assertEqual(stream.current_position(),0); self.assertEqual(digest(value),before)
        with mock.patch.object(api,'MAX_BYTES',3), self.assertRaises(ValueError):
            value.append(Binary.from_bytes(b'abcd'))
        self.assertEqual(digest(value),before)

    def test_read_or_digest_failure_rolls_back_cursor_and_hash(self):
        value=Hash(Function.SHA1); value.append('a'); before=digest(value)
        stream=Memory(Buffer.from_bytes(b'bc'))
        with mock.patch.object(value,'_updated',side_effect=ValueError('bounded failure')):
            with self.assertRaises(ValueError): value.append(stream)
        self.assertEqual(stream.current_position(),0); self.assertEqual(digest(value),before)
        stream.close()
        with self.assertRaises(ValueError): value.append(stream)
        self.assertEqual(digest(value),before)

    def test_bsl_aliases_types_optional_holes_and_codec_refusal(self):
        out=[]; Interpreter(out.append).execute('''H=New ХешированиеДанных(ХешФункция.CRC32);
H.Добавить("123456789"); Message(Format(H.ХешСумма,"ЧГ=0")); Message(H.ХешФункция=HashFunction.CRC32);
Message(TypeOf(H)=Type("DataHashing")); Message(TypeOf(HashFunction.SHA512)=Type("ХешФункция"));
S=New MemoryStream; H.Append(S,); Message(S.CurrentPosition());
Try H.HashSum=0; Except Message("readonly"); EndTry;
Try ValueToStringInternal(H); Except Message("no-codec"); EndTry;
Try New HashFunction; Except Message("no-constructor"); EndTry;''')
        self.assertEqual(out,['3421780262','Да','Да','Да','0','readonly','no-codec','no-constructor'])
        self.assertIs(type_of(Hash(Function.CRC32)),BSLType.DATA_HASHING)
        with self.assertRaises(ValueError): serialization.value_to_string_internal(Function.CRC32)

    def test_dynamic_new_and_unknown_factory_omission_guard(self):
        out=[]; Interpreter(out.append).execute('''A=New Array; A.Add(HashFunction.SHA256);
H=New("DataHashing",A); H.Append("abc"); Message(H.HashSum.Size());
Function Make() Message("called"); Return H; EndFunction
Try Make().Append(New MemoryStream,); Except Message("blocked"); EndTry;''')
        self.assertEqual(out,['32','blocked'])


if __name__=='__main__': unittest.main()
