"""Bounded, borrowed adapters for text/JSON/XML over admitted BSL streams.

This is a local profile, not a claim about native ownership or buffering.
Snapshots consume from the current position; failed transforms restore it.
No arbitrary host streams, network endpoints, or implicit source close.
"""
from .binary_streams import BSLStream, BSLMemoryStream, BSLFileStream, _number
from .file_io import MAX_BYTES


def is_stream(value):
    return type(value) in (BSLStream, BSLMemoryStream, BSLFileStream)


def _stream(value):
    if not is_stream(value):
        raise TypeError('Ожидается Поток')
    return value


def read_snapshot(stream, transform, max_bytes=MAX_BYTES):
    stream = _stream(stream)
    stream._readable()
    limit = _number(max_bytes)
    position = stream._open().position
    count = max(0, stream._size() - position)
    if count > limit:
        raise ValueError('Превышен предел ресурсов Yadinassi')
    try:
        return transform(stream._read_bytes(count))
    except BaseException:
        stream._state.position = position
        raise


class BinaryStreamSink:
    """Minimal bytes sink that never owns/closes the caller's stream."""
    def __init__(self, stream):
        stream = _stream(stream)
        stream._write_check(0)
        self._stream = stream

    def _open(self):
        if self._stream is None:
            raise ValueError('Запись потока закрыта')
        return self._stream

    def write(self, data):
        if type(data) is not bytes:
            raise TypeError('Ожидаются байты')
        if len(data) > MAX_BYTES:
            raise ValueError('Превышен предел ресурсов Yadinassi')
        self._open()._write_bytes(data)
        return len(data)

    def flush(self):
        self._open().flush()

    def close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.flush()
