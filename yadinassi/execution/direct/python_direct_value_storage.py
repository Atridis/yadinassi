"""Canonical standalone ValueStorage constructor and bounded Get."""

from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.formats.storage import value_storage as storage
from yadinassi.types.values import HostFunction

_NAMES = ('valuestorage', 'хранилищезначения')
_GET = ('get', 'получить')
_STORAGE = storage.BSLValueStorage
_DEFLATION_NAMES = ('deflation', 'сжатиеданных')
_DEFLATION = storage.BSLDeflation


def constructor(boundary, key, factory, *, require_value=False, allow_references=False, **unused):
    from .source.python_direct_source_value_storage import check_factories

    aliases, expected = (_NAMES, _STORAGE) if key in _NAMES else (_DEFLATION_NAMES, _DEFLATION)

    def validate():
        boundary._check_effect()
        check_factories()
        registry = boundary.vm.types
        if (type(registry) is not dict or type(factory) is not HostFunction
                or factory.function is not expected or factory.returns_value is not True
                or type(factory.reference_parameters) is not frozenset or factory.reference_parameters
                or any(registry.get(alias) is not factory for alias in aliases)):
            raise BoundaryViolation('direct ValueStorage constructor binding changed')

    validate()
    boundary._validate_host_function(factory, require_value, allow_references)

    def create(*values):
        boundary._before('call_value', key)
        validate()
        if expected is _DEFLATION:
            return _DEFLATION(*values)
        if not 1 <= len(values) <= 2:
            raise TypeError('ValueStorage requires one value and optional compression')
        snapshot = storage.capture(values[0], compression=values[1] if len(values) == 2 else None,
                                   _source_direct=True)
        return _STORAGE._from_snapshot(snapshot)

    def prepare_omissions(current, positions, count):
        if count != 2 or positions != (1,):
            raise TypeError('ValueStorage value argument is required')
        return current, {1: None}

    if expected is _STORAGE:
        create.prepare_omissions = prepare_omissions
    if allow_references:
        create.requires_reference = lambda index: False
    return create


def resolve_get(boundary, value, name, *, omitted=()):
    from .source.python_direct_source_value_storage import check_factories, _snapshot

    if type(value) is not _STORAGE or type(name) is not str or name.casefold() not in _GET:
        raise ValueError('ValueStorage member unavailable')
    if omitted:
        raise TypeError('ValueStorage.Get takes no arguments')
    boundary._check_effect()
    check_factories()
    original = storage._required_field(value, '_snapshot')

    def get(*values):
        if values:
            raise TypeError('ValueStorage.Get takes no arguments')
        boundary._before('call_member', name.casefold())
        boundary._check_effect()
        check_factories()
        if storage._required_field(value, '_snapshot') is not original:
            raise BoundaryViolation('direct ValueStorage snapshot changed during argument evaluation')
        if type(original) is not storage.Snapshot:
            raise storage.SnapshotError('expected an internal snapshot')
        storage._required_field(original, '_root')
        try:
            _snapshot(original)
        except BoundaryViolation as error:
            raise storage.SnapshotError(str(error)) from None
        return storage.restore(original)

    return get
