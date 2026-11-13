"""Explicitly selected supported source form; no inferred CRUD/profile grants."""
from .configuration_source_runtime import _SourceInterpreter
from .form_runtime import _FormInterpreter
from .configuration_forms import _definition
from .ui.form_app import FormController


class _SourceNoContextInterpreter(_SourceInterpreter):
    """Source services without any form session, attributes, parameters or UI hooks."""
    def __init__(self, application, *args, budget=None, **kwargs):
        super().__init__(application, *args, **kwargs)
        self._transaction_activation_allowed = False
        self._source_call_budget = [0] if budget is None else budget

    def _inherit_host_bindings(self, parent):
        if isinstance(parent, _SourceFormInterpreter):
            # Keep the fresh source-only registries: never copy bound form helpers,
            # FormAttribute constructors, OpenForm callbacks or UI capabilities.
            return
        super()._inherit_host_bindings(parent)

    def _visit(self, node):
        self._source_call_budget[0] += 1
        if self._source_call_budget[0] > 100000:
            from .form_runtime import FormLimitError
            raise FormLimitError('Source NoContext execution limit')
        return (yield from super()._visit(node))

    def _activation_interpreter(self):
        return type(self)(self.application, output=self.output, budget=self._source_call_budget,
                          family_owner=self._family_owner, encoding=self.encoding,
                          native_target=self.native_target, compilation_profile=self.compilation_profile)


class _SourceNoContextServer:
    """Declared RPC endpoints over the existing scalar wire and no-replay gate."""
    def __init__(self, application, program):
        from .form_program import admitted_program
        from .invocation import InvocationServer
        self.application = application
        self.sink = None
        self.prototype = _SourceNoContextInterpreter(application, output=self._message,
            family_owner=application.interpreter, compilation_profile=application.compilation_profile)
        self.prototype._logical_side = 'server'
        self.prototype.execute_program(admitted_program(program.nocontext, side='nocontext', label='<source-form-nocontext>'))
        endpoints = {}
        for binding in program.nocontext_bindings:
            routine = self.prototype.server_routines[binding.name.casefold()]
            endpoints[binding.endpoint] = (binding, lambda values, routine=routine: self._invoke(routine, values))
        self.server = InvocationServer.from_handlers(endpoints, message_scope=self._scope)

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
        from .native_targets import target_context
        from .syntax import ast
        self.application.require_open()
        self.prototype._source_call_budget = [0]
        activation = self.prototype._new_server_activation(module_context=False)
        activation._context_stack.append('server')
        activation._module_context_stack.append(False)
        try:
            arguments = [ast.Literal(routine.token, value) for value in values]
            with self.application.safe_mode.execution(), target_context(activation.native_target), localcontext():
                return activation._scheduler.run_inline(activation.call_routine(
                    routine, arguments, activation, require_value=routine.is_function))
        finally:
            activation._module_context_stack.pop()
            activation._context_stack.pop()
            activation._scheduler.active_context.state.pop(activation._diagnostic_owner, None)

    def exchange(self, raw):
        self.application.require_open()
        return self.server.exchange(raw)


class _SourceFormInterpreter(_SourceInterpreter, _FormInterpreter):
    def __init__(self, application, session, output, navigation=None, **kwargs):
        super().__init__(application, session, output=output,
                         family_owner=application.interpreter, **kwargs)
        self._transaction_activation_allowed = False
        self._source_navigation = navigation
        if navigation is not None:
            self.register_function('OpenForm', self._open_source_form, 'ОткрытьФорму', returns_value=False)

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
    if progressive:
        from .source_form_projection import project_source_form
        from dataclasses import replace
        from hashlib import sha256
        projection = project_source_form(raw)
        definition = _definition(name, metadata._entry.identity, projection.xml, module)
        if diagnostics is not None:
            diagnostics.extend(projection.diagnostics)
        return replace(definition, source_sha256=sha256(raw+b'\0'+module).hexdigest())
    return _definition(name, metadata._entry.identity, raw, module)


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
                from .invocation import InvocationPort
                self.nocontext = _SourceNoContextServer(application, self.definition.program)
                port = InvocationPort(self.nocontext.exchange)
                for binding in self.definition.program.nocontext_bindings:
                    self.client.session.bind_nocontext(port, binding)

    def exchange(self, request):
        self.application.require_open()
        with self.application.safe_mode.execution():
            return self.client.exchange(request)

    def close(self):
        self.application.close()
