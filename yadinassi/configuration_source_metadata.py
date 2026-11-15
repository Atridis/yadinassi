"""Read-only source metadata, not operational database metadata.

Collections follow the actual XML ChildObjects inventory and retain its order.
Only source-backed scalar properties are exposed. Unknown object properties,
types, storage managers and absent declarations are not guessed. Inline child
identities are read from XML without granting executable/storage capabilities.
"""
import xml.etree.ElementTree as ET
from io import BytesIO

from .configuration_source import ConfigurationSource, SourceMetadata, _identity
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
    ('ChartOfCharacteristicTypes', 'ChartsOfCharacteristicTypes', 'ПланыВидовХарактеристик', 'ПланВидовХарактеристик'),
    ('ChartOfAccounts', 'ChartsOfAccounts', 'ПланыСчетов', 'ПланСчетов'),
    ('ChartOfCalculationTypes', 'ChartsOfCalculationTypes', 'ПланыВидовРасчета', 'ПланВидовРасчета'),
    ('AccountingRegister', 'AccountingRegisters', 'РегистрыБухгалтерии', 'РегистрБухгалтерии'),
    ('CalculationRegister', 'CalculationRegisters', 'РегистрыРасчета', 'РегистрРасчета'),
    ('CommonAttribute', 'CommonAttributes', 'ОбщиеРеквизиты', 'ОбщийРеквизит'),
    ('EventSubscription', 'EventSubscriptions', 'ПодпискиНаСобытия', 'ПодпискаНаСобытие'),
    ('FunctionalOptionsParameter', 'FunctionalOptionsParameters', 'ПараметрыФункциональныхОпций', 'ПараметрФункциональныхОпций'),
    ('SettingsStorage', 'SettingsStorages', 'ХранилищаНастроек', 'ХранилищеНастроек'),
    ('HTTPService', 'HTTPServices', 'HTTPСервисы', 'HTTPСервис'),
    ('WebService', 'WebServices', 'WebСервисы', 'WebСервис'),
    ('WSReference', 'WSReferences', 'WSСсылки', 'WSСсылка'),
    ('XDTOPackage', 'XDTOPackages', 'XDTOПакеты', 'XDTOПакет'),
    ('StyleItem', 'StyleItems', 'ЭлементыСтиля', 'ЭлементСтиля'),
    ('Interface', 'Interfaces', 'Интерфейсы', 'Интерфейс'),
    ('Style', 'Styles', 'Стили', 'Стиль'),
    ('FilterCriterion', 'FilterCriteria', 'КритерииОтбора', 'КритерийОтбора'),
)
_EMBEDDED = (
    ('Attribute', 'Attributes', 'Реквизиты', 'Реквизит'),
    ('TabularSection', 'TabularSections', 'ТабличныеЧасти', 'ТабличнаяЧасть'),
    ('Dimension', 'Dimensions', 'Измерения', 'Измерение'),
    ('Resource', 'Resources', 'Ресурсы', 'Ресурс'),
    ('EnumValue', 'EnumValues', 'ЗначенияПеречисления', 'ЗначениеПеречисления'),
    ('Command', 'Commands', 'Команды', 'Команда'),
)
_EMBEDDED_OWNERS = {
    'Attribute': {'Catalog', 'Document', 'DataProcessor', 'Report', 'ExchangePlan',
                  'ChartOfCharacteristicTypes', 'ChartOfAccounts', 'ChartOfCalculationTypes',
                  'BusinessProcess', 'Task', 'TabularSection', 'InformationRegister',
                  'AccumulationRegister', 'AccountingRegister', 'CalculationRegister'},
    'TabularSection': {'Catalog', 'Document', 'DataProcessor', 'Report', 'ExchangePlan',
                       'ChartOfCharacteristicTypes', 'ChartOfAccounts', 'ChartOfCalculationTypes',
                       'BusinessProcess', 'Task'},
    'Dimension': {'InformationRegister', 'AccumulationRegister', 'AccountingRegister', 'CalculationRegister'},
    'Resource': {'InformationRegister', 'AccumulationRegister', 'AccountingRegister', 'CalculationRegister'},
    'EnumValue': {'Enum'},
    'Command': {'Catalog', 'Document', 'DataProcessor', 'Report', 'ExchangePlan',
                'ChartOfCharacteristicTypes', 'ChartOfAccounts', 'ChartOfCalculationTypes',
                'BusinessProcess', 'Task', 'InformationRegister', 'AccumulationRegister',
                'AccountingRegister', 'CalculationRegister', 'DocumentJournal'},
}
_FILE_CHILDREN = (
    ('Form', 'Forms', 'Формы', 'Форма'),
    ('Template', 'Templates', 'Макеты', 'Макет'),
)
_FILE_OWNERS = _EMBEDDED_OWNERS['Command']
_COLLECTIONS = {name.casefold(): family for family in _FAMILIES + _EMBEDDED + _FILE_CHILDREN for name in family[1:3]}
_FAMILY = {family[0]: family for family in _FAMILIES + _EMBEDDED + _FILE_CHILDREN}
_FULL_FAMILIES = {name.casefold(): family for family in _FAMILIES + _EMBEDDED + _FILE_CHILDREN for name in (family[0], family[3])}
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

    def _embedded_collection(self, family):
        if self._entry.family not in _EMBEDDED_OWNERS[family[0]]:
            raise ValueError('embedded metadata collection is unsupported for ' + self._entry.family)
        if family[0] in self._collections:
            return self._collections[family[0]]
        nodes = self._object().findall('{' + MD + '}ChildObjects')
        if len(nodes) > 1:
            raise ValueError('ambiguous source ChildObjects')
        values, identities, external_names = [], set(), []
        for node in nodes[0] if nodes else ():
            if node.tag != '{' + MD + '}' + family[0]:
                continue
            if family[0] == 'Command' and not node.attrib and not len(node):
                name = node.text or ''
                if not name.isidentifier() or len(name) > 128:
                    raise ValueError('invalid external command name')
                external_names.append(name)
                child = self._file_child(family, name)
                if child._entry.identity in identities:
                    raise ValueError('duplicate embedded metadata identity')
                identities.add(child._entry.identity)
                values.append(child)
                continue
            identity = _identity(node)
            if identity in identities:
                raise ValueError('duplicate embedded metadata identity')
            identities.add(identity)
            properties = node.findall('{' + MD + '}Properties')
            names = properties[0].findall('{' + MD + '}Name') if len(properties) == 1 else []
            if (len(names) != 1 or names[0].attrib or len(names[0])
                    or not names[0].text or not names[0].text.isidentifier()
                    or len(names[0].text) > 128):
                raise ValueError('invalid embedded source metadata name')
            name = names[0].text
            entry = SourceMetadata(identity, family[0], name, self._entry.path)
            child = SourceMetadataObject(self._root, entry, self)
            child._xml = node
            child._namespaces = self._namespaces
            values.append(child)
        if family[0] == 'Command':
            self._check_file_inventory(family, external_names)
        result = _DeclaredMetadataCollection(tuple(values))
        self._collections[family[0]] = result
        return result

    def _file_prefix(self, family):
        directory = '' if self._entry.family == 'Configuration' else self._entry.path[:-4] + '/'
        return directory + family[1] + '/'

    def _check_file_inventory(self, family, names):
        prefix = self._file_prefix(family)
        expected = {prefix + name + '.xml' for name in names}
        actual = {path for path, entry in self._root._inventory.items()
                  if entry.family == family[0] and path.startswith(prefix)
                  and '/' not in path[len(prefix):]}
        if expected != actual:
            raise ValueError('source metadata declared files do not match inventory: ' + prefix)

    def _file_child(self, family, name):
        path = self._file_prefix(family) + name + '.xml'
        entry = self._root._inventory.get(path)
        if entry is None or entry.name != name or entry.family != family[0]:
            raise ValueError('source metadata declaration/name mismatch: ' + path)
        parent = None if self._entry.family == 'Configuration' else self
        return self._root._objects.setdefault(path, SourceMetadataObject(self._root, entry, parent))

    def _collection(self, family):
        if family in _EMBEDDED:
            return self._embedded_collection(family)
        if not (
                self._entry.family == 'Configuration' and family in _FAMILIES
                or self._entry.family == 'Subsystem' and family[0] == 'Subsystem'
                or self._entry.family in _FILE_OWNERS and family in _FILE_CHILDREN):
            raise ValueError('source metadata child collection is unsupported: ' + family[1])
        if family[0] in self._collections:
            return self._collections[family[0]]
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
        self._check_file_inventory(family, names)
        values = [self._file_child(family, name) for name in names]
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
