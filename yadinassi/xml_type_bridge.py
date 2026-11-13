"""Explicit legacy XML type mapping for the supported scalar value model.

This is not XDTO's core namespace registry or serialization of metadata objects.
No namespace is resolved through the network and no host reflection is used.
"""
from dataclasses import dataclass
from .values import BSLObject, BSLType

XS = 'http://www.w3.org/2001/XMLSchema'
DATA = 'http://v8.1c.ru/data'


@dataclass(frozen=True, slots=True)
class BSLXMLDataType(BSLObject):
    type_name: str
    namespace_uri: str

    def __post_init__(self):
        if type(self.type_name) is not str or type(self.namespace_uri) is not str:
            raise TypeError('ТипДанныхXML: имя и URI должны иметь тип Строка')
        if len(self.type_name) > 1024 or len(self.namespace_uri) > 4096:
            raise ValueError('ТипДанныхXML: превышен предел длины')

    def get_member(self, name):
        key = name.casefold()
        if key in ('typename', 'имятипа'):
            return self.type_name
        if key in ('namespaceuri', 'uriпространстваимен'):
            return self.namespace_uri
        return super(BSLXMLDataType, self).get_member(name)

    def __str__(self):
        return 'ТипДанныхXML'


_FORWARD = {
    BSLType.STRING: BSLXMLDataType('string', XS),
    BSLType.BOOLEAN: BSLXMLDataType('boolean', XS),
    BSLType.NUMBER: BSLXMLDataType('decimal', XS),
    BSLType.DATE: BSLXMLDataType('dateTime', XS),
    BSLType.UUID: BSLXMLDataType('UUID', DATA),
    BSLType.BINARY_DATA: BSLXMLDataType('base64Binary', XS),
    BSLType.NULL: BSLXMLDataType('Null', DATA),
    BSLType.VALUE_STORAGE: BSLXMLDataType('ValueStorage', DATA),
    BSLType.TYPE: BSLXMLDataType('Type', DATA),
    BSLType.TYPE_DESCRIPTION: BSLXMLDataType('TypeDescription', DATA),
}
_REVERSE = {(value.type_name, value.namespace_uri): key for key, value in _FORWARD.items()}
_MISSING = object()


def xml_type(value_type):
    from .catalog_types import BSLCatalogType
    from .document_types import BSLDocumentType
    from .enum_types import BSLEnumType
    prefixes = {BSLCatalogType: {'ref':'CatalogRef', 'object':'CatalogObject'},
                BSLDocumentType: {'ref':'DocumentRef', 'object':'DocumentObject'},
                BSLEnumType: {'ref':'EnumRef'}}
    for kind, families in prefixes.items():
        if type(value_type) is kind:
            if value_type.family not in families:
                raise ValueError('XMLТип: XML-соответствие семейства метаданных пока не поддержано')
            return BSLXMLDataType(families[value_type.family] + '.' + value_type.name, '')
    if type(value_type) is not BSLType:
        raise TypeError('XMLТип: поддержан только встроенный Тип; типы метаданных пока не поддержаны')
    if value_type not in _FORWARD:
        raise ValueError('XMLТип: XML-соответствие этого типа пока не поддержано')
    return _FORWARD[value_type]


def xml_type_of(value):
    from .type_values import type_of
    return xml_type(type_of(value))


def from_xml_type(value, namespace=_MISSING, *, resolver=None):
    if type(value) is BSLXMLDataType:
        if namespace is not _MISSING:
            raise TypeError('ИзXMLТипа: при ТипДанныхXML второй аргумент не допускается')
        key = value.type_name, value.namespace_uri
    elif type(value) is str and type(namespace) is str:
        descriptor = BSLXMLDataType(value, namespace)
        key = descriptor.type_name, descriptor.namespace_uri
    else:
        raise TypeError('ИзXMLТипа: ожидается ТипДанныхXML или имя типа и URI')
    if key in _REVERSE:
        return _REVERSE[key]
    if not key[1] and key[0].partition('.')[0] in ('CatalogRef','CatalogObject','DocumentRef','DocumentObject','EnumRef'):
        if resolver is None:
            raise ValueError('ИзXMLТипа: тип метаданных требует контекст конфигурации')
        value_type = resolver(key[0])
        # The resolver is the interpreter-owned registry; never construct a new
        # metadata identity or accept case-folded names as exact XML identities.
        if value_type is None:
            return None
        return value_type if xml_type(value_type) == BSLXMLDataType(*key) else None
    # Unknown namespace/type is not aliased by local name or case folding.
    return None


BUILTINS = (('XMLТип', xml_type, 'XMLType'),
            ('XMLТипЗнч', xml_type_of, 'XMLTypeOf'),
            ('ИзXMLТипа', from_xml_type, 'FromXMLType'))
