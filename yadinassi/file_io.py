"""Ordinary local file/text/binary workflows, with bounded regular-file I/O.

No network URLs, devices, streams, permission changes or implicit recursive
cleanup. Native calibration of ordinary defaults is a separate evidence gate.
"""
import base64
import codecs
from decimal import Decimal
from enum import Enum
import fnmatch
from functools import wraps
import locale
import os
import stat
import tempfile
import uuid

from .values import BSLObject, BSLArray, HostFunction

MAX_BYTES = 16 * 1024 * 1024
MAX_FILES = 100_000


def _file_errors(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except OSError as error:
            raise ValueError(f"Файлы: {error}") from error
    return call


def _text(value):
    if type(value) is not str:
        raise TypeError("Файлы: ожидается Строка")
    if len(value) > 16 * 1024 * 1024:
        raise ValueError("Файлы: превышен предел ресурсов Yadinassi")
    return value


def _path(value):
    value = _text(value)
    if not value or '\0' in value or '://' in value:
        raise ValueError("Файлы: требуется локальное имя файла")
    return value


def _bool(value, default=False):
    if value is None:
        return default
    if type(value) is not bool:
        raise TypeError("Файлы: ожидается Булево")
    return value


@_file_errors
def _open_regular(path, writing=False, append=False):
    # Inspect the opened descriptor before truncating, as in JSON file I/O.
    flags = os.O_WRONLY | os.O_CREAT if writing else os.O_RDONLY
    if append:
        flags |= os.O_APPEND
    flags |= getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    fd = os.open(_path(path), flags, 0o666)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Файлы: требуется обычный файл")
        if info.st_size > MAX_BYTES:
            raise ValueError("Файлы: превышен предел ресурсов Yadinassi")
        if writing and not append:
            os.ftruncate(fd, 0)
        stream = os.fdopen(fd, 'ab' if append else ('wb' if writing else 'rb'))
        fd = None
        return stream
    finally:
        if fd is not None:
            os.close(fd)


@_file_errors
def _read_bytes(path):
    with _open_regular(path) as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Файлы: превышен предел ресурсов Yadinassi")
    return data


@_file_errors
def _write_bytes(path, data):
    with _open_regular(path, writing=True) as stream:
        stream.write(data)


class BSLTextEncoding(Enum):
    UTF8 = 'UTF8'
    UTF16 = 'UTF16'
    ANSI = 'ANSI'
    OEM = 'OEM'
    SYSTEM = 'Системная'

    def __str__(self):
        return self.value


class BSLTextEncodings(BSLObject):
    def get_member(self, name):
        for value in BSLTextEncoding:
            if name.casefold() in (value.name.casefold(), value.value.casefold()):
                return value
        return super().get_member(name)


TEXT_ENCODINGS = BSLTextEncodings()


def _encoding(value=None, default='utf-8'):
    if value is None:
        return default
    if type(value) is BSLTextEncoding:
        # !todo ANSI/OEM locale tables beyond the supported Russian target;
        # do not silently substitute a codec for an unknown platform locale.
        return {BSLTextEncoding.UTF8: 'utf-8', BSLTextEncoding.UTF16: 'utf-16-le',
                BSLTextEncoding.ANSI: 'cp1251', BSLTextEncoding.OEM: 'cp866',
                BSLTextEncoding.SYSTEM: locale.getpreferredencoding(False)}[value]
    value = _text(value).casefold().replace('_', '-').replace('windows-', 'cp')
    aliases = {'utf8': 'utf-8', 'utf16': 'utf-16-le', 'utf-16': 'utf-16-le',
               'utf16le': 'utf-16-le', 'utf-16le': 'utf-16-le',
               'utf16be': 'utf-16-be', 'utf-16be': 'utf-16-be'}
    value = aliases.get(value, value)
    # !todo ICU-only/exotic encodings and malformed-byte substitution require
    # a later native matrix. Explicitly reject instead of guessing.
    allowed = {'utf-8', 'utf-16-le', 'utf-16-be', 'cp1251', 'cp866', 'ascii',
               'us-ascii', 'iso-8859-1', 'koi8-r'}
    if value not in allowed:
        raise ValueError("Файлы: кодировка пока не поддерживается")
    return codecs.lookup(value).name


_BOMS = ((codecs.BOM_UTF8, 'utf-8'), (codecs.BOM_UTF16_LE, 'utf-16-le'),
         (codecs.BOM_UTF16_BE, 'utf-16-be'))


def _encode(text, encoding, bom=False):
    data = _text(text).encode(encoding)
    if bom:
        data = next((mark for mark, enc in _BOMS if enc == encoding), b'') + data
    if len(data) > MAX_BYTES:
        raise ValueError("Файлы: превышен предел ресурсов Yadinassi")
    return data


def _decode(data, encoding=None, default='cp1251'):
    enc = _encoding(encoding, default)
    for mark, detected in _BOMS:
        if data.startswith(mark):
            if encoding is None:
                enc = detected
            if enc == detected:
                data = data[len(mark):]
            break
    return data.decode(enc)


class _FileMethods(BSLObject):
    _methods = {}
    def get_method(self, name):
        spec = self._methods.get(name.casefold())
        if spec is not None:
            method, returns_value = spec
            return HostFunction(name, getattr(self, method), returns_value=returns_value)
        return super().get_method(name)


def _methods(*specs):
    return {alias.casefold(): (method, returns) for method, returns, aliases in specs
            for alias in aliases.split()}


class BSLFile(_FileMethods):
    def __init__(self, filename):
        self._filename = _path(filename)
    def __str__(self):
        return self._filename
    def get_member(self, name):
        path = self._filename
        key = name.casefold()
        directory, filename = os.path.split(path.rstrip(os.sep))
        values = {'fullname': path, 'полноеимя': path, 'name': filename, 'имя': filename,
                  'basename': os.path.splitext(filename)[0], 'имябезрасширения': os.path.splitext(filename)[0],
                  'extension': os.path.splitext(filename)[1], 'расширение': os.path.splitext(filename)[1],
                  'path': directory + os.sep if directory else '', 'путь': directory + os.sep if directory else ''}
        if key in values:
            return values[key]
        return super().get_member(name)
    def exists(self): return os.path.exists(self._filename)
    def is_file(self): return os.path.isfile(self._filename)
    def is_directory(self): return os.path.isdir(self._filename)
    @_file_errors
    def size(self):
        with _open_regular(self._filename) as stream:
            return Decimal(os.fstat(stream.fileno()).st_size)
    # !todo Modification timestamps, hidden/read-only attributes, UNC/foreign
    # path lexing, symlink metadata and async methods need separate calibration.
    _methods = _methods(('exists', True, 'Exists Существует'),
                        ('is_file', True, 'IsFile ЭтоФайл'),
                        ('is_directory', True, 'IsDirectory ЭтоКаталог'),
                        ('size', True, 'Size Размер'))


class BSLBinaryData(_FileMethods):
    def __init__(self, filename): self._data = _read_bytes(filename)
    @classmethod
    def from_bytes(cls, data):
        if type(data) is not bytes or len(data) > MAX_BYTES:
            raise ValueError("ДвоичныеДанные: недопустимый буфер")
        obj = cls.__new__(cls); obj._data = data
        return obj
    def __str__(self): return 'ДвоичныеДанные'
    @_file_errors
    def size(self): return Decimal(len(self._data))
    @_file_errors
    def write(self, filename):
        from .binary_streams import BSLStream, BSLMemoryStream, BSLFileStream
        if type(filename) in (BSLStream, BSLMemoryStream, BSLFileStream):
            filename._write_bytes(self._data)
        else:
            _write_bytes(filename, self._data)
    def open_stream_for_read(self):
        from .binary_streams import binary_data_stream
        return binary_data_stream(self)
    _methods = _methods(('size', True, 'Size Размер'), ('write', False, 'Write Записать'),
                        ('open_stream_for_read', True, 'OpenStreamForRead ОткрытьПотокДляЧтения'))


def _binary(value):
    if type(value) is not BSLBinaryData:
        raise TypeError("Ожидаются ДвоичныеДанные")
    return value._data


# !todo Native line wrapping for long base64 records and permissive malformed
# input rules need later calibration; the current codec is strict RFC4648.
def base64_string(value): return base64.b64encode(_binary(value)).decode('ascii')
def base64_value(value):
    if type(value) is not str:
        raise TypeError("Base64: ожидается Строка")
    encoded_limit = 4 * ((MAX_BYTES + 2) // 3)
    if len(value) > 2 * encoded_limit:
        raise ValueError("Base64: превышен предел ресурсов Yadinassi")
    encoded = ''.join(value.split())
    if len(encoded) > encoded_limit:
        raise ValueError("Base64: превышен предел ресурсов Yadinassi")
    return BSLBinaryData.from_bytes(base64.b64decode(encoded, validate=True))
def binary_from_string(value, encoding=None, bom=None):
    return BSLBinaryData.from_bytes(_encode(value, _encoding(encoding), _bool(bom)))
def string_from_binary(value, encoding=None):
    return _decode(_binary(value), encoding, default='utf-8')


class BSLTextReader(_FileMethods):
    def __init__(self, filename=None, encoding=None, splitter=None, convertible=None, exclusive=None):
        self._text = None; self._position = 0
        if filename is not None:
            self.open(filename, encoding, splitter, convertible, exclusive)
    def __str__(self): return 'ЧтениеТекста'
    @_file_errors
    def open(self, filename, encoding=None, splitter=None, convertible=None, exclusive=None):
        _bool(exclusive, True)
        splitter = '\n' if splitter is None else _text(splitter)
        convertible = '\r\n' if convertible is None else _text(convertible)
        if not splitter:
            raise ValueError("ЧтениеТекста: пустой разделитель")
        text = _decode(_read_bytes(filename), encoding)
        if convertible:
            text = text.replace(convertible, '\n')
        self._text, self._position, self._splitter = text, 0, splitter
        # !todo OS-specific sharing/exclusive locks and live concurrently edited
        # streams. This bounded reader snapshots a regular file and closes it.
    @_file_errors
    def close(self): self._text = None; self._position = 0
    def _require_open(self):
        if self._text is None: raise ValueError("ЧтениеТекста: файл не открыт")
    def read(self, size=None):
        # !todo Native partial reads at a UTF-16 surrogate boundary; current
        # Python slicing preserves scalar characters rather than splitting one.
        self._require_open()
        if size is not None and (type(size) is not Decimal or not size.is_finite()
                                or size != size.to_integral_value() or size < 0):
            raise TypeError("ЧтениеТекста: ожидается целое неотрицательное число")
        if self._position == len(self._text): return None
        end = len(self._text) if size is None else self._position + int(min(size, MAX_BYTES))
        value = self._text[self._position:end]; self._position += len(value)
        return value
    def read_line(self, splitter=None):
        self._require_open()
        splitter = self._splitter if splitter is None else _text(splitter)
        if not splitter: raise ValueError("ЧтениеТекста: пустой разделитель")
        if self._position == len(self._text): return None
        end = self._text.find(splitter, self._position)
        if end < 0: return self.read()
        value = self._text[self._position:end]; self._position = end + len(splitter)
        return value
    _methods = _methods(('open', False, 'Open Открыть'), ('close', False, 'Close Закрыть'),
                        ('read', True, 'Read Прочитать'), ('read_line', True, 'ReadLine ПрочитатьСтроку'))


class BSLTextWriter(_FileMethods):
    def __init__(self, filename=None, encoding=None, splitter=None, append=None, convertible=None):
        self._stream = None
        if filename is not None: self.open(filename, encoding, splitter, append, convertible)
    def __str__(self): return 'ЗаписьТекста'
    @_file_errors
    def open(self, filename, encoding=None, splitter=None, append=None, convertible=None):
        enc = _encoding(encoding)
        splitter = '\n' if splitter is None else _text(splitter)
        convertible = '\r\n' if convertible is None else _text(convertible)
        append = _bool(append)
        _encode('', enc)  # validate before opening/truncating
        filename = _path(filename)
        # Close/flush the previous stream BEFORE truncating: reopening the same
        # file must not flush an old buffered BOM over the new document.
        self.close()
        stream = _open_regular(filename, writing=True, append=append)
        try:
            size = os.fstat(stream.fileno()).st_size
            if not size:
                mark = _encode('', enc, True)
                stream.write(mark); size = len(mark)
        except BaseException:
            stream.close(); raise
        self._stream, self._encoding, self._size = stream, enc, size
        self._splitter, self._convertible = splitter, convertible
    @_file_errors
    def close(self):
        stream, self._stream = self._stream, None
        if stream is not None: stream.close()
    def __del__(self):
        if getattr(self, '_stream', None) is not None:
            self._stream.close()
    @_file_errors
    def write(self, value):
        if self._stream is None: raise ValueError("ЗаписьТекста: файл не открыт")
        value = _text(value)
        # Normal text input LF is rendered with the configured file separator.
        if self._convertible:
            value = value.replace('\r\n', '\n')
            expanded = len(value) + value.count('\n') * (len(self._convertible) - 1)
            if expanded > MAX_BYTES:
                raise ValueError("ЗаписьТекста: превышен предел ресурсов Yadinassi")
            value = value.replace('\n', self._convertible)
        data = _encode(value, self._encoding)
        if self._size + len(data) > MAX_BYTES:
            raise ValueError("ЗаписьТекста: превышен предел ресурсов Yadinassi")
        self._stream.write(data); self._stream.flush(); self._size += len(data)
    def write_line(self, value, splitter=None):
        if self._stream is None: raise ValueError("ЗаписьТекста: файл не открыт")
        value = _text(value)
        splitter = self._splitter if splitter is None else _text(splitter)
        if len(value) + len(splitter) > MAX_BYTES:
            raise ValueError("ЗаписьТекста: превышен предел ресурсов Yadinassi")
        self.write(value + splitter)
    # !todo Stream overload/WriteBOM, cross-process sharing locks, exact
    # malformed-surrogate handling and append-to-incompatible-encoding files.
    _methods = _methods(('open', False, 'Open Открыть'), ('close', False, 'Close Закрыть'),
                        ('write', False, 'Write Записать'), ('write_line', False, 'WriteLine ЗаписатьСтроку'))


def temp_files_dir(): return tempfile.gettempdir() + os.sep

def temp_file_name(extension=None):
    extension = 'tmp' if extension is None else _text(extension).lstrip('.')
    if any(c in extension for c in '/\\\0') or len(extension) > 100:
        raise ValueError("Недопустимое расширение временного файла")
    # Names only, like 1C; no file is created and no unrelated cleanup occurs.
    # !todo Session/restart garbage collection is intentionally not implicit.
    return os.path.join(tempfile.gettempdir(), 'yadinassi-' + uuid.uuid4().hex + ('.' + extension if extension else ''))

@_file_errors
def create_directory(path): os.makedirs(_path(path), exist_ok=True)
@_file_errors
def copy_file(source, destination):
    data = _read_bytes(source)
    if os.path.exists(destination) and os.path.samefile(source, destination):
        raise ValueError("Источник и приемник совпадают")
    _write_bytes(destination, data)
@_file_errors
def move_file(source, destination):
    # Validate both names and ordinary source before the operation.
    source, destination = _path(source), _path(destination)
    with _open_regular(source): pass
    if os.path.exists(destination) and not os.path.isfile(destination):
        raise ValueError("Приемник должен быть обычным файлом")
    os.replace(source, destination)
    # !todo Cross-filesystem copy-and-unlink and URL schemes are not supported.

def _array(items):
    result = BSLArray(); result.items = items
    return result

@_file_errors
def find_files(path, mask=None, recursive=None):
    path = _path(path)
    if _bool(recursive):
        raise ValueError("Рекурсивный поиск пока не поддерживается")
    if mask is None:
        return _array([BSLFile(path)] if os.path.exists(path) else [])
    mask = _text(mask)
    if '/' in mask or '\\' in mask: raise ValueError("Маска не должна содержать путь")
    result = []
    with os.scandir(path) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_FILES: raise ValueError("Превышен предел числа файлов")
            if fnmatch.fnmatchcase(entry.name, mask): result.append(BSLFile(entry.path))
    return _array(result)

@_file_errors
def delete_files(path, mask=None):
    path = _path(path)
    if mask is not None:
        raise ValueError("Удаление по маске пока не поддерживается")
    # !todo Recursive directory/mask deletion requires a separately reviewed
    # no-follow traversal. Empty directory and exact file workflows are usable.
    if os.path.islink(path) or not os.path.isdir(path):
        try: os.unlink(path)
        except FileNotFoundError: pass
    else: os.rmdir(path)


FUNCTIONS = (
    ('КаталогВременныхФайлов', temp_files_dir, 'TempFilesDir', True),
    ('ПолучитьИмяВременногоФайла', temp_file_name, 'GetTempFileName', True),
    ('СоздатьКаталог', create_directory, 'CreateDirectory', False),
    ('КопироватьФайл', copy_file, 'CopyFile', False),
    ('ПереместитьФайл', move_file, 'MoveFile', False),
    ('НайтиФайлы', find_files, 'FindFiles', True),
    ('УдалитьФайлы', delete_files, 'DeleteFiles', False),
    ('Base64Строка', base64_string, 'Base64String', True),
    ('Base64Значение', base64_value, 'Base64Value', True),
    ('ПолучитьДвоичныеДанныеИзСтроки', binary_from_string, 'GetBinaryDataFromString', True),
    ('ПолучитьСтрокуИзДвоичныхДанных', string_from_binary, 'GetStringFromBinaryData', True),
)
