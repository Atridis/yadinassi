"""Bounded XML 1.0 document reader; no DTD, external entities or network I/O.

The token snapshot owns no open file descriptors. Native calibration is pending.
!todo Streaming/lazy malformed-input timing, XML 1.1, DTD, XSD, DOM and XDTO
remain outside this ordinary document workflow; never enable entity resolution.
"""
from decimal import Decimal
from enum import Enum
from xml.parsers import expat

from .values import BSLObject, BSLArray, HostFunction
from .maps import BSLMap
from .file_io import _FileMethods, _methods, _read_bytes, _decode, _text, _bool

MAX_XML_BYTES = 16 * 1024 * 1024
MAX_XML_DEPTH = 256
MAX_XML_NODES = 100_000
MAX_NAMESPACE_BINDINGS = 1_000_000
_XML_URI = 'http://www.w3.org/XML/1998/namespace'


class BSLXMLNodeType(Enum):
    NONE = ('None', 'Ничего')
    START = ('StartElement', 'НачалоЭлемента')
    END = ('EndElement', 'КонецЭлемента')
    ATTRIBUTE = ('Attribute', 'Атрибут')
    TEXT = ('Text', 'Текст')
    CDATA = ('CDATASection', 'СекцияCDATA')
    COMMENT = ('Comment', 'Комментарий')
    PI = ('ProcessingInstruction', 'ИнструкцияОбработки')
    DECLARATION = ('XMLDeclaration', 'ОбъявлениеXML')
    WHITESPACE = ('Whitespace', 'ПробельныеСимволы')

    def __str__(self): return self.value[1]


class BSLXMLSpace(Enum):
    DEFAULT = ('Default', 'ПоУмолчанию')
    PRESERVE = ('Preserve', 'Сохранять')
    def __str__(self): return self.value[1]


class BSLXMLValidationType(Enum):
    NO_VALIDATE = ('NoValidate', 'НетПроверки')
    def __str__(self): return self.value[1]


class _EnumNamespace(BSLObject):
    def __init__(self, enum): self._enum = enum
    def get_member(self, name):
        for value in self._enum:
            if name.casefold() in (alias.casefold() for alias in value.value): return value
        return super().get_member(name)


XML_NODE_TYPES = _EnumNamespace(BSLXMLNodeType)
XML_SPACES = _EnumNamespace(BSLXMLSpace)
XML_VALIDATION_TYPES = _EnumNamespace(BSLXMLValidationType)
T = BSLXMLNodeType


class BSLXMLReaderSettings(BSLObject):
    _props = {'version': 'version', 'версия': 'version', 'lang': 'lang', 'язык': 'lang',
              'space': 'space', 'пробельныесимволы': 'space',
              'validationtype': 'validation', 'типпроверкиправильности': 'validation',
              'ignorexmldeclaration': 'ignore_declaration', 'игнорироватьобъявлениеxml': 'ignore_declaration',
              'ignoredocumenttype': 'ignore_doctype', 'игнорироватьтипдокумента': 'ignore_doctype',
              'ignoreprocessinginstructions': 'ignore_pi', 'игнорироватьинструкцииобработки': 'ignore_pi',
              'ignorecomments': 'ignore_comments', 'игнорироватькомментарии': 'ignore_comments',
              'ignorewhitespace': 'ignore_whitespace', 'игнорироватьпробельныесимволы': 'ignore_whitespace',
              'cdatasectionastext': 'cdata_as_text', 'секцииcdataкактекст': 'cdata_as_text',
              'useignorablewhitespace': 'use_whitespace', 'использоватьигнорируемыепробельныесимволы': 'use_whitespace'}

    def __init__(self, version=None, language=None, space=None, validation=None,
                 ignore_declaration=None, ignore_doctype=None, ignore_pi=None,
                 ignore_comments=None, ignore_whitespace=None, cdata_as_text=None,
                 use_whitespace=None):
        self.version = '1.0' if version is None else _text(version)
        if self.version != '1.0': raise ValueError('XML: поддерживается версия 1.0')
        self.lang = '' if language is None else _text(language)
        self.space = BSLXMLSpace.DEFAULT if space is None else space
        if type(self.space) is not BSLXMLSpace: raise TypeError('XML: ожидается ПробельныеСимволыXML')
        self.validation = BSLXMLValidationType.NO_VALIDATE if validation is None else validation
        if self.validation is not BSLXMLValidationType.NO_VALIDATE:
            raise ValueError('XML: проверка схемы/DTD не поддерживается')
        self.ignore_declaration = _bool(ignore_declaration, True)
        self.ignore_doctype = _bool(ignore_doctype, True)
        self.ignore_pi = _bool(ignore_pi)
        self.ignore_comments = _bool(ignore_comments)
        self.ignore_whitespace = _bool(ignore_whitespace, True)
        self.cdata_as_text = _bool(cdata_as_text)
        self.use_whitespace = _bool(use_whitespace)

    def __str__(self): return 'ПараметрыЧтенияXML'
    def get_member(self, name):
        attr = self._props.get(name.casefold())
        if attr: return getattr(self, attr)
        return super().get_member(name)


class BSLXMLNamespaceContext(_FileMethods):
    _methods = _methods(('lookup_prefix', True, 'LookupPrefix НайтиПрефикс'),
                        ('lookup_namespace_uri', True, 'LookupNamespaceURI НайтиURIПространстваИмен'),
                        ('namespace_mappings', True, 'NamespaceMappings СоответствияПространствИмен'),
                        ('prefixes', True, 'Prefixes Префиксы'),
                        ('namespace_uris', True, 'NamespaceURIs URIПространствИмен'))
    def __init__(self, mappings=None, depth=0):
        self._mappings = dict(mappings or {})
        self._depth = depth
    def __str__(self): return 'КонтекстПространствИменXML'
    def lookup_prefix(self, uri):
        uri = _text(uri)
        return next((p for p, u in self._mappings.items() if u == uri), None)
    def lookup_namespace_uri(self, prefix): return self._mappings.get(_text(prefix))
    def namespace_mappings(self):
        result = BSLMap()
        for p, u in self._mappings.items(): result.insert(p, u)
        return result
    def prefixes(self, uri):
        uri = _text(uri)
        result = BSLArray()
        result.items = [p for p, u in self._mappings.items() if u == uri]
        return result
    def namespace_uris(self):
        result = BSLArray()
        result.items = list(dict.fromkeys(self._mappings.values()))
        return result
    def get_member(self, name):
        key = name.casefold()
        if key in ('defaultnamespace', 'пространствоименпоумолчанию'): return self._mappings.get('', '')
        if key in ('depth', 'глубина'): return Decimal(self._depth)
        return super().get_member(name)


def _name(name):
    parts = name.split('|')
    if len(parts) == 1: return name, name, '', ''
    uri, local = parts[:2]
    prefix = parts[2] if len(parts) == 3 else ''
    return (prefix + ':' if prefix else '') + local, local, prefix, uri


def _event(kind, name='', value='', **extra):
    full, local, prefix, uri = _name(name)
    return dict(kind=kind, name=full, local=local, prefix=prefix, uri=uri,
                value=value, attrs=[], declarations=[], context={}, depth=0, **extra)


class BSLXMLReader(_FileMethods):
    _methods = _methods(
        ('set_string', False, 'SetString УстановитьСтроку'),
        ('open_file', False, 'OpenFile ОткрытьФайл'), ('close', False, 'Close Закрыть'),
        ('read', True, 'Read Прочитать'), ('skip', False, 'Skip Пропустить'),
        ('move_to_content', True, 'MoveToContent ПерейтиКСодержимому'),
        ('read_attribute', True, 'ReadAttribute ПрочитатьАтрибут NextAttribute СледующийАтрибут'),
        ('first_attribute', True, 'FirstAttribute ПервыйАтрибут'),
        ('attribute_count', True, 'AttributeCount КоличествоАтрибутов'),
        ('get_attribute', True, 'GetAttribute ПолучитьАтрибут'),
        ('attribute_name', True, 'AttributeName ИмяАтрибута'),
        ('attribute_local_name', True, 'AttributeLocalName ЛокальноеИмяАтрибута'),
        ('attribute_prefix', True, 'AttributePrefix ПрефиксАтрибута'),
        ('attribute_namespace_uri', True, 'AttributeNamespaceURI URIПространстваИменАтрибута'),
        ('attribute_value', True, 'AttributeValue ЗначениеАтрибута'))
    def __init__(self): self.close()
    def __str__(self): return 'ЧтениеXML'
    def close(self):
        self._source = None
        self._tokens = None
        self._position = -1
        self._attribute = -1
        self._current = _event(T.NONE)
        self._settings = BSLXMLReaderSettings()
        self._version = ''; self._xml_encoding = ''; self._input_encoding = ''
    def _set_source(self, source, settings, schemas):
        if settings is not None and type(settings) is not BSLXMLReaderSettings:
            raise TypeError('XML: ожидается ПараметрыЧтенияXML')
        if schemas is not None: raise ValueError('XML: схемы пока не поддерживаются')
        self.close()
        if settings is not None:
            self._settings = BSLXMLReaderSettings(
                settings.version, settings.lang, settings.space, settings.validation,
                settings.ignore_declaration, settings.ignore_doctype, settings.ignore_pi,
                settings.ignore_comments, settings.ignore_whitespace, settings.cdata_as_text,
                settings.use_whitespace)
        self._source = source
    def set_string(self, text, settings=None, schemas=None):
        text = _text(text)
        if len(text.encode('utf-8')) > MAX_XML_BYTES: raise ValueError('XML: превышен предел размера')
        self._set_source(text, settings, schemas)
    def open_file(self, filename, settings=None, schemas=None, encoding=None):
        data = _read_bytes(filename)
        if len(data) > MAX_XML_BYTES: raise ValueError('XML: превышен предел размера')
        source = data if encoding in (None, '') else _decode(data, encoding, 'utf-8')
        self._set_source(source, settings, schemas)
        self._input_encoding = encoding or ''
    def _parse(self):
        parser = expat.ParserCreate(namespace_separator='|')
        parser.namespace_prefixes = True
        parser.ordered_attributes = True
        parser.buffer_text = True
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        tokens, stack, pending = [], [], []
        cdata = False
        bindings = 0
        attribute_nodes = 0
        settings = self._settings
        def forbidden(*args): raise ValueError('XML: DTD и внешние сущности запрещены')
        parser.StartDoctypeDeclHandler = forbidden
        parser.EntityDeclHandler = forbidden
        parser.ExternalEntityRefHandler = forbidden
        parser.SkippedEntityHandler = forbidden
        def add(event):
            if len(tokens) >= MAX_XML_NODES: raise ValueError('XML: превышен предел узлов')
            if stack:
                event['context'] = stack[-1]['context']
                event['depth'] = len(stack)
                event['space'] = stack[-1]['space']
                event['lang'] = stack[-1]['lang']
            else:
                event['space'] = settings.space; event['lang'] = settings.lang
            tokens.append(event)
        def start(name, attrs):
            nonlocal bindings, attribute_nodes
            if len(stack) >= MAX_XML_DEPTH: raise ValueError('XML: превышена глубина')
            context = dict(stack[-1]['context']) if stack else {'xml': _XML_URI}
            context.update(pending)
            bindings += len(context)
            if bindings > MAX_NAMESPACE_BINDINGS: raise ValueError('XML: превышен предел пространств имен')
            e = _event(T.START, name)
            e['context'] = context; e['declarations'] = list(pending); pending.clear()
            e['space'] = stack[-1]['space'] if stack else settings.space
            e['lang'] = stack[-1]['lang'] if stack else settings.lang
            for i in range(0, len(attrs), 2):
                attribute_nodes += 1
                if attribute_nodes > MAX_XML_NODES: raise ValueError('XML: превышен предел атрибутов')
                attr = _event(T.ATTRIBUTE, attrs[i], attrs[i+1])
                e['attrs'].append(attr)
                if attr['uri'] == _XML_URI and attr['local'] == 'space':
                    if attr['value'] not in ('default', 'preserve'): raise ValueError('XML: неверный xml:space')
                    e['space'] = BSLXMLSpace.PRESERVE if attr['value'] == 'preserve' else BSLXMLSpace.DEFAULT
                if attr['uri'] == _XML_URI and attr['local'] == 'lang': e['lang'] = attr['value']
            stack.append(e); add(e)
        def end(name):
            add(_event(T.END, name)); stack.pop()
        def characters(value):
            if not value: return
            kind = T.CDATA if cdata and not settings.cdata_as_text else T.TEXT
            whitespace = kind is T.TEXT and not value.strip(' \t\r\n')
            if whitespace:
                kind = T.WHITESPACE if settings.use_whitespace else T.TEXT
            # Keep Expat's chunks in a list; avoid quadratic concatenation.
            if tokens and tokens[-1]['kind'] is kind and tokens[-1].get('_chunks') is not None and tokens[-1].get('_whitespace') == whitespace:
                tokens[-1]['_chunks'].append(value)
            else:
                e = _event(kind); e['_chunks'] = [value]; e['_whitespace'] = whitespace; add(e)
        def declaration(version, encoding, standalone):
            if version != '1.0': raise ValueError('XML: поддерживается версия 1.0')
            self._version = version; self._xml_encoding = encoding or ''
            if not settings.ignore_declaration:
                value = 'version="'+version+'"' + (' encoding="'+encoding+'"' if encoding else '')
                add(_event(T.DECLARATION, 'xml', value))
        def set_cdata(value):
            nonlocal cdata
            cdata = value
        parser.StartNamespaceDeclHandler = lambda prefix, uri: pending.append((prefix or '', uri or ''))
        parser.StartElementHandler = start; parser.EndElementHandler = end
        parser.CharacterDataHandler = characters
        parser.XmlDeclHandler = declaration
        parser.CommentHandler = lambda value: None if settings.ignore_comments else add(_event(T.COMMENT, value=value))
        parser.ProcessingInstructionHandler = lambda name, value: None if settings.ignore_pi else add(_event(T.PI, name, value))
        parser.StartCdataSectionHandler = lambda: set_cdata(True)
        parser.EndCdataSectionHandler = lambda: set_cdata(False)
        try: parser.Parse(self._source, True)
        except expat.ExpatError as error: raise ValueError(f'XML: {error}') from error
        for e in tokens:
            if '_chunks' in e: e['value'] = ''.join(e.pop('_chunks'))
        self._tokens = tokens
    def read(self):
        if self._source is None: raise ValueError('XML: источник не открыт')
        if self._tokens is None: self._parse()
        self._position = min(self._position + 1, len(self._tokens))
        while self._position < len(self._tokens):
            token = self._tokens[self._position]
            if not (token.get('_whitespace') and self._settings.ignore_whitespace
                    and token.get('space') is not BSLXMLSpace.PRESERVE): break
            self._position += 1
        self._attribute = -1
        self._current = self._tokens[self._position] if self._position < len(self._tokens) else _event(T.NONE)
        return self._current['kind'] is not T.NONE
    def skip(self):
        if self._current['kind'] in (T.START, T.ATTRIBUTE):
            depth = self._tokens[self._position]['depth']
            while self.read():
                if self._current['kind'] is T.END and self._current['depth'] == depth: break
        self.read()
    def move_to_content(self, space=None):
        if space is not None and type(space) is not BSLXMLSpace: raise TypeError('XML: ожидается ПробельныеСимволыXML')
        while True:
            kind = self._current['kind']
            if kind in (T.START, T.END, T.CDATA): return kind
            if kind in (T.TEXT, T.WHITESPACE):
                preserve = (space or self._current.get('space')) is BSLXMLSpace.PRESERVE
                if preserve or self._current['value'].strip(' \t\r\n'): return kind
            if not self.read(): return T.NONE
    def _attributes(self):
        if self._current['kind'] not in (T.START, T.ATTRIBUTE): return []
        return self._tokens[self._position]['attrs']
    def attribute_count(self): return Decimal(len(self._attributes()))
    def first_attribute(self):
        self._attribute = -1
        return self.read_attribute()
    def read_attribute(self):
        attrs = self._attributes()
        if self._attribute + 1 >= len(attrs): return False
        self._attribute += 1
        self._current = dict(attrs[self._attribute])
        parent = self._tokens[self._position]
        for k in ('context', 'depth', 'space', 'lang'): self._current[k] = parent[k]
        return True
    def _attribute_at(self, index):
        if type(index) is not Decimal or not index.is_finite() or index != index.to_integral_value(): raise TypeError('XML: индекс должен быть Число')
        attrs = self._attributes()
        if index < 0 or index >= len(attrs): raise ValueError('XML: индекс атрибута вне границ')
        return attrs[int(index)]
    def get_attribute(self, name, uri=None):
        if type(name) is Decimal:
            if uri is not None: raise TypeError('XML: лишний параметр')
            return self._attribute_at(name)['value']
        name = _text(name)
        if uri is not None: uri = _text(uri)
        return next((a['value'] for a in self._attributes()
                     if (a['name'] == name if uri is None else a['local'] == name and a['uri'] == uri)), None)
    # !todo XMLAttributeType and DTD declaration cursor are not inferred from
    # ordinary attributes; DTD input remains forbidden regardless of settings.
    def attribute_name(self, index): return self._attribute_at(index)['name']
    def attribute_local_name(self, index): return self._attribute_at(index)['local']
    def attribute_prefix(self, index): return self._attribute_at(index)['prefix']
    def attribute_namespace_uri(self, index): return self._attribute_at(index)['uri']
    def attribute_value(self, name, uri=None): return self.get_attribute(name, uri)
    def _writer_current(self):
        e = self._current
        kinds = {T.START:'start', T.END:'end', T.TEXT:'text', T.WHITESPACE:'text', T.CDATA:'cdata',
                 T.COMMENT:'comment', T.PI:'pi', T.DECLARATION:'declaration', T.ATTRIBUTE:'attribute'}
        if e['kind'] not in kinds: raise ValueError('XML: текущий узел отсутствует')
        return dict(e, kind=kinds[e['kind']], empty=False,
                    attrs=[('xmlns'+(':'+p if p else ''),u) for p,u in e['declarations']] +
                          [(a['name'],a['value']) for a in e['attrs']])
    def get_member(self, name):
        key = name.casefold(); e = self._current
        props = {'nodetype':'kind','типузла':'kind','name':'name','имя':'name','localname':'local',
                 'локальноеимя':'local','prefix':'prefix','префикс':'prefix','namespaceuri':'uri',
                 'uriпространстваимен':'uri','value':'value','значение':'value'}
        if key in props: return e[props[key]]
        if key in ('hasname','имеетимя'): return bool(e['name'])
        if key in ('hasvalue','имеетзначение'): return e['kind'] in (T.TEXT,T.CDATA,T.WHITESPACE,T.ATTRIBUTE,T.COMMENT,T.PI,T.DECLARATION)
        if key in ('ischaracters','этосимвольныеданные'): return e['kind'] in (T.TEXT,T.CDATA,T.WHITESPACE)
        if key in ('iswhitespace','этопробельныесимволы'): return e['kind'] in (T.TEXT,T.WHITESPACE) and not e['value'].strip(' \t\r\n')
        if key in ('namespacecontext','контекстпространствимен'): return BSLXMLNamespaceContext(e['context'],e['depth'])
        if key in ('settings','параметры'): return self._settings
        if key in ('ignorewhitespace','игнорироватьпробелы'): return self._settings.ignore_whitespace
        if key in ('xmlversion','версияxml'): return self._version
        if key in ('xmlencoding','кодировкаxml'): return self._xml_encoding
        if key in ('inputencoding','кодировкаисточника'): return self._input_encoding
        if key in ('lang','язык'): return e.get('lang',self._settings.lang)
        if key in ('space','пробельныесимволы'): return e.get('space',self._settings.space)
        return super().get_member(name)
    def set_member(self, name, value):
        if name.casefold() in ('ignorewhitespace','игнорироватьпробелы'):
            self._settings.ignore_whitespace = _bool(value)
            return
        return super().set_member(name,value)
