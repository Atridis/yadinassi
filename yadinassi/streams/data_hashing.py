"""Bounded incremental 1C data checksums; not authentication or password storage.

MD5/SHA1 are compatibility algorithms, not security recommendations. Only the
existing exact binary/stream types and explicit local regular-file paths enter.
!todo: native calibration of Count/EOF and CRC representation; custom streams,
asynchronous operations and serialized hash-state formats are unsupported.
"""
from decimal import Decimal
import hashlib
import zlib

from .file_io import BSLBinaryData, _FileMethods, _methods, MAX_BYTES
from .binary_streams import (BSLStream, BSLMemoryStream, BSLFileStream,
    BSLFileOpenMode, BSLFileAccess, _Enum, _Namespace, _number)
from .data_io import _encoded

MAX_TOTAL_BYTES = 64 * 1024 * 1024
_STREAMS = (BSLStream, BSLMemoryStream, BSLFileStream)


class BSLHashFunction(_Enum):
    CRC32 = ('CRC32',)
    MD5 = ('MD5',)
    SHA1 = ('SHA1',)
    SHA256 = ('SHA256',)
    SHA512 = ('SHA512',)


HASH_FUNCTIONS = _Namespace(BSLHashFunction)


class BSLDataHashing(_FileMethods):
    def __init__(self, function):
        if type(function) is not BSLHashFunction:
            raise TypeError('Ожидается ХешФункция')
        self._function = function
        # No provider fallback or change to platform security settings. These
        # algorithms are requested solely for non-security 1C compatibility.
        self._hash = (0 if function is BSLHashFunction.CRC32 else
                      hashlib.new(function.name.lower(), usedforsecurity=False))
        self._total = 0

    def __str__(self): return 'ХешированиеДанных'

    def get_member(self, name):
        key = name.casefold()
        if key in ('hashfunction', 'хешфункция'): return self._function
        if key in ('hashsum', 'хешсумма'):
            if self._function is BSLHashFunction.CRC32: return Decimal(self._hash)
            return BSLBinaryData.from_bytes(self._hash.digest())
        return super().get_member(name)

    def _preflight(self, size):
        if size > MAX_BYTES or self._total + size > MAX_TOTAL_BYTES:
            raise ValueError('ХешированиеДанных: превышен предел ресурсов')

    def _updated(self, data):
        self._preflight(len(data))
        if self._function is BSLHashFunction.CRC32:
            return zlib.crc32(data, self._hash) & 0xffffffff
        result = self._hash.copy()
        result.update(data)
        return result

    def append(self, value, count=None):
        if type(value) in _STREAMS:
            value._readable()
            requested = None if count is None else _number(count)
            # !todo Explicit zero-count stream workflow failed on native 8.3.27;
            # its semantics are unmeasured. Do not guess a no-op or all-data read.
            if requested == 0:
                raise ValueError('ХешированиеДанных: нулевое количество потока пока не поддерживается')
            available = max(0, value._size() - value._state.position)
            size = available if requested is None else min(requested, available)
            self._preflight(size)
            position = value._state.position
            try:
                data = value._read_bytes(size)
                updated = self._updated(data)
            except BaseException:
                value._state.position = position
                raise
        else:
            if count is not None: raise TypeError('Количество допустимо только для потока')
            if type(value) is str:
                # Precise UTF8 length preflight, no BOM or implicit str coercion.
                if len(value) > MAX_BYTES: self._preflight(len(value))
                size = sum(1 if ord(c) < 128 else 2 if ord(c) < 2048 else
                           3 if ord(c) < 65536 else 4 for c in value)
                self._preflight(size)
                data = _encoded(value, 'utf-8')
            elif type(value) is BSLBinaryData: data = value._data
            else: raise TypeError('Ожидается Строка, ДвоичныеДанные или Поток')
            updated = self._updated(data)
        self._hash = updated
        self._total += len(data)

    def append_file(self, filename):
        # The same pre-open UNC/device/ADS and regular-file boundary as FileStream.
        stream = BSLFileStream(filename, BSLFileOpenMode.OPEN, BSLFileAccess.READ)
        try: self.append(stream)
        finally: stream.close()

    _methods = _methods(('append', False, 'Append Добавить'),
                        ('append_file', False, 'AppendFile ДобавитьФайл'))
