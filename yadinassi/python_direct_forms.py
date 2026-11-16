"""Small direct managed-form event bridge; no AST execution fallback."""
from contextlib import contextmanager
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .python_direct import REPAIRS
from .python_direct_handlers import prepare_handlers
from .syntax import ast

SYSTEM_NAMES = ('thisobject','этотобъект','items','элементы','commands','команды',
                'parameters','параметры','formfieldtype','видполяформы')

class FormBoundary(BoundaryContext):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self._services = session.interpreter.functions
        self.generation = session.interpreter._family_owner._family_generation

    def _check(self):
        super()._check()
        from . import safe_mode, source_transactions, database_transactions
        if (safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None
                or database_transactions._execution.get() is not None):
            raise BoundaryViolation("direct restricted form execution is not connected")
        vm = self.session.interpreter
        if vm._configuration_runtime is not None:
            raise BoundaryViolation("direct configuration form authority is not connected")
        if (vm._family_owner._family_closed or vm._family_released
                or vm._family_owner._family_generation != self.generation):
            raise BoundaryViolation("form interpreter authority closed")
        self.session.form._check()

    def checkpoint(self):
        self._check()
        from .form_runtime import MAX_STEPS, FormLimitError
        self.session._steps += 1
        if self.session._steps > MAX_STEPS:
            raise FormLimitError('Форма: превышен предел исполнения события')

    def external_get(self, name):
        self._check()
        form = self.session.form
        if name in ('thisobject','этотобъект'): return form
        if name in ('items','элементы'): return form.items
        if name in ('commands','команды'): return form.commands
        if name in ('parameters','параметры'): return self.session._parameters
        if name in ('formfieldtype','видполяформы'):
            from .form_model import FORM_FIELD_VIEWS
            return FORM_FIELD_VIEWS
        return form.get_member(name)

    def external_set(self, name, value):
        self._check()
        if name in SYSTEM_NAMES: raise ValueError('Форма: поле только для чтения')
        self.session.form.set_member(name, value)


def prepare_form(session, program, source, attributes, tables):
    from .form_runtime import _FormInterpreter
    if (type(session.interpreter) is not _FormInterpreter
            or session.interpreter._configuration_runtime is not None):
        raise BoundaryViolation('direct specialized source-form runtime is not connected')
    from . import safe_mode, source_transactions, database_transactions
    if (safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None
            or database_transactions._execution.get() is not None):
        raise BoundaryViolation("direct restricted form execution is not connected")
    # These AST tables are signature metadata only; execution never reads bodies.
    for node in program:
        if type(node) is ast.Routine:
            registry = session.interpreter.server_routines if node.execution_context == 'server' else session.interpreter.routines
            registry[node.name.casefold()] = node
    names = tuple(attr.name.casefold() for attr in attributes) + tuple(t.name.casefold() for t in tables) + SYSTEM_NAMES
    return prepare_handlers(program, source_text=source if type(source) is str else '',
                            external_names=names, repairs=REPAIRS+('authority_checkpoints',))


def invoke_form(session, handler, side, arguments):
    @contextmanager
    def scope():
        vm = session.interpreter
        previous_transactions = getattr(vm, "_transaction_activation_allowed", True)
        vm._transaction_activation_allowed = False
        vm._context_stack.append(side)
        vm._module_context_stack.append(True)
        try: yield
        finally:
            vm._module_context_stack.pop()
            vm._context_stack.pop()
            vm._transaction_activation_allowed = previous_transactions
    # Server module variables are activation-local; client variables persist.
    state = {} if side == 'server' else session.interpreter.variables
    return session._direct_handlers.invoke(handler, side, arguments, state=state,
                context_factory=lambda: FormBoundary(session), execution_scope=scope)
