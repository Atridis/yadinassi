"""DOM adapters for the existing bounded XML reader/writer, not new file authority."""
import copy
from .file_io import _FileMethods, _methods
from .xml_io import BSLXMLReader, T
from .xml_writer import BSLXMLWriter, BSLXMLWriterSettings, _XMLNS_URI
from .dom_nodes import BSLDOMDocument, K, _node, _walk, MAX_NODES, MAX_UNITS, MAX_DEPTH


class BSLDOMBuilder(_FileMethods):
    _methods = _methods(('read', True, 'Read Прочитать'))
    def __str__(self): return 'ПостроительDOM'
    def read(self, reader):
        if type(reader) is not BSLXMLReader: raise TypeError('DOM: ожидается ЧтениеXML')
        if reader._source is None: raise ValueError('DOM: источник не открыт')
        original = reader
        # Builder retains comments even when the ordinary reader default hides
        # them. Keep its settings/failed cursor untouched; commit only at EOF.
        reader = copy.copy(original)
        reader._settings = copy.copy(original._settings)
        reader._settings.ignore_comments = False
        reader._tokens = None
        saved = (reader._position, reader._attribute, reader._current)
        doc = BSLDOMDocument._empty(); stack = [doc]; count = 0
        try:
            # !todo ReadWithContext and a reader already positioned inside a
            # subtree require separate semantics; this operation reads a document.
            if reader._position >= 0: raise ValueError('DOM: чтение требуется с начала документа')
            while reader.read():
                event = reader._current; kind = event['kind']; count += 1
                if count > 2*MAX_NODES: raise ValueError('DOM: превышен предел чтения')
                if kind is T.START:
                    node = doc.create_element(event['uri'], event['name'])
                    for prefix, uri in event['declarations']: node.set_namespace_mapping(prefix, uri)
                    for attr in event['attrs']:
                        a = doc.create_attribute(attr['uri'], attr['name']) if attr['uri'] else doc.create_attribute(attr['name'])
                        a._set_data(attr['value']); node.set_attribute_node(a)
                    stack[-1].append_child(node); stack.append(node)
                elif kind is T.END:
                    if len(stack) <= 1: raise ValueError('DOM: неверная структура XML')
                    stack.pop()
                elif kind in (T.TEXT,T.WHITESPACE,T.CDATA):
                    if len(stack) == 1:
                        if event['value'].strip(): raise ValueError('DOM: текст вне корня')
                        continue
                    node = (doc.create_cdata_section(event['value']) if kind is T.CDATA else doc.create_text_node(event['value']))
                    stack[-1].append_child(node)
                elif kind is T.COMMENT: stack[-1].append_child(doc.create_comment(event['value']))
                elif kind is T.PI: stack[-1].append_child(doc.create_processing_instruction(event['name'],event['value']))
            if len(stack) != 1 or doc.document_element() is None: raise ValueError('DOM: требуется корневой элемент')
            original._version, original._xml_encoding = reader._version, reader._xml_encoding
            original._tokens = reader._tokens
            original._position, original._attribute, original._current = reader._position, reader._attribute, reader._current
            return doc
        except BaseException:
            reader._position, reader._attribute, reader._current = saved
            raise


def _serialize(node, inherited_default=''):
    # The existing writer owns XML escaping and a stricter 1M output cap.
    writer = BSLXMLWriter(); writer.set_string(BSLXMLWriterSettings('', '1.0', False))
    stack = [(node, False)]; count = 0
    while stack:
        current, end = stack.pop(); count += 1
        if count > 2*MAX_NODES: raise ValueError('DOM: превышен предел записи')
        if end: writer.write_end_element(); continue
        kind = current._kind
        if kind is K.ELEMENT:
            writer.write_start_element(current._name)
            mappings = dict(current._ns)
            if current._uri: mappings[current._prefix] = current._uri
            elif not current._prefix and writer._scope().get('', inherited_default): mappings[''] = ''
            attrs = []
            for attr in current._attrs:
                if attr._uri == _XMLNS_URI:continue
                name = attr._name
                if attr._uri:
                    prefix = attr._prefix
                    if not prefix:
                        prefix = next((p for p,u in {**writer._scope(),**mappings}.items() if p and u==attr._uri), '')
                        if not prefix:
                            n=1
                            while 'ns'+str(n) in mappings or 'ns'+str(n) in writer._scope(): n+=1
                            prefix='ns'+str(n)
                        name=prefix+':'+attr._local
                    if prefix in mappings and mappings[prefix]!=attr._uri: raise ValueError('DOM: конфликт пространства имен атрибута')
                    mappings[prefix]=attr._uri
                attrs.append((name,attr._data))
            for prefix,uri in mappings.items():
                if prefix != 'xml': writer.write_namespace_mapping(prefix,uri)
            for name,value in attrs: writer.write_attribute(name,value)
            stack.append((current,True)); stack.extend((n,False) for n in reversed(current._children))
        elif kind in (K.DOCUMENT,K.FRAGMENT): stack.extend((n,False) for n in reversed(current._children))
        elif kind is K.TEXT: writer.write_text(current._data)
        elif kind is K.CDATA: writer.write_cdata_section(current._data)
        elif kind is K.COMMENT: writer.write_comment(current._data)
        elif kind is K.PI: writer.write_processing_instruction(current._name,current._data)
        else: raise ValueError('DOM: запись отдельного атрибута пока не поддерживается')
    return writer.close()


class BSLDOMWriter(_FileMethods):
    _methods = _methods(('write', False, 'Write Записать'))
    def __str__(self): return 'ЗаписьDOM'
    def write(self, node, writer):
        node = _node(node)
        if type(writer) is not BSLXMLWriter: raise TypeError('DOM: ожидается ЗаписьXML')
        writer._require()
        # Preflight entire DOM before serialization; only bounded in-memory data.
        for _, depth in _walk(node):
            if depth > MAX_DEPTH: raise ValueError('DOM: превышена глубина')
        text = _serialize(node, writer._scope().get('', ''))
        # The existing target is bounded too. Stage its in-memory state without
        # copying/closing its borrowed file descriptor; commit only on success.
        staged = object.__new__(BSLXMLWriter)
        staged.__dict__ = copy.deepcopy({k:v for k,v in writer.__dict__.items() if k != '_stream'})
        staged._stream = None
        staged.write_raw(text)
        stream = writer._stream
        writer.__dict__.update(staged.__dict__); writer._stream = stream
