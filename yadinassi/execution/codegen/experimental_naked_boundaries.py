"""Optional boundary primitives for the UNSAFE naked-translator experiment.

Not connected to production VM policy, AST authority or node budgets. A budget
unit is one generated loop header calling checkpoint(), not one BSL AST node.
Registered services are trusted Python capabilities, not a Python sandbox.
Post-call invalidation does not undo a service's already completed side effects.
"""
from dataclasses import dataclass
from decimal import Decimal
from yadinassi.types.values import HostFunction, _DIRECT_INTERPRETER_CALL_TYPE
from yadinassi.temporal.dates import BSLDate
_MISSING=object()
_SCALAR_TYPE_IDS = frozenset(map(id, (str, int, bool, Decimal, BSLDate, type(None))))


class BoundaryViolation(BaseException):
    """Fail-closed boundary rejection; raw BSL except Exception cannot swallow it."""


class UnsupportedHostSignature(BoundaryViolation):
    """Unsupported dynamic byref signature rejected before argument effects."""

@dataclass(frozen=True)
class HostMembers:
    value: object
    readable: tuple = ()
    writable: tuple = ()
    callable: tuple = ()


class BoundaryContext:
    _verify_context = True

    def __init__(self, *, services=None, members=(), loop_budget=None, policy=None):
        if loop_budget is not None and (type(loop_budget) is not int or loop_budget < 0):
            raise ValueError('loop_budget must be a nonnegative integer or None')
        self._services = {name.casefold(): function for name, function in (services or {}).items()}
        self._members = {}
        for capability in members:
            self.expose(capability)
        self.loop_budget = loop_budget
        self.loop_backedges = 0
        self.policy = policy
        self._epoch = 0
        self._admitted_epoch = None
        self._revoked = False
        self._handled_errors = []

    def external_get(self, name):
        """Explicit product namespace seam; ordinary contexts grant none."""
        self._check()
        raise BoundaryViolation('unregistered external namespace: '+name)

    def external_set(self, name, value):
        self._check()
        raise BoundaryViolation('unregistered external namespace: '+name)

    def external_reference(self, name):
        # Keep the managed-form bare-attribute byref limitation explicit.
        self._check()
        raise TypeError("Форма: передача реквизита без Знач пока не поддерживается")

    def _validate_host_function(self,value,require_value,allow_references=False):
        if type(value) is not HostFunction:raise TypeError('Значение не является функцией')
        if value.reference_parameters and not allow_references:
            raise UnsupportedHostSignature('dynamic HostFunction reference parameters require explicit argument lowering')
        if require_value and not value.returns_value:
            raise TypeError('Процедура не возвращает значение: '+value.name)

    def expose(self, capability):
        """Trusted host explicitly grants members, including on a new result.

        Merely returning an object from a registered service grants nothing.
        This API is for the trusted embedding, not translated BSL reflection.
        """
        if type(capability) is not HostMembers:
            raise TypeError('expose requires explicit HostMembers')
        self._members[id(capability.value)] = (
            capability.value,
            frozenset(name.casefold() for name in capability.readable),
            frozenset(name.casefold() for name in capability.writable),
            frozenset(name.casefold() for name in capability.callable),
        )
        return capability.value

    def resolve_optional_service(self,name,*args,**kwargs):
        """Only generated calls with positional holes enter this path."""
        return self.resolve_service(name,*args,**kwargs)

    def resolve_service(self,name,fallback=_MISSING,*,require_value=False,allow_references=False,argument_count=None):
        if self._verify_context:self._check()
        key=name.casefold()
        if key not in self._services:
            if fallback is not _MISSING:
                return self.resolve_extension_value(fallback,require_value=require_value,allow_references=allow_references)
            raise BoundaryViolation('unregistered host service: '+name)
        function=self._services[key]  # Registered service outranks a variable.
        if key in ('errordescription','описаниеошибки','errorinfo','информацияобошибке') and type(function) is HostFunction:
            from .experimental_naked_errors import description_service
            function=description_service(self,function)
        if type(function) is HostFunction:
            if getattr(self,'_direct_transaction_owner',None) is not None:
                from yadinassi.execution.direct.python_direct_transactions import service as transaction_service
                function=transaction_service(self,function)
            self._validate_host_function(function,require_value,allow_references)
            if type(function.function) is _DIRECT_INTERPRETER_CALL_TYPE:
                raise ValueError('interpreter-aware call requires an explicit interpreter dispatch')
        def invoke(*args):
            self._before('call',key)
            # Standalone BSL scalars do not execute Python hooks. An embedding
            # can still pass opaque values or install an output callback; these
            # are actual host boundaries, not ordinary runtime probes.
            guarded = self._verify_context or (
                key in ('message','сообщить')
                or any(id(type(arg)) not in _SCALAR_TYPE_IDS for arg in args))
            if guarded and not self._verify_context:self._check_effect()
            try:return function(*args)
            except PermissionError as error:raise BoundaryViolation(str(error)) from error
            finally:
                if guarded:self._check_effect()
        if allow_references:invoke.requires_reference=lambda index: type(function) is HostFunction and index in function.reference_parameters
        return invoke

    def resolve_member(self,value,name):
        key=self._member(value,name,3)
        try:function=getattr(value,key)
        except PermissionError as error:raise BoundaryViolation(str(error)) from error
        finally:self._check()
        if not callable(function):raise TypeError('Значение не является функцией')
        def invoke(*args):
            # Capability revocation and policy are fresh, callee binding is not.
            self._member(value,key,3)
            self._before('call_member',key)
            try:return function(*args)
            except PermissionError as error:raise BoundaryViolation(str(error)) from error
            finally:self._check()
        return invoke



    def resolve_extension_value(self,value,*,require_value=False,allow_references=False):
        if getattr(self,'_restrict_python_extensions',False):
            return self.resolve_callable(value,require_value=require_value,
                allow_references=allow_references,_extension_value=True)
        return self.resolve_callable(value,require_value=require_value,allow_references=allow_references)

    def resolve_callable(self,value,*,require_value=False,allow_references=False,_extension_value=False):
        if self._verify_context or _extension_value:self._check()
        if _extension_value and type(value) is HostFunction:
            from yadinassi.execution.direct.python_direct_captured_values import resolve
            bound=resolve(self,value,require_value=require_value,allow_references=allow_references)
            if bound is not None:return bound
            raise BoundaryViolation('callable Python values require allow_extensions=True')
        if type(value) is HostFunction and getattr(self,'_direct_transaction_owner',None) is not None:
            from yadinassi.execution.direct.python_direct_transactions import service as transaction_service
            value=transaction_service(self,value)
        self._validate_host_function(value,require_value,allow_references)
        if type(value.function) is _DIRECT_INTERPRETER_CALL_TYPE:
            raise ValueError('interpreter-aware call requires an explicit interpreter dispatch')
        # Bind the canonical wrapper, not its mutable implementation field.
        name=value.name.casefold()
        def invoke(*args):
            self._before('call_value',name)
            try:return value(*args)
            except PermissionError as error:raise BoundaryViolation(str(error)) from error
            finally:
                if self._verify_context or _extension_value:self._check()
        # Canonical HostFunction metadata is supplied by the trusted embedding.
        # Read it per argument, as callbacks can change it during evaluation.
        if allow_references:invoke.requires_reference=lambda index: index in value.reference_parameters
        return invoke

    def invoke_callable(self,value,*args):
        return self.resolve_callable(value)(*args)

    def resolve_set_member(self,value,name):
        key=self._member(value,name,2)
        def write(new_value):
            self._member(value,key,2)
            self._before('set_member',key)
            try:setattr(value,key,new_value)
            except PermissionError as error:raise BoundaryViolation(str(error)) from error
            finally:self._check()
        return write

    def resolve_optional_open_file(self,value,name,*,require_value=False,omitted=(),argument_count=None):
        return self.resolve_member_call(value,name,require_value=require_value,omitted=omitted)

    def resolve_member_call(self, value, name, *, require_value=False, omitted=()):
        """Call-site facts for receivers with a stricter public call protocol."""
        return self.resolve_member(value, name)

    def reference_member(self, value, name):
        """Bind a host output slot with one eager read before entering callee.

        Binding requires read access only; a later set checks write access.
        No backing dict or raw host attribute is exposed to generated code.
        """
        self._member(value, name, 1)
        self.get_member(value, name)
        return _HostMemberReference(self, value, name)

    def reference_index(self, value, index):
        """Bind through explicit host indexing capabilities, without reflection.

        Read-only slots are valid arguments. Writes require __setitem__ only
        when the callee actually writes, matching deferred byref authority.
        """
        self.call_member(value, '__getitem__', index)
        return _HostIndexReference(self, value, index)

    def revoke(self):
        self._epoch += 1
        self._revoked = True

    def enter(self):
        self.start()

    def leave(self):
        pass

    def start(self):
        self._start_lease()
        if self._verify_context:self._check()

    def _start_lease(self):
        if self._revoked:
            raise BoundaryViolation('execution authority revoked')
        self._admitted_epoch = self._epoch
        self.loop_backedges = 0

    def _check_effect(self):
        self._check()

    def _check(self):
        self._check_lease()

    def _check_lease(self):
        if self._admitted_epoch is None:
            raise BoundaryViolation('execution boundary not started')
        if self._revoked or self._epoch != self._admitted_epoch:
            raise BoundaryViolation('execution authority revoked')

    def _check_loop(self):
        self._check()

    def checkpoint(self):
        self._check_loop()
        if self.loop_budget is not None and self.loop_backedges >= self.loop_budget:
            raise BoundaryViolation('generated loop backedge budget exhausted')
        self.loop_backedges += 1

    def _before(self, operation, name):
        policy=self.policy
        if self._verify_context or policy is not None:self._check()
        if policy is not None:
            try:permitted=policy(operation,name)
            except PermissionError as error:raise BoundaryViolation(str(error)) from error
            if permitted is False:raise BoundaryViolation('service policy denied: '+name)
            self._check()

    def _run(self, operation, name, function, args):
        self._before(operation, name)
        try:
            return function(*args)
        except PermissionError as error:
            raise BoundaryViolation(str(error)) from error
        finally:
            self._check()  # Invalidated services are never retried.

    def invoke(self, name, *args):
        self._check()
        key = name.casefold()
        if key not in self._services:
            raise BoundaryViolation('unregistered host service: ' + name)
        return self._run('call', key, self._services[key], args)

    def _member(self, value, name, index):
        self._check()
        key = name.casefold()
        capability = self._members.get(id(value))
        if capability is None or capability[0] is not value or key not in capability[index]:
            raise BoundaryViolation('unregistered host member: ' + name)
        return key

    def get_member(self, value, name):
        key = self._member(value, name, 1)
        return self._run('get_member', key, getattr, (value, key))

    def set_member(self, value, name, new_value):
        key = self._member(value, name, 2)
        return self._run('set_member', key, setattr, (value, key, new_value))

    def call_member(self, value, name, *args):
        key = self._member(value, name, 3)
        self._before('call_member', key)
        try:
            function = getattr(value, key)
            self._check()  # A permitted descriptor may revoke before returning.
            return function(*args)
        except PermissionError as error:
            raise BoundaryViolation(str(error)) from error
        finally:
            self._check()


class _HostMemberReference:
    __slots__ = ('_context', '_value', '_name')

    def __init__(self, context, value, name):
        self._context = context
        self._value = value
        self._name = name

    def get(self):
        return self._context.get_member(self._value, self._name)

    def set(self, value):
        return self._context.set_member(self._value, self._name, value)

    value = property(get, set)


class _HostIndexReference:
    __slots__ = ('_context', '_value', '_index')

    def __init__(self, context, value, index):
        self._context = context
        self._value = value
        self._index = index

    def get(self):
        return self._context.call_member(self._value, '__getitem__', self._index)

    def set(self, value):
        return self._context.call_member(self._value, '__setitem__', self._index, value)

    value = property(get, set)
