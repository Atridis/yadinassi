"""Exact one-element lists internally; reference adapters only at boundaries."""
from yadinassi.execution.codegen.experimental_naked_collections import _Reference,_UNSET_REF
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


def NativeCell(value=_UNSET_REF):return [value]

class ReferenceCell:
    __slots__=('reference','context')
    def __init__(self,reference,context):self.reference=reference;self.context=context
    def __getitem__(self,index):
        self.context._check()
        try:return self.reference.get()
        finally:self.context._check()
    def __setitem__(self,index,value):
        self.context._check()
        try:self.reference.set(value)
        finally:self.context._check()

class PlainReferenceCell(ReferenceCell):
    __slots__=()

    def __getitem__(self,index):
        if self.context.vm._family_closed:
            raise BoundaryViolation('python-direct interpreter was closed during execution')
        try:return self.reference.get()
        finally:
            if self.context.vm._family_closed:
                raise BoundaryViolation('python-direct interpreter was closed during execution')

    def __setitem__(self,index,value):
        # The RHS or the replaced value's finalizer can close an embedding.
        # Check that one lifetime condition, not the full context on every access.
        if self.context.vm._family_closed:
            raise BoundaryViolation('python-direct interpreter was closed during execution')
        try:self.reference.set(value)
        finally:
            if self.context.vm._family_closed:
                raise BoundaryViolation('python-direct interpreter was closed during execution')


class CellReference(_Reference):
    __slots__=('cell',)
    def __init__(self,cell):self.cell=cell
    @property
    def value(self):return self.cell[0]
    @value.setter
    def value(self,value):self.cell[0]=value


def reference(cell):
    if type(cell) in (ReferenceCell,PlainReferenceCell):return CellReference(cell)
    if type(cell) is not list or len(cell)!=1:raise TypeError('invalid internal cell')
    if cell[0] is _UNSET_REF:raise NameError('Uninitialized reference')
    return CellReference(cell)


def adapt(value,context):
    if type(value) in (ReferenceCell,PlainReferenceCell):value=value.reference
    if isinstance(value,_Reference):
        if not context._verify_context:return PlainReferenceCell(value,context)
        return ReferenceCell(value,context)
    # A public array value is not confused with our private address ABI.
    return NativeCell(value)


def fragment_binding(cell):
    from .python_direct_execute import local_binding
    return local_binding(lambda:cell[0],lambda value:cell.__setitem__(0,value),
                         lambda:cell[0] is not _UNSET_REF,cell)


def host_reference(getter,setter,name,storage,activation,context):
    from yadinassi.execution.codegen.experimental_naked_collections import _host_name_reference
    from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
    def check():
        context._check()
        if not activation[0]:raise BoundaryViolation('expired routine reference')
    def get():
        check();return getter()
    def set(value):
        check();setter(value);check()
    return _host_name_reference(get,set,name)
