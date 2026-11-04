"""Local scalar simulation of freshly analyzed IR, never a BSL/host executor.

This API supplies no activation, persistence, native compatibility or rollback
guarantee. It accepts source, not an externally constructed analysis/IR object.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import (Clamped, Context, Decimal, DecimalException, DivisionByZero,
                     FloatOperation, Inexact, InvalidOperation, Overflow,
                     ROUND_HALF_EVEN, Rounded, Subnormal, Underflow, localcontext)
import re
from uuid import UUID

from .catalog_backend import CatalogSchema, FieldSchema
from .object_module_analysis import (ObjectModuleAnalysis, ObjectModuleAnalysisError,
                                     ObjectModuleBinding, analyze_object_module)

PROFILE = 'catalog-before-write-pure-simulation-v1'
NATIVE_PARITY = False
MAX_SOURCE_BYTES = 16384
MAX_STRING = 1024
MAX_NUMBER_TEXT = 60
MAX_DIGITS = 38
MAX_SCALE = 18
MAX_STEPS = 8192
MAX_VALUE_BYTES = 1048576
MAX_CALL_DEPTH = 16
MAX_EXPRESSION_DEPTH = 48
MAX_BLOCK_DEPTH = 48
_NUMBER_TEXT = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?')
_IR_NUMBER_TEXT = re.compile(r'-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?')
_UNSET = object()
_ERRORS = frozenset(('invalid_input', 'source_rejected', 'invalid_ir',
                     'type_mismatch', 'numeric_limit', 'division_by_zero',
                     'field_limit', 'resource_limit'))


class ObjectModuleSimulationError(ValueError):
    """A closed, value-free category; never a successful cancellation result."""
    def __init__(self, code):
        if type(code) is not str or code not in _ERRORS:
            raise ValueError('invalid simulation error')
        self.code = code
        super().__init__('object module simulation: ' + code)


def _fail(code):
    raise ObjectModuleSimulationError(code) from None


@dataclass(frozen=True, slots=True)
class NumberValue:
    """Bounded fixed-point text on the public boundary, NOT an external Decimal.

    Construction is not admission. Every simulation validates the exact type,
    text length, ASCII grammar and numeric range before creating a Decimal.
    """
    text: str


@dataclass(frozen=True, slots=True)
class ScalarSnapshot:
    code: str
    description: str
    values: tuple  # NumberValue / exact bool / exact naive second datetime.


@dataclass(frozen=True, slots=True)
class SimulationResult:
    snapshot: ScalarSnapshot
    cancel: bool
    profile: str = PROFILE
    native_parity: bool = NATIVE_PARITY


def _attribute(value, name):
    # Only called after checking the exact known slotted class. An incomplete
    # object.__new__ instance is malformed input, not an opportunity for repr.
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        _fail('invalid_input')


def _text(value, limit, code='invalid_input'):
    if type(value) is not str or len(value) > limit:
        _fail(code)
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        _fail(code)
    return value


def _identity(value):
    if type(value) is not UUID:
        _fail('invalid_input')
    number = _attribute(value, 'int')
    if type(number) is not int or not 1 <= number < 2**128:
        _fail('invalid_input')
    return UUID(int=number)


def _binding_copy(binding):
    """Detach exact primitive metadata before the existing analyzer sees it."""
    if type(binding) is not ObjectModuleBinding:
        _fail('invalid_input')
    database = _identity(_attribute(binding, 'database_id'))
    configuration = _identity(_attribute(binding, 'configuration_id'))
    generation = _attribute(binding, 'configuration_generation')
    if type(generation) is not int or not 1 <= generation <= 2**63 - 1:
        _fail('invalid_input')
    digest = _text(_attribute(binding, 'source_sha256'), 64)
    catalog = _attribute(binding, 'catalog')
    if type(catalog) is not CatalogSchema:
        _fail('invalid_input')
    identity = _identity(_attribute(catalog, 'identity'))
    name = _text(_attribute(catalog, 'name'), 128)
    code_length = _attribute(catalog, 'code_length')
    description_length = _attribute(catalog, 'description_length')
    if (type(code_length) is not int or not 1 <= code_length <= 64 or
            type(description_length) is not int or not 0 <= description_length <= MAX_STRING):
        _fail('invalid_input')
    # Refuse unsupported section metadata instead of dropping it while copying.
    sections = _attribute(catalog, 'tabular_sections')
    if type(sections) is not tuple or len(sections) != 0:
        _fail('invalid_input')
    fields = _attribute(catalog, 'fields')
    if type(fields) is not tuple or len(fields) > 64:
        _fail('invalid_input')
    copied = []
    for field in fields:
        if type(field) is not FieldSchema:
            _fail('invalid_input')
        field_identity = _identity(_attribute(field, 'identity'))
        field_name = _text(_attribute(field, 'name'), 128)
        kind = _text(_attribute(field, 'kind'), 16)
        qualifiers = _attribute(field, 'qualifiers')
        if (type(qualifiers) is not tuple or len(qualifiers) > 3 or
                _attribute(field, 'target_catalog_id') is not None):
            _fail('invalid_input')
        for qualifier in qualifiers:
            if type(qualifier) is str:
                _text(qualifier, 16)
            elif type(qualifier) is not int or not 0 <= qualifier <= MAX_DIGITS:
                _fail('invalid_input')
        copied.append(FieldSchema(field_identity, field_name, kind, tuple(qualifiers)))
    schema = CatalogSchema(identity, name, code_length, description_length, tuple(copied))
    return ObjectModuleBinding(database, configuration, generation, schema, digest)


def _context():
    # Every field is explicit, including traps: neither getcontext() nor mutable
    # DefaultContext contributes precision, flags or exception behavior.
    return Context(prec=80, rounding=ROUND_HALF_EVEN, Emin=-80, Emax=80,
                   capitals=1, clamp=0, flags=[],
                   traps=[Clamped, DivisionByZero, FloatOperation, Inexact,
                          InvalidOperation, Overflow, Rounded, Subnormal, Underflow])


class _Budget:
    def __init__(self):
        self.steps = MAX_STEPS
        self.value_bytes = MAX_VALUE_BYTES

    def step(self, count=1):
        if count > self.steps:
            _fail('resource_limit')
        self.steps -= count

    def value(self, size):
        if size > self.value_bytes:
            _fail('resource_limit')
        self.value_bytes -= size


def _number(value, budget):
    """Private Decimal only: constructors/operations already have bounded size."""
    if type(value) is not Decimal or not value.is_finite():
        _fail('numeric_limit')
    sign, digits, exponent = value.as_tuple()
    # The largest input is a <=60-character token. Arithmetic precision is 80.
    if len(digits) > 80 or type(exponent) is not int or not -160 <= exponent <= 80:
        _fail('numeric_limit')
    if not any(digits):
        budget.value(1)
        return Decimal(0)
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    if exponent > 0:
        if len(digits) + exponent > MAX_DIGITS:
            _fail('numeric_limit')
        digits.extend([0] * exponent)
        exponent = 0
    if len(digits) > MAX_DIGITS or exponent < -MAX_SCALE:
        _fail('numeric_limit')
    budget.value(len(digits) + 3)
    return Decimal((sign, tuple(digits), exponent))


def _read_number(value, budget, *, literal=False):
    if not literal:
        if type(value) is not NumberValue:
            _fail('invalid_input')
        value = _attribute(value, 'text')
    pattern = _IR_NUMBER_TEXT if literal else _NUMBER_TEXT
    if (type(value) is not str or not 1 <= len(value) <= MAX_NUMBER_TEXT or
            pattern.fullmatch(value) is None):
        _fail('invalid_ir' if literal else 'invalid_input')
    return _number(Decimal(value), budget)


def _date(value):
    if (type(value) is not datetime or value.tzinfo is not None or
            value.microsecond != 0 or value.fold != 0):
        _fail('type_mismatch')
    # Exact datetime is not sufficient: its bytes-based pickle constructor can
    # admit invalid calendar/time fields. Reconstruct to validate their ranges.
    try:
        return datetime(value.year, value.month, value.day,
                        value.hour, value.minute, value.second)
    except (ValueError, OverflowError):
        _fail('type_mismatch')


def _field(value, kind, limit=None):
    if kind == 'string':
        return _text(value, limit, 'field_limit')
    if kind == 'boolean':
        if type(value) is not bool:
            _fail('type_mismatch')
        return value
    if kind == 'datetime':
        return _date(value)
    if kind == 'number':
        if type(value) is not Decimal:
            _fail('type_mismatch')
        # Private numbers are finite, canonical and <=38 digits. No quantize,
        # coercion, rounding or context-dependent abs is required here.
        _, digits, exponent = value.as_tuple()
        if exponent < -2 or len(digits) + exponent > 10:
            _fail('field_limit')
        return value
    _fail('invalid_ir')


def _snapshot_copy(snapshot, catalog, budget):
    if type(snapshot) is not ScalarSnapshot:
        _fail('invalid_input')
    code = _field(_attribute(snapshot, 'code'), 'string', catalog.code_length)
    description = _field(_attribute(snapshot, 'description'), 'string', catalog.description_length)
    raw = _attribute(snapshot, 'values')
    if type(raw) is not tuple or len(raw) != len(catalog.fields):
        _fail('invalid_input')
    budget.value(4 * (len(code) + len(description)))
    values = {'code': code, 'description': description}
    for field, value in zip(catalog.fields, raw):
        budget.step()
        if field.kind == 'number':
            value = _read_number(value, budget)
        value = _field(value, field.kind)
        budget.value(16 if field.kind == 'datetime' else 1)
        values[field.name.casefold()] = value
    return values


class _Cell:
    __slots__ = ('value', 'cancel')

    def __init__(self, value=_UNSET, *, cancel=False):
        self.value = value
        self.cancel = cancel

    def get(self):
        if self.value is _UNSET:
            _fail('invalid_ir')
        return self.value

    def set(self, value):
        if self.cancel and type(value) is not bool:
            _fail('type_mismatch')
        self.value = value


def _boolean(value):
    if type(value) is not bool:
        _fail('type_mismatch')
    return value


class _Simulation:
    def __init__(self, analysis, values, budget, context):
        self.procedures = {p.name: p for p in analysis.procedures}
        self.values = values
        self.budget = budget
        self.context = context
        catalog = analysis.binding.catalog
        self.fields = {'code': ('string', catalog.code_length),
                       'description': ('string', catalog.description_length)}
        self.fields.update((f.name.casefold(), (f.kind, None)) for f in catalog.fields)

    def expression(self, node, frame, depth=0):
        self.budget.step()
        if depth > MAX_EXPRESSION_DEPTH:
            _fail('resource_limit')
        operation, args = node.operation, node.arguments
        if operation == 'local':
            return frame[args[0]].get()
        if operation == 'field':
            return self.values[args[0]]
        if operation == 'string':
            value = _text(args[0], MAX_STRING, 'invalid_ir')
            self.budget.value(4 * len(value))
            return value
        if operation == 'number':
            return _read_number(args[0], self.budget, literal=True)
        if operation == 'boolean':
            return _boolean(args[0])
        if operation == 'undefined':
            return None
        if operation == 'unary':
            operator, operand = args
            value = self.expression(operand, frame, depth + 1)
            if operator == 'NOT':
                return not _boolean(value)
            if type(value) is not Decimal:
                _fail('type_mismatch')
            if operator == '+':
                return value
            if operator == '-':
                return _number(value.copy_negate(), self.budget)
            _fail('invalid_ir')
        if operation == 'conditional':
            condition, yes, no = args
            selected = yes if _boolean(self.expression(condition, frame, depth + 1)) else no
            return self.expression(selected, frame, depth + 1)
        if operation != 'binary':
            _fail('invalid_ir')
        operator, left, right = args
        left = self.expression(left, frame, depth + 1)
        if operator == 'AND':
            return _boolean(left) and _boolean(self.expression(right, frame, depth + 1))
        if operator == 'OR':
            return _boolean(left) or _boolean(self.expression(right, frame, depth + 1))
        right = self.expression(right, frame, depth + 1)
        if operator in ('=', '<>'):
            if type(left) is not type(right):
                _fail('type_mismatch')
            equal = left == right
            return equal if operator == '=' else not equal
        if operator in ('<', '<=', '>', '>='):
            if type(left) is not type(right) or type(left) not in (Decimal, str):
                _fail('type_mismatch')
            if operator == '<': return left < right
            if operator == '<=': return left <= right
            if operator == '>': return left > right
            return left >= right
        if operator == '+' and type(left) is str and type(right) is str:
            size = len(left) + len(right)
            if size > MAX_STRING:
                _fail('resource_limit')
            self.budget.value(4 * size)
            return left + right
        if type(left) is not Decimal or type(right) is not Decimal:
            _fail('type_mismatch')
        if operator in ('/', '%') and right.is_zero():
            _fail('division_by_zero')
        # Explicit Context methods, never ambient arithmetic or host dispatch.
        try:
            if operator == '+': value = self.context.add(left, right)
            elif operator == '-': value = self.context.subtract(left, right)
            elif operator == '*': value = self.context.multiply(left, right)
            elif operator == '/': value = self.context.divide(left, right)
            elif operator == '%': value = self.context.remainder(left, right)
            else: _fail('invalid_ir')
        except DecimalException:
            _fail('numeric_limit')
        return _number(value, self.budget)

    def block(self, body, frame, call_depth, block_depth=0):
        if block_depth > MAX_BLOCK_DEPTH:
            _fail('resource_limit')
        for node in body:
            self.budget.step()
            operation, args = node.operation, node.arguments
            if operation == 'return':
                return True
            if operation == 'assign':
                target, expression = args
                value = self.expression(expression, frame)
                if target.operation == 'local':
                    frame[target.arguments[0]].set(value)
                elif target.operation == 'field':
                    name = target.arguments[0]
                    self.values[name] = _field(value, *self.fields[name])
                else:
                    _fail('invalid_ir')
            elif operation == 'if':
                branches, selected = args
                for condition, branch in branches:
                    if _boolean(self.expression(condition, frame)):
                        selected = branch
                        break
                if self.block(selected, frame, call_depth, block_depth + 1):
                    return True
            elif operation == 'call':
                name, arguments = args
                procedure = self.procedures[name]
                cells = []
                for (_, by_value), argument in zip(procedure.parameters, arguments):
                    self.budget.step()
                    if by_value:
                        cells.append(_Cell(self.expression(argument, frame)))
                    else:
                        if argument.operation != 'local':
                            _fail('invalid_ir')
                        cell = frame[argument.arguments[0]]
                        cell.get()
                        cells.append(cell)
                self.run(procedure, cells, call_depth + 1)
            else:
                _fail('invalid_ir')
        return False

    def run(self, procedure, cells, depth):
        self.budget.step(1 + len(procedure.parameters) + len(procedure.locals))
        if depth > MAX_CALL_DEPTH or len(cells) != len(procedure.parameters):
            _fail('resource_limit')
        frame = {name: cell for (name, _), cell in zip(procedure.parameters, cells)}
        frame.update((name, _Cell()) for name in procedure.locals)
        self.block(procedure.body, frame, depth)


def simulate_object_module(source: bytes, binding: ObjectModuleBinding,
                           snapshot: ScalarSnapshot, *, cancel=False) -> SimulationResult:
    """Compute a new bounded scalar snapshot; never write/activate an object.

    A fresh static analysis is mandatory on every call. Public analysis/IR,
    runtime Decimal, containers, callbacks and host objects are not inputs.
    Cancel is a Boolean simulation output, not an implicit stop or rollback.
    """
    if type(source) is not bytes or not 1 <= len(source) <= MAX_SOURCE_BYTES:
        _fail('invalid_input')
    if type(cancel) is not bool:
        _fail('invalid_input')
    binding = _binding_copy(binding)
    budget = _Budget()
    try:
        with localcontext(_context()) as context:
            try:
                analysis = analyze_object_module(source, binding)
            except ObjectModuleAnalysisError:
                _fail('source_rejected')
            # This is a version tripwire on our own freshly produced result,
            # not an authenticity check or an intake path for supplied IR.
            if (type(analysis) is not ObjectModuleAnalysis or
                    type(analysis.profile) is not str or
                    analysis.profile != 'catalog-before-write-static-v1' or
                    analysis.native_parity is not False):
                _fail('invalid_ir')
            values = _snapshot_copy(snapshot, analysis.binding.catalog, budget)
            simulation = _Simulation(analysis, values, budget, context)
            cancellation = _Cell(cancel, cancel=True)
            simulation.run(simulation.procedures[analysis.event], [cancellation], 1)
            output = []
            for field in binding.catalog.fields:
                value = values[field.name.casefold()]
                if field.kind == 'number':
                    value = NumberValue(format(value, 'f'))
                output.append(value)
            return SimulationResult(ScalarSnapshot(values['code'], values['description'],
                                                   tuple(output)), cancellation.get())
    except RecursionError:
        _fail('resource_limit')
