"""Bounded ordinary DataReader/DataWriter workflows; native calibration pending.

Existing local regular-file and stream authority only. No new host callbacks,
network, implicit external codecs or asynchronous workers. !todo: async/Begin,
ICU-only encodings, malformed byte substitution and exotic stream implementations.
"""
from decimal import Decimal

from .values import BSLArray, BSLFixedArray
from .file_io import (BSLBinaryData, BSLTextEncoding, _FileMethods, _methods,
                      _encoding, _BOMS, _bool, MAX_BYTES)
from .binary_streams import (BSLStream, BSLMemoryStream, BSLFileStream,
    BSLBinaryDataBuffer, BSLByteOrder, BSLFileOpenMode, BSLFileAccess,
    _number, _order, binary_data_stream)

MAX_PARTS = 4096
MAX_MARKERS = 64
MAX_MARKER_BYTES = 4096
MAX_SCAN = 64 * 1024 * 1024
_STREAMS = (BSLStream, BSLMemoryStream, BSLFileStream)
_MISSING = object()


def _string(value, maximum=MAX_BYTES):
    if type(value) is not str: raise TypeError('Данные: ожидается Строка')
    if len(value) > maximum: raise ValueError('Данные: превышен предел ресурсов')
    return value


def _encoded(value, codec):
    value = _string(value)
    # All admitted codecs use at most four bytes per Unicode scalar. Preflight
    # the precise UTF widths without allocating the encoded output first.
    if codec == 'utf-8':
        size = sum(1 if ord(c) < 128 else 2 if ord(c) < 2048 else 3 if ord(c) < 65536 else 4 for c in value)
    elif codec.startswith('utf-16'): size = 2 * sum(1 + (ord(c) > 65535) for c in value)
    else: size = len(value)
    if size > MAX_BYTES: raise ValueError('Данные: превышен предел ресурсов')
    return value.encode(codec)


def _converted(value, source, target):
    if not source: return value
    count = value.count(source)
    size = len(value) + count * (len(target) - len(source))
    if size > MAX_BYTES: raise ValueError('Данные: превышен предел ресурсов')
    return value.replace(source, target)


def _stream_alias(source):
    # Native DF26: distinct Stream identity, shared cursor/storage/close lifetime.
    # Flatten only this internal link so repeated wrappers cannot build recursion.
    source._open()
    result = BSLStream.__new__(BSLStream)
    result._state, result._readonly, result._closed = source._state, source._readonly, False
    result._data_io_source = getattr(source, '_data_io_source', source)
    return result


class BSLReadDataResult(_FileMethods):
    def __init__(self): raise TypeError('РезультатЧтенияДанных не имеет конструктора')
    @classmethod
    def _create(cls, data, marker=-1):
        if len(data) > MAX_BYTES: raise ValueError('Данные: превышен предел ресурсов')
        result = cls.__new__(cls)
        result._data, result._marker = bytes(data), marker
        return result
    def __str__(self): return 'РезультатЧтенияДанных'
    def get_member(self, name):
        key = name.casefold()
        if key in ('size', 'размер'): return Decimal(len(self._data))
        if key in ('markerfound', 'маркернайден'): return self._marker >= 0
        if key in ('markerindex', 'индексмаркера'): return Decimal(self._marker)
        return super().get_member(name)
    def get_binary_data(self): return BSLBinaryData.from_bytes(self._data)
    def get_buffer(self): return BSLBinaryDataBuffer.from_bytes(self._data)
    def open_stream(self): return binary_data_stream(self.get_binary_data())
    _methods = _methods(('get_binary_data', True, 'GetBinaryData ПолучитьДвоичныеДанные'),
        ('get_buffer', True, 'GetBinaryDataBuffer ПолучитьБуферДвоичныхДанных'),
        ('open_stream', True, 'OpenStreamForRead ОткрытьПотокДляЧтения'))


class _DataIO(_FileMethods):
    def _settings(self, encoding, order, splitter, convert, writing=False):
        self._encoding_value = BSLTextEncoding.UTF8 if encoding is None else encoding
        self._codec = _encoding(self._encoding_value)
        self._order = BSLByteOrder.LITTLE if order is None else order
        _order(self._order)
        self._splitter = ('\n' if writing else None) if splitter is None else _string(splitter, MAX_MARKER_BYTES)
        self._convert = '\r\n' if convert is None else _string(convert, MAX_MARKER_BYTES)
        self._closed = True
        self._owned = False
    def _open(self):
        if self._closed: raise ValueError('Чтение/запись данных закрыто')
        self._stream._open()
        return self._stream
    def _codec_for(self, value): return self._codec if value is None else _encoding(value)
    def close(self):
        if self._closed: return
        try:
            if type(self) is BSLDataWriter: self._stream.flush()
        finally:
            self._closed = True
            if self._owned: self._stream.close()
    def get_member(self, name):
        key = name.casefold(); self._open()
        if key in ('textencoding', 'кодировкатекста'): return self._encoding_value
        if key in ('byteorder', 'порядокбайтов'): return self._order
        if key in ('linesplitter', 'разделительстрок'): return self._splitter
        if key in ('convertedlinedelimiter', 'convertiblesplitteroflines', 'конвертируемыйразделительстрок'): return self._convert
        return super().get_member(name)
    def set_member(self, name, value):
        key = name.casefold(); self._open()
        if key in ('textencoding', 'кодировкатекста'):
            codec = _encoding(value); self._codec, self._encoding_value = codec, value; return
        if key in ('byteorder', 'порядокбайтов') and type(self) is BSLDataReader:
            self._order = _order(value); return
        if key in ('linesplitter', 'разделительстрок'):
            self._splitter = _string(value, MAX_MARKER_BYTES); return
        if key in ('convertedlinedelimiter', 'convertiblesplitteroflines', 'конвертируемыйразделительстрок'):
            self._convert = _string(value, MAX_MARKER_BYTES); return
        return super().set_member(name, value)


class BSLDataReader(_DataIO):
    def __init__(self, source, encoding=None, order=None, splitter=None, convert=None):
        self._settings(encoding, order, splitter, convert)
        if type(source) is str:
            source = BSLFileStream(source, BSLFileOpenMode.OPEN, BSLFileAccess.READ)
            self._owned = True
        elif type(source) is BSLBinaryData:
            source = binary_data_stream(source); self._owned = True
        elif type(source) not in _STREAMS: raise TypeError('Ожидается файл, поток или ДвоичныеДанные')
        try: source._readable()
        except BaseException:
            if self._owned: source.close()
            raise
        self._stream, self._closed = source, False
        self._completed = False
    def __str__(self): return 'ЧтениеДанных'
    def _available(self):
        stream = self._open(); stream._readable()
        return max(0, stream._size() - stream._state.position)
    def _peek(self):
        stream = self._open(); count = self._available(); position = stream._state.position
        try: return stream._read_bytes(count)
        finally: stream._state.position = position
    def _consume(self, count): self._stream._state.position += count
    def source_stream(self): return _stream_alias(self._open())
    def get_member(self, name):
        if name.casefold() in ('readcompleted', 'чтениезавершено'):
            self._open(); return self._completed
        return super().get_member(name)
    def read(self, count=None):
        available = self._available()
        requested = available + 1 if count is None else _number(count)
        data = self._stream._read_bytes(min(requested, available))
        self._completed = len(data) < requested
        return BSLReadDataResult._create(data)
    def read_buffer(self, buffer_or_count=None, position=_MISSING, count=_MISSING):
        if type(buffer_or_count) is BSLBinaryDataBuffer:
            if position is _MISSING or count is _MISSING: raise TypeError('Требуется позиция и количество')
            self._open()
            actual = self._stream.read(buffer_or_count, position, count)
            self._completed = actual < count
            return actual
        if position is not _MISSING or count is not _MISSING: raise TypeError('Неверные параметры чтения буфера')
        return self.read(buffer_or_count).get_buffer()
    def _integer(self, width, order=None):
        codec = 'little' if _order(order, self._order) is BSLByteOrder.LITTLE else 'big'; self._open()
        # Native41310612604 DF06: incomplete integer does not consume bytes.
        self._completed = self._available() < width
        if self._completed: return None
        return Decimal(int.from_bytes(self._stream._read_bytes(width), codec))
    def read_byte(self): return self._integer(1)
    def read16(self, order=None): return self._integer(2, order)
    def read32(self, order=None): return self._integer(4, order)
    def read64(self, order=None): return self._integer(8, order)
    def skip(self, count):
        count = min(_number(count), self._available()); self._consume(count)
        return self._stream.current_position()
    def _markers(self, value, encoding=None):
        codec = self._codec_for(encoding)
        if type(value) in (BSLArray, BSLFixedArray):
            if len(value.items) > MAX_MARKERS: raise ValueError('Слишком много маркеров')
            values = list(value)
        else: values = [value]
        if not values: raise ValueError('Требуется маркер')
        markers = []
        for item in values:
            if type(item) is BSLBinaryDataBuffer:
                if len(item._view) > MAX_MARKER_BYTES: raise ValueError('Маркер слишком велик')
                raw = bytes(item._view)
            else: raw = _encoded(_string(item, MAX_MARKER_BYTES), codec)
            if not raw or len(raw) > MAX_MARKER_BYTES: raise ValueError('Пустой или слишком большой маркер')
            markers.append(raw)
        return markers
    @staticmethod
    def _find(data, start, markers, budget):
        cost = (len(data) - start) * len(markers)
        if cost > budget: raise ValueError('Данные: превышен предел поиска')
        best = None
        for index, marker in enumerate(markers):
            position = data.find(marker, start)
            if position >= 0 and (best is None or position < best[0] or (position == best[0] and len(marker) > best[2])): best = (position, index, len(marker))
        return best, budget - cost
    def read_to(self, marker, encoding=None):
        markers = self._markers(marker, encoding); data = self._peek()
        found, _ = self._find(data, 0, markers, MAX_SCAN)
        if found is None: end, index, consumed = len(data), -1, len(data)
        else: end, index, size = found; consumed = end + size
        result = BSLReadDataResult._create(data[:end], index)
        self._consume(consumed); self._completed = found is None; return result
    def skip_to(self, marker, encoding=None): return Decimal(self.read_to(marker, encoding)._marker)
    def split_parts(self, size):
        size = _number(size, MAX_BYTES, 1); count = self._available()
        if (count + size - 1) // size > MAX_PARTS: raise ValueError('Слишком много частей')
        data = self._peek(); result = BSLArray()
        for start in range(0, len(data), size): result.add(BSLReadDataResult._create(data[start:start+size]))
        self._consume(len(data)); self._completed = True; return result
    def split(self, separator=None, encoding=None):
        markers = self._markers(self._splitter or '\n' if separator is None else separator, encoding)
        data = self._peek(); start = 0; budget = MAX_SCAN; result = BSLArray()
        while start <= len(data):
            if len(result.items) >= MAX_PARTS: raise ValueError('Слишком много частей')
            found, budget = self._find(data, start, markers, budget)
            end, index = (len(data), -1) if found is None else found[:2]
            result.add(BSLReadDataResult._create(data[start:end], index))
            if found is None: break
            start = end + found[2]
        self._consume(len(data)); self._completed = True; return result
    def _text_bytes(self, encoding):
        codec = self._codec_for(encoding); data = self._peek(); prefix = 0
        if self._stream._state.position == 0:
            for mark, bom_codec in _BOMS:
                if data.startswith(mark): prefix, codec = len(mark), bom_codec; break
        return data[prefix:], codec, prefix
    @staticmethod
    def _prefix_size(data, codec, count):
        if count is None: return len(data)
        if codec not in ('utf-8', 'utf-16-le', 'utf-16-be'): return min(count, len(data))
        position = 0; characters = 0
        while position < len(data) and characters < count:
            if codec == 'utf-8':
                lead = data[position]
                width = 1 if lead < 128 else 2 if 0xc2 <= lead <= 0xdf else 3 if 0xe0 <= lead <= 0xef else 4 if 0xf0 <= lead <= 0xf4 else 1
            else:
                unit = int.from_bytes(data[position:position+2], 'little' if codec.endswith('le') else 'big')
                width = 4 if 0xd800 <= unit <= 0xdbff else 2
            position = min(position + width, len(data)); characters += 2 if width == 4 else 1
        return position
    def read_chars(self, count=None, encoding=None):
        count = None if count is None else _number(count)
        data, codec, prefix = self._text_bytes(encoding)
        size = self._prefix_size(data, codec, count)
        # Decode only the selected prefix: later fields may use another encoding
        # or contain binary data. Strict errors leave the cursor unchanged.
        chosen = data[:size].decode(codec)
        units = sum(1 + (ord(char) > 65535) for char in chosen)
        # Native DF18: a one-unit boundary consumes the whole encoded scalar
        # but returns only its high surrogate; no pending low unit is retained.
        if count is not None and units > count:
            chosen = chosen[:-1] + chr(0xd800 + ((ord(chosen[-1]) - 0x10000) >> 10))
        result = _converted(chosen, self._convert, '\n')
        self._consume(size + prefix)
        self._completed = count is not None and units < count
        return result
    def read_line(self, encoding=None, splitter=None):
        data, codec, prefix = self._text_bytes(encoding)
        splitter = self._splitter if splitter is None else _string(splitter, MAX_MARKER_BYTES)
        markers = ('\r\n', '\r', '\n') if splitter is None else (splitter,)
        if not all(markers): raise ValueError('Пустой разделитель строки')
        raw_markers = [_encoded(marker, codec) for marker in markers]
        found, _ = self._find(data, 0, raw_markers, MAX_SCAN)
        end, consumed = (len(data), len(data)) if found is None else (found[0], found[0] + found[2])
        result = data[:end].decode(codec)
        self._consume(consumed + prefix); self._completed = found is None
        return result
    def copy_to(self, target, count=None):
        if type(target) is BSLDataWriter: target = target._open()
        self._open(); return self._stream.copy_to(target, count)
    _methods = _methods(('close', False, 'Close Закрыть'), ('source_stream', True, 'SourceStream ИсходныйПоток'),
        ('read', True, 'Read Прочитать'), ('read_buffer', True, 'ReadIntoBinaryDataBuffer ПрочитатьВБуферДвоичныхДанных'),
        ('read_byte', True, 'ReadByte ПрочитатьБайт'), ('read16', True, 'ReadInt16 ПрочитатьЦелое16'),
        ('read32', True, 'ReadInt32 ПрочитатьЦелое32'), ('read64', True, 'ReadInt64 ПрочитатьЦелое64'),
        ('skip', True, 'Skip Пропустить'), ('skip_to', True, 'SkipTo ПропуститьДо'),
        ('read_to', True, 'ReadTo ПрочитатьДо'), ('split', True, 'Split Разделить'),
        ('split_parts', True, 'SplitInPartsOf РазделитьНаЧастиПо'),
        ('read_chars', True, 'ReadChars ПрочитатьСимволы'), ('read_line', True, 'ReadLine ПрочитатьСтроку'),
        ('copy_to', True, 'CopyTo КопироватьВ'))


class BSLDataWriter(_DataIO):
    def __init__(self, target, encoding=None, order=None, splitter=None, *tail):
        file = type(target) is str
        if len(tail) > (3 if file else 2): raise TypeError('Неверные параметры ЗаписьДанных')
        values = (*tail, None, None, None)
        append, convert, bom = (values[0], values[1], values[2]) if file else (False, values[0], values[1])
        append = _bool(append); bom = _bool(bom)
        self._settings(encoding, order, splitter, convert, writing=True)
        mark = next((mark for mark, enc in _BOMS if enc == self._codec), b'') if bom else b''
        if file:
            target = BSLFileStream(target, BSLFileOpenMode.APPEND if append else BSLFileOpenMode.OPEN_OR_CREATE, BSLFileAccess.WRITE)
            self._owned = True
        elif type(target) not in _STREAMS: raise TypeError('Ожидается имя файла или Поток')
        try:
            target._writable()
            if mark and target._state.position == 0: target._write_bytes(mark)
        except BaseException:
            if self._owned: target.close()
            raise
        self._stream, self._closed = target, False
    def __str__(self): return 'ЗаписьДанных'
    def target_stream(self): return _stream_alias(self._open())
    def flush(self): self._open().flush()
    def _integer(self, value, width, order=None):
        codec = 'little' if _order(order, self._order) is BSLByteOrder.LITTLE else 'big'; value = _number(value, (1 << (8 * width)) - 1)
        self._open()._write_bytes(value.to_bytes(width, codec))
    def write_byte(self, value): self._integer(value, 1)
    def write16(self, value, order=None): self._integer(value, 2, order)
    def write32(self, value, order=None): self._integer(value, 4, order)
    def write64(self, value, order=None): self._integer(value, 8, order)
    def write(self, value):
        if type(value) not in (BSLBinaryData, BSLReadDataResult): raise TypeError('Ожидается ДвоичныеДанные или РезультатЧтенияДанных')
        self._open()._write_bytes(value._data)
    def write_buffer(self, buffer, position=None, count=None):
        if type(buffer) is not BSLBinaryDataBuffer: raise TypeError('Ожидается БуферДвоичныхДанных')
        if (position is None) != (count is None): raise TypeError('Требуются позиция и количество')
        position, count = (0, len(buffer._view)) if position is None else (position, count)
        self._open().write(buffer, position, count)
    def write_chars(self, text, encoding=None):
        text = _converted(_string(text), '\n', self._convert)
        data = _encoded(text, self._codec_for(encoding)); self._open()._write_bytes(data)
    def write_line(self, text, encoding=None, splitter=None):
        text = _string(text); splitter = self._splitter if splitter is None else _string(splitter, MAX_MARKER_BYTES)
        if len(text) + len(splitter) > MAX_BYTES: raise ValueError('Данные: превышен предел ресурсов')
        data = _encoded(text + splitter, self._codec_for(encoding)); self._open()._write_bytes(data)
    _methods = _methods(('close', False, 'Close Закрыть'), ('flush', False, 'Flush СброситьБуферы'),
        ('target_stream', True, 'TargetStream ЦелевойПоток'), ('write', False, 'Write Записать'),
        ('write_byte', False, 'WriteByte ЗаписатьБайт'), ('write16', False, 'WriteInt16 ЗаписатьЦелое16'),
        ('write32', False, 'WriteInt32 ЗаписатьЦелое32'), ('write64', False, 'WriteInt64 ЗаписатьЦелое64'),
        ('write_buffer', False, 'WriteBinaryDataBuffer ЗаписатьБуферДвоичныхДанных'),
        ('write_chars', False, 'WriteChars ЗаписатьСимволы'), ('write_line', False, 'WriteLine ЗаписатьСтроку'))
