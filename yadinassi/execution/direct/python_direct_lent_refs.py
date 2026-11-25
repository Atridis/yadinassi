"""Exact lexical and own exported addresses lent to a synchronous dual call."""
from threading import get_ident
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.types.values import Reference


class _Address:
    __slots__ = ('owner', 'get', 'set', 'read', 'write')

    def __init__(self, owner, reference, read, write):
        self.owner = owner
        self.get, self.set = reference.get, reference.set
        self.read, self.write = read, write


def remember(reference, owner, read, write):
    reference._direct_lent_address = _Address(owner, reference, read, write)
    return reference


class LendScope:
    __slots__ = ('owner', 'stack', 'prefix', 'thread', 'scheduler', 'generation', 'state', 'active')

    def __init__(self, owner):
        vm = owner.vm
        self.owner = owner
        self.stack = vm._module_context_stack
        self.prefix = tuple(self.stack)
        self.thread = get_ident()
        self.scheduler = vm._scheduler
        self.generation = vm._family_generation
        self.state = vm.variables
        self.active = True

    def check(self, owner):
        vm = owner.vm
        if (not self.active or owner is not self.owner or vm._family_owner is not vm
                or get_ident() != self.thread or vm._scheduler is not self.scheduler
                or self.scheduler._active_task is not None
                or vm._family_generation != self.generation or vm.variables is not self.state
                or vm._module_context_stack is not self.stack
                or len(self.stack) != len(self.prefix) + 1
                or self.stack[-1] is not False
                or any(actual is not expected for actual, expected in zip(self.stack, self.prefix))):
            raise BoundaryViolation('dual reference lend expired or changed')

    def wrap(self, reference):
        address = getattr(reference, '_direct_lent_address', None)
        if (type(address) is not _Address or address.owner is not self.owner
                or address.get is not reference.get or address.set is not reference.set):
            return reference

        def read():
            return address.read(self)

        def write(value):
            address.write(value,self)

        return Reference(read, write)


def scope(owner):
    vm = owner.vm
    if (getattr(owner, '_check_lent_reference', False) is True
            and vm._family_owner is vm and vm.database_context is None
            and vm.execution_context == 'client' and vm._has_module_context
            and vm._scheduler._active_task is None):
        return LendScope(owner)
    return None
