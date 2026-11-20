"""Explicitly selected supported source form; no inferred CRUD/profile grants."""
from yadinassi.configuration.configuration_source_runtime import _SourceInterpreter
from .form_runtime import _FormInterpreter
from yadinassi.runtime import Interpreter
from yadinassi.execution.invocation import InvocationServer, InvocationPort
from yadinassi.configuration.configuration_forms import _definition
from yadinassi.ui.form_app import FormController


class _SourceNoContextInterpreter(_SourceInterpreter):
    """Source services without any form session, attributes, parameters or UI hooks."""
    def __init__(self, application, *args, budget=None, **kwargs):
        super().__init__(application, *args, **kwargs)
        self._transaction_activation_allowed = False
        self._application_exports_enabled = True
        self._source_call_budget = [0] if budget is None else budget

    def _inherit_host_bindings(self, parent):
        if isinstance(parent, _SourceFormInterpreter):
            # Keep the fresh source-only registries: never copy bound form helpers,
            # FormAttribute constructors, OpenForm callbacks or UI capabilities.
            return
        super()._inherit_host_bindings(parent)

    def _visit(self, node):
        from yadinassi.execution.direct.python_direct import _reject
        _reject("single-node adapter evaluation is retired; use the direct entrypoint")

    def compiled_before(self, node):
        self._source_call_budget[0] += 1
        if self._source_call_budget[0] > 100000:
            from .form_runtime import FormLimitError
            raise FormLimitError('Source NoContext execution limit')
        return super().compiled_before(node)

    def _activation_interpreter(self):
        return type(self)(self.application, output=self.output, budget=self._source_call_budget,
                          family_owner=self._family_owner, encoding=self.encoding,
                          native_target=self.native_target, compilation_profile=self.compilation_profile)


class _SourceNoContextServer:
    """Declared RPC endpoints over the existing scalar wire and no-replay gate."""
    def __init__(self, application, program):
        from .form_program import admitted_program
        from yadinassi.execution.invocation import InvocationServer
        self.application = application
        self.sink = None
        for cls,name,expected in (*_DIRECT_SOURCE_NOCONTEXT_ABI,*_DIRECT_SOURCE_NOCONTEXT_TRANSPORT_ABI):
            if getattr(cls,name) is not expected:
                raise ValueError('source NoContext factory hooks changed')
        if _SourceNoContextInterpreter is not _DIRECT_SOURCE_NOCONTEXT_CLASS:
            raise ValueError('source NoContext factory class changed')
        self.prototype = _SourceNoContextInterpreter(application, output=self._message,
            family_owner=application.interpreter, compilation_profile=application.compilation_profile)
        self.prototype._logical_side = 'server'
        nodes=admitted_program(program.nocontext, side='nocontext', label='<source-form-nocontext>')
        from yadinassi.execution.direct.source.python_direct_source_nocontext import prepare
        prepare(self,nodes)
        endpoints = {}
        for binding in program.nocontext_bindings:
            routine = self.prototype.server_routines[binding.name.casefold()]
            endpoints[binding.endpoint] = (binding, lambda values, routine=routine: self._invoke(routine, values))
        self.server = InvocationServer.from_handlers(endpoints, message_scope=self._scope)
        self._direct_transport=(self.server,self.server._callbacks,tuple(self.server._callbacks.items()),
            self.server._routines,tuple(self.server._routines.items()),self.server._message_scope,self.server._gate)

    def _message(self, value):
        if self.sink is None:
            raise ValueError('NoContext message outside invocation')
        self.sink(value)

    def _scope(self, sink):
        from contextlib import contextmanager
        @contextmanager
        def scope():
            self.sink = sink
            try:
                yield
            finally:
                self.sink = None
        return scope()

    def _invoke(self, routine, values):
        from decimal import localcontext
        from yadinassi.execution.codegen.native_targets import target_context
        from yadinassi.syntax import ast
        self.application.require_open()
        from yadinassi.execution.direct.source.python_direct_source_nocontext import invoke
        return invoke(self,routine,values)

    def exchange(self, raw):
        self.application.require_open()
        from yadinassi.execution.direct.source.python_direct_source_nocontext import _check
        _check(self)
        return self.server.exchange(raw)


class _SourceFormInterpreter(_SourceInterpreter, _FormInterpreter):
    def __init__(self, application, session, output, navigation=None, **kwargs):
        super().__init__(application, session, output=output,
                         family_owner=application.interpreter, **kwargs)
        self._transaction_activation_allowed = False
        self._application_exports_enabled = True
        self._source_navigation = navigation
        if navigation is not None:
            self._register_platform_function('OpenForm', self._open_source_form, 'ОткрытьФорму', returns_value=False)

    def _invocation_argument(self, node, *, _evaluation=None):
        # Only sealed Val InvocationPort calls use this hook. Source form scalar
        # attributes are snapshots, never dictionary references/copy-out sinks.
        from yadinassi.syntax import ast
        actual = self.ungroup(node)
        if (isinstance(actual, ast.Name) and actual.name.casefold() in self._form_session.form._static
                and not (self.locals is not None and actual.name.casefold() in self.locals)):
            return (yield from (self._visit(node) if _evaluation is None else _evaluation.evaluate(node)))
        return (yield from (super()._invocation_argument(node) if _evaluation is None else super()._invocation_argument(node, _evaluation=_evaluation)))

    def _open_source_form(self, name, parameters=None):
        if (not self._form_session._busy or not self._context_stack
                or self._context_stack[-1] != 'client'):
            raise ValueError('source OpenForm requires an active client form event')
        self._source_navigation(name, parameters)

    def _new_server_activation(self, *, module_context=True):
        # The base runtime constructs the activation synchronously, before any BSL runs.
        self._creating_formless_activation = not module_context
        try:
            return super()._new_server_activation(module_context=module_context)
        finally:
            self._creating_formless_activation = False

    def _activation_interpreter(self):
        if getattr(self, '_creating_formless_activation', False):
            return _SourceNoContextInterpreter(self.application, output=self.output,
                family_owner=self._family_owner, encoding=self.encoding,
                native_target=self.native_target, compilation_profile=self.compilation_profile)
        child = type(self)(self.application, self._form_session, self.output,
                           encoding=self.encoding, native_target=self.native_target,
                           compilation_profile=self.compilation_profile, navigation=self._source_navigation)
        child._logical_side = self._logical_side
        return child


# Definition-time source-form admission ABI. Legacy evaluator hooks are excluded
# deliberately so direct tests can poison them without changing admission.
_DIRECT_SOURCE_FORM_ABI=tuple((name,getattr(_SourceFormInterpreter,name)) for name in (
    'compiled_before','compiled_after','compiled_exception','semantic_name','semantic_index',
    'semantic_assign','set_variable','_visit','execute','execute_program',
    '_activation_interpreter','_invocation_argument','_new_query','_new_type_description',
    '_new_temp_tables_manager','_make_attribute'))


_DIRECT_SOURCE_NOCONTEXT_TRANSPORT_ABI=tuple(
    (cls,name,getattr(cls,name)) for cls,names in (
        (InvocationServer,('exchange','_reply','_message')),
        (InvocationPort,('invoke',)),
    ) for name in names)
_DIRECT_SOURCE_NOCONTEXT_SERVER_CLASS=_SourceNoContextServer
_DIRECT_SOURCE_NOCONTEXT_CLASS=_SourceNoContextInterpreter
_DIRECT_SOURCE_NOCONTEXT_ABI=tuple(
    (cls,name,getattr(cls,name)) for cls,names in (
        (_SourceNoContextInterpreter,('__init__','__new__','compiled_before','_visit','_activation_interpreter','_inherit_host_bindings','register_function','register_type','_bind_schema_scope')),
        (_SourceNoContextServer,('__init__','_message','_scope','_invoke','exchange')),
        (_SourceInterpreter,('__init__','__new__','register_function','register_type','_bind_schema_scope')),
        (Interpreter,('__init__','register_function','register_type','_register_platform_function','_register_platform_type','_bind_schema_scope')),
    ) for name in names)


def source_form_definition(application, name, *, progressive=False, diagnostics=None):
    application.require_open()
    if application.constant_store is not None:
        raise ValueError('selected source forms currently require memory-only source startup')
    metadata = application.metadata.find_by_full_name(name)
    if metadata is None or metadata._entry.family not in ('Form', 'CommonForm'):
        raise ValueError('declared source Form or CommonForm required')
    node = metadata._property('FormType')
    if node.attrib or len(node) or node.text != 'Managed':
        raise ValueError('selected source form must declare Managed FormType')
    prefix = metadata._entry.path[:-4]
    definition_path = prefix + '/Ext/Form.xml'
    if definition_path not in application.files:
        raise ValueError('selected form definition missing: ' + definition_path)
    raw = application.files[definition_path]
    module = application.files.get(prefix + '/Ext/Form/Module.bsl', b'')
    validation_child=None
    def validation_factory(session,output,**kwargs):
        nonlocal validation_child
        validation_child=_SourceFormInterpreter(application,session,output,**kwargs)
        validation_child._logical_side='server'
        return validation_child
    def definition_for(xml):
        try:
            with application.safe_mode.execution():
                return _definition(name,metadata._entry.identity,xml,module,compilation_profile=application.compilation_profile,
                                   validation_interpreter_factory=validation_factory,reject_nocontext=False)
        finally:
            if validation_child is not None and not validation_child._family_released:validation_child.close()
    if progressive:
        from .source_form_projection import project_source_form
        from dataclasses import replace
        from hashlib import sha256
        projection = project_source_form(raw)
        definition = definition_for(projection.xml)
        if diagnostics is not None:
            diagnostics.extend(projection.diagnostics)
        return replace(definition, source_sha256=sha256(raw+b'\0'+module).hexdigest())
    return definition_for(raw)


class SourceFormController:
    """One actual form after successful source startup; no browser code endpoint."""
    def __init__(self, application, name, *, progressive=False, parameters=None, navigation=None):
        self.application = application
        diagnostics = []
        self.definition = source_form_definition(application, name, progressive=progressive, diagnostics=diagnostics)
        self.diagnostics = tuple(diagnostics)
        def factory(side):
            def make(session, output, **kwargs):
                if kwargs.get('database_context') is not None:
                    raise ValueError('selected source form cannot acquire database authority')
                child = _SourceFormInterpreter(application, session, output, navigation=navigation, **kwargs)
                child._logical_side = side
                return child
            return make
        with application.safe_mode.execution():
            self.server = self.definition.create_server(interpreter_factory=factory('server'), parameters=parameters)
            self.client = FormController(self.definition.client_package(), self.server.exchange,
                                         interpreter_factory=factory('client'), parameters=parameters)
            self.nocontext = None
            if self.definition.program.nocontext_bindings:
                from yadinassi.execution.invocation import InvocationPort
                if _SourceNoContextServer is not _DIRECT_SOURCE_NOCONTEXT_SERVER_CLASS:
                    raise ValueError('source NoContext server factory changed')
                self.nocontext = _SourceNoContextServer(application, self.definition.program)
                self.nocontext._direct_source_sessions=(self.client.session,self.server.session)
                self.client.session._direct_source_nocontext_server=self.nocontext
                self.server.session._direct_source_nocontext_server=self.nocontext
                port = InvocationPort(self.nocontext.exchange)
                for binding in self.definition.program.nocontext_bindings:
                    self.client.session.bind_nocontext(port, binding)
                self.nocontext._direct_client_bindings=tuple(
                    (binding.name.casefold(),self.client.session.interpreter._invocation_bindings[binding.name.casefold()])
                    for binding in self.definition.program.nocontext_bindings)
                self.nocontext._direct_port=(port,port._exchange,port._gate)

    def exchange(self, request):
        self.application.require_open()
        with self.application.safe_mode.execution():
            return self.client.exchange(request)

    def close(self):
        self.application.close()
