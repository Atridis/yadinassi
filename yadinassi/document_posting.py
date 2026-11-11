"""Source-bound document write handlers for the fresh recorder profile only.

A write is one savepoint in its origin-owned journal. Handlers can stage owned
movements, never begin, commit or roll back the caller's transaction. No object
module initializer, imports, asynchronous execution or arbitrary handler grant
is exposed by this adapter.
"""
from hashlib import sha256
from enum import Enum
from .catalog_backend import BackendError
from .configuration_posting_application import canonical_runtime as canonical
from .configuration_modules import compile_module
from .document_posting_values import DocumentWriteMode, BSLRecorderCollection
from .runtime import Interpreter
from .syntax import ast
from .structures import BSLStructure
from .values import Reference
from .database_transactions import admission, execution, current, begin, require_admission
from .sqlite_document_posting_state import PostedIntent
from .transaction_backend import TransactionRequest

MAX_SOURCE = 65536
MAX_STEPS = 100000
_EVENTS = {
    'before': (('beforewrite','передзаписью'),3),
    'after': (('onwrite','призаписи'),1),
    'posting': (('posting','обработкапроведения'),2),
    'undo': (('undoposting','обработкаудаленияпроведения'),1),
}


class _PostingMode(Enum):
    NON_REALTIME = 'non_realtime'
    def __str__(self): raise ValueError('posting mode presentation is outside this profile')


class PostingLimitError(BaseException):
    """Uncatchable host budget, not a native language assertion."""


class _PostingInterpreter(Interpreter):
    def __init__(self, document, parent, program):
        self._document = document; self._steps = 0
        super().__init__(parent.output, native_target=parent.native_target,
                         database_context=parent.database_context,
                         family_owner=parent._family_owner)
        self._transaction_activation_allowed = False
        self._logical_side = 'server'
        # This closed synchronous callback shares its document owner snapshot.
        # Factories remain bound to this VM, not copied host callables.
        self._metadata = parent._metadata; self._catalogs = parent._catalogs
        self._documents = parent._documents
        self._information_registers = parent._information_registers
        self.routines = {routine.name.casefold():routine for routine in program}
    def _visit(self, node):
        self._steps += 1
        if self._steps > MAX_STEPS: raise PostingLimitError('document handler execution budget')
        return (yield from super()._visit(node))
    def _member(self, name):
        from .documents import _name
        key = _name(name)
        return (key in self._document._values or key in self._document._sections or
                key in ('additionalproperties','дополнительныесвойства','registerrecords','движения'))
    def visit_Name(self, node):
        key = node.name.casefold()
        if self.locals is not None and key in self.locals: return super().visit_Name(node)
        if key in ('thisobject','этотобъект'): return self._document
        if self._member(node.name): return self._document.get_member(node.name)
        return super().visit_Name(node)
    def call(self, node, *, require_value):
        callee = self.ungroup(node.callee)
        if type(callee) is ast.Name and self._member(callee.name) and callee.name.casefold() in self.functions:
            node = ast.Call(node.token,ast.Literal(node.token,self.functions[callee.name.casefold()]),node.arguments)
        return (yield from super().call(node,require_value=require_value))
    def set_variable(self, name, value):
        if self._member(name) and not (self.locals is not None and name.casefold() in self.locals):
            self._document.set_member(name,value); return
        return super().set_variable(name,value)
    def argument(self, node):
        value = self.ungroup(node)
        if type(value) is ast.Name and self._member(value.name) and not (self.locals is not None and value.name.casefold() in self.locals):
            return Reference(lambda:self._document.get_member(value.name),lambda item:self._document.set_member(value.name,item))
        return (yield from super().argument(node))
    def invoke(self, routine, values):
        if routine is None: return
        arguments = [ast.Attribute(routine.token,ast.Literal(routine.token,values),name)
                     for name in ('Cancel','WriteMode','PostingMode')[:len(routine.parameters)]]
        # Posting has Cancel, PostingMode rather than BeforeWrite's three slots.
        if len(routine.parameters)==2:
            arguments[1] = ast.Attribute(routine.token,ast.Literal(routine.token,values),'PostingMode')
        self._context_stack.append('server')
        self._module_context_stack.append(True)
        try:
            with admission(False):
                self._scheduler.run_inline(self.call_routine(routine,arguments,self,require_value=False))
        finally:
            self._module_context_stack.pop(); self._context_stack.pop()
        cancel = values.get_member('Cancel')
        if type(cancel) is not bool: raise TypeError('document cancellation requires Boolean')
        if cancel: raise ValueError('document write cancelled')


class PostingRuntime:
    def __init__(self, documents, configuration):
        self.documents = documents
        self.configuration = canonical(configuration)
        self._programs = {}; self._events = {}
        files = dict(configuration.files)
        for identity,path,digest in configuration.handlers:
            raw = files[path]
            if len(raw)>MAX_SOURCE or sha256(raw).hexdigest()!=digest: raise ValueError('document source binding')
            program = compile_module(raw,path,'server',common=True)
            names = [routine.name.casefold() for routine in program]
            if len(names)!=len(set(names)): raise ValueError('duplicate document routine')
            events = {}
            for event,(aliases,arity) in _EVENTS.items():
                selected = [routine for routine in program if routine.name.casefold() in aliases]
                if len(selected)>1: raise ValueError('duplicate document handler')
                routine = selected[0] if selected else None
                if routine is not None and (routine.is_function or len(routine.parameters)!=arity or
                        any(parameter.default is not None for parameter in routine.parameters) or routine.parameters[0].by_value):
                    raise ValueError('document handler signature')
                events[event] = routine
            self._programs[identity] = program; self._events[identity] = events
    def movements(self, document):
        if document._movements is None:
            schemas = tuple(schema for schema in self.configuration.registers
                            if document._key.document_id in schema.recorder_documents)
            document._movements = BSLRecorderCollection(document,schemas)
        return document._movements
    def write(self, document, mode):
        from .documents import _OMITTED
        require_admission()
        if mode is _OMITTED: mode = DocumentWriteMode.WRITE
        if type(mode) is not DocumentWriteMode: raise TypeError('DocumentWriteMode required')
        if document._pending_write is not None or document._posting_active is not None: raise BackendError('unsupported')
        if not document._manager._writable(): raise BackendError('unsupported')
        parent = self.documents._interpreter
        parent._require_family()
        if parent._scheduler._active_task is not None or parent._scheduler.pending: raise BackendError('unsupported')
        backend = document._manager._backend
        vm = _PostingInterpreter(document,parent,self._programs[document._key.document_id])
        events = self._events[document._key.document_id]
        values = BSLStructure('Cancel,WriteMode,PostingMode',False,mode,_PostingMode.NON_REALTIME)
        movements = self.movements(document)
        with execution(backend):
            transaction = current(backend); implicit = transaction is None
            if implicit:
                begin(backend); transaction = current(backend)
            old_posted = document._values['posted']
            try:
                with transaction.savepoint():
                    document._posting_active = transaction
                    vm.invoke(events['before'],values)
                    if mode is DocumentWriteMode.UNDO_POSTING: vm.invoke(events['undo'],values)
                    posted = old_posted if mode is DocumentWriteMode.WRITE else mode is DocumentWriteMode.POSTING
                    draft = document._draft(); expected = document._revision
                    document._posting_previous = old_posted
                    transaction.stage(document,'document_create' if expected is None else 'document_update',
                                      draft,expected,(draft,expected,document._operation_id))
                    outcome = transaction.unit._results[-1].result
                    transaction.unit.stage(TransactionRequest('document_set_posted',
                        PostedIntent(document._key,int(outcome.revision.token),posted)))
                    document._values['posted'] = posted
                    if mode is DocumentWriteMode.UNDO_POSTING:
                        for movement in movements._sets.values(): movement._replace(transaction,())
                    vm.invoke(events['after'],values)
                    if mode is DocumentWriteMode.POSTING:
                        vm.invoke(events['posting'],values)
                        for movement in movements._sets.values():
                            if movement._selected: movement.write()
                document._posting_active = None
                if implicit: transaction.commit()
            except BaseException:
                document._posting_active = None
                if document._pending_write is None:
                    document._values['posted'] = old_posted; document._posting_previous = None
                if implicit and transaction.unit.state=='open': transaction.rollback()
                raise
            finally:
                document._posting_active = None
                vm._scheduler.active_context.state.pop(vm._diagnostic_owner,None)
                vm.close()
        return None
