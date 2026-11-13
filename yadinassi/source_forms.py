"""Explicitly selected supported source form; no inferred CRUD/profile grants."""
from .configuration_source_runtime import _SourceInterpreter
from .form_runtime import _FormInterpreter
from .configuration_forms import _definition
from .ui.form_app import FormController


class _SourceFormInterpreter(_SourceInterpreter, _FormInterpreter):
    def __init__(self, application, session, output, **kwargs):
        super().__init__(application, session, output=output,
                         family_owner=application.interpreter, **kwargs)
        self._transaction_activation_allowed = False

    def _activation_interpreter(self):
        child = type(self)(self.application, self._form_session, self.output,
                           encoding=self.encoding, native_target=self.native_target,
                           compilation_profile=self.compilation_profile)
        child._logical_side = self._logical_side
        return child


def source_form_definition(application, name):
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
    return _definition(name, metadata._entry.identity, application.files[definition_path],
                       application.files.get(prefix + '/Ext/Form/Module.bsl', b''),
                       compilation_profile=application.compilation_profile)


class SourceFormController:
    """One actual form after successful source startup; no browser code endpoint."""
    def __init__(self, application, name):
        self.application = application
        self.definition = source_form_definition(application, name)
        if self.definition.program.nocontext_bindings:
            raise ValueError('selected source form AtServerNoContext is not supported yet')
        def factory(side):
            def make(session, output, **kwargs):
                if kwargs.get('database_context') is not None:
                    raise ValueError('selected source form cannot acquire database authority')
                child = _SourceFormInterpreter(application, session, output, **kwargs)
                child._logical_side = side
                return child
            return make
        with application.safe_mode.execution():
            self.server = self.definition.create_server(interpreter_factory=factory('server'))
            self.client = FormController(self.definition.client_package(), self.server.exchange,
                                         interpreter_factory=factory('client'))

    def exchange(self, request):
        self.application.require_open()
        with self.application.safe_mode.execution():
            return self.client.exchange(request)

    def close(self):
        self.application.close()
