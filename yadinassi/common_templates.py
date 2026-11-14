"""Owned resource retrieval returns fresh values without filesystem access."""
from .metadata import _MetadataObject,_DeclaredMetadataCollection
from .values import HostFunction

class CommonTemplateMetadata(_MetadataObject):
    def __init__(self,definition):self._name=definition.name
    def get_member(self,name):
        key=name.casefold()
        if key in ('name','имя'):return self._name
        if key in ('fullname','полноеимя'):return HostFunction(name,lambda:'ОбщийМакет.'+self._name)
        return super().get_member(name)

def get_common_template_marker(*args):raise ValueError('common templates require an active application')

class ApplicationCommonTemplates:
    def __init__(self,app,definitions):
        import weakref
        self._app=weakref.ref(app);self._definitions={d.name.casefold():d for d in definitions}
        items=tuple(CommonTemplateMetadata(d) for d in definitions)
        self.metadata=_DeclaredMetadataCollection(items)
        self._metadata_items={id(item):(item,d.name.casefold()) for item,d in zip(items,definitions)}
    def authorize(self,caller):
        app=self._app()
        if app is None or caller._configuration_runtime is not app or caller._family_owner is not app.interpreter or caller._scheduler is not app.interpreter._scheduler:raise ValueError('foreign common template owner')
        app.require_open();caller._require_family()
        if app.state not in ('starting','running','before_exit','exiting'):raise ValueError('inactive common template owner')
    def get(self,caller,name):
        self.authorize(caller)
        if type(name) is CommonTemplateMetadata:
            entry=self._metadata_items.get(id(name))
            if entry is None or entry[0] is not name:raise ValueError('foreign common template metadata')
            key=entry[1]
        elif type(name) is str and 1<=len(name)<=128:key=name.casefold()
        else:raise TypeError('common template name requires String or owned metadata')
        definition=self._definitions.get(key)
        if definition is None:raise ValueError('unknown common template')
        if definition.kind=='TextDocument':
            from .text_documents import BSLTextDocument
            value=BSLTextDocument();value.set_text(definition.content.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n'));return value
        from .file_io import BSLBinaryData
        return BSLBinaryData.from_bytes(definition.content)


class SourceCommonTemplates:
    """Lazy, bounded source resources, separate from strict application grants."""
    def __init__(self, application):
        import weakref
        self._app = weakref.ref(application)
        self._entries = {entry.name.casefold(): entry for entry in application.source.metadata
                         if entry.family == 'CommonTemplate'}
        self._loaded = {}
        self._bytes = 0

    def authorize(self, caller):
        app = self._app()
        if app is None:
            raise ValueError('source common template owner is closed')
        app.require_open()
        caller._require_family()
        if (caller._family_owner is not app.interpreter
                or caller._scheduler is not app.interpreter._scheduler
                or getattr(caller, 'application', None) is not app
                or app.state not in ('starting', 'running', 'before_exit', 'exiting')):
            raise ValueError('foreign or inactive source common template owner')
        return app

    def get(self, caller, name):
        from .configuration_source_metadata import SourceMetadataObject
        app = self.authorize(caller)
        if type(name) is str and 1 <= len(name) <= 128:
            key = name.casefold()
        elif type(name) is SourceMetadataObject:
            entry = name._entry
            if (name._root is not app.metadata or entry.family != 'CommonTemplate'
                    or app.metadata.find_by_full_name('CommonTemplate.' + entry.name) is not name):
                raise ValueError('foreign source common template metadata')
            key = entry.name.casefold()
        else:
            raise TypeError('common template name requires String or owned metadata')
        entry = self._entries.get(key)
        if entry is None:
            raise ValueError('unknown source common template')
        if app.metadata.find_by_full_name('CommonTemplate.' + entry.name) is None:
            raise ValueError('source common template is not declared')
        definition = self._loaded.get(key)
        if definition is None:
            if len(self._loaded) >= 128:
                raise ValueError('source common template resource count bound')
            from .configuration_templates import read_common_templates
            try:
                issues = []
                definition, = read_common_templates(app.files, [entry.name], set(), issues)
                if issues or definition.identity != entry.identity:
                    raise ValueError('source common template metadata mismatch')
            except ValueError as error:
                raise ValueError(entry.path + ': common template cannot be loaded: ' + str(error)) from None
            if self._bytes + len(definition.content) > 8 * 1024 * 1024:
                raise ValueError('source common template total resource bound')
            self._loaded[key] = definition
            self._bytes += len(definition.content)
        if definition.kind == 'TextDocument':
            from .text_documents import BSLTextDocument
            value = BSLTextDocument()
            value.set_text(definition.content.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n'))
            return value
        from .file_io import BSLBinaryData
        return BSLBinaryData.from_bytes(definition.content)


class SourceTemplateCall:
    def __init__(self, owner):
        self.owner = owner

    def __call__(self, *args):
        raise ValueError('source templates require an interpreter invocation')

    def invoke(self, caller, values):
        if len(values) != 1:
            raise TypeError('GetCommonTemplate requires one argument')
        return self.owner.get(caller, values[0])
