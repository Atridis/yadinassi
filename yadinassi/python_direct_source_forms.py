"""Exact source-form admission over the existing direct form lifecycle."""
from .python_direct_forms import FormBoundary,SYSTEM_NAMES,CALLBACK_CONSTRUCTORS,DECLARATION_CONSTRUCTORS
from .python_direct_source import SourceBoundary,_external_names,_signature_matches
from .experimental_naked_boundaries import BoundaryContext,BoundaryViolation
from . import safe_mode,source_transactions,database_transactions
from .python_direct_source_query import CONSTRUCTOR_NAMES
from .source_forms import _SourceFormInterpreter,_DIRECT_SOURCE_FORM_ABI
from .configuration_source_runtime import SourceApplication,_SourceInterpreter,_DIRECT_SOURCE_ABI
from .values import HostFunction
from .python_direct_services import CONSTRUCTORS as SERVICE_CONSTRUCTORS

CONSTRUCTORS=tuple(dict.fromkeys((*SERVICE_CONSTRUCTORS,*CONSTRUCTOR_NAMES,'uuid','уникальныйидентификатор')))



def is_source_session(session):return type(session.interpreter) is _SourceFormInterpreter


def check_source_session(session,routine=None):
    if not is_source_session(session):raise BoundaryViolation('source form requires exact interpreter')
    vm=session.interpreter;app=vm.application
    if type(app) is not SourceApplication:raise BoundaryViolation('source form application changed')
    for name,expected in _DIRECT_SOURCE_FORM_ABI:
        if name in vars(vm) or getattr(_SourceFormInterpreter,name) is not expected:
            raise BoundaryViolation('source form hooks changed')
    for name,expected in _DIRECT_SOURCE_ABI:
        if name in vars(vm) or getattr(_SourceInterpreter,name) is not expected:
            raise BoundaryViolation('source host hooks changed')
    root=app.interpreter
    if (app.state!='running' or vm._family_owner is not root or vm._scheduler is not root._scheduler
            or root._family_closed or vm._family_released or vm._family_generation!=root._family_generation
            or vm._scheduler.pending or vm._scheduler._active_task is not None):
        raise BoundaryViolation('source form family is inactive')
    if (vm._form_session is not session or vm.database_context is not None or app.constant_store is not None
            or vm._configuration_runtime is not None or vm.execution_backend!='python-direct'
            or vm.compilation_profile!=app.compilation_profile or vm.locals is not None
            or database_transactions._execution.get() is not None
            or safe_mode._CURRENT.get() is not app.safe_mode
            or source_transactions._current.get() not in (None,app)):
        raise BoundaryViolation('source form scope changed')
    if any(type(value) is not dict for value in (vm.variables,vm.functions,vm.types)):
        raise BoundaryViolation('source form namespaces changed')
    if routine is not None:
        if (source_transactions._current.get() is not app or not vm._has_module_context
                or vm.execution_context!=routine.execution_context or vm._logical_side!=routine.execution_context):
            raise BoundaryViolation('source form event side changed')
        from .python_direct import _admit_bindings
        constructors=getattr(session,'_direct_source_constructors',None)
        if constructors is None:raise BoundaryViolation('source form constructors not admitted')
        _admit_bindings(vm,frozenset(),constructors,frozenset())
        signatures=getattr(session,'_direct_source_signatures',None)
        if signatures is None:raise BoundaryViolation('source form declarations not admitted')
        for node,signature in signatures:
            registry=vm.server_routines if signature[1]=='server' else vm.routines
            if registry.get(signature[0].casefold()) is not node or not _signature_matches(node,signature):
                raise BoundaryViolation('source form declaration changed')
        if not any(node is routine for node,_ in signatures):raise BoundaryViolation('foreign source form routine')
        session.form._check()
    return app


def external_names(session):return _external_names(session.interpreter)


class SourceFormBoundary(FormBoundary,SourceBoundary):
    def __init__(self,session,routine):
        FormBoundary.__init__(self,session,routine)
        self.vm=self.owner;self.app=self.vm.application
        self.side=self.vm.execution_context;self.logical_side=self.vm._logical_side
        self.storage=self.vm.variables;self.types=self.vm.types
        self.form=session.form;self._active=True

    def _check(self):
        BoundaryContext._check(self)
        if (not self._active or self.session.interpreter is not self.vm or self.session.form is not self.form
                or self.vm.application is not self.app or self.vm.variables is not self.storage
                or self.vm.functions is not self._services or self.vm.types is not self.types
                or self.vm._family_generation!=self.generation or self.vm.execution_context!=self.side
                or self.vm._logical_side!=self.logical_side):
            raise BoundaryViolation('source form activation changed')
        check_source_session(self.session,self.routine)

    def _form_name(self,name):
        form=self.session.form
        return name in SYSTEM_NAMES or name in form._static or name in form._tables or name in form._methods

    def external_get(self,name):
        return FormBoundary.external_get(self,name) if self._form_name(name) else SourceBoundary.external_get(self,name)

    def external_set(self,name,value):
        return FormBoundary.external_set(self,name,value) if self._form_name(name) else SourceBoundary.external_set(self,name,value)

    def external_reference(self,name):
        if self._form_name(name):return BoundaryContext.external_reference(self,name)
        return SourceBoundary.external_reference(self,name)

    def resolve_service(self,name,*args,**kwargs):
        key=name.casefold()
        special=tuple('new:'+n for n in CALLBACK_CONSTRUCTORS+DECLARATION_CONSTRUCTORS)
        if key in tuple('new:'+n for n in DECLARATION_CONSTRUCTORS):
            bound=FormBoundary.resolve_service(self,name,*args,**kwargs)
            registration=key[4:];factory=self.vm.types.get(registration)
            function=factory.function
            def construct(*values):
                self._check()
                if self.vm.types.get(registration) is not factory or factory.function is not function:
                    raise BoundaryViolation('source form constructor registration changed')
                try:return bound(*values)
                finally:self._check()
            if hasattr(bound,'requires_reference'):construct.requires_reference=bound.requires_reference
            return construct
        if key in special or key in self.owner._invocation_bindings or key in ('changeattributes','изменитьреквизиты','getattributes','получитьреквизиты'):
            return FormBoundary.resolve_service(self,name,*args,**kwargs)
        return SourceBoundary.resolve_service(self,name,*args,**kwargs)

    def _form_value(self,value):
        from . import python_direct_form_objects as objects
        from .direct_form_parameters import is_parameters
        from .form_dialogs import QUESTION_DIALOG_MODES,DIALOG_RETURN_CODES
        return value is self.form or objects.recognized(value) or is_parameters(self.session,value) or value is QUESTION_DIALOG_MODES or value is DIALOG_RETURN_CODES

    def get_member(self,value,name):
        return FormBoundary.get_member(self,value,name) if self._form_value(value) else SourceBoundary.get_member(self,value,name)

    def resolve_member(self,value,name):
        return FormBoundary.resolve_member(self,value,name) if self._form_value(value) else SourceBoundary.resolve_member(self,value,name)

    def resolve_source_member(self,value,name,**contract):
        if not self._form_value(value):return SourceBoundary.resolve_source_member(self,value,name,**contract)
        function=self.resolve_member(value,name)
        from . import python_direct_form_objects as objects
        returns_value=True;references=frozenset()
        if value is self.form and name.casefold() in ('close','закрыть'):
            returns_value=False
        elif objects.recognized(value) and not name.startswith('__'):
            objects.require(self.session,value)
            canonical=value.get_method(name)
            if type(canonical) is not HostFunction:raise BoundaryViolation('noncanonical form method')
            returns_value=canonical.returns_value;references=canonical.reference_parameters
        return self.resolve_callable(HostFunction(name,function,returns_value=returns_value,reference_parameters=references),
            require_value=contract.get('require_value',False),allow_references=contract.get('allow_references',False))

    def resolve_set_member(self,value,name):
        return FormBoundary.resolve_set_member(self,value,name) if self._form_value(value) else SourceBoundary.resolve_set_member(self,value,name)

    def set_member(self,value,name,new_value):return self.resolve_set_member(value,name)(new_value)

    def reference_member(self,value,name):
        return FormBoundary.reference_member(self,value,name) if self._form_value(value) else SourceBoundary.reference_member(self,value,name)

    def iterate(self,value):
        if self._form_value(value):
            yield from self.resolve_member(value,'__iter__')()
            self._check()
        else:
            yield from SourceBoundary.iterate(self,value)
