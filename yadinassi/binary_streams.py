"""Bounded ordinary binary buffers and local memory/file streams.

Only explicit BSL types enter this API. No arbitrary Python streams, devices,
network paths, callbacks, or permission changes are accepted.
"""
from decimal import Decimal
from enum import Enum
import os
import stat

from .values import BSLObject
from .file_io import (_FileMethods, _methods, _file_errors, _path, MAX_BYTES,
                      BSLBinaryData)


def _number(value, maximum=MAX_BYTES, minimum=0):
    if (type(value) not in (int, Decimal) or (type(value) is Decimal and not value.is_finite())
            or not (minimum <= value <= maximum) or value != int(value)):
        raise ValueError('Двоичные данные: недопустимое целое число')
    return int(value)


class _Enum(Enum):
    def __str__(self): return self.value[-1]


class BSLByteOrder(_Enum):
    LITTLE = ('LittleEndian',)
    BIG = ('BigEndian',)


class BSLFileOpenMode(_Enum):
    OPEN = ('Open', 'Открыть')
    CREATE = ('Create', 'Создать')
    CREATE_NEW = ('CreateNew', 'СоздатьНовый')
    OPEN_OR_CREATE = ('OpenOrCreate', 'ОткрытьИлиСоздать')
    TRUNCATE = ('Truncate', 'Обрезать')
    APPEND = ('Append', 'Дописать')


class BSLFileAccess(_Enum):
    READ = ('Read', 'Чтение')
    WRITE = ('Write', 'Запись')
    READ_WRITE = ('ReadAndWrite', 'ЧтениеИЗапись')


class BSLPositionInStream(_Enum):
    BEGIN = ('Begin', 'Начало')
    CURRENT = ('Current', 'Текущая')
    END = ('End', 'Конец')


class _Namespace(BSLObject):
    def __init__(self, enum): self._enum = enum
    def get_member(self, name):
        for item in self._enum:
            if name.casefold() in (alias.casefold() for alias in item.value): return item
        return super().get_member(name)


BYTE_ORDERS = _Namespace(BSLByteOrder)
FILE_OPEN_MODES = _Namespace(BSLFileOpenMode)
FILE_ACCESSES = _Namespace(BSLFileAccess)
POSITIONS_IN_STREAM = _Namespace(BSLPositionInStream)


def _order(value, default=BSLByteOrder.LITTLE):
    if value is None: value = default
    if type(value) is not BSLByteOrder: raise TypeError('Ожидается ПорядокБайтов')
    return value


def _buffer(value):
    if type(value) is not BSLBinaryDataBuffer: raise TypeError('Ожидается БуферДвоичныхДанных')
    return value


class BSLBinaryDataBuffer(_FileMethods):
    def __init__(self, size, byte_order=None):
        self._order = _order(byte_order)
        self._view = memoryview(bytearray(_number(size)))
        self._readonly = False

    @classmethod
    def _from_view(cls, view, order, readonly=False):
        result = cls.__new__(cls)
        result._view, result._order, result._readonly = view, order, readonly
        return result

    @classmethod
    def from_bytes(cls, data, order=BSLByteOrder.LITTLE):
        if type(data) is not bytes or len(data) > MAX_BYTES: raise ValueError('Недопустимый буфер')
        return cls._from_view(memoryview(bytearray(data)), order)

    def __str__(self): return 'БуферДвоичныхДанных'
    def __iter__(self):
        for value in self._view: yield Decimal(value)
    def _range(self, position, count):
        start, size = _number(position), _number(count)
        if start + size > len(self._view): raise ValueError('Выход за границы буфера')
        return start, size
    def _writable(self):
        if self._readonly: raise ValueError('Буфер доступен только для чтения')
    def get_member(self, name):
        key = name.casefold()
        if key in ('size', 'размер'): return Decimal(len(self._view))
        if key in ('readonly', 'толькочтение'): return self._readonly
        if key in ('byteorder', 'порядокбайтов'): return self._order
        return super().get_member(name)
    def set_member(self, name, value):
        if name.casefold() in ('byteorder', 'порядокбайтов'):
            self._order = _order(value); return
        return super().set_member(name, value)
    def get(self, position):
        start, _ = self._range(position, 1)
        return Decimal(self._view[start])
    def set(self, position, value):
        self._writable(); start, _ = self._range(position, 1)
        self._view[start] = _number(value, 255)
    def get_index(self, position): return self.get(position)
    def set_index(self, position, value): return self.set(position, value)
    def set_readonly(self): self._readonly = True
    def get_slice(self, position, count=None):
        position = _number(position)
        start, size = self._range(position, len(self._view) - position if count is None else count)
        return self._from_view(self._view[start:start+size], self._order, self._readonly)
    def read(self, position, count):
        return self.from_bytes(bytes(self.get_slice(position, count)._view), self._order)
    def copy(self): return self.from_bytes(bytes(self._view), self._order)
    def reverse(self): return self.from_bytes(bytes(self._view)[::-1], self._order)
    def concat(self, other):
        other = _buffer(other)
        if len(self._view) + len(other._view) > MAX_BYTES: raise ValueError('Превышен предел ресурсов Yadinassi')
        return self.from_bytes(bytes(self._view) + bytes(other._view), self._order)
    def write(self, position, other, count=None):
        self._writable(); other = _buffer(other)
        count = len(other._view) if count is None else _number(count)
        start, count = self._range(position, count); other._range(0, count)
        self._view[start:start+count] = bytes(other._view[:count])
    def _read_int(self, position, width, order):
        start, _ = self._range(position, width)
        endian = 'little' if _order(order, self._order) is BSLByteOrder.LITTLE else 'big'
        return Decimal(int.from_bytes(self._view[start:start+width], endian))
    def _write_int(self, position, value, width, order):
        self._writable(); start, _ = self._range(position, width)
        value = _number(value, (1 << (8*width)) - 1)
        endian = 'little' if _order(order, self._order) is BSLByteOrder.LITTLE else 'big'
        self._view[start:start+width] = value.to_bytes(width, endian)
    def read16(self, position, order=None): return self._read_int(position, 2, order)
    def read32(self, position, order=None): return self._read_int(position, 4, order)
    def read64(self, position, order=None): return self._read_int(position, 8, order)
    def write16(self, position, value, order=None): self._write_int(position, value, 2, order)
    def write32(self, position, value, order=None): self._write_int(position, value, 4, order)
    def write64(self, position, value, order=None): self._write_int(position, value, 8, order)
    # !todo Split and bitwise bulk operations, DataReader/DataWriter and async
    # stream APIs are a separate ordinary workflow, not inferred here.
    _methods = _methods(('get', True, 'Get Получить'), ('set', False, 'Set Установить'),
        ('set_readonly', False, 'SetReadOnly УстановитьТолькоЧтение'),
        ('get_slice', True, 'GetSlice ПолучитьСрез'), ('read', True, 'Read Прочитать'),
        ('write', False, 'Write Записать'), ('copy', True, 'Copy Скопировать'),
        ('reverse', True, 'Reverse Перевернуть'), ('concat', True, 'Concat Соединить'),
        ('read16', True, 'ReadInt16 ПрочитатьЦелое16'), ('read32', True, 'ReadInt32 ПрочитатьЦелое32'),
        ('read64', True, 'ReadInt64 ПрочитатьЦелое64'),
        ('write16', False, 'WriteInt16 ЗаписатьЦелое16'), ('write32', False, 'WriteInt32 ЗаписатьЦелое32'),
        ('write64', False, 'WriteInt64 ЗаписатьЦелое64'))


class _State:
    def __init__(self, data=None, file=None):
        self.data = bytearray() if data is None else data
        self.file = file
        self.position = 0
        self.capacity = MAX_BYTES
        self.read = self.write = True
        self.buffer = None
    def __del__(self):
        if self.file is not None:
            self.file.close()


class BSLStream(_FileMethods):
    def __init__(self): raise TypeError('Поток не имеет конструктора')
    def __str__(self): return 'Поток'
    def _open(self):
        if self._closed: raise ValueError('Поток закрыт')
        if self._state.file is not None and self._state.file.closed: raise ValueError('Поток закрыт')
        return self._state
    def _canwrite(self):
        state = self._open()
        return state.write and not self._readonly and not (state.buffer is not None and state.buffer._readonly)
    def _readable(self):
        if not self._open().read: raise ValueError('Поток не поддерживает чтение')
    def _writable(self):
        if not self._canwrite(): raise ValueError('Поток не поддерживает запись')
    @_file_errors
    def _size(self):
        state = self._open()
        size = os.fstat(state.file.fileno()).st_size if state.file is not None else len(state.data)
        if size > MAX_BYTES: raise ValueError('Превышен предел ресурсов Yadinassi')
        return size
    def get_member(self, name):
        key = name.casefold()
        if key in ('canread', 'доступночтение'): return self._open().read
        if key in ('canwrite', 'доступназапись'):
            self._open()
            return True if getattr(self, '_reported_writable_view', False) else self._canwrite()
        if key in ('canseek', 'доступноизменениепозиции'): self._open(); return True
        return super().get_member(name)
    def close(self):
        if self._closed: return
        self._closed = True
        if self._state.file is not None: self._state.file.close()
    def size(self): return Decimal(self._size())
    def current_position(self): return Decimal(self._open().position)
    def seek(self, offset, origin=None):
        state = self._open(); offset = _number(offset, MAX_BYTES, -MAX_BYTES)
        # Native41255849371 case17: omitted origin raises despite EDT optional marker.
        if origin is None: raise TypeError('Перейти: требуется ПозицияВПотоке')
        if type(origin) is not BSLPositionInStream: raise TypeError('Ожидается ПозицияВПотоке')
        start = 0 if origin is BSLPositionInStream.BEGIN else (state.position if origin is BSLPositionInStream.CURRENT else self._size())
        position = _number(start + offset)
        state.position = position
        return Decimal(position)
    @_file_errors
    def set_size(self, size):
        self._writable(); state = self._state; size = _number(size, state.capacity)
        if state.file is not None: state.file.truncate(size)
        elif state.buffer is not None:
            # !todo Calibrate SetSize on fixed buffer-backed streams before
            # enabling logical-size changes independently of shared storage.
            if size != len(state.data): raise ValueError('Размер буферного потока фиксирован')
        else:
            if size < len(state.data): del state.data[size:]
            else: state.data.extend(b'\0' * (size - len(state.data)))
    @_file_errors
    def _read_bytes(self, count):
        self._readable(); state = self._state
        count = min(_number(count), max(0, self._size() - state.position))
        if state.file is not None:
            state.file.seek(state.position); data = state.file.read(count)
        else: data = bytes(state.data[state.position:state.position+count])
        state.position += len(data)
        return data
    def _write_check(self, count):
        self._writable(); state = self._state
        if state.position + count > state.capacity: raise ValueError('Превышена емкость потока')
        self._size()
    @_file_errors
    def _write_bytes(self, data):
        self._write_check(len(data)); state = self._state
        if state.file is not None:
            state.file.seek(state.position)
            written = state.file.write(data)
            if written != len(data): raise ValueError('Неполная запись потока')
        else:
            end = state.position + len(data)
            if end > len(state.data): state.data.extend(b'\0' * (end - len(state.data)))
            state.data[state.position:end] = data
        state.position += len(data)
    def read(self, buffer, position, count):
        self._readable(); buffer = _buffer(buffer); buffer._writable()
        start, count = buffer._range(position, count)
        data = self._read_bytes(count)
        buffer._view[start:start+len(data)] = data
        return Decimal(len(data))
    def write(self, buffer, position, count):
        buffer = _buffer(buffer); start, count = buffer._range(position, count)
        self._write_bytes(bytes(buffer._view[start:start+count]))
    def copy_to(self, target, count=None):
        if type(target) not in (BSLStream, BSLMemoryStream, BSLFileStream): raise TypeError('Ожидается Поток')
        self._readable()
        if target._state is self._state: raise ValueError('Копирование потока в себя недопустимо')
        available = max(0, self._size() - self._state.position)
        count = available if count is None else min(_number(count), available)
        target._write_check(count)
        data = self._read_bytes(count)
        target._write_bytes(data)
        return Decimal(len(data))
    @_file_errors
    def flush(self):
        state = self._open()
        if state.file is not None: state.file.flush()
    def get_readonly_stream(self):
        self._readable()
        result = BSLStream.__new__(BSLStream)
        result._state, result._readonly, result._closed = self._state, True, False
        return result
    # !todo Async/Begin methods, cross-process sharing/locking and platform
    # sparse-file details need separate calibration. Gap bytes are unspecified
    # by 1C; this bounded implementation zero-fills rather than leaking memory.
    _methods = _methods(('close', False, 'Close Закрыть'), ('size', True, 'Size Размер'),
        ('current_position', True, 'CurrentPosition ТекущаяПозиция'),
        ('seek', True, 'Seek Перейти'), ('set_size', False, 'SetSize УстановитьРазмер'),
        ('read', True, 'Read Прочитать'), ('write', False, 'Write Записать'),
        ('copy_to', True, 'CopyTo КопироватьВ'), ('flush', False, 'Flush СброситьБуферы'),
        ('get_readonly_stream', True, 'GetReadonlyStream ПолучитьПотокТолькоДляЧтения'))


class BSLMemoryStream(BSLStream):
    def __init__(self, source=None):
        self._closed = self._readonly = False
        if type(source) is BSLBinaryDataBuffer:
            self._state = _State(source._view)
            self._state.capacity = len(source._view)
            self._state.buffer = source
        else:
            if source is not None: _number(source)
            self._state = _State()
    def get_readonly_stream(self):
        self._readable()
        result = BSLStream.__new__(BSLStream)
        result._state = _State(self._state.data)
        result._state.capacity, result._state.buffer = self._state.capacity, self._state.buffer
        result._readonly, result._closed = True, False
        # Native41256517386 BF26: independent cursor, shared data, generic Stream;
        # CanWrite reports True but actual writes are rejected. Never use this
        # presentation quirk for _writable checks or any mutation authorization.
        result._reported_writable_view = True
        # !todo Source-close/view lifetime needs native calibration; child close
        # leaves the parent usable, as observed by BF27.
        return result
    def __str__(self): return 'ПотокВПамяти'
    def close_and_get_binary_data(self):
        self._open()
        data = BSLBinaryData.from_bytes(bytes(self._state.data))
        self.close()
        return data
    _methods = {**BSLStream._methods, **_methods(
        ('close_and_get_binary_data', True, 'CloseAndGetBinaryData ЗакрытьИПолучитьДвоичныеДанные'))}


def _stream_path(filename):
    path = _path(filename)
    # Reject network/device namespaces before opening: on Windows fstat comes
    # too late to prevent UNC access or a blocking named-pipe/device open.
    portable = path.replace('\\', '/')
    if portable.startswith('//') or portable.startswith('/??/'):
        raise ValueError('ФайловыйПоток: требуется локальный обычный файл')
    tail = portable[2:] if len(portable) > 1 and portable[1] == ':' and portable[0].isascii() and portable[0].isalpha() else portable
    if ':' in tail:
        raise ValueError('ФайловыйПоток: потоки имен устройств не поддерживаются')
    leaf = portable.rsplit('/', 1)[-1].rstrip(' .').split('.', 1)[0].rstrip(' .').upper()
    if (leaf in ('CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$')
            or (len(leaf) == 4 and leaf[:3] in ('COM', 'LPT') and leaf[3] in '123456789¹²³')):
        raise ValueError('ФайловыйПоток: имя устройства не поддерживается')
    return path


class BSLFileStream(BSLStream):
    @_file_errors
    def __init__(self, filename, mode, access=None, buffer_size=None):
        self._closed = True; self._readonly = False
        if type(mode) is not BSLFileOpenMode: raise TypeError('Ожидается РежимОткрытияФайла')
        if type(access) in (int, Decimal):
            if buffer_size is not None: raise TypeError('Неверные параметры ФайловыйПоток')
            buffer_size, access = access, None
        if buffer_size is not None: _number(buffer_size, MAX_BYTES, 1)
        if access is None: access = BSLFileAccess.READ_WRITE
        if type(access) is not BSLFileAccess: raise TypeError('Ожидается ДоступКФайлу')
        writing = access is not BSLFileAccess.READ
        if not writing and mode in (BSLFileOpenMode.CREATE, BSLFileOpenMode.CREATE_NEW, BSLFileOpenMode.TRUNCATE, BSLFileOpenMode.APPEND):
            raise ValueError('Режим открытия требует записи')
        flags = os.O_RDONLY if not writing else (os.O_WRONLY if access is BSLFileAccess.WRITE else os.O_RDWR)
        if mode in (BSLFileOpenMode.CREATE, BSLFileOpenMode.CREATE_NEW, BSLFileOpenMode.OPEN_OR_CREATE, BSLFileOpenMode.APPEND): flags |= os.O_CREAT
        if mode is BSLFileOpenMode.CREATE_NEW: flags |= os.O_EXCL
        flags |= getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
        self._filename = os.path.abspath(_stream_path(filename))
        fd = os.open(self._filename, flags, 0o666)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode): raise ValueError('Требуется обычный файл')
            if info.st_size > MAX_BYTES: raise ValueError('Превышен предел ресурсов Yadinassi')
            if mode in (BSLFileOpenMode.CREATE, BSLFileOpenMode.TRUNCATE): os.ftruncate(fd, 0)
            file = os.fdopen(fd, 'rb' if not writing else ('wb' if access is BSLFileAccess.WRITE else 'r+b'), buffering=0)
            fd = None
            self._state = _State(file=file)
            self._state.read = access is not BSLFileAccess.WRITE
            self._state.write = writing
            if mode is BSLFileOpenMode.APPEND: self._state.position = info.st_size
            self._closed = False
        finally:
            if fd is not None: os.close(fd)
    def __str__(self): return 'ФайловыйПоток'
    def get_member(self, name):
        if name.casefold() in ('filename', 'имяфайла'): return self._filename
        return super().get_member(name)


def buffer_to_binary_data(buffer): return BSLBinaryData.from_bytes(bytes(_buffer(buffer)._view))
def binary_data_to_buffer(data):
    if type(data) is not BSLBinaryData: raise TypeError('Ожидается ДвоичныеДанные')
    return BSLBinaryDataBuffer.from_bytes(data._data)

def binary_data_stream(data):
    if type(data) is not BSLBinaryData: raise TypeError('Ожидается ДвоичныеДанные')
    result = BSLStream.__new__(BSLStream)
    result._state = _State(bytearray(data._data))
    result._readonly, result._closed = True, False
    return result


FUNCTIONS = (
    ('ПолучитьДвоичныеДанныеИзБуфераДвоичныхДанных', buffer_to_binary_data, 'GetBinaryDataFromBinaryDataBuffer'),
    ('ПолучитьБуферДвоичныхДанныхИзДвоичныхДанных', binary_data_to_buffer, 'GetBinaryDataBufferFromBinaryData'),
)
