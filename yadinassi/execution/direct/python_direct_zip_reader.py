"""Standalone ZIP file reading/writing and anchored extraction."""
from weakref import ref

from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.streams.zip_archives import BSLZipFileReader, BSLZipFileEntries, BSLZipFileEntry, BSLZipFileWriter
from yadinassi.types.values import HostFunction

CONSTRUCTORS = dict.fromkeys(('zipfilereader', 'чтениеzipфайла'), BSLZipFileReader)
CONSTRUCTORS.update(dict.fromkeys(('zipfilewriter', 'записьzipфайла'), BSLZipFileWriter))
NAMES = frozenset(CONSTRUCTORS)
_TYPES = (BSLZipFileReader, BSLZipFileEntries, BSLZipFileEntry, BSLZipFileWriter)
_READ = {id(kind): kind.get_member for kind in _TYPES}
TYPE_IDS = frozenset(_READ)
_OWNERS = {}
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
        _source(source, optional=True)
        try:
            return _publish(boundary, expected(source, *options))
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
            if method in _WRITER_PATHS and actuals:
                _source(actuals[0])
            try:
                return method(value, *actuals)
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
                _source(actuals[0])
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
