"""Bounded XML 1.0 writer; no DTD, entities, streams or external resources."""
from xml.parsers import expat
from .values import BSLObject, HostFunction
from . import file_io

MAX_TEXT = 1_000_000
MAX_DEPTH = 128
MAX_NODES = 100_000
_XML_URI = 'http://www.w3.org/XML/1998/namespace'
_XMLNS_URI = 'http://www.w3.org/2000/xmlns/'


def _text(value):
    if type(value) is not str:
        raise TypeError('XML: ожидается Строка')
    if len(value) > MAX_TEXT:
        raise ValueError('XML: превышен предел ресурсов Yadinassi')
    if any(not (c in '\t\r\n' or '\x20' <= c <= '\ud7ff' or '\ue000' <= c <= '\ufffd' or '\U00010000' <= c <= '\U0010ffff') for c in value):
        raise ValueError('XML: недопустимый символ XML 1.0')
    return value


def _name(value, qualified=True):
    value = _text(value)
    parts = value.split(':') if qualified else [value]
    if len(parts) > 2 or any(not p or not (p[0].isalpha() or p[0] == '_') or
                            any(not (c.isalnum() or c in '_.-') for c in p) for p in parts):
        raise ValueError('XML: недопустимое имя')
    # !todo Full XML Unicode name ranges, notably combining marks, need a
    # later names matrix; ordinary Latin/Cyrillic identifiers are supported.
    return value


def _escape(value, attribute=False):
    value = _text(value)
    chars = {'&': '&amp;', '<': '&lt;', '>': '&gt;'}
    if attribute:
        chars.update({'"': '&quot;', '\r': '&#xD;', '\n': '&#xA;', '\t': '&#x9;'})
    size = sum(len(chars.get(c, c)) for c in value)
    if size > MAX_TEXT:
        raise ValueError('XML: превышен предел экранированного текста')
    return ''.join(chars.get(c, c) for c in value)


class BSLXMLWriterSettings(BSLObject):
    def __init__(self, encoding=None, version=None, indent=None, indent_attributes=None, indent_chars=None):
        self.encoding = 'UTF-8' if encoding is None else _text(encoding)
        if self.encoding: file_io._encoding(self.encoding)
        self.version = '1.0' if version is None else _text(version)
        # !todo XML 1.1 control-character rules are not inferred from XML 1.0.
        if self.version != '1.0': raise ValueError('XML: поддерживается версия 1.0')
        self.indent = file_io._bool(indent, True)
        self.indent_attributes = file_io._bool(indent_attributes)
        self.indent_chars = '\t' if indent_chars is None else _text(indent_chars)
        if any(c not in ' \r\n\t' for c in self.indent_chars):
            raise ValueError('XML: отступ должен состоять из пробельных символов')
        if len(self.indent_chars) > 256: raise ValueError('XML: превышен предел отступа')
    def __str__(self): return 'ПараметрыЗаписиXML'
    def get_member(self, name):
        names = {'encoding': 'encoding', 'кодировка': 'encoding', 'version': 'version', 'версия': 'version',
                 'indent': 'indent', 'отступ': 'indent', 'indentattributes': 'indent_attributes',
                 'отступатрибутов': 'indent_attributes', 'indentchars': 'indent_chars', 'символыотступа': 'indent_chars'}
        if name.casefold() in names: return getattr(self, names[name.casefold()])
        return super().get_member(name)


class BSLXMLWriter(BSLObject):
    def __init__(self):
        self._active = False; self._stream = None; self._indent_setting = True
        self._settings = BSLXMLWriterSettings(''); self._stack = []
    def __str__(self): return 'ЗаписьXML'
    def _require(self):
        if not self._active: raise ValueError('ЗаписьXML: запись не открыта')
    def _configure(self, settings):
        if settings is None or type(settings) is str:
            encoding = '' if settings is None else _text(settings)
            settings = BSLXMLWriterSettings(encoding, indent=self._indent_setting)
        elif type(settings) is not BSLXMLWriterSettings:
            raise TypeError('ЗаписьXML: ожидаются параметры записи или кодировка')
        # Copy settings: host-side mutation must not change an active writer.
        return BSLXMLWriterSettings(settings.encoding, settings.version, settings.indent,
                                    settings.indent_attributes, settings.indent_chars)
    def _reset(self, settings):
        self._dispose()
        self._settings = settings; self._roots = []; self._stack = []
        self._cost = 0; self._nodes = 0; self._attribute = None; self._active = True
    @file_io._file_errors
    def set_string(self, settings=None): self._reset(self._configure(settings))
    @file_io._file_errors
    def open_file(self, filename, settings=None, add_bom=None):
        settings = self._configure(settings)
        filename = file_io._path(filename); add_bom = file_io._bool(add_bom, True)
        encoding = file_io._encoding(settings.encoding or None)
        mark = file_io._encode('', encoding, add_bom)
        # Flush/close old descriptor before a same-file truncation.
        self._reset(settings)
        try:
            self._stream = file_io._open_regular(filename, writing=True)
            self._encoding, self._bom = encoding, mark
        except BaseException:
            self._active = False
            raise
    def _dispose(self):
        stream, self._stream = self._stream, None
        self._active = False
        if stream is not None: stream.close()
    def __del__(self):
        stream = getattr(self, '_stream', None)
        if stream is not None: stream.close()
    def _charge(self, cost=0, nodes=0):
        if self._cost + cost > MAX_TEXT or self._nodes + nodes > MAX_NODES:
            raise ValueError('XML: превышен предел ресурсов Yadinassi')
        self._cost += cost; self._nodes += nodes
    def _scope(self):
        result = {'xml': _XML_URI}
        for element in self._stack: result.update(element['ns'])
        return result
    def lookup_prefix(self, uri):
        self._require(); uri = _text(uri)
        for prefix, mapped in reversed(tuple(self._scope().items())):
            if uri == mapped: return prefix
        return None
    def _resolve(self, name, uri, attribute=False):
        scope = self._scope()
        if uri is not None:
            matches = [p for p,u in scope.items() if u == uri and (p or not attribute)]
            if not uri: return name
            if not matches: raise ValueError('XML: пространство имен не объявлено')
            prefix = matches[-1]
            return prefix + ':' + name if prefix else name
        if ':' in name and name.split(':')[0] not in scope:
            raise ValueError('XML: префикс не объявлен')
        return name
    def _finish_start(self):
        if self._attribute is not None: raise ValueError('XML: запись атрибута не завершена')
        if self._stack:
            element = self._stack[-1]
            if element['pending']:
                if element['uri'] == '' and self._scope().get('', ''):
                    if '' in element['ns']:
                        raise ValueError('XML: URI элемента конфликтует с пространством по умолчанию')
                    self.write_namespace_mapping('', '')
                element['qname'] = self._resolve(element['name'], element['uri'])
                element['pending'] = False
    def _append(self, node):
        self._require(); self._finish_start()
        (self._stack[-1]['children'] if self._stack else self._roots).append(node)
    def write_start_element(self, name, uri=None):
        self._require(); name = _name(name, uri is None)
        uri = None if uri is None else _text(uri)
        if len(self._stack) >= MAX_DEPTH: raise ValueError('XML: превышен предел глубины')
        self._finish_start()
        self._charge(len(name)*2+5, 1)
        element = {'kind':'element','name':name,'uri':uri,'qname':None,'ns':{},'attrs':[],
                   'attrkeys':set(),'children':[],'pending':True}
        (self._stack[-1]['children'] if self._stack else self._roots).append(element)
        self._stack.append(element)
    def write_namespace_mapping(self, prefix, uri):
        self._require(); prefix = _text(prefix); uri = _text(uri)
        if prefix: _name(prefix, False)
        if not self._stack or not self._stack[-1]['pending'] or self._attribute is not None:
            raise ValueError('XML: пространство имен должно предшествовать содержимому')
        if prefix == 'xmlns' or uri == _XMLNS_URI or (prefix == 'xml') != (uri == _XML_URI) or (prefix and not uri):
            raise ValueError('XML: недопустимое отображение пространства имен')
        element = self._stack[-1]
        if prefix in element['ns']: raise ValueError('XML: повторное объявление префикса')
        if prefix and any(name.startswith(prefix+':') for name,_ in element['attrs']) and self._scope().get(prefix) != uri:
            raise ValueError('XML: нельзя изменить пространство уже записанного атрибута')
        escaped = _escape(uri, True); self._charge(len(prefix)+len(escaped)+10, 1)
        element['ns'][prefix] = uri
        element['attrs'].append(('xmlns:'+prefix if prefix else 'xmlns', escaped))
    def _attribute_name(self, name, uri):
        if not self._stack or not self._stack[-1]['pending'] or self._attribute is not None:
            raise ValueError('XML: атрибут должен предшествовать содержимому')
        name = _name(name, uri is None); uri = None if uri is None else _text(uri)
        if name == 'xmlns' or name.startswith('xmlns:'):
            raise ValueError('XML: используйте ЗаписатьСоответствиеПространстваИмен')
        qname = self._resolve(name, uri, True)
        local = qname.split(':')[-1]
        mapped = self._scope().get(qname.split(':')[0], '') if ':' in qname else ''
        key = (mapped, local)
        if key in self._stack[-1]['attrkeys']: raise ValueError('XML: повторный атрибут')
        return qname,key
    def write_attribute(self, name, *args):
        self._require()
        if len(args) == 1: uri,value = None,args[0]
        elif len(args) == 2: uri,value = args
        else: raise TypeError('XML: ожидаются имя, значение или имя, URI, значение')
        qname,key = self._attribute_name(name,uri); value = _escape(value,True)
        self._charge(len(qname)+len(value)+4,1)
        self._stack[-1]['attrkeys'].add(key); self._stack[-1]['attrs'].append((qname,value))
    def write_start_attribute(self,name,uri=None):
        self._require(); qname,key=self._attribute_name(name,uri)
        self._charge(len(qname)+4,1); self._attribute=[qname,key,[]]
    def write_end_attribute(self):
        self._require()
        if self._attribute is None: raise ValueError('XML: нет открытого атрибута')
        name,key,parts=self._attribute
        self._stack[-1]['attrkeys'].add(key); self._stack[-1]['attrs'].append((name,''.join(parts)))
        self._attribute=None
    def write_text(self,value):
        self._require(); escaped=_escape(value,self._attribute is not None)
        if self._attribute is not None:
            self._charge(len(escaped)); self._attribute[2].append(escaped); return
        if not self._stack: raise ValueError('XML: текст должен находиться внутри элемента')
        self._finish_start(); self._charge(len(escaped),1)
        self._stack[-1]['children'].append({'kind':'text','value':escaped})
    def write_end_element(self):
        self._require()
        if not self._stack: raise ValueError('XML: нет открытого элемента')
        self._finish_start(); self._stack.pop()
    def write_xml_declaration(self):
        self._require()
        if self._roots or self._stack: raise ValueError('XML: декларация должна быть первой')
        value = '<?xml version="1.0"' + (' encoding="'+_escape(self._settings.encoding,True)+'"' if self._settings.encoding else '') + '?>'
        self._charge(len(value),1); self._roots.append({'kind':'declaration','value':value})
    def write_comment(self,value):
        self._require(); value=_text(value)
        if '--' in value or value.endswith('-'): raise ValueError('XML: недопустимый комментарий')
        self._finish_start(); self._charge(len(value)+7,1)
        self._append({'kind':'comment','value':'<!--'+value+'-->'})
    def write_cdata_section(self,value):
        self._require(); value=_text(value)
        if not self._stack: raise ValueError('XML: CDATA должна находиться внутри элемента')
        if ']]>' in value: raise ValueError('XML: недопустимая CDATA')
        self._finish_start(); self._charge(len(value)+12,1)
        self._append({'kind':'cdata','value':'<![CDATA['+value+']]>'})
    def write_processing_instruction(self,name,value):
        self._require(); name=_name(name,False);value=_text(value)
        if name.casefold() == 'xml' or '?>' in value: raise ValueError('XML: недопустимая инструкция')
        self._finish_start(); self._charge(len(name)+len(value)+5,1)
        self._append({'kind':'pi','value':'<?'+name+(' '+value if value else '')+'?>'})
    def write_raw(self,value):
        self._require(); value=_text(value)
        self._finish_start()
        # Bounded extension: unlike native unchecked WriteRaw, validate a local
        # fragment. No DTD/entity loading, files or network can be consulted.
        # !todo Unchecked malformed fragment insertion is intentionally absent.
        mappings = ''.join(' xmlns'+(':'+p if p else '')+'="'+_escape(u,True)+'"'
                           for p,u in self._scope().items() if p != 'xml')
        source='<wrapper'+mappings+'>'+value+'</wrapper>'
        if len(source)>MAX_TEXT: raise ValueError('XML: превышен предел фрагмента')
        parser=expat.ParserCreate(namespace_separator='|')
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        depth=0; nodes=0
        def forbidden(*args): raise ValueError('XML: DTD и сущности запрещены')
        def start(name,attrs):
            nonlocal depth,nodes
            depth+=1;nodes+=1+len(attrs)
            if depth-1+len(self._stack)>MAX_DEPTH or nodes>MAX_NODES:
                raise ValueError('XML: превышен предел фрагмента')
        def end(name):
            nonlocal depth
            depth-=1
        def event(*args):
            nonlocal nodes
            nodes+=1
            if nodes>MAX_NODES:raise ValueError('XML: превышен предел фрагмента')
        parser.StartElementHandler=start;parser.EndElementHandler=end
        parser.CharacterDataHandler=event;parser.CommentHandler=event;parser.ProcessingInstructionHandler=event
        parser.StartDoctypeDeclHandler=forbidden;parser.EntityDeclHandler=forbidden
        parser.ExternalEntityRefHandler=forbidden;parser.SkippedEntityHandler=forbidden
        try:parser.Parse(source,True)
        except expat.ExpatError as error:raise ValueError('XML: некорректный фрагмент') from error
        self._charge(len(value),nodes)
        self._append({'kind':'raw','value':value})
    def write_current(self,reader):
        from .xml_io import BSLXMLReader
        if type(reader) is not BSLXMLReader: raise TypeError('XML: ожидается ЧтениеXML')
        event=reader._writer_current()
        kind=event['kind']
        if kind == 'start':
            self.write_start_element(event['name'])
            for name,value in event.get('attrs',[]):
                if name == 'xmlns': self.write_namespace_mapping('',value)
                elif name.startswith('xmlns:'): self.write_namespace_mapping(name[6:],value)
            for name,value in event.get('attrs',[]):
                if name != 'xmlns' and not name.startswith('xmlns:'): self.write_attribute(name,value)
            if event.get('empty'): self.write_end_element()
        elif kind == 'end': self.write_end_element()
        elif kind == 'attribute': self.write_attribute(event['name'],event['value'])
        elif kind in ('text','whitespace'):
            value = event['value']
            if not self._stack and not _text(value).strip():
                self._require(); self._charge(len(value),1)
                self._roots.append({'kind':'whitespace','value':value})
            else: self.write_text(value)
        elif kind == 'cdata': self.write_cdata_section(event['value'])
        elif kind == 'comment': self.write_comment(event['value'])
        elif kind == 'pi': self.write_processing_instruction(event['name'],event['value'])
        elif kind == 'declaration': self.write_xml_declaration()
        else: raise ValueError('XML: текущее состояние чтения не поддерживается')
    def _render(self):
        chunks=[]; size=0
        def emit(text):
            nonlocal size
            size+=len(text)
            if size>MAX_TEXT: raise ValueError('XML: превышен предел результата')
            chunks.append(text)
        def node(value,depth):
            if value['kind']!='element': emit(value['value']);return
            emit('<'+value['qname'])
            for name,text in value['attrs']:
                emit(('\n'+self._settings.indent_chars*(depth+1)) if self._settings.indent_attributes else ' ')
                emit(name+'="'+text+'"')
            if not value['children']: emit('/>');return
            emit('>')
            pretty=self._settings.indent and not any(x['kind'] in ('text','cdata','raw') for x in value['children'])
            for child in value['children']:
                if pretty: emit('\n'+self._settings.indent_chars*(depth+1))
                node(child,depth+1)
            if pretty: emit('\n'+self._settings.indent_chars*depth)
            emit('</'+value['qname']+'>')
        for index,value in enumerate(self._roots):
            if index and self._settings.indent: emit('\n')
            node(value,0)
        return ''.join(chunks)
    @file_io._file_errors
    def close(self):
        self._require()
        is_file=self._stream is not None
        try:
            if self._stack or self._attribute is not None:
                raise ValueError('XML: незавершенная запись элемента или атрибута')
            result=self._render()
            if not is_file:
                self._active=False;return result
            data=file_io._encode(result,self._encoding)
            if len(data)+len(self._bom)>file_io.MAX_BYTES: raise ValueError('XML: превышен предел файла')
            self._stream.write(self._bom+data)
            return ''
        finally:
            # File Close is terminal even when rendering, encoding or writing
            # fails. String assembly remains repairable after incomplete Close.
            if is_file:self._dispose()
    # !todo Native calibration of exact pretty-print bytes, implicit closing of
    # incomplete documents, repeated Close and advanced XML 1.1 settings.
    # Fragment output (including multiple roots) is not document validation.
    # DTD/entity references are deliberately not exposed.
    def get_member(self,name):
        key=name.casefold()
        if key in ('indent','отступ'):return self._indent_setting
        if key in ('settings','параметры'):return self._settings
        if key in ('namespacecontext','контекстпространствимен'):
            from .xml_io import BSLXMLNamespaceContext
            return BSLXMLNamespaceContext(self._scope(),len(self._stack))
        return super().get_member(name)
    def set_member(self,name,value):
        if name.casefold() in ('indent','отступ'):
            self._indent_setting=file_io._bool(value)
            return
        return super().set_member(name,value)
    def get_method(self,name):
        methods={
            'setstring':self.set_string,'установитьстроку':self.set_string,
            'openfile':self.open_file,'открытьфайл':self.open_file,
            'writexmldeclaration':self.write_xml_declaration,'записатьобъявлениеxml':self.write_xml_declaration,
            'writestartelement':self.write_start_element,'записатьначалоэлемента':self.write_start_element,
            'writeendelement':self.write_end_element,'записатьконецэлемента':self.write_end_element,
            'writeattribute':self.write_attribute,'записатьатрибут':self.write_attribute,
            'writestartattribute':self.write_start_attribute,'записатьначалоатрибута':self.write_start_attribute,
            'writeendattribute':self.write_end_attribute,'записатьконецатрибута':self.write_end_attribute,
            'writetext':self.write_text,'записатьтекст':self.write_text,
            'writecomment':self.write_comment,'записатькомментарий':self.write_comment,
            'writecdatasection':self.write_cdata_section,'записатьсекциюcdata':self.write_cdata_section,
            'writeprocessinginstruction':self.write_processing_instruction,'записатьинструкциюобработки':self.write_processing_instruction,
            'writenamespacemapping':self.write_namespace_mapping,'записатьсоответствиепространстваимен':self.write_namespace_mapping,
            'writeraw':self.write_raw,'записатьбезобработки':self.write_raw,
            'writecurrent':self.write_current,'записатьтекущий':self.write_current,
            'lookupprefix':self.lookup_prefix,'найтипрефикс':self.lookup_prefix,
            'close':self.close,'закрыть':self.close}
        key=name.casefold()
        if key in methods: return HostFunction(name,methods[key],returns_value=key in ('close','закрыть','lookupprefix','найтипрефикс'))
        return super().get_method(name)
