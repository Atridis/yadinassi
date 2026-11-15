"""Explicit compatibility-target view; never an installed native-platform claim."""
import re
import weakref
from .values import BSLObject


def validate_target(target):
    if target is not None and (type(target) is not str or len(target) > 32
                              or re.fullmatch(r'(?:0|[1-9][0-9]{0,5})(?:\.(?:0|[1-9][0-9]{0,5})){3}', target) is None):
        raise ValueError('source compatibility target requires four numeric version components')
    return target


class SourceSystemInfo(BSLObject):
    def __init__(self, application):
        self._application = weakref.ref(application)

    def get_member(self, name):
        app = self._application()
        if app is None:
            raise ValueError('source system information belongs to a closed application')
        app.require_open()
        key = name.casefold()
        if key in ('appversion', 'версияприложения'):
            if app.compatibility_target is None:
                raise ValueError('source host is not 1C:Enterprise; AppVersion requires explicit --source-compatibility-target')
            return app.compatibility_target
        if key in ('yadinassiversion',):
            from . import __version__
            return __version__
        if key in ('compatibilitytarget',):
            return app.compatibility_target
        if key in ('iscompatibilitytarget',):
            return app.compatibility_target is not None
        raise ValueError('source SystemInfo property is not supported: ' + name)
