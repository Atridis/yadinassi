"""Standalone ZIP file reading/writing and anchored extraction."""
from weakref import ref
from yadinassi.streams import binary_streams, file_io, zip_archives
from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI, _DIRECT_HOST_FUNCTION_CALL_CODE

from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.streams.zip_archives import BSLZipFileReader, BSLZipFileEntries, BSLZipFileEntry, BSLZipFileWriter
from yadinassi.types.values import HostFunction

CONSTRUCTORS = dict.fromkeys(('zipfilereader', 'чтениеzipфайла'), BSLZipFileReader)
CONSTRUCTORS.update(dict.fromkeys(('zipfilewriter', 'записьzipфайла'), BSLZipFileWriter))
NAMES = frozenset(CONSTRUCTORS)
_TYPES = (BSLZipFileReader, BSLZipFileEntries, BSLZipFileEntry, BSLZipFileWriter)
_READ = {id(kind): kind.get_member for kind in _TYPES}
TYPE_IDS = frozenset(_READ)
_OWNERS = {}
_STREAMS = {}
_TARGETS = {}
_STREAM_ABI = binary_streams._DIRECT_ZIP_STREAM_ABI
_BINARY_ABI = file_io._DIRECT_ZIP_BINARY_ABI
_ARCHIVE_ABI = zip_archives._DIRECT_ZIP_ARCHIVE_ABI
_STREAM_BINDINGS = binary_streams._DIRECT_ZIP_STREAM_BINDINGS
_STATE_CLASS, _READ_CLASS, _MEMORY_CLASS = (record[0] for record in _STREAM_ABI)
_BINARY_CLASS = _BINARY_ABI[-1][0]
_OPEN_MEMORY = dict(_STREAM_BINDINGS)['binary_data_stream']
_OPEN_MEMORY_CODE = binary_streams._DIRECT_ZIP_OPEN_MEMORY_CODE
_BYTEARRAY = binary_streams._DIRECT_ZIP_BYTEARRAY
_HOST_CLASS, _HOST_MRO, _HOST_FIELDS = _DIRECT_COLLECTION_CLASS_ABI[-1]
_HOST_DICT = vars(_HOST_CLASS)
_HOST_CALL = dict(_HOST_FIELDS)['__call__']
_HOST_CALL_CODE = _DIRECT_HOST_FUNCTION_CALL_CODE
_READ_ALIASES = frozenset(('openstreamforread', 'открытьпотокдлячтения'))
_WRITE = BSLZipFileWriter.write
_OPEN, _CLOSE = BSLZipFileReader.open, BSLZipFileReader.close
_EXTRACT, _EXTRACT_ALL = BSLZipFileReader.extract, BSLZipFileReader.extract_all
_ENTRY_GET, _ENTRY_SET = BSLZipFileEntries.get, BSLZipFileEntries.set
_SYNTAX = {'__getitem__': _ENTRY_GET, '__setitem__': _ENTRY_SET,
           '__iter__': BSLZipFileEntries.__iter__}
_READER = {alias: method for aliases, method in (
    (('open', 'открыть'), _OPEN), (('close', 'закрыть'), _CLOSE),
    (('extract', 'извлечь'), _EXTRACT), (('extractall', 'извлечьвсе'), _EXTRACT_ALL))
    for alias in aliases}
_WRITER = {alias: (method, returns_value) for aliases, method, returns_value in (
    (('open', 'открыть'), BSLZipFileWriter.open, False),
    (('add', 'добавить'), BSLZipFileWriter.add, False),
    (('write', 'записать'), BSLZipFileWriter.write, False),
    (('getbinarydata', 'получитьдвоичныеданные'), BSLZipFileWriter.get_binary_data, True))
    for alias in aliases}
_WRITER_PATHS = (BSLZipFileWriter.open, BSLZipFileWriter.add)
_ENTRIES = {alias: method for aliases, method in (
    (('get', 'получить'), _ENTRY_GET), (('find', 'найти'), BSLZipFileEntries.find),
    (('count', 'количество'), BSLZipFileEntries.count))
    for alias in aliases}


def _check(boundary):
    from yadinassi.runtime import Interpreter
    vm = boundary.vm
    if (type(vm) is not Interpreter or vm.database_context is not None
            or vm._configuration_runtime is not None):
        raise BoundaryViolation('ZIP file access requires a standalone interpreter')
    if boundary._verify_context:
        boundary._check()


def _owned(boundary, value):
    _check(boundary)
    entry = _OWNERS.get(id(value))
    if entry is None or entry[0]() is not value or entry[1]() is not boundary.vm._family_owner:
        raise BoundaryViolation('foreign ZIP writer' if type(value) is BSLZipFileWriter
                                else 'foreign ZIP reader or metadata')


def _publish(boundary, value):
    if id(type(value)) not in TYPE_IDS:
        return value
    identity = id(value)
    family = boundary.vm._family_owner
    entry = _OWNERS.get(identity)
    if entry is not None and entry[0]() is value:
        if entry[1]() is not family:
            raise BoundaryViolation('foreign ZIP writer' if type(value) is BSLZipFileWriter
                                else 'foreign ZIP reader or metadata')
        return value

    def forget(dead):
        entry = _OWNERS.get(identity)
        if entry is not None and entry[0] is dead:
            del _OWNERS[identity]

    _OWNERS[identity] = ref(value, forget), ref(family)
    return value


def _source(value, *, optional=False):
    if not (type(value) is str or (optional and value is None)):
        raise TypeError('ZIP: ожидается имя файла')


def _stream_mode(boundary):
    from yadinassi.runtime import Interpreter
    vm = boundary.vm
    return (type(vm) is Interpreter and vm.database_context is None
            and vm._configuration_runtime is None)


def _check_abi(records):
    for cls, mro, fields in records:
        current = vars(cls)
        if (cls.__mro__ is not mro or
                any(current.get(name) is not value for name, value in fields) or
                len(current) != len(fields) + ('__slotnames__' in current
                                                and not any(n == '__slotnames__' for n, _ in fields))):
            raise BoundaryViolation('ZIP memory transport ABI changed')
        if '__slotnames__' in current:
            names = current['__slotnames__']
            if type(names) is not list or names:
                raise BoundaryViolation('ZIP memory transport slot metadata changed')


def _canonical_bytearray(function):
    return (function.__globals__.get('bytearray', function.__builtins__.get('bytearray'))
            is _BYTEARRAY)


def _stream_abi():
    _check_abi((*_STREAM_ABI, *_BINARY_ABI, _DIRECT_COLLECTION_CLASS_ABI[0]))
    if (_OPEN_MEMORY.__code__ is not _OPEN_MEMORY_CODE or not _canonical_bytearray(_OPEN_MEMORY)
            or any(vars(binary_streams).get(name) is not value for name, value in _STREAM_BINDINGS)):
        raise BoundaryViolation('ZIP memory transport binding changed')


# Constructor ownership is about the allocation and the backing it creates.
# Audit the entire transport only on borrow, not on unrelated construction.
_STATE_FIELDS = frozenset(('data', 'file', 'position', 'capacity', 'read', 'write', 'buffer'))
_MEMORY_FIELDS = frozenset(('_state', '_readonly', '_closed'))
_STATE_MRO, _MEM_MRO, _BINARY_MRO = _STREAM_ABI[0][1], _STREAM_ABI[-1][1], _BINARY_ABI[-1][1]
_STATE_INIT_CODE, _MEMORY_INIT_CODE = binary_streams._DIRECT_ZIP_STREAM_INIT_CODES
_BINARY_INIT_CODE = file_io._DIRECT_ZIP_BINARY_INIT_CODE
_STATE_DICT, _MEMORY_DICT, _BINARY_DICT = map(vars, (_STATE_CLASS, _MEMORY_CLASS, _BINARY_CLASS))
_STATE_INIT = dict(_STREAM_ABI[0][2])['__init__']
_MEMORY_INIT = dict(_STREAM_ABI[-1][2])['__init__']
_BINARY_INIT = dict(_BINARY_ABI[-1][2])['__init__']
_MEMORY_BASE_DICTS = tuple(vars(cls) for cls in _MEM_MRO[1:-1])
_BINARY_BASE_DICTS = tuple(vars(cls) for cls in _BINARY_MRO[1:-1])
_INSTANCE_DICT = dict(_DIRECT_COLLECTION_CLASS_ABI[0][2])['__dict__']


def _producer_abi(expected):
    if (expected.__new__ is not object.__new__
            or expected.__setattr__ is not object.__setattr__):
        raise BoundaryViolation('ZIP memory producer allocation changed')
    if expected is _MEMORY_CLASS:
        if (expected.__mro__ is not _MEM_MRO or _MEMORY_DICT.get('__init__') is not _MEMORY_INIT
                or _MEMORY_INIT.__code__ is not _MEMORY_INIT_CODE
                or binary_streams._State is not _STATE_CLASS
                or _STATE_CLASS.__mro__ is not _STATE_MRO
                or _STATE_CLASS.__new__ is not object.__new__
                or _STATE_CLASS.__setattr__ is not object.__setattr__
                or _STATE_DICT.get('__init__') is not _STATE_INIT
                or _STATE_INIT.__code__ is not _STATE_INIT_CODE
                or not _canonical_bytearray(_STATE_INIT)
                or not _STATE_DICT.keys().isdisjoint(_STATE_FIELDS)
                or not _MEMORY_DICT.keys().isdisjoint(_MEMORY_FIELDS)
                or any(not fields.keys().isdisjoint(_MEMORY_FIELDS) for fields in _MEMORY_BASE_DICTS)):
            raise BoundaryViolation('ZIP memory producer backing changed')
    elif (expected.__mro__ is not _BINARY_MRO or _BINARY_DICT.get('__init__') is not _BINARY_INIT
            or _BINARY_INIT.__code__ is not _BINARY_INIT_CODE
            or '_data' in _BINARY_DICT or any('_data' in fields for fields in _BINARY_BASE_DICTS)):
        raise BoundaryViolation('ZIP BinaryData producer backing changed')


def _fields(value):
    fields = object.__getattribute__(value, '__dict__')
    if type(fields) is not dict or any(type(key) is not str for key in fields):
        raise BoundaryViolation('ZIP memory transport state changed')
    return fields


def _remember(store, value, family, backing):
    key = id(value)

    def forget(dead):
        entry = store.get(key)
        if entry is not None and entry[0] is dead:
            del store[key]

    store[key] = (ref(value, forget), ref(family), backing)


def _entry(store, value):
    entry = store.get(id(value))
    return entry if entry is not None and entry[0]() is value else None


def owns_producer(factory):
    return factory is _MEMORY_CLASS or factory is _BINARY_CLASS


def producer(boundary, name, factory, expected, *, allow_references=False):
    if not _stream_mode(boundary):
        return None
    if boundary._verify_context:
        boundary._check()
    boundary._validate_host_function(factory, False)
    vm = boundary.vm
    family = vm._family_owner
    policy_name = factory.name.casefold()
    memory = expected is _MEMORY_CLASS

    def create(*values):
        # Leave buffer-backed/shared MemoryStream construction and all non-file
        # BinaryData inputs on their existing routes, without enrolling them.
        issued = not values if memory else len(values) == 1 and type(values[0]) is str
        checked = not memory or boundary._verify_context
        if checked:
            boundary._check_effect()
        if factory.function is not expected:
            raise BoundaryViolation('canonical constructor changed during argument evaluation')
        boundary._before('call_value', policy_name)
        try:
            if issued:
                if (vm._family_owner is not family or vm.types.get(name) is not factory
                        or factory.function is not expected):
                    raise BoundaryViolation('ZIP memory producer binding changed')
                # Keep ordinary HostFunction wrapping (notably an explicit
                # Python extension), but never enroll its custom results.
                issued = (_HOST_CLASS.__mro__ is _HOST_MRO and _HOST_DICT.get('__call__') is _HOST_CALL
                          and _HOST_CALL.__code__ is _HOST_CALL_CODE
                          and _HOST_CLASS.__getattribute__ is object.__getattribute__
                          and '__getattr__' not in _HOST_DICT and 'function' not in _HOST_DICT)
                if issued:
                    _producer_abi(expected)
            value = factory(*values)
        except PermissionError as error:
            raise BoundaryViolation(str(error)) from error
        finally:
            if checked:
                boundary._check_effect()
        if issued:
            key = '_state' if memory else '_data'
            backing = _INSTANCE_DICT.__get__(value).get(key)
            if type(backing) is not (_STATE_CLASS if memory else bytes):
                raise BoundaryViolation('ZIP memory producer did not install canonical backing')
            _remember(_STREAMS, value, family, backing)
        return value

    if allow_references:
        create.requires_reference = lambda index: False
    return create


def resolve_binary_stream(boundary, value, name):
    if type(value) is not _BINARY_CLASS or name.casefold() not in _READ_ALIASES:
        return None
    entry = _entry(_STREAMS, value)
    # Existing detached BinaryData calls stay unchanged; their stream results
    # have no ZIP borrowing authority, even if otherwise readable.
    if entry is None or entry[1]() is not boundary.vm._family_owner or not _stream_mode(boundary):
        return None

    boundary._check_effect()

    def open_stream():
        _check(boundary)
        boundary._check_effect()
        _stream_abi()
        fields = _fields(value)
        data = fields.get('_data')
        if fields.keys() != {'_data'} or data is not entry[2] or type(data) is not bytes:
            raise BoundaryViolation('ZIP BinaryData backing changed')
        try:
            stream = _OPEN_MEMORY(value)
        finally:
            boundary._check_effect()
        _remember(_STREAMS, stream, boundary.vm._family_owner, _fields(stream)['_state'])
        return stream

    return open_stream


def _stream(boundary, value, *, writing):
    if not (type(value) is _MEMORY_CLASS or (not writing and type(value) is _READ_CLASS)):
        _source(value)
    entry = _entry(_STREAMS, value)
    if entry is None or entry[1]() is not boundary.vm._family_owner:
        _source(value)
    _stream_abi()
    fields = _fields(value)
    state = fields.get('_state')
    if (state is not entry[2] or type(state) is not _STATE_CLASS
            or set(fields) != {'_state', '_readonly', '_closed'}
            or type(fields['_readonly']) is not bool or type(fields['_closed']) is not bool):
        raise BoundaryViolation('ZIP memory stream state changed')
    slots = _fields(state)
    if (slots.keys() != {'file', 'data', 'position', 'capacity', 'read', 'write', 'buffer'}
            or slots['file'] is not None or slots['buffer'] is not None
            or type(slots['data']) is not _BYTEARRAY
            or type(slots['position']) is not int or slots['position'] < 0
            or type(slots['capacity']) is not int or slots['capacity'] < 0
            or type(slots['read']) is not bool or type(slots['write']) is not bool):
        raise BoundaryViolation('ZIP memory stream backing changed')
    if fields['_closed']:
        raise ValueError('Поток закрыт')
    if writing and (fields['_readonly'] or not slots['write']):
        raise ValueError('Поток не поддерживает запись')
    if not writing and not slots['read']:
        raise ValueError('Поток не поддерживает чтение')
    # Canonical ZIP kernel retains cursor, capacity and archive bounds.


def _archive_source(boundary, value, *, writing, optional=False):
    if type(value) is str or (optional and value is None):
        return
    _stream(boundary, value, writing=writing)
    _check_abi((_ARCHIVE_ABI[int(writing)],))


def _writer_target(boundary, writer, target):
    if type(target) is _MEMORY_CLASS:
        _remember(_TARGETS, writer, boundary.vm._family_owner, ref(target))
    else:
        _TARGETS.pop(id(writer), None)


def _check_write_target(boundary, writer):
    entry = _entry(_TARGETS, writer)
    if entry is not None:
        _check_abi((_ARCHIVE_ABI[1], _BINARY_ABI[0], _DIRECT_COLLECTION_CLASS_ABI[0]))
        target = _fields(writer).get('_target')
        if entry[1]() is not boundary.vm._family_owner or target is not entry[2]():
            raise BoundaryViolation('ZIP memory target changed')
        _stream(boundary, target, writing=True)
    else:
        _source(object.__getattribute__(writer, '_target'), optional=True)


def constructor(boundary, name, factory, *, require_value=False, allow_references=False, **unused):
    _check(boundary)
    expected = CONSTRUCTORS[name]
    if factory is None and expected is BSLZipFileWriter:
        raise ValueError('Тип не определен: '+name)
    if type(factory) is not HostFunction or factory.function is not expected:
        raise BoundaryViolation('ZIP constructor requires canonical registration')
    boundary._validate_host_function(factory, require_value, allow_references)

    def create(source=None, *options):
        boundary._check_effect()
        boundary._before('call_value', name)
        if (boundary.vm.types.get(name) is not factory
                or factory.function is not expected):
            raise BoundaryViolation('ZIP constructor binding changed')
        writing = expected is BSLZipFileWriter
        _archive_source(boundary, source, writing=writing, optional=True)
        try:
            value = _publish(boundary, expected(source, *options))
            if writing:
                _writer_target(boundary, value, source)
            return value
        finally:
            boundary._check_effect()

    if allow_references:
        create.requires_reference = lambda index: False
    return create


def get(boundary, value, name):
    _owned(boundary, value)
    if type(value) is BSLZipFileWriter:
        raise ValueError('Поле объекта не обнаружено: ' + name)
    return _publish(boundary, _READ[id(type(value))](value, name))


def resolve(boundary, value, name, *, syntax=False, require_value=False, omitted=()):
    _owned(boundary, value)
    kind = type(value)
    if kind is BSLZipFileWriter:
        entry = _WRITER.get(name.casefold())
        if entry is None or syntax:
            raise ValueError('Метод объекта не обнаружен: ' + name)
        if omitted:
            raise TypeError('ZIP: обязательный аргумент пропущен')
        method, returns_value = entry

        def effect(*actuals):
            _owned(boundary, value)
            boundary._check_effect()
            if method is _WRITER_PATHS[0] and actuals:
                _archive_source(boundary, actuals[0], writing=True)
            elif method is _WRITER_PATHS[1] and actuals:
                _source(actuals[0])
            elif method is _WRITE:
                _check_write_target(boundary, value)
            try:
                result = method(value, *actuals)
                if method is _WRITER_PATHS[0] and actuals:
                    _writer_target(boundary, value, actuals[0])
                return result
            finally:
                boundary._check_effect()

        return boundary.resolve_callable(HostFunction(name, effect, returns_value=returns_value),
                                         require_value=require_value)
    if kind is BSLZipFileReader:
        method = _READER.get(name.casefold())
        if method is None or syntax:
            raise ValueError('Метод объекта не обнаружен: ' + name)
        if omitted:
            raise TypeError('ZIP: обязательный аргумент пропущен')
        if require_value:
            raise TypeError('Процедура не возвращает значение: ' + name)

        def effect(*actuals):
            boundary._check_effect()
            if method is _OPEN and actuals:
                _owned(boundary, value)
                _archive_source(boundary, actuals[0], writing=False)
            elif method is _EXTRACT or method is _EXTRACT_ALL:
                _owned(boundary, value)
                if method is _EXTRACT:
                    if actuals and type(actuals[0]) is BSLZipFileEntry:
                        _owned(boundary, actuals[0])
                    if len(actuals) >= 2:
                        _source(actuals[1])
                elif actuals:
                    _source(actuals[0])
            try:
                return method(value, *actuals)
            finally:
                boundary._check_effect()

        return boundary.resolve_callable(HostFunction(name, effect, returns_value=False),
                                         require_value=require_value)
    if kind is BSLZipFileEntries and not omitted:
        method = _SYNTAX.get(name) if syntax else None
        if method is None:
            method = _ENTRIES.get(name.casefold())
        if method is not None:
            def read(*actuals):
                if boundary._verify_context:
                    boundary._check()
                result = method(value, *actuals)
                if method is _SYNTAX['__iter__']:
                    return (_publish(boundary, entry) for entry in result)
                return _publish(boundary, result)

            return read
    raise ValueError('Метод объекта не обнаружен: ' + name)
