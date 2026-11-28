"""Standalone owned HTTP settings. No certificate store, file or network operations."""

from decimal import Decimal
from weakref import ref

from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.http.http_security import (
    BSLInternetProxy as _PROXY,
    BSLOSCertificationAuthorityCertificates as _OS_CA,
    BSLOpenSSLSecureConnection as _TLS,
)
from yadinassi.types.values import HostFunction


CONSTRUCTORS = {
    'internetproxy': _PROXY, 'интернетпрокси': _PROXY,
    'oscertificationauthoritycertificates': _OS_CA,
    'сертификатыудостоверяющихцентровос': _OS_CA,
    'opensslsecureconnection': _TLS, 'защищенноесоединениеopenssl': _TLS,
}
TYPE_IDS = frozenset(map(id, CONSTRUCTORS.values()))
_OWNERS = {}
_TLS_READ = _TLS.get_member
_TLS_FIELDS = frozenset((
    'clientcertificate', 'сертификатклиента',
    'certificationauthoritycertificates', 'сертификатыудостоверяющихцентров',
))
_PROXY_SET = _PROXY.set
_PROXY_METHODS = {
    alias: method for aliases, method in (
        (('set', 'установить'), _PROXY_SET),
        (('server', 'сервер'), _PROXY.server),
        (('port', 'порт'), _PROXY.port),
        (('user', 'пользователь'), _PROXY.user),
        (('password', 'пароль'), _PROXY.password),
        (('useosauthentication', 'использоватьаутентификациюос'), _PROXY.use_os_authentication),
    ) for alias in aliases
}
_PROXY_HOLES = frozenset((2, 3, 4, 5))


def _standalone(boundary):
    from yadinassi.runtime import Interpreter

    vm = boundary.vm
    if (type(vm) is not Interpreter or vm.execution_context != 'client' or getattr(vm, 'application', None) is not None
            or vm.database_context is not None or vm._configuration_runtime is not None):
        raise BoundaryViolation('HTTP settings require a standalone interpreter')
    return vm._family_owner


def _owned(value, family):
    entry = _OWNERS.get(id(value))
    if entry is None or entry[0]() is not value or entry[1]() is not family:
        raise BoundaryViolation('foreign HTTP settings')


def _remember(value, family):
    identity = id(value)

    def forget(dead):
        entry = _OWNERS.get(identity)
        if entry is not None and entry[0] is dead:
            del _OWNERS[identity]

    _OWNERS[identity] = ref(value, forget), ref(family)
    return value


def constructor(boundary, name, factory, *, require_value=False, allow_references=False, **unused):
    _standalone(boundary)
    boundary._check_effect()
    kind = CONSTRUCTORS[name]
    if type(factory) is not HostFunction or factory.function is not kind:
        raise BoundaryViolation('HTTP settings constructor requires canonical registration')
    boundary._validate_host_function(factory, require_value, allow_references)

    def create(*args):
        boundary._before('call_value', name)
        if not boundary._verify_context:
            boundary._check_effect()
        family = _standalone(boundary)
        if boundary.vm.types.get(name) is not factory or factory.function is not kind:
            raise BoundaryViolation('HTTP settings constructor binding changed')
        if kind is _TLS and len(args) == 2:
            authority = args[1]
            if type(authority) is not _OS_CA:
                raise ValueError('TLS: явно укажите сертификаты УЦ ОС')
            _owned(authority, family)
        return _remember(kind(*args), family)

    if kind is _TLS:
        def prepare_omissions(bound, positions, count):
            if count != 2 or positions != (0,):
                raise TypeError('TLS: пропущен обязательный аргумент')
            return bound, {0: None}
        create.prepare_omissions = prepare_omissions
    if allow_references:
        create.requires_reference = lambda index: False
    return create


def get(boundary, value, name):
    family = _standalone(boundary)
    boundary._check_effect()
    _owned(value, family)
    if type(value) is not _TLS or name.casefold() not in _TLS_FIELDS:
        raise ValueError('Поле объекта не обнаружено: ' + name)
    result = _TLS_READ(value, name)
    if result is not None:
        if type(result) is not _OS_CA:
            raise BoundaryViolation('HTTP settings authority changed')
        _owned(result, family)
    return result


def resolve(boundary, value, name, *, require_value=False, omitted=()):
    family = _standalone(boundary)
    boundary._check_effect()
    _owned(value, family)
    key = name.casefold()
    method = _PROXY_METHODS.get(key) if type(value) is _PROXY else None
    if method is None:
        raise ValueError('Метод объекта не обнаружен: ' + name)
    if require_value and method is _PROXY_SET:
        raise TypeError('Процедура не возвращает значение: ' + name)
    if omitted and (method is not _PROXY_SET or any(index not in _PROXY_HOLES for index in omitted)):
        raise TypeError('Пропущен обязательный аргумент настройки прокси')

    def invoke(*args):
        boundary._before('call_value', key)
        if not boundary._verify_context:
            boundary._check_effect()
        _owned(value, _standalone(boundary))
        if method is _PROXY_SET and len(args) >= 3 and args[2] is not None:
            # Keep the shared stream number parser's type comparisons inert.
            kind = type(args[2])
            if kind is not int and kind is not Decimal:
                raise ValueError('Двоичные данные: недопустимое целое число')
        return method(value, *args)

    return invoke
