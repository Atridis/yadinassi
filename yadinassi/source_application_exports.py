"""Owned client application exports, shared slots rather than copied globals."""
from .runtime import _VariableReference


def _family(caller):
    app = caller.application
    app.require_open()
    caller._require_family()
    if (caller._family_owner is not app.interpreter
            or caller._scheduler is not app.interpreter._scheduler):
        raise ValueError('foreign source application export caller')
    return app.interpreter


def owner(caller):
    root = _family(caller)
    if (caller.execution_context != 'client'
            or not getattr(caller, '_application_exports_enabled', False)):
        return None
    return root


def _shadowed(caller, key):
    if caller.locals is not None and key in caller.locals:
        return True
    if (caller._has_module_context and key in caller.variables
            and (caller.locals is None or key in caller.module_names)):
        return True
    if key in caller.functions or caller._resolve_routine(key) is not None:
        return True
    form_session = getattr(caller, '_form_session', None)
    if form_session is not None:
        form = form_session.form
        if (key in form._static or key in form._tables
                or key in ('thisobject','этотобъект','items','элементы',
                           'commands','команды','parameters','параметры',
                           'formfieldtype','видполяформы')):
            return True
    return False


def variable(caller, name):
    key = name.casefold()
    if _shadowed(caller, key):
        return None
    root = owner(caller)
    if root is None or key not in root.exported_variables:
        return None

    # The admitted private reference is also used by the engine during copy-back
    # while the server frame is still active. Revalidate family/lifetime, not
    # the transient scheduler side; server BSL never receives this reference.
    def get():
        if _family(caller) is not root:
            raise ValueError('source application export context changed')
        return root.variables[key]

    def put(value):
        if _family(caller) is not root:
            raise ValueError('source application export context changed')
        root.variables[key] = value

    return _VariableReference(get, put)


def routine(caller, name):
    root = owner(caller)
    if root is None:
        return None
    selected = root.routines.get(name.casefold())
    if selected is None or not selected.exported:
        return None
    return selected, root
