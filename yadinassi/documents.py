"""Document database operations are not implemented by the SQLite catalog MVP."""
from .values import BSLObject
from .catalog_backend import BackendError

class BSLDocuments(BSLObject):
    def __init__(self, metadata, context, catalogs):
        self._catalogs=catalogs
    def get_member(self, name):
        raise BackendError('unsupported')
    get_index = get_member
    def type_by_name(self, name):
        if type(name) is str and name.partition('.')[0].casefold() in ('documentref','документссылка','documentmanager','документменеджер','documentselection','документвыборка','documenttabularsection','документтабличнаячасть','documenttabularsectionrow','документтабличнаячастьстрока'):
            raise BackendError('unsupported')
        return self._catalogs.type_by_name(name)
    def __str__(self):
        return 'Документы менеджер'

class BSLDocumentManager(BSLObject):
    def __init__(self, *args, **kwargs):
        raise BackendError('unsupported')

class BSLDocumentSelection(BSLDocumentManager):
    pass
