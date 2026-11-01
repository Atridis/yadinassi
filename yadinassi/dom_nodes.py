"""Bounded ordinary XML DOM; no DTD/entities, XPath, HTML or external resources.

All allocations belong to a document ledger (including detached nodes). Mutations
validate ownership, hierarchy and resource limits before changing the graph.
!todo DTD defaults/IDs, user data, XPath, traversal filters and XML1.1 are excluded.
"""
from decimal import Decimal
from enum import Enum
from .values import BSLObject
from .file_io import _FileMethods, _methods
from .xml_writer import _text, _name, _XML_URI, _XMLNS_URI

MAX_NODES = 10000
MAX_UNITS = 4 * 1024 * 1024
MAX_DEPTH = 128
MAX_WORK = 200000


def _flag(value):
    if type(value) is not bool: raise TypeError('DOM: ожидается Булево')
    return value


def _index(value):
    if type(value) not in (int, Decimal) or not 0 <= value <= MAX_UNITS:
        raise ValueError('DOM: неверный индекс')
    if int(value) != value: raise ValueError('DOM: индекс должен быть целым')
    return int(value)


def _named(args):
    if len(args) == 1: return _name(args[0]), '', '', ''
    if len(args) != 2: raise TypeError('DOM: требуется имя или URI и имя')
    uri, name = _text(args[0]), _name(args[1])
    prefix, sep, local = name.partition(':')
    if not sep: prefix, local = '', prefix
    if (prefix and not uri) or (prefix == 'xml' and uri != _XML_URI) or prefix == 'xmlns' or uri == _XMLNS_URI:
        raise ValueError('DOM: неверное пространство имен')
    return name, uri, local, prefix


def _binding(prefix,uri):
    if prefix:_name(prefix,False)
    if prefix=='xmlns' or uri==_XMLNS_URI or (prefix=='xml') != (uri==_XML_URI) or (prefix and not uri):raise ValueError('DOM: неверное пространство имен')


class BSLDOMNodeType(Enum):
    ELEMENT = ('Element', 'Элемент')
    ATTRIBUTE = ('Attribute', 'Атрибут')
    TEXT = ('Text', 'Текст')
    CDATA = ('CDATASection', 'СекцияCDATA')
    COMMENT = ('Comment', 'Комментарий')
    PI = ('ProcessingInstruction', 'ИнструкцияОбработки')
    DOCUMENT = ('Document', 'Документ')
    FRAGMENT = ('DocumentFragment', 'ФрагментДокумента')
    def __str__(self): return self.value[1]


class _NodeTypes(BSLObject):
    def get_member(self, name):
        for value in BSLDOMNodeType:
            if name.casefold() in (x.casefold() for x in value.value): return value
        return super().get_member(name)

DOM_NODE_TYPES = _NodeTypes()
K = BSLDOMNodeType


def _node(value):
    if type(value) not in _NODE_CLASSES: raise TypeError('DOM: ожидается узел DOM')
    return value


def _walk(root, *, include_root=True):
    stack = [(root, 0)]; work = 0
    while stack:
        node, depth = stack.pop(); work += 1
        if work > MAX_WORK or depth > MAX_DEPTH: raise ValueError('DOM: превышен предел обхода')
        if include_root or node is not root: yield node, depth
        stack.extend((child, depth + 1) for child in reversed(node._children))


class BSLDOMNodeList(_FileMethods):
    _methods = _methods(('count', True, 'Count Количество'), ('item', True, 'Item Элемент'))
    def __init__(self, node): self._node = node
    def __str__(self): return 'СписокУзловDOM'
    def _items(self): return self._node._children
    def count(self): return Decimal(len(self._items()))
    def item(self, index):
        index = _index(index); items = self._items()
        return items[index] if index < len(items) else None
    def __iter__(self): return iter(tuple(self._items()))
    def __getitem__(self, index): return self.item(index)


class BSLDOMElementList(BSLDOMNodeList):
    def __init__(self, node, args):
        self._node = node
        if len(args) not in (1, 2): raise TypeError('DOM: неверные параметры поиска')
        self._query = tuple(_text(a) for a in args)
        self._snapshot = tuple(self._select()) if node._kind is K.DOCUMENT else None
    def __str__(self): return 'СписокЭлементовDOM'
    def _items(self):
        return self._snapshot if self._snapshot is not None else self._select()
    def _select(self):
        q = self._query; out = []
        for n, _ in _walk(self._node, include_root=False):
            # Measured Document queries snapshot local-name matches, including
            # empty/prefixed namespaces. !todo Broader qualified-name patterns.
            if self._node._kind is K.DOCUMENT:
                if n._kind is K.ELEMENT and q[-1] in ('*', n._local, n._name): out.append(n)
                continue
            if n._kind is K.ELEMENT and ((len(q) == 1 and q[0] in ('*', n._name)) or
                (len(q) == 2 and q[0] in ('*', n._uri) and q[1] in ('*', n._local))): out.append(n)
        return out


class BSLDOMAttributeMap(BSLDOMNodeList):
    _methods = dict(BSLDOMNodeList._methods, **_methods(
        ('get_named_item', True, 'GetNamedItem ПолучитьИменованныйЭлемент'),
        ('set_named_item', True, 'SetNamedItem УстановитьИменованныйЭлемент'),
        ('remove_named_item', True, 'RemoveNamedItem УдалитьИменованныйЭлемент')))
    def __str__(self): return 'КоллекцияАтрибутовDOM'
    def _items(self): return self._node._attrs
    def get_named_item(self, *args): return self._node.get_attribute_node(*args)
    def set_named_item(self, attr): return self._node.set_attribute_node(attr)
    def remove_named_item(self, *args):
        attr = self.get_named_item(*args)
        if attr is None: raise ValueError('DOM: атрибут не найден')
        return self._node.remove_attribute_node(attr)


class _DOMNode(_FileMethods):
    _methods = _methods(
        ('append_child', True, 'AppendChild ДобавитьДочерний'),
        ('insert_before', True, 'InsertBefore ВставитьПеред'),
        ('replace_child', True, 'ReplaceChild ЗаменитьДочерний'),
        ('remove_child', True, 'RemoveChild УдалитьДочерний'),
        ('has_child_nodes', True, 'HasChildNodes ЕстьДочерниеУзлы'),
        ('has_attributes', True, 'HasAttributes ЕстьАтрибуты'),
        ('clone_node', True, 'CloneNode КлонироватьУзел'),
        ('normalize', False, 'Normalize Нормализовать'),
        ('is_same_node', True, 'IsSameNode УзелИдентичен'),
        ('is_equal_node', True, 'IsEqualNode УзелРавен'),
        ('lookup_namespace_uri', True, 'LookupNamespaceURI НайтиURIПространстваИмен'),
        ('lookup_prefix', True, 'LookupPrefix НайтиПрефикс'),
        ('is_default_namespace', True, 'IsDefaultNamespace ПространствоИменПоУмолчанию'))
    def __init__(self, owner, kind, name='', uri='', local='', prefix='', data=''):
        self._owner = owner; self._kind = kind; self._name = name
        self._uri = uri; self._local = local; self._prefix = prefix; self._data = data
        self._parent = None; self._children = []; self._attrs = []; self._ns = {}
        self._owner_element = None
    def __str__(self): return _TYPE_NAMES[type(self)]
    def _doc(self): return self if self._kind is K.DOCUMENT else self._owner
    def _siblings(self): return self._parent._children if self._parent is not None else []
    def get_member(self, name):
        key = name.casefold()
        common = {'nodetype': self._kind, 'типузла': self._kind,
            'nodename': self._name, 'имяузла': self._name,
            'parentnode': self._parent, 'родительскийузел': self._parent,
            'ownerdocument': self._owner, 'документвладелец': self._owner,
            'namespaceuri': self._uri, 'uriпространстваимен': self._uri,
            'localname': self._local, 'локальноеимя': self._local,
            'prefix': self._prefix, 'префикс': self._prefix,
            'firstchild': self._children[0] if self._children else None,
            'первыйдочерний': self._children[0] if self._children else None,
            'lastchild': self._children[-1] if self._children else None,
            'последнийдочерний': self._children[-1] if self._children else None}
        if key in common: return common[key]
        if key in ('childnodes', 'дочерниеузлы'): return BSLDOMNodeList(self)
        if key in ('attributes', 'атрибуты'): return BSLDOMAttributeMap(self) if self._kind is K.ELEMENT else None
        if key in ('nextsibling', 'следующийсоседний', 'previoussibling', 'предыдущийсоседний'):
            if self._parent is None: return None
            rows = self._siblings(); i = rows.index(self) + (1 if key in ('nextsibling', 'следующийсоседний') else -1)
            return rows[i] if 0 <= i < len(rows) else None
        if key in ('nodevalue', 'значениеузла'): return self._data if self._kind in _DATA_KINDS else None
        if key in ('textcontent', 'текстовоесодержимое'): return self.text_content()
        if key in ('baseuri', 'базовыйuri'): return ''
        return super().get_member(name)
    def set_member(self, name, value):
        key = name.casefold()
        if key in ('nodevalue', 'значениеузла') and self._kind in _DATA_KINDS:
            return self._set_data(value)
        if key in ('textcontent', 'текстовоесодержимое'):
            if self._kind in _DATA_KINDS: return self._set_data(value)
            if self._kind not in (K.ELEMENT, K.FRAGMENT): raise ValueError('DOM: свойство недоступно для записи')
            value = _text(value); doc = self._doc()
            if value:
                current=self;depth=0
                while current is not None:
                    depth+=1;current=current._parent
                    if depth>MAX_DEPTH:raise ValueError('DOM: превышена глубина')
            doc._reserve(1 if value else 0, len(value))
            new = _make(doc, K.TEXT, data=value, charge=False) if value else None
            for child in self._children: child._parent = None
            self._children = [] if new is None else [new]
            if new is not None: new._parent = self
            return
        if key in ('prefix', 'префикс') and self._kind in (K.ELEMENT, K.ATTRIBUTE):
            value = _text(value)
            if not self._local: raise ValueError('DOM: узел без пространства имен')
            named = _named((self._uri, (value + ':' if value else '') + self._local))
            self._doc()._reserve(0, len(named[0])); self._name, self._uri, self._local, self._prefix = named
            return
        return super().set_member(name, value)
    def _set_data(self, value):
        value = _text(value)
        if self._kind is K.ATTRIBUTE and self._uri == _XMLNS_URI:
            _binding(self._local if self._prefix else '',value)
        self._doc()._reserve(0, len(value)); self._data = value
        if self._kind is K.ATTRIBUTE and self._uri == _XMLNS_URI and self._owner_element is not None:
            self._owner_element._ns[self._local if self._prefix else ''] = value
    def text_content(self):
        if self._kind in _DATA_KINDS: return self._data
        if self._kind is K.DOCUMENT: return None
        chunks = []; size = 0
        for n, _ in _walk(self, include_root=False):
            if n._kind in (K.TEXT, K.CDATA):
                size += len(n._data)
                if size > MAX_UNITS: raise ValueError('DOM: превышен предел текста')
                chunks.append(n._data)
        return ''.join(chunks)
    def has_child_nodes(self): return bool(self._children)
    def has_attributes(self): return bool(self._attrs)
    def is_same_node(self, other): return self is _node(other)
    def is_equal_node(self, other):
        other = _node(other); left = list(_walk(self)); right = list(_walk(other))
        if len(left) != len(right): return False
        for (a, ad), (b, bd) in zip(left, right):
            if ad != bd or (a._kind,a._name,a._uri,a._local,a._prefix,a._data,a._ns) != (b._kind,b._name,b._uri,b._local,b._prefix,b._data,b._ns): return False
            if [(x._name,x._uri,x._data) for x in a._attrs] != [(x._name,x._uri,x._data) for x in b._attrs]: return False
        return True
    def append_child(self, new): return self.insert_before(new, None)
    def insert_before(self, new, old=None): return self._insert(new, old, False)
    def replace_child(self, new, old): return self._insert(new, old, True)
    def _insert(self, new, old, replace):
        new = _node(new)
        if self._kind not in (K.DOCUMENT, K.ELEMENT, K.FRAGMENT):
            # !todo Attribute child text/entity nodes are not exposed yet.
            raise ValueError('DOM: узел не допускает дочерние узлы')
        if old is not None: _node(old)
        if (replace and old is None) or (old is not None and old._parent is not self): raise ValueError('DOM: дочерний узел не найден')
        if new is old: return new
        if new._doc() is not self._doc(): raise ValueError('DOM: другой документ; используйте ИмпортироватьУзел')
        incoming = list(new._children) if new._kind is K.FRAGMENT else [new]
        if any(n._kind not in (K.ELEMENT,K.TEXT,K.CDATA,K.COMMENT,K.PI) for n in incoming): raise ValueError('DOM: недопустимый тип дочернего узла')
        identities = {id(n) for n in incoming}
        ancestor = self; depth = 0
        while ancestor is not None:
            if ancestor is new or id(ancestor) in identities: raise ValueError('DOM: цикл узлов')
            depth += 1
            if depth > MAX_DEPTH: raise ValueError('DOM: превышена глубина')
            ancestor = ancestor._parent
        for node in incoming:
            for _, subdepth in _walk(node):
                if depth + subdepth > MAX_DEPTH: raise ValueError('DOM: превышена глубина')
        pending = [n for n in self._children if id(n) not in identities]
        index = pending.index(old) if old is not None else len(pending)
        if replace: pending.pop(index)
        pending[index:index] = incoming
        if self._kind is K.DOCUMENT and (sum(n._kind is K.ELEMENT for n in pending) > 1 or any(n._kind in (K.TEXT,K.CDATA) for n in pending)):
            raise ValueError('DOM: неверная структура документа')
        # Fragment children share one parent; filter each affected list once.
        parents = {id(n._parent): n._parent for n in incoming if n._parent is not None}
        for parent in parents.values():
            parent._children = [n for n in parent._children if id(n) not in identities]
        if replace: old._parent = None
        self._children = pending
        for n in incoming: n._parent = self
        return old if replace else new
    def remove_child(self, child):
        child = _node(child)
        if child._parent is not self: raise ValueError('DOM: дочерний узел не найден')
        self._children.remove(child); child._parent = None
        return child
    def clone_node(self, deep):
        _flag(deep)
        if self._kind is K.DOCUMENT:
            target = BSLDOMDocument._empty(); _copy_into(self, target, deep, target); return target
        return _copy_into(self, self._doc(), deep, attributes=deep or self._kind is not K.ELEMENT)
    def normalize(self):
        plans = []; extra = 0
        for node, _ in _walk(self):
            rows = []; group = []; merges = []
            for child in node._children + [None]:
                if child is not None and child._kind is K.TEXT: group.append(child); continue
                if group:
                    size=sum(len(c._data) for c in group);extra+=size
                    if extra>MAX_UNITS:raise ValueError('DOM: превышен предел нормализации')
                    if size:rows.append(group[0])
                    merges.append((group,size));group=[]
                if child is not None:rows.append(child)
            if merges:plans.append((node,rows,merges))
        self._doc()._reserve(0,extra)
        for node,rows,merges in plans:
            for group,size in merges:
                group[0]._data=''.join(c._data for c in group)
                for child in group[1:] + ([] if size else [group[0]]):child._parent=None
            node._children=rows
    def _scope(self):
        current = self._owner_element if self._kind is K.ATTRIBUTE else self
        if current is not None and current._kind is K.DOCUMENT: current = current.document_element()
        result = {'xml': _XML_URI}; chain = []
        while current is not None:
            chain.append(current)
            if len(chain) > MAX_DEPTH + 1: raise ValueError('DOM: превышена глубина')
            current = current._parent
        for n in reversed(chain):
            result.update(n._ns)
            if n._uri: result[n._prefix] = n._uri
        return result
    def lookup_namespace_uri(self, prefix): return self._scope().get(_text(prefix), '')
    def lookup_prefix(self, uri):
        uri = _text(uri)
        return next((p for p,u in self._scope().items() if p and u == uri), '')
    def is_default_namespace(self, uri): return self.lookup_namespace_uri('') == _text(uri)


class BSLDOMElement(_DOMNode):
    _methods = dict(_DOMNode._methods, **_methods(
        ('get_attribute', True, 'GetAttribute ПолучитьАтрибут'),
        ('set_attribute', False, 'SetAttribute УстановитьАтрибут'),
        ('remove_attribute', False, 'RemoveAttribute УдалитьАтрибут'),
        ('has_attribute', True, 'HasAttribute ЕстьАтрибут'),
        ('get_attribute_node', True, 'GetAttributeNode ПолучитьУзелАтрибута'),
        ('set_attribute_node', True, 'SetAttributeNode УстановитьУзелАтрибута'),
        ('remove_attribute_node', True, 'RemoveAttributeNode УдалитьУзелАтрибута'),
        ('get_elements', True, 'GetElementByTagName ПолучитьЭлементыПоИмени'),
        ('set_namespace_mapping', True, 'SetNamespaceMapping УстановитьСоответствиеПространстваИмен'),
        ('unset_namespace_mapping', False, 'UnsetNamespaceMapping ОтменитьСоответствиеПространстваИмен')))
    def get_member(self, name):
        if name.casefold() in ('tagname','имяэлемента'): return self._name
        return super().get_member(name)
    def get_attribute_node(self, *args):
        if len(args) not in (1,2): raise TypeError('DOM: неверные параметры атрибута')
        args = tuple(_text(a) for a in args)
        return next((a for a in self._attrs if (a._name == args[0] if len(args)==1 else (a._uri,a._local)==args)), None)
    def get_attribute(self, *args):
        a = self.get_attribute_node(*args); return None if a is None else a._data
    def has_attribute(self, *args): return self.get_attribute_node(*args) is not None
    def set_attribute(self, *args):
        if len(args) not in (2,3): raise TypeError('DOM: неверные параметры атрибута')
        value = _text(args[-1]); key = args[:-1]; attr = self.get_attribute_node(*key)
        if attr is not None: attr._set_data(value); return
        named = _named(key); self._doc()._reserve(1,len(value)+sum(map(len,named)))
        attr = _make(self._doc(),K.ATTRIBUTE,*named,data=value,charge=False); self.set_attribute_node(attr)
    def remove_attribute(self, *args):
        attr = self.get_attribute_node(*args)
        if attr is not None: self.remove_attribute_node(attr)
    def set_attribute_node(self, attr):
        if type(attr) is not BSLDOMAttribute: raise TypeError('DOM: ожидается АтрибутDOM')
        if attr._owner is not self._doc(): raise ValueError('DOM: другой документ')
        if attr._owner_element is not None and attr._owner_element is not self: raise ValueError('DOM: атрибут уже принадлежит элементу')
        old = self.get_attribute_node(attr._uri,attr._local) if attr._local else self.get_attribute_node(attr._name)
        if old is attr: return old
        if attr._uri == _XMLNS_URI:_binding(attr._local if attr._prefix else '',attr._data)
        if old is not None: self._attrs[self._attrs.index(old)] = attr; old._owner_element = None
        else: self._attrs.append(attr)
        attr._owner_element = self
        if attr._uri == _XMLNS_URI:self._ns[attr._local if attr._prefix else '']=attr._data
        return old
    def remove_attribute_node(self, attr):
        if type(attr) is not BSLDOMAttribute or attr._owner_element is not self: raise ValueError('DOM: атрибут не найден')
        self._attrs.remove(attr); attr._owner_element = None
        if attr._uri == _XMLNS_URI: self._ns.pop(attr._local if attr._prefix else '',None)
        return attr
    def get_elements(self,*args): return BSLDOMElementList(self,args)
    def set_namespace_mapping(self,*args):
        # !todo Automatic prefix spelling and recursive reconcile need their
        # own native observations; do not silently treat URI-only as default NS.
        if len(args) not in (2,3) or type(args[1]) is not str:
            raise ValueError('DOM: автоматический префикс пока не поддерживается')
        prefix,uri=_text(args[0]),_text(args[1])
        if len(args)==3 and _flag(args[2]):raise ValueError('DOM: согласование префиксов пока не поддерживается')
        _binding(prefix,uri)
        if prefix in self._ns:return None
        name='xmlns:'+prefix if prefix else 'xmlns'
        self._doc()._reserve(1,len(name)+len(uri)+len(_XMLNS_URI)+len(prefix))
        attr=_make(self._doc(),K.ATTRIBUTE,name,_XMLNS_URI,prefix or 'xmlns','xmlns' if prefix else '',uri,charge=False)
        self._attrs.append(attr);attr._owner_element=self;self._ns[prefix]=uri
        return attr
    def unset_namespace_mapping(self,prefix):
        prefix=_text(prefix);attr=self.get_attribute_node('xmlns:'+prefix if prefix else 'xmlns')
        if attr is not None and attr._uri==_XMLNS_URI:self.remove_attribute_node(attr)



class BSLDOMAttribute(_DOMNode):
    def get_member(self,name):
        key=name.casefold()
        if key in ('name','имя'):return self._name
        if key in ('value','значение'):return self._data
        if key in ('ownerelement','элементвладелец'):return self._owner_element
        if key in ('specified','указан'):return True
        if key in ('isid','являетсяидентификатором'):return False
        return super().get_member(name)
    def set_member(self,name,value):
        if name.casefold() in ('value','значение'):return self._set_data(value)
        return super().set_member(name,value)


class _CharacterData(_DOMNode):
    _methods=dict(_DOMNode._methods, **_methods(
        ('substring_data',True,'SubstringData ВыбратьДанные'),('append_data',False,'AppendData ДобавитьДанные'),
        ('insert_data',False,'InsertData ВставитьДанные'),('delete_data',False,'DeleteData УдалитьДанные'),
        ('replace_data',False,'ReplaceData ЗаменитьДанные')))
    def get_member(self,name):
        if name.casefold() in ('data','данные'):return self._data
        if name.casefold() in ('length','размер'):return Decimal(len(self._data.encode('utf-16-le'))//2)
        return super().get_member(name)
    def set_member(self,name,value):
        if name.casefold() in ('data','данные'):return self._set_data(value)
        return super().set_member(name,value)
    def _range(self,offset,count):
        offset,count=_index(offset),_index(count);raw=self._data.encode('utf-16-le')
        if offset*2>len(raw):raise ValueError('DOM: смещение вне данных')
        return raw,offset*2,min(len(raw),(offset+count)*2)
    def substring_data(self,offset,count):
        raw,a,b=self._range(offset,count)
        # !todo Unpaired UTF16 boundaries are rejected, not silently repaired.
        return raw[a:b].decode('utf-16-le')
    def append_data(self,value): self.replace_data(self.get_member('Length'),0,value)
    def insert_data(self,offset,value): self.replace_data(offset,0,value)
    def delete_data(self,offset,count): self.replace_data(offset,count,'')
    def replace_data(self,offset,count,value):
        value=_text(value);raw,a,b=self._range(offset,count)
        size=len(raw)-(b-a)+len(value.encode('utf-16-le'))
        if size>2*MAX_UNITS:raise ValueError('DOM: превышен предел текста')
        self._set_data((raw[:a]+value.encode('utf-16-le')+raw[b:]).decode('utf-16-le'))

class BSLDOMText(_CharacterData):
    _methods=dict(_CharacterData._methods, **_methods(('split_text',True,'SplitText РазделитьТекст')))
    def get_member(self,name):
        if name.casefold() in ('wholetext','полныйтекст'):
            if self._parent is None:return self._data
            rows=self._parent._children;i=rows.index(self);a=i;b=i+1
            while a and rows[a-1]._kind in (K.TEXT,K.CDATA):a-=1
            while b<len(rows) and rows[b]._kind in (K.TEXT,K.CDATA):b+=1
            return ''.join(n._data for n in rows[a:b])
        if name.casefold() in ('iselementcontentwhitespace','этопробельныесимволыэлемента'):return not self._data.strip(' \t\r\n')
        return super().get_member(name)
    def split_text(self,offset):
        raw,a,_=self._range(offset,0);left=raw[:a].decode('utf-16-le');right=raw[a:].decode('utf-16-le')
        doc=self._doc();doc._reserve(1,len(left)+len(right))
        new=_make(doc,K.TEXT,data=right,charge=False)
        if self._parent is not None:
            rows=self._parent._children;rows.insert(rows.index(self)+1,new);new._parent=self._parent
        self._data=left;return None

class BSLDOMCDATASection(_CharacterData): pass
class BSLDOMComment(_CharacterData): pass
class BSLDOMProcessingInstruction(_DOMNode):
    def get_member(self,name):
        if name.casefold() in ('target','цель'):return self._name
        if name.casefold() in ('data','данные'):return self._data
        return super().get_member(name)
    def set_member(self,name,value):
        if name.casefold() in ('data','данные'):return self._set_data(value)
        return super().set_member(name,value)
class BSLDOMDocumentFragment(_DOMNode):pass


class BSLDOMDocument(_DOMNode):
    _methods=dict(_DOMNode._methods, **_methods(
        ('create_element',True,'CreateElement СоздатьЭлемент'),('create_attribute',True,'CreateAttribute СоздатьАтрибут'),
        ('create_text_node',True,'CreateTextNode СоздатьТекстовыйУзел'),('create_comment',True,'CreateComment СоздатьКомментарий'),
        ('create_cdata_section',True,'CreateCDATASection СоздатьСекциюCDATA'),
        ('create_processing_instruction',True,'CreateProcessingInstruction СоздатьИнструкциюОбработки'),
        ('create_document_fragment',True,'CreateDocumentFragment СоздатьФрагментДокумента'),
        ('import_node',True,'ImportNode ИмпортироватьУзел'),('get_elements',True,'GetElementByTagName ПолучитьЭлементыПоИмени')))
    def __init__(self,uri,name):
        super().__init__(None,K.DOCUMENT,'#document');self._allocated=1;self._units=0
        self.append_child(self.create_element(uri,name))
    @classmethod
    def _empty(cls):
        doc=object.__new__(cls);_DOMNode.__init__(doc,None,K.DOCUMENT,'#document');doc._allocated=1;doc._units=0;return doc
    def _reserve(self,nodes,units):
        if self._allocated+nodes>MAX_NODES or self._units+units>MAX_UNITS:raise ValueError('DOM: превышен предел ресурсов документа')
        self._allocated+=nodes;self._units+=units
    def document_element(self):return next((n for n in self._children if n._kind is K.ELEMENT),None)
    def get_member(self,name):
        if name.casefold() in ('documentelement','элементдокумента'):return self.document_element()
        if name.casefold() in ('xmlversion','версияxml'):return '1.0'
        if name.casefold() in ('doctype','определениетипадокумента'):return None
        return super().get_member(name)
    def create_element(self,*args):return _make(self,K.ELEMENT,*_named(args))
    def create_attribute(self,*args):return _make(self,K.ATTRIBUTE,*_named(args))
    def create_text_node(self,value):return _make(self,K.TEXT,data=_text(value))
    def create_comment(self,value):return _make(self,K.COMMENT,data=_text(value))
    def create_cdata_section(self,value):return _make(self,K.CDATA,data=_text(value))
    def create_processing_instruction(self,name,value):return _make(self,K.PI,_name(name,False),data=_text(value))
    def create_document_fragment(self):return _make(self,K.FRAGMENT)
    def import_node(self,node,deep):
        node=_node(node);_flag(deep)
        if node._kind is K.DOCUMENT:raise ValueError('DOM: документ нельзя импортировать')
        return _copy_into(node,self,deep)
    def get_elements(self,*args):return BSLDOMElementList(self,args)


_NODE_CLASSES=(BSLDOMDocument,BSLDOMElement,BSLDOMAttribute,BSLDOMText,BSLDOMCDATASection,BSLDOMComment,BSLDOMProcessingInstruction,BSLDOMDocumentFragment)
_CLASS_BY_KIND=dict(zip((K.DOCUMENT,K.ELEMENT,K.ATTRIBUTE,K.TEXT,K.CDATA,K.COMMENT,K.PI,K.FRAGMENT),_NODE_CLASSES))
_TYPE_NAMES=dict(zip(_NODE_CLASSES,('ДокументDOM','ЭлементDOM','АтрибутDOM','ТекстDOM','СекцияCDATADOM','КомментарийDOM','ИнструкцияОбработкиDOM','ФрагментДокументаDOM')))
_DATA_KINDS=(K.TEXT,K.CDATA,K.COMMENT,K.PI,K.ATTRIBUTE)
_DEFAULT_NAMES={K.TEXT:'#text',K.CDATA:'#cdata-section',K.COMMENT:'#comment',K.FRAGMENT:'#document-fragment'}


def _make(doc,kind,name='',uri='',local='',prefix='',data='',*,charge=True):
    if charge:doc._reserve(1,sum(map(len,(name,uri,local,prefix,data))))
    node=object.__new__(_CLASS_BY_KIND[kind]);_DOMNode.__init__(node,doc,kind,name or _DEFAULT_NAMES.get(kind,''),uri,local,prefix,data)
    return node


def _copy_into(source,doc,deep,existing=None,*,attributes=True):
    rows=list(_walk(source)) if deep else [(source,0)]
    allnodes=[n for n,_ in rows]+[a for n,_ in rows for a in (n._attrs if attributes else ())]
    doc._reserve(len(allnodes)-(1 if existing is not None else 0),sum(sum(map(len,(n._name,n._uri,n._local,n._prefix,n._data)))+sum(len(k)+len(v) for k,v in n._ns.items()) for n in allnodes))
    copies={}
    for n,_ in rows:
        copy=existing if n is source and existing is not None else _make(doc,n._kind,n._name,n._uri,n._local,n._prefix,n._data,charge=False)
        copy._ns=dict(n._ns);copies[id(n)]=copy
        for a in (n._attrs if attributes else ()):
            attr=_make(doc,K.ATTRIBUTE,a._name,a._uri,a._local,a._prefix,a._data,charge=False);attr._owner_element=copy;copy._attrs.append(attr)
        if n is not source:
            parent=copies[id(n._parent)];parent._children.append(copy);copy._parent=parent
    return copies[id(source)]
