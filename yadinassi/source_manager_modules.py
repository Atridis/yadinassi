"""Source manager namespaces exposing BSL exports, not implicit persistence."""
import weakref
from .values import BSLObject

MANAGER_NAMES = {
    'catalogs': 'Catalog', 'справочники': 'Catalog',
    'documents': 'Document', 'документы': 'Document',
    'reports': 'Report', 'отчеты': 'Report',
    'dataprocessors': 'DataProcessor', 'обработки': 'DataProcessor',
}


class SourceManagers(BSLObject):
    def __init__(self, application, family):
        self._application = weakref.ref(application)
        self._family = family

    def member(self, caller, name):
        app = self._application()
        if app is None:
            raise ValueError('source manager belongs to a closed application')
        return app.manager_module(self._family, name, caller)
