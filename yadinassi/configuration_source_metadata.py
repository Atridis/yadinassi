"""Read-only source metadata, not operational database metadata.

Collections follow the actual XML ChildObjects inventory and retain its order.
Only source-backed scalar properties are exposed. Unknown object properties,
embedded fields, types, storage managers and absent declarations are not guessed.
"""
import xml.etree.ElementTree as ET
from io import BytesIO

from .configuration_source import ConfigurationSource
from .configuration_xml import MD, XR, XSI
from .metadata import _MetadataObject, _DeclaredMetadataCollection
from .values import HostFunction

# XML family, directory/English collection, Russian collection, full-name label.
_FAMILIES = (
    ('Language', 'Languages', 'Языки', 'Язык'),
    ('Subsystem', 'Subsystems', 'Подсистемы', 'Подсистема'),
    ('CommonModule', 'CommonModules', 'ОбщиеМодули', 'ОбщийМодуль'),
    ('SessionParameter', 'SessionParameters', 'ПараметрыСеанса', 'ПараметрСеанса'),
    ('Catalog', 'Catalogs', 'Справочники', 'Справочник'),
    ('Document', 'Documents', 'Документы', 'Документ'),
    ('Enum', 'Enums', 'Перечисления', 'Перечисление'),
    ('InformationRegister', 'InformationRegisters', 'РегистрыСведений', 'РегистрСведений'),
    ('AccumulationRegister', 'AccumulationRegisters', 'РегистрыНакопления', 'РегистрНакопления'),
    ('Report', 'Reports', 'Отчеты', 'Отчет'),
    ('DataProcessor', 'DataProcessors', 'Обработки', 'Обработка'),
    ('CommonForm', 'CommonForms', 'ОбщиеФормы', 'ОбщаяФорма'),
    ('CommonTemplate', 'CommonTemplates', 'ОбщиеМакеты', 'ОбщийМакет'),
    ('Constant', 'Constants', 'Константы', 'Константа'),
    ('Role', 'Roles', 'Роли', 'Роль'),
    ('CommonCommand', 'CommonCommands', 'ОбщиеКоманды', 'ОбщаяКоманда'),
    ('ScheduledJob', 'ScheduledJobs', 'РегламентныеЗадания', 'РегламентноеЗадание'),
    ('FunctionalOption', 'FunctionalOptions', 'ФункциональныеОпции', 'ФункциональнаяОпция'),
    ('ExchangePlan', 'ExchangePlans', 'ПланыОбмена', 'ПланОбмена'),
    ('DocumentJournal', 'DocumentJournals', 'ЖурналыДокументов', 'ЖурналДокументов'),
    ('BusinessProcess', 'BusinessProcesses', 'БизнесПроцессы', 'БизнесПроцесс'),
    ('Task', 'Tasks', 'Задачи', 'Задача'),
)
_COLLECTIONS = {name.casefold(): family for family in _FAMILIES for name in family[1:3]}
_FAMILY = {family[0]: family for family in _FAMILIES}
_FULL_FAMILIES = {name.casefold(): family for family in _FAMILIES for name in (family[0], family[3])}
_SCALARS = {
    'languagecode': ('LanguageCode', str), 'кодязыка': ('LanguageCode', str),
    'comment': ('Comment', str), 'комментарий': ('Comment', str),
    'version': ('Version', str), 'версия': ('Version', str),
    'includeincommandinterface': ('IncludeInCommandInterface', bool),
    'включатьвкомандныйинтерфейс': ('IncludeInCommandInterface', bool),
    'includehelpincontents': ('IncludeHelpInContents', bool),
    'включатьсправкувсодержание': ('IncludeHelpInContents', bool),
    'global': ('Global', bool), 'глобальный': ('Global', bool),
    'clientmanagedapplication': ('ClientManagedApplication', bool),
    'клиентуправляемоеприложение': ('ClientManagedApplication', bool),
    'server': ('Server', bool), 'сервер': ('Server', bool),
    'servercall': ('ServerCall', bool), 'вызовсервера': ('ServerCall', bool),
    'privileged': ('Privileged', bool), 'привилегированный': ('Privileged', bool),
}


class SourceMetadataObject(_MetadataObject):
    def __init__(self, root, entry, parent=None):
        self._root, self._entry, self._parent = root, entry, parent
        self._name = entry.name
        self._xml = None
        self._collections = {}

    def _object(self):
        if self._xml is None:
            # Preserve QName namespace scopes as ElementTree does not expand
            # attribute values such as xsi:type.
            self._namespaces = {}
            scopes, pending = [{}], {}
            parser = ET.iterparse(BytesIO(self._root._files[self._entry.path]),
                                  events=('start-ns', 'start', 'end'))
            for event, value in parser:
                if event == 'start-ns':
                    pending[value[0]] = value[1]
                elif event == 'start':
                    scope = dict(scopes[-1]); scope.update(pending); pending.clear()
                    scopes.append(scope); self._namespaces[value] = scope
                else:
                    scopes.pop()
            self._xml = parser.root[0]
        return self._xml

    def _property(self, name):
        properties = self._object().find('{' + MD + '}Properties')
        items = properties.findall('{' + MD + '}' + name) if properties is not None else []
        if len(items) != 1:
            raise ValueError('source metadata property absent or ambiguous: ' + self._entry.path + ': ' + name)
        return items[0]

    def full_name(self):
        if self._entry.family == 'Configuration':
            raise ValueError('configuration root FullName is unsupported')
        family = _FAMILY[self._entry.family]
        # Keep the established interpreter metadata FullName convention.
        name = family[3] + '.' + self._name
        return self._parent.full_name() + '.' + name if self._parent is not None else name

    def _collection(self, family):
        if self._entry.family != 'Configuration' and not (
                self._entry.family == 'Subsystem' and family[0] == 'Subsystem'):
            raise ValueError('source metadata child collection is unsupported: ' + family[1])
        if family[0] in self._collections:
            return self._collections[family[0]]
        directory = '' if self._entry.family == 'Configuration' else self._entry.path[:-4] + '/'
        prefix = directory + family[1] + '/'
        nodes = self._object().findall('{' + MD + '}ChildObjects')
        if len(nodes) > 1:
            raise ValueError('ambiguous source ChildObjects')
        names = []
        for node in nodes[0] if nodes else ():
            if node.tag != '{' + MD + '}' + family[0]:
                continue
            if node.attrib or len(node) or not node.text or not node.text.isidentifier():
                raise ValueError('unsupported source metadata child declaration')
            names.append(node.text)
        expected = {prefix + name + '.xml' for name in names}
        actual = {path for path, entry in self._root._inventory.items()
                  if entry.family == family[0] and path.startswith(prefix)
                  and '/' not in path[len(prefix):]}
        if expected != actual:
            raise ValueError('source metadata declared files do not match inventory: ' + prefix)
        values = []
        for name in names:
            path = prefix + name + '.xml'
            entry = self._root._inventory[path]
            if entry.name != name or entry.family != family[0]:
                raise ValueError('source metadata declaration/name mismatch: ' + path)
            parent = None if self._entry.family == 'Configuration' else self
            values.append(self._root._objects.setdefault(path, SourceMetadataObject(self._root, entry, parent)))
        result = _DeclaredMetadataCollection(tuple(values))
        self._collections[family[0]] = result
        return result

    def get_member(self, name):
        key = name.casefold()
        if key in ('name', 'имя'):
            return self._name
        if key in ('fullname', 'полноеимя'):
            return HostFunction(name, self.full_name)
        family = _COLLECTIONS.get(key)
        if family is not None:
            return self._collection(family)
        scalar = _SCALARS.get(key)
        if scalar is not None:
            property_name, kind = scalar
            node = self._property(property_name)
            if node.attrib or len(node):
                raise ValueError('structured source metadata property is unsupported: ' + property_name)
            value = node.text or ''
            if kind is bool:
                if value not in ('true', 'false'):
                    raise ValueError('invalid source metadata Boolean: ' + property_name)
                return value == 'true'
            return value
        return super().get_member(name)


class SourceMetadataRoot(SourceMetadataObject):
    def __init__(self, source):
        if type(source) is not ConfigurationSource:
            raise TypeError('admitted ConfigurationSource required')
        self._files = {entry.path: entry.content for entry in source.files}
        self._inventory = {entry.path: entry for entry in source.metadata}
        self._objects = {}
        entry = self._inventory['Configuration.xml']
        super().__init__(self, entry)

    def _reference_collection(self, property_name, family):
        """Resolve declared references only; metadata membership grants no rights."""
        cache_key = 'reference:' + property_name
        if cache_key in self._collections:
            return self._collections[cache_key]
        node = self._property(property_name)
        if node.attrib or (node.text or '').strip():
            raise ValueError('invalid source metadata reference collection: ' + property_name)
        values = []
        for child in node:
            qname = child.get('{' + XSI + '}type', '').split(':')
            prefix, local = (qname if len(qname) == 2 else ('', qname[0]))
            if (child.tag != '{' + XR + '}Item' or len(child)
                    or set(child.attrib) != {'{' + XSI + '}type'}
                    or len(qname) > 2 or local != 'MDObjectRef'
                    or self._namespaces[child].get(prefix) != XR
                    or (child.tail or '').strip()):
                raise ValueError('unsupported source metadata reference item: ' + property_name)
            text = child.text or ''
            parts = text.split('.')
            if len(parts) != 2 or parts[0] != family or not parts[1].isidentifier():
                raise ValueError('invalid source metadata reference: ' + text)
            value = self.find_by_full_name(text)
            if value is None:
                raise ValueError('source metadata reference is not declared: ' + text)
            values.append(value)
        result = _DeclaredMetadataCollection(tuple(values))
        self._collections[cache_key] = result
        return result

    def find_by_full_name(self, name):
        if type(name) is not str:
            raise TypeError('metadata full name requires String')
        parts = name.split('.')
        if len(parts) % 2 or not parts:
            return None
        owner = self
        for index in range(0, len(parts), 2):
            family = _FULL_FAMILIES.get(parts[index].casefold())
            if family is None:
                raise ValueError('unsupported source metadata family: ' + parts[index])
            owner = owner._collection(family).find(parts[index + 1])
            if owner is None:
                return None
        return owner

    def get_member(self, name):
        if name.casefold() in ('defaultroles', 'основныероли'):
            return self._reference_collection('DefaultRoles', 'Role')
        if name.casefold() in ('objectproperties', 'свойстваобъектов'):
            from .source_metadata_properties import SourceObjectProperties
            return SourceObjectProperties()
        if name.casefold() in ('compatibilitymode', 'режимсовместимости'):
            from .source_metadata_properties import compatibility_mode
            node = self._property('CompatibilityMode')
            if node.attrib or len(node):
                raise ValueError('unsupported structured source CompatibilityMode')
            return compatibility_mode(node.text or '')
        if name.casefold() in ('scriptvariant', 'вариантвстроенногоязыка'):
            from .source_metadata_properties import script_variant
            node = self._property('ScriptVariant')
            if node.attrib or len(node):
                raise ValueError('unsupported structured source ScriptVariant')
            return script_variant(node.text or '')
        if name.casefold() in ('defaultlanguage', 'основнойязык'):
            node = self._property('DefaultLanguage')
            if node.attrib or len(node):
                raise ValueError('unsupported source metadata language reference')
            text = node.text or ''
            parts = text.split('.')
            if len(parts) != 2 or parts[0] != 'Language' or not parts[1].isidentifier():
                raise ValueError('invalid source metadata default language reference')
            language = self.find_by_full_name(text)
            if language is None:
                raise ValueError('source metadata default language is not declared')
            return language
        if name.casefold() in ('findbyfullname', 'найтипополномуимени'):
            return HostFunction(name, self.find_by_full_name)
        return super().get_member(name)
