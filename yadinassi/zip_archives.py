"""Bounded ordinary ZIP workflows. No encryption, links, devices or permissions.

Archive input and all expanded content are validated before extraction writes.
Only explicit BSL streams are accepted; no arbitrary host file-like adapters.
"""
from datetime import datetime
from decimal import Decimal
import fnmatch
from functools import wraps
import io
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import secrets
from contextlib import contextmanager
import zipfile
import zlib
import unicodedata

from .binary_streams import (BSLStream, BSLMemoryStream, BSLFileStream, _Enum,
                             _Namespace, _number, _stream_path)
from .file_io import _FileMethods, _methods, _text, MAX_BYTES, BSLBinaryData
from .dates import _date_from_datetime as from_datetime

MAX_ENTRIES = 1024
MAX_NAME = 4096
_STREAMS = (BSLStream, BSLMemoryStream, BSLFileStream)


def _zip_errors(function):
    @wraps(function)
    def call(*args, **kwargs):
        try: return function(*args, **kwargs)
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, UnicodeError, zlib.error, RuntimeError) as error:
            raise ValueError('ZIP: ошибка архива или файловой операции') from error
    return call


class BSLZIPCompressionMethod(_Enum):
    COPY = ('Copy', 'Копирование')
    DEFLATE = ('Deflate', 'Сжатие')
    BZIP2 = ('BZIP2',)


class BSLZIPCompressionLevel(_Enum):
    MINIMUM = ('Minimum', 'Минимальный')
    OPTIMAL = ('Optimal', 'Оптимальный')
    MAXIMUM = ('Maximum', 'Максимальный')


class BSLZIPStorePathMode(_Enum):
    FLAT = ('DontStorePath', 'НеСохранятьПути')
    RELATIVE = ('StoreRelativePath', 'СохранятьОтносительныеПути')
    FULL = ('StoreFullPath', 'СохранятьПолныеПути')


class BSLZIPSubDirProcessingMode(_Enum):
    NO = ('DontProcess', 'НеОбрабатывать')
    RECURSIVE = ('ProcessRecursively', 'ОбрабатыватьРекурсивно')


class BSLZIPRestoreFilePathsMode(_Enum):
    RESTORE = ('Restore', 'Восстанавливать')
    FLAT = ('DontRestore', 'НеВосстанавливать')


class BSLZIPEncryptionMethod(_Enum):
    ZIP20 = ('Zip20',)
    AES128 = ('AES128',)
    AES192 = ('AES192',)
    AES256 = ('AES256',)


class BSLFileNamesEncodingInZipFile(_Enum):
    AUTO = ('Auto', 'Авто')
    UTF8 = ('UTF8',)
    OS_UTF8 = ('OSEncodingWithUTF8', 'КодировкаОСДополнительноUTF8')


def _enum(value, default):
    if value is None: return default
    if type(value) is not type(default): raise TypeError('ZIP: недопустимое перечисление')
    return value


def _password(value):
    if value is not None and _text(value):
        raise ValueError('ZIP: шифрование не поддерживается')


def _name(value):
    value = _text(value).replace('\\', '/')
    if not value or len(value) > MAX_NAME or value.startswith('/') or '\0' in value:
        raise ValueError('ZIP: небезопасное имя элемента')
    parts = value.rstrip('/').split('/')
    for part in parts:
        if part in ('', '.', '..') or part != part.rstrip(' .') or any(c in part for c in ':<>|?*"'):
            raise ValueError('ZIP: небезопасное имя элемента')
        _stream_path(part)  # Reject DOS device names before filesystem access.
    return '/'.join(parts) + ('/' if value.endswith('/') else '')


def _darwin_system_path(path):
    # macOS ordinary temp paths use these two OS-owned aliases. Resolve no
    # arbitrary user ancestor and retain all subsequent no-follow checks.
    if sys.platform == 'darwin':
        for prefix, target in (('/var', '/private/var'), ('/tmp', '/private/tmp')):
            if str(path) == prefix or str(path).startswith(prefix + '/'):
                if os.path.realpath(prefix) != target:
                    raise ValueError('ZIP: неожиданное системное сопоставление пути')
                return Path(target) / path.relative_to(prefix)
    return path


def _host_path(value):
    value = _stream_path(value)
    if len(value) > MAX_NAME: raise ValueError('ZIP: слишком длинный путь')
    path = _darwin_system_path(Path(os.path.abspath(value)))
    # Reject symlink/reparse traversal, including ancestors. No network/device
    # path reaches even stat/open through this API.
    for part in (path, *path.parents):
        try: info = part.lstat()
        except FileNotFoundError: continue
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError('ZIP: компонент пути не является каталогом')
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('ZIP: символические ссылки не поддерживаются')
    return path


@contextmanager
def _directory(path, create=False):
    path = _host_path(str(path))
    anchored = os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')
    if not anchored:
        # !todo Windows concurrent hostile reparse-point swaps need an anchored
        # handle backend. Static reparse/symlink/device checks remain mandatory;
        # this ordinary local-file API is not a hostile-writer filesystem sandbox.
        if create: path.mkdir(parents=True, exist_ok=True)
        _host_path(str(path))
        yield None
        return
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            if create:
                try: os.mkdir(part, dir_fd=fd)
                except FileExistsError: pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        yield fd
    finally: os.close(fd)


def _read_file(path):
    path = _host_path(str(path))
    with _directory(path.parent) as parent:
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
        fd = os.open(path if parent is None else path.name, flags, **({} if parent is None else {'dir_fd': parent}))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError('ZIP: требуется ограниченный обычный файл')
            data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES: raise ValueError('ZIP: превышен предел ресурсов')
    return data, info


def _write_file(path, data):
    path = _host_path(str(path))
    if path.exists() and not path.is_file(): raise ValueError('ZIP: требуется обычный файл')
    # Stage the bounded result, then replace only the selected file. On POSIX
    # all operations are relative to a no-follow directory descriptor.
    with _directory(path.parent) as parent:
        if parent is None:
            fd, temporary = tempfile.mkstemp(prefix='.yadinassi-zip-', dir=path.parent)
        else:
            temporary = '.yadinassi-zip-' + secrets.token_hex(16)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, 'wb') as stream: stream.write(data)
            _host_path(str(path))
            if parent is None: os.replace(temporary, path)
            else: os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            try:
                if parent is None: os.unlink(temporary)
                else: os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError: pass


def _unique_names(names):
    seen = set()
    files = set()
    for name in names:
        key = unicodedata.normalize('NFC', name.rstrip('/')).casefold()
        if key in seen: raise ValueError('ZIP: коллизия имен элементов')
        seen.add(key)
        if not name.endswith('/'): files.add(key)
    for key in seen:
        parts = key.split('/')
        if any('/'.join(parts[:i]) in files for i in range(1, len(parts))):
            raise ValueError('ZIP: коллизия файла и каталога')


def _preflight_zip(raw):
    # Bound central-directory work before ZipFile constructs its entry objects.
    end = raw.rfind(b'PK\x05\x06', max(0, len(raw) - 65557))
    if end < 0 or end + 22 > len(raw): raise ValueError('ZIP: поврежденный архив')
    disk, start_disk, disk_count, count, size, offset, comment = struct.unpack_from('<4H2IH', raw, end + 4)
    if disk or start_disk or disk_count != count or count > MAX_ENTRIES or end + 22 + comment != len(raw):
        raise ValueError('ZIP: multipart/число элементов не поддерживается')
    if offset + size != end: raise ValueError('ZIP: ZIP64/нестандартный каталог не поддерживается')
    cursor = offset; observed = 0
    while cursor < end:
        if raw[cursor:cursor+4] != b'PK\x01\x02' or cursor + 46 > end: raise ValueError('ZIP: поврежденный каталог')
        name, extra, note, start = struct.unpack_from('<4H', raw, cursor + 28)
        if start: raise ValueError('ZIP: multipart не поддерживается')
        cursor += 46 + name + extra + note; observed += 1
        if cursor > end or observed > MAX_ENTRIES: raise ValueError('ZIP: превышен предел каталога')
    if observed != count: raise ValueError('ZIP: неверное число элементов')


def _scan_files(base, pattern, recursive):
    pending = [base]; visited = 0; matches = []
    while pending:
        folder = pending.pop(); _host_path(str(folder))
        with os.scandir(folder) as iterator:
            children = []
            for entry in iterator:
                visited += 1
                if visited > MAX_ENTRIES: raise ValueError('ZIP: превышен предел обхода')
                child = _host_path(entry.path); children.append((entry.name, child, entry.is_dir(follow_symlinks=False)))
        for name, child, directory in sorted(children):
            if directory:
                if recursive: pending.append(child)
            elif fnmatch.fnmatchcase(name, pattern): matches.append(child)
    return sorted(matches)


class BSLZipFileEntry(_FileMethods):
    def __init__(self, owner, info): self._owner, self._info = owner, info
    def __str__(self): return 'ЭлементZipФайла'
    def get_member(self, name):
        info = self._info; full = info.filename.replace('\\', '/')
        leaf = full.rstrip('/').rsplit('/', 1)[-1]
        stem, extension = os.path.splitext(leaf)
        path = full[:-len(leaf)] if not full.endswith('/') else full
        values = {
            'name имя originalname исходноеимя': leaf,
            'basename имябезрасширения originalbasename исходноеимябезрасширения': stem,
            'extension расширение originalextension исходноерасширение': extension,
            'fullname полноеимя originalfullname исходноеполноеимя': full,
            'path путь originalpath исходныйпуть': path,
            'compressedsize размерсжатого': Decimal(info.compress_size),
            'uncompressedsize размернесжатого': Decimal(info.file_size),
            'encrypted зашифрован': bool(info.flag_bits & 1),
            'hidden невидимый': bool(info.external_attr & 2),
            'readonly толькочтение': bool(info.external_attr & 1),
            'modified времяизменения': from_datetime(datetime(*info.date_time)),
        }
        for aliases, value in values.items():
            if name.casefold() in aliases.split(): return value
        return super().get_member(name)


class BSLZipFileEntries(_FileMethods):
    def __init__(self, entries): self._entries = tuple(entries)
    def __str__(self): return 'ЭлементыZipФайла'
    def __iter__(self): return iter(self._entries)
    def __getitem__(self, index): return self.get(index)
    def get(self, index):
        index = _number(index, MAX_ENTRIES)
        if index >= len(self._entries): raise IndexError('ZIP: индекс за границами')
        return self._entries[index]
    def set(self, index, value): raise TypeError("ZIP: коллекция доступна только для чтения")
    def count(self): return Decimal(len(self._entries))
    def find(self, name):
        name = _text(name)
        for item in self._entries:
            if item._info.filename == name: return item
        return None
    _methods = _methods(('get', True, 'Get Получить'), ('count', True, 'Count Количество'),
                        ('find', True, 'Find Найти'))


class BSLZipFileReader(_FileMethods):
    @_zip_errors
    def __init__(self, source=None, password=None):
        self._archive = None; self._items = BSLZipFileEntries(())
        if source is not None: self.open(source, password)
        else: _password(password)
    def __str__(self): return 'ЧтениеZipФайла'
    def _open(self):
        if self._archive is None: raise ValueError('ZIP: архив закрыт')
        return self._archive
    @_zip_errors
    def open(self, source, password=None):
        _password(password)
        if type(source) is str: raw, _ = _read_file(source)
        elif type(source) in _STREAMS:
            source._readable(); remaining = source._size() - source._state.position
            if remaining < 0 or remaining > MAX_BYTES: raise ValueError('ZIP: превышен предел ресурсов')
            raw = source._read_bytes(remaining)
        else: raise TypeError('ZIP: ожидается имя файла или Поток')
        archive = None
        try:
            _preflight_zip(raw)
            archive = zipfile.ZipFile(io.BytesIO(raw), 'r')
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES or len(raw) > MAX_BYTES: raise ValueError('ZIP: превышен предел ресурсов')
            total = 0; names = []
            for info in infos:
                names.append(_name(info.orig_filename))
                mode = info.external_attr >> 16
                if info.flag_bits & 1 or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError('ZIP: шифрование/ссылки/устройства не поддерживаются')
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ValueError('ZIP: метод сжатия не поддерживается')
                if info.file_size > MAX_BYTES or info.compress_size > MAX_BYTES: raise ValueError('ZIP: превышен предел ресурсов')
                if info.is_dir() and info.file_size != 0: raise ValueError("ZIP: каталог содержит данные")
                total += info.file_size
                if total > MAX_BYTES: raise ValueError('ZIP: превышен предел ресурсов')
            _unique_names(names)
            self.close(); self._archive = archive
            self._items = BSLZipFileEntries(BSLZipFileEntry(self, info) for info in infos)
        except Exception:
            if archive is not None: archive.close()
            raise
    def close(self):
        if self._archive is not None: self._archive.close()
        self._archive = None; self._items = BSLZipFileEntries(())
    def get_member(self, name):
        if name.casefold() in ('items', 'элементы'): self._open(); return self._items
        if name.casefold() in ('comment', 'комментарий'): return self._open().comment.decode('utf-8')
        return super().get_member(name)
    def _extract(self, entries, path, restore):
        archive = self._open(); restore = _enum(restore, BSLZIPRestoreFilePathsMode.RESTORE)
        if not (os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")):
            # !todo Add a reviewed anchored Windows handle backend; never silently
            # downgrade untrusted archive extraction to pathname-only checks.
            raise ValueError("ZIP: безопасная распаковка недоступна на этой платформе")
        root = _host_path(path)
        if root.exists() and not root.is_dir(): raise ValueError('ZIP: требуется каталог')
        planned = []; names = []; total = 0
        for item in entries:
            info = item._info; name = _name(info.filename)
            if restore is BSLZIPRestoreFilePathsMode.FLAT:
                if not info.is_dir(): name = name.rsplit('/', 1)[-1]
            target = _host_path(str(root / name)); names.append(name)
            if os.path.commonpath((root, target)) != str(root): raise ValueError('ZIP: выход из каталога')
            if target.exists() and (target.is_dir() != info.is_dir()): raise ValueError('ZIP: коллизия назначения')
            # Validate even directory local headers and CRCs before skipping a
            # directory in flat extraction; directory payloads are rejected at open.
            with archive.open(info) as source:
                chunks = []; size = 0
                while True:
                    chunk = source.read(min(65536, MAX_BYTES - total + 1))
                    if not chunk: break
                    size += len(chunk); total += len(chunk)
                    if total > MAX_BYTES: raise ValueError('ZIP: превышен предел распаковки')
                    chunks.append(chunk)
                data = b''.join(chunks)
            if size != info.file_size: raise ValueError('ZIP: поврежденный размер')
            if info.is_dir() and restore is BSLZIPRestoreFilePathsMode.FLAT:
                names.pop(); continue
            planned.append((target, info.is_dir(), data))
        _unique_names(names)
        # All paths, collisions, expanded bytes and CRCs pass before first write.
        for target, directory, data in planned:
            _host_path(str(target))
            with _directory(target if directory else target.parent, create=True): pass
            if not directory: _write_file(target, data)
    @_zip_errors
    def extract(self, item, path, restore=None, password=None):
        _password(password)
        if type(item) is not BSLZipFileEntry or item._owner is not self or item not in self._items._entries:
            raise TypeError('ZIP: элемент не принадлежит открытому архиву')
        self._extract((item,), path, restore)
    @_zip_errors
    def extract_all(self, path, restore=None): self._extract(self._items._entries, path, restore)
    _methods = _methods(('open', False, 'Open Открыть'), ('close', False, 'Close Закрыть'),
                        ('extract', False, 'Extract Извлечь'), ('extract_all', False, 'ExtractAll ИзвлечьВсе'))


class BSLZipFileWriter(_FileMethods):
    @_zip_errors
    def __init__(self, target=None, password=None, comment=None, method=None, level=None, encryption=None, encoding=None):
        self._target = None; self._closed = False; self._entries = []
        self._options(password, comment, method, level, encryption, encoding)
        if target is not None: self.open(target, password, comment, method, level, encryption, encoding)
    def __str__(self): return 'ЗаписьZipФайла'
    def _options(self, password, comment, method, level, encryption, encoding):
        _password(password)
        comment = '' if comment is None else _text(comment)
        if len(comment.encode('utf-8')) > 65535: raise ValueError('ZIP: комментарий слишком велик')
        method = _enum(method, BSLZIPCompressionMethod.DEFLATE)
        level = _enum(level, BSLZIPCompressionLevel.OPTIMAL)
        encryption = _enum(encryption, BSLZIPEncryptionMethod.ZIP20)
        encoding = _enum(encoding, BSLFileNamesEncodingInZipFile.AUTO)
        if method is BSLZIPCompressionMethod.BZIP2 or encryption is not BSLZIPEncryptionMethod.ZIP20 or encoding is BSLFileNamesEncodingInZipFile.OS_UTF8:
            raise ValueError('ZIP: неподдержанный метод/кодировка')
        self._comment, self._method, self._level = comment, method, level
    def _open(self):
        if self._closed: raise ValueError('ZIP: архив закрыт')
    @_zip_errors
    def open(self, target, password=None, comment=None, method=None, level=None, encryption=None, encoding=None):
        if type(target) is str: target = str(_host_path(target))
        elif type(target) in _STREAMS: target._writable()
        else: raise TypeError('ZIP: ожидается имя файла или Поток')
        self._options(password, comment, method, level, encryption, encoding)
        self._target, self._entries, self._closed = target, [], False
    @_zip_errors
    def add(self, filename, mode=None, recursive=None):
        self._open(); filename = _text(filename)
        mode = _enum(mode, BSLZIPStorePathMode.FLAT)
        recursive = _enum(recursive, BSLZIPSubDirProcessingMode.NO)
        pattern_path = _host_path(filename)
        base, pattern = pattern_path.parent, pattern_path.name
        matches = []
        if '*' not in pattern and '?' not in pattern:
            if not pattern_path.exists(): raise ValueError('ZIP: исходный файл не найден')
            if pattern_path.is_file(): matches = [pattern_path]
            elif pattern_path.is_dir():
                base = pattern_path
                matches = _scan_files(base, '*', recursive is BSLZIPSubDirProcessingMode.RECURSIVE)
            else: raise ValueError('ZIP: требуется обычный файл')
        else:
            matches = _scan_files(base, pattern, recursive is BSLZIPSubDirProcessingMode.RECURSIVE)
        pending = []; total = sum(len(data) for _, data, _ in self._entries)
        for path in matches:
            if self._target is not None and type(self._target) is str and path == Path(self._target):
                raise ValueError('ZIP: архив не может включать себя')
            data, info = _read_file(path); total += len(data)
            if total > MAX_BYTES: raise ValueError('ZIP: превышен предел ресурсов')
            if mode is BSLZIPStorePathMode.FLAT: name = path.name
            elif mode is BSLZIPStorePathMode.RELATIVE: name = path.relative_to(base).as_posix()
            else: name = path.as_posix().lstrip('/').replace(':', '')
            pending.append((_name(name), data, info.st_mtime))
        if len(pending) + len(self._entries) > MAX_ENTRIES: raise ValueError('ZIP: слишком много элементов')
        _unique_names([name for name, _, _ in self._entries + pending])
        self._entries.extend(pending)
    def _bytes(self):
        self._open(); target = io.BytesIO()
        method = zipfile.ZIP_STORED if self._method is BSLZIPCompressionMethod.COPY else zipfile.ZIP_DEFLATED
        level = {BSLZIPCompressionLevel.MINIMUM: 1, BSLZIPCompressionLevel.OPTIMAL: 6, BSLZIPCompressionLevel.MAXIMUM: 9}[self._level]
        with zipfile.ZipFile(target, 'w', compression=method, compresslevel=level, allowZip64=False) as archive:
            archive.comment = self._comment.encode('utf-8')
            for name, data, modified in self._entries:
                stamp = datetime.fromtimestamp(modified)
                if not 1980 <= stamp.year <= 2107: stamp = datetime(1980, 1, 1)
                info = zipfile.ZipInfo(name, stamp.timetuple()[:6]); info.compress_type = method
                archive.writestr(info, data, compresslevel=level)
                if target.tell() > MAX_BYTES: raise ValueError('ZIP: превышен предел ресурсов')
        raw = target.getvalue()
        if len(raw) > MAX_BYTES: raise ValueError('ZIP: превышен предел ресурсов')
        return raw
    @_zip_errors
    def write(self):
        self._open()
        if self._target is None: raise ValueError('ZIP: не задано назначение')
        raw = self._bytes()
        if type(self._target) is str: _write_file(self._target, raw)
        else: self._target._write_bytes(raw)
        self._closed = True; self._entries = []
    @_zip_errors
    def get_binary_data(self, password=None, comment=None, method=None, level=None, encryption=None):
        self._open()
        if self._target is not None: raise ValueError('ZIP: требуется конструктор без параметров')
        self._options(password, comment, method, level, encryption, None)
        result = BSLBinaryData.from_bytes(self._bytes()); self._closed = True; self._entries = []
        return result
    # !todo Encryption/passwords, multipart/overbudget ZIP64, BZIP2, exotic name
    # encodings, duplicate-name native renaming and OS attributes are unsupported.
    # !todo Stream cursor/ownership defaults and source-close/view lifetime need
    # the ordinary native batch; do not infer ownership from host zipfile.
    _methods = _methods(('open', False, 'Open Открыть'), ('add', False, 'Add Добавить'),
                        ('write', False, 'Write Записать'), ('get_binary_data', True, 'GetBinaryData ПолучитьДвоичныеДанные'))


NAMESPACES = tuple((ru, en, _Namespace(cls)) for ru, en, cls in (
    ('МетодСжатияZIP', 'ZIPCompressionMethod', BSLZIPCompressionMethod),
    ('УровеньСжатияZIP', 'ZIPCompressionLevel', BSLZIPCompressionLevel),
    ('РежимСохраненияПутейZIP', 'ZIPStorePathMode', BSLZIPStorePathMode),
    ('РежимОбработкиПодкаталоговZIP', 'ZIPSubDirProcessingMode', BSLZIPSubDirProcessingMode),
    ('РежимВосстановленияПутейФайловZIP', 'ZIPRestoreFilePathsMode', BSLZIPRestoreFilePathsMode),
    ('МетодШифрованияZIP', 'ZIPEncryptionMethod', BSLZIPEncryptionMethod),
    ('КодировкаИменФайловВZipФайле', 'FileNamesEncodingInZipFile', BSLFileNamesEncodingInZipFile)))
