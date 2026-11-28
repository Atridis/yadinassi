"""Detached scalar helpers for an already-admitted ordinary server form."""

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from yadinassi.execution.codegen.direct_emitter import compile_owned
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen.direct_errors import convert_error
from yadinassi.forms.form_model import scalar
from yadinassi.temporal.dates import BSLDate, MAX_TICKS
from yadinassi.types.values import NULL
from .python_direct import _snapshot
from .python_direct_forms import FormBoundary
from .python_direct_source import _signature, _signature_matches


_SCALAR_TYPES = frozenset(map(id, (str, bool, Decimal, BSLDate)))
_DATE_TICKS = vars(BSLDate)['ticks']
_DATE_BOUNDARY = vars(BSLDate)['boundary']


def _scalar(value):
    if type(value) is int:
        if value.bit_length()>426:
            raise ValueError('Форма: превышен предел числа')
        value=Decimal(value)
    if value is not None and value is not NULL and id(type(value)) not in _SCALAR_TYPES:
        raise TypeError('Form NoContext helpers accept only scalar values')
    if type(value) is BSLDate:
        # Repeat the Date constructor's payload invariant on host-provided
        # values, using the pinned slots so validation cannot run host hooks.
        try:
            ticks = _DATE_TICKS.__get__(value)
            boundary = _DATE_BOUNDARY.__get__(value)
        except AttributeError:
            raise ValueError('invalid form NoContext Date payload') from None
        if (type(ticks) is not int or type(boundary) is not bool
                or not 0 <= ticks <= MAX_TICKS or (boundary and ticks not in (0, MAX_TICKS))):
            raise ValueError('invalid form NoContext Date payload')
        return value
    return scalar(value)


@dataclass(frozen=True, slots=True)
class _Prepared:
    owner: object
    routines: MappingProxyType
    plan: object
    function: object
    constants: tuple


def prepare(session, routines, source):
    admitted = {}
    for routine in routines:
        signature = _signature(routine)
        name = signature[0].casefold()
        if (name in admitted or signature[1] != 'server' or any(signature[3:6])
                or any(not by_value or not required for _, by_value, required in signature[7])):
            raise ValueError('form NoContext helpers require synchronous server routines with required Val parameters')
        admitted[name] = routine, signature
    plan = compile_owned(_snapshot(routines), source_text=source, source_name='<form-nocontext>',
                         exports=True, meter_loops=True, retain_generated=False)
    return _Prepared(session.interpreter, MappingProxyType(admitted), plan, plan.function, plan.constants)


class _DetachedBoundary(BoundaryContext):
    def _unregistered_service(self, name):
        # The helper has no host service table. This is an unsupported BSL
        # operation, not a revoked form authority or uncertain transport.
        raise ValueError('Host service is unavailable in a form NoContext helper: ' + name)


class FormWithNoContext(FormBoundary):
    def __init__(self, session, routine):
        super().__init__(session, routine)
        prepared = session._direct_form_nocontext
        if type(prepared) is not _Prepared:
            raise BoundaryViolation('unprepared form NoContext helpers')
        self._prepared_helpers = prepared

    def resolve_service(self, name, *args, **kwargs):
        prepared = self._prepared_helpers
        key = name.casefold()
        item = prepared.routines.get(key)
        if item is None:
            return super().resolve_service(name, *args, **kwargs)
        routine, signature = item
        arity = len(signature[7])

        def check():
            if self.session.interpreter is not prepared.owner or self.owner is not prepared.owner:
                raise BoundaryViolation('form NoContext interpreter changed')
            self._check()
            if (self.owner.execution_context != 'server'
                    or self.routine.execution_context != 'server'
                    or self.session._direct_form_nocontext is not prepared
                    or self.owner.server_routines.get(key) is not routine
                    or prepared.plan.function is not prepared.function
                    or prepared.plan.constants is not prepared.constants
                    or not _signature_matches(routine, signature)):
                raise BoundaryViolation('form NoContext helper binding changed')

        check()
        if kwargs.get('require_value', False) and not signature[2]:
            raise TypeError('Процедура не возвращает значение: ' + name)
        if kwargs.get('argument_count') != arity:
            raise TypeError('form NoContext helper argument count')

        def invoke(*values):
            check()
            # Scalars cannot carry form or host authority into the helper.
            actuals = tuple(_scalar(value) for value in values)
            if len(actuals) != arity:
                raise TypeError('form NoContext helper argument count')
            # No interpreter, services, module data, form members or transport.
            # Leave the suspended contextual VM untouched; debit its live event
            # budget at the generated plan's normal authority checkpoints.
            detached = _DetachedBoundary()
            detached.checkpoint = self.checkpoint
            detached._handled_errors = self._handled_errors
            detached.enter()
            try:
                exports = prepared.function({}, prepared.constants, detached)
                return _scalar(exports[key](*actuals))
            except Exception as error:
                converted = convert_error(error, prepared.plan.source_name, prepared.plan.source_text)
                if converted is error:
                    raise
                raise converted from None
            finally:
                detached.revoke()
                check()

        invoke.requires_reference = lambda index: False
        return invoke
