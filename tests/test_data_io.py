"""Ordinary owned data-I/O workflows and deterministic bounded admission tests."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter, serialization
from yadinassi import data_io as api
from yadinassi.data_io import BSLDataReader as Reader, BSLDataWriter as Writer, BSLReadDataResult as Result
from yadinassi.binary_streams import (BSLMemoryStream as Memory, BSLBinaryDataBuffer as Buffer,
    BSLByteOrder as Order, BSLPositionInStream as Origin)
from yadinassi.file_io import BSLBinaryData as Binary
from yadinassi.values import BSLArray, BSLType
from yadinassi.type_values import type_of


def reader(data): return Reader(Binary.from_bytes(data))
def array(*values):
    result = BSLArray()
    for value in values: result.add(value)
    return result


class DataIOTests(unittest.TestCase):
    def test_unsigned_integer_roundtrip_all_widths_and_orders(self):
        stream = Memory(); writer = Writer(stream)
        for order in (Order.LITTLE, Order.BIG):
            for width in (2,4,8): getattr(writer, 'write'+str(width*8))((1<<(width*8))-1, order)
        writer.write_byte(255); writer.close(); stream.seek(0, Origin.BEGIN)
        source = Reader(stream)
        for order in (Order.LITTLE, Order.BIG):
            for width in (2,4,8): self.assertEqual(getattr(source, 'read'+str(width*8))(order), (1<<(width*8))-1)
        self.assertEqual(source.read_byte(), 255)
        self.assertFalse(source.get_member('ReadCompleted'))
        self.assertIsNone(source.read_byte()); self.assertTrue(source.get_member('ReadCompleted'))

    def test_read_result_copy_and_readonly_stream(self):
        source = reader(b'abc'); result = source.read(2); source.close()
        self.assertEqual(result.get_member('Size'), 2)
        self.assertFalse(result.get_member('MarkerFound')); self.assertEqual(result.get_member('MarkerIndex'), -1)
        buffer = result.get_buffer(); buffer.set(0, 90)
        self.assertEqual(result.get_binary_data()._data,b'ab')
        stream = result.open_stream()
        self.assertEqual(stream._read_bytes(1),b'a')
        with self.assertRaises(ValueError): stream._write_bytes(b'z')
        self.assertEqual(result.open_stream()._read_bytes(2),b'ab')
        with self.assertRaises((ValueError,TypeError)): result.set_member('Size',0)

    def test_buffer_overloads_preflight_and_count(self):
        source = reader(b'abcd'); target = Buffer(5)
        self.assertEqual(source.read_buffer(target,1,2),2)
        self.assertEqual(bytes(target._view),b'\0ab\0\0')
        self.assertEqual(bytes(source.read_buffer(2)._view),b'cd')
        source = reader(b'ab'); readonly = Buffer(2); readonly.set_readonly()
        with self.assertRaises(ValueError): source.read_buffer(readonly,0,2)
        self.assertEqual(source.source_stream().current_position(),0)
        with self.assertRaises(ValueError): source.read_buffer(target,4,2)
        self.assertEqual(source.source_stream().current_position(),0)

    def test_marker_results_and_remaining_cursor(self):
        source = reader(b'aa::bb|cc'); marker = array('::',Buffer.from_bytes(b'|'))
        result = source.read_to(marker)
        self.assertEqual((result._data,result._marker), (b'aa',0))
        self.assertEqual(source.skip_to(marker),1)
        self.assertEqual(source.read()._data,b'cc')
        self.assertEqual(reader(b'abc').skip_to('!'),-1)
        self.assertEqual(reader(b'abc').read_to('!')._data,b'abc')

    def test_split_parts_and_delimiters(self):
        parts = reader(b'a|bb|').split('|')
        self.assertEqual([x._data for x in parts],[b'a',b'bb',b''])
        self.assertEqual([x._marker for x in parts],[0,0,-1])
        self.assertEqual([x._data for x in reader(b'abcde').split_parts(2)],[b'ab',b'cd',b'e'])
        self.assertEqual(reader(b'').split_parts(2).items,[])

    def test_partition_limits_leave_source_position_unchanged(self):
        source = reader(b'a|b|c')
        with mock.patch.object(api,'MAX_PARTS',2),self.assertRaises(ValueError): source.split('|')
        self.assertEqual(source.source_stream().current_position(),0)
        with mock.patch.object(api,'MAX_PARTS',2),self.assertRaises(ValueError): source.split_parts(1)
        self.assertEqual(source.source_stream().current_position(),0)
        with mock.patch.object(api,'MAX_SCAN',3),self.assertRaises(ValueError): source.read_to('|')
        self.assertEqual(source.source_stream().current_position(),0)

    def test_markers_are_closed_bounded_types(self):
        source = reader(b'abc')
        for value in ('',array(),object(),Buffer(0)):
            with self.assertRaises((ValueError,TypeError)): source.read_to(value)
        with mock.patch.object(api,'MAX_MARKERS',1),self.assertRaises(ValueError): source.read_to(array('a','b'))
        self.assertEqual(source.source_stream().current_position(),0)

    def test_text_encoding_bom_and_line_conversion(self):
        stream = Memory(); writer = Writer(stream,'UTF-16BE',None,'!', '\r\n',True)
        writer.write_chars('Ж\n'); writer.write_line('Ю'); writer.close()
        self.assertTrue(bytes(stream._state.data).startswith(b'\xfe\xff'))
        stream.seek(0,Origin.BEGIN); source = Reader(stream,'UTF-16BE',None,'!')
        self.assertEqual(source.read_chars(3),'Ж\n')
        self.assertEqual(source.read_line(),'Ю')
        self.assertEqual(source.read_line(),'')

    def test_utf8_chars_and_default_line_splitters(self):
        source = reader('Ж😀X'.encode())
        self.assertEqual(source.read_chars(1),'Ж')
        self.assertEqual(source.read_chars(1),'😀')
        self.assertEqual(source.read_chars(),'X')
        source = reader(b'a\r\nb\nc\rd')
        self.assertEqual([source.read_line() for _ in range(4)],['a','b','c','d'])

    def test_mixed_encoding_and_binary_fields_do_not_decode_ahead(self):
        source = reader('Ж'.encode('utf-16-le') + b'x\xff')
        self.assertEqual(source.read_chars(1, 'UTF-16LE'), 'Ж')
        self.assertEqual(source.read_chars(1, 'UTF-8'), 'x')
        self.assertEqual(source.read_byte(), 255)
        source = reader(b'hello\n\xff')
        self.assertEqual(source.read_line(), 'hello')
        self.assertEqual(source.read_byte(), 255)

    def test_measured_partial_integer_longest_marker_and_text_completion(self):
        source = reader(b'x')
        self.assertIsNone(source.read16())
        self.assertEqual(source.source_stream().current_position(), 0)
        self.assertTrue(source.get_member('ReadCompleted'))
        self.assertEqual(source.read_byte(), 120)
        source = reader(b'a::b')
        result = source.read_to(array(':', '::'))
        self.assertEqual((result._data, result._marker, source.read_chars()), (b'a', 1, 'b'))
        source = reader(b'ab')
        self.assertEqual(source.read_chars(), 'ab')
        self.assertFalse(source.get_member('ReadCompleted'))

    def test_measured_file_writer_preserves_unwritten_suffix(self):
        with tempfile.TemporaryDirectory(prefix='data-io-owned-') as tmp:
            path = Path(tmp)/'packet.bin'; path.write_bytes(b'ab')
            writer = Writer(str(path)); writer.write_chars('x'); writer.close()
            self.assertEqual(path.read_bytes(), b'xb')

    def test_settings_mutability(self):
        source = reader(b'\x01\x02')
        source.set_member('ByteOrder',Order.BIG); self.assertEqual(source.read16(),258)
        source.set_member('TextEncoding','cp1251'); self.assertEqual(source.get_member('TextEncoding'),'cp1251')
        source.set_member('LineSplitter','!'); source.set_member('ConvertedLineDelimiter','~')
        writer = Writer(Memory())
        with self.assertRaises((ValueError,TypeError)): writer.set_member('ByteOrder',Order.BIG)
        with self.assertRaises(ValueError): source.set_member('TextEncoding','unknown-codec')
        self.assertEqual(source.get_member('TextEncoding'),'cp1251')

    def test_owned_file_create_append_close_and_binary_transfer(self):
        with tempfile.TemporaryDirectory(prefix='data-io-owned-') as tmp:
            path=Path(tmp)/'packet.bin'
            writer=Writer(str(path)); writer.write_byte(1); writer.write(Binary.from_bytes(b'ab')); writer.close()
            writer=Writer(str(path),None,None,None,True); writer.write_byte(2); writer.close()
            source=Reader(str(path)); self.assertEqual(source.read()._data,b'\x01ab\x02'); internal=source.source_stream(); source.close()
            with self.assertRaises(ValueError): internal.current_position()
            self.assertEqual(path.read_bytes(),b'\x01ab\x02')

    def test_invalid_constructor_settings_do_not_truncate_file(self):
        with tempfile.TemporaryDirectory(prefix='data-io-owned-') as tmp:
            path=Path(tmp)/'keep.bin'; path.write_bytes(b'keep')
            for kwargs in ({'encoding':'unknown'}, {'order':'big'}, {'splitter':1}):
                with self.assertRaises((ValueError,TypeError)): Writer(str(path),**kwargs)
                self.assertEqual(path.read_bytes(),b'keep')

    def test_borrowed_stream_lifecycle_and_reader_writer_copy(self):
        source_stream=Memory(Buffer.from_bytes(b'abc')); source=Reader(source_stream)
        target_stream=Memory(); target=Writer(target_stream)
        self.assertEqual(source.copy_to(target,2),2)
        target.write(source.read()); target.flush(); source.close(); target.close()
        self.assertEqual(bytes(target_stream._state.data),b'abc')
        self.assertEqual(source_stream.current_position(),3)
        with self.assertRaises(ValueError): source.read()
        with self.assertRaises(ValueError): target.write_byte(2)

    def test_write_failure_does_not_advance_source(self):
        source=reader(b'ab'); target=Memory(Buffer(1)); writer=Writer(target)
        with self.assertRaises(ValueError): source.copy_to(writer)
        self.assertEqual(source.source_stream().current_position(),0)
        self.assertEqual(bytes(target._state.data),b'\0')

    def test_write_ranges_and_text_budget_before_mutation(self):
        target=Memory(); writer=Writer(target)
        for value in (-1,256,True,'1',Decimal('NaN'),Decimal('1.1')):
            with self.assertRaises((ValueError,TypeError)): writer.write_byte(value)
        with mock.patch.object(api,'MAX_BYTES',3),self.assertRaises(ValueError): writer.write_chars('😀')
        with mock.patch.object(api,'MAX_BYTES',3),self.assertRaises(ValueError): writer.write_chars('\n\n')
        self.assertEqual(target.current_position(),0)
        writer.write_buffer(Buffer.from_bytes(b'abcd'),1,2)
        self.assertEqual(bytes(target._state.data),b'bc')

    def test_optional_holes_do_not_evaluate_unknown_factory_receivers(self):
        out=[]; Interpreter(out.append).execute('''S=New MemoryStream; W=New DataWriter(S);
Function Make() Message("factory-called"); Return W; EndFunction
Try Make().WriteLine("x",,"!"); Except Message("rejected"); EndTry;
Message(S.Size());''')
        self.assertEqual(out,['rejected','0'])

    def test_types_codecs_optional_dispatch_and_readonly_result(self):
        out=[]; Interpreter(out.append).execute('''S=New MemoryStream; W=New DataWriter(S,,ByteOrder.BigEndian);
W.WriteInt16(258); W.WriteLine("x",,"!"); W.Close(); S.Seek(0,PositionInStream.Begin);
R=New DataReader(S,,ByteOrder.BigEndian); Message(R.ReadInt16()); Q=R.Read();
Message(TypeOf(R)=Type("DataReader")); Message(TypeOf(W)=Type("ЗаписьДанных"));
Message(TypeOf(Q)=Type("ReadDataResult")); Message(Q.Size);
Try New ReadDataResult; Except Message("no-constructor"); EndTry;
Try ValueToStringInternal(Q); Except Message("no-codec"); EndTry;''')
        self.assertEqual(out,['258','Да','Да','Да','2','no-constructor','no-codec'])
        self.assertIs(type_of(reader(b'a')),BSLType.DATA_READER)
        with self.assertRaises(ValueError): serialization.value_to_string_internal(reader(b'a'))

if __name__=='__main__': unittest.main()
