"""Closed XSD admission for ordinary XDTO records; never an XSD resolver."""
from .xdto_values import (XS,MAX_TYPES,MAX_PROPERTIES,MAX_DEPTH,BSLXDTOObjectType,
    BSLXDTOProperty,BSLXDTOPropertyCollection,BSLXDTOPackage,BSLXDTOPackageCollection,text)
from .xml_io import BSLXMLReader,BSLXMLReaderSettings,T
from .xml_writer import _name
from .file_io import _open_regular
from .binary_streams import _stream_path
from .values import BSLArray,BSLFixedArray

MAX_SCHEMA_BYTES=262144
MAX_SCHEMA_NODES=2048
MAX_SCHEMAS=8


def _xml_tree(source):
    if not (type(source) is str or type(source) is bytes) or len(source)>MAX_SCHEMA_BYTES:raise ValueError('XDTO: превышен размер XML')
    reader=BSLXMLReader();reader._settings=BSLXMLReaderSettings(ignore_comments=True,ignore_whitespace=False,cdata_as_text=True)
    reader._source=source;roots=[];stack=[];count=0
    while reader.read():
        e=reader._current;k=e['kind']
        if k is T.START:
            count+=1
            if count>MAX_SCHEMA_NODES or len(stack)>=MAX_DEPTH or len(e['attrs'])>MAX_PROPERTIES:raise ValueError('XDTO: превышен предел XML')
            node={'name':e['local'],'uri':e['uri'],'attrs':{(a['uri'],a['local']):a['value'] for a in e['attrs']},'context':e['context'],'children':[],'text':''}
            (stack[-1]['children'] if stack else roots).append(node);stack.append(node)
        elif k is T.END:stack.pop()
        elif k in (T.TEXT,T.CDATA,T.WHITESPACE):
            if stack:
                if len(stack[-1]['text'])+len(e['value'])>MAX_SCHEMA_BYTES:raise ValueError('XDTO: превышен размер текста')
                stack[-1]['text']+=e['value']
            elif e['value'].strip():raise ValueError('XDTO: текст вне корня')
        elif k in (T.PI,T.COMMENT):raise ValueError('XDTO: инструкции и комментарии схемы пока не поддерживаются')
    if len(roots)!=1:raise ValueError('XDTO: требуется один корень')
    return roots[0]


def _attrs(node,tag,allowed):
    if node['uri']!=XS or node['name']!=tag or node['text'].strip():raise ValueError('XDTO: неподдержанная конструкция XSD')
    if any(uri or key not in allowed for uri,key in node['attrs']):raise ValueError('XDTO: неподдержанный атрибут XSD')
    return {key:value for (_,key),value in node['attrs'].items()}


def _identifier(value):
    value=text(value)
    if not value or len(value)>128 or ':' in value:raise ValueError('XDTO: неверное имя схемы')
    return _name(value)


def _boolean(value):
    if value not in ('true','false','1','0'):raise ValueError('XDTO: неверный флаг схемы')
    return value in ('true','1')


def _bound(value,upper=False):
    if upper and value=='unbounded':return -1
    if len(value)>4 or not value.isascii() or not value.isdigit():raise ValueError('XDTO: неверная кратность')
    n=int(value)
    if n>4096:raise ValueError('XDTO: превышена кратность')
    return n


def _resolve(factory,node,value):
    if not value or len(value)>256 or value.count(':')>1:raise ValueError('XDTO: неверное имя типа')
    prefix,sep,name=value.partition(':')
    if not sep:name=prefix;prefix=''
    uri=node['context'].get(prefix)
    if uri is None:raise ValueError('XDTO: неизвестный префикс типа')
    kind=factory._types.get((uri,name))
    if kind is None:raise ValueError('XDTO: неизвестный тип')
    return kind


def load_schemas(factory,paths,packages=None):
    # !todo imported packages, include/import/redefine, inheritance, mixed/choice,
    # recursive types and facets require separate bounded semantic support.
    if packages is not None:raise ValueError('XDTO: дополнительные пакеты пока не поддерживаются')
    if type(paths) is str:paths=[paths]
    elif (type(paths) is BSLArray or type(paths) is BSLFixedArray):paths=paths.items
    else:raise TypeError('XDTO: ожидается путь или массив путей')
    if not 1<=len(paths)<=MAX_SCHEMAS:raise ValueError('XDTO: неверное число схем')
    schemas=[];total=0;namespaces=set();declarations=[];roots=[]
    for path in paths:
        with _open_regular(_stream_path(path)) as stream:
            source=stream.read(MAX_SCHEMA_BYTES+1)
        total+=len(source)
        if total>MAX_SCHEMA_BYTES:raise ValueError('XDTO: превышен общий размер схем')
        node=_xml_tree(source)
        attrs=_attrs(node,'schema',{'targetNamespace','elementFormDefault','attributeFormDefault','version'})
        uri=text(attrs.get('targetNamespace',''))
        if not uri or len(uri)>1024 or uri==XS or uri in namespaces:raise ValueError('XDTO: неверное пространство схемы')
        namespaces.add(uri)
        element_form=attrs.get('elementFormDefault','unqualified');attribute_form=attrs.get('attributeFormDefault','unqualified')
        if element_form not in ('qualified','unqualified') or attribute_form not in ('qualified','unqualified'):raise ValueError('XDTO: неверная форма схемы')
        schemas.append((uri,element_form,attribute_form,node))
        for child in node['children']:
            if child['name']=='complexType':
                a=_attrs(child,'complexType',{'name'})
                name=_identifier(a.get('name',''))
                if (uri,name) in factory._types or len(declarations)>=MAX_TYPES:raise ValueError('XDTO: повтор или предел типов')
                kind=BSLXDTOObjectType(factory,name,uri);factory._types[uri,name]=kind
                declarations.append((kind,element_form,attribute_form,child))
            elif child['name']=='element':roots.append((uri,child))
            else:raise ValueError('XDTO: неподдержанный компонент схемы')
    count=0
    for kind,element_form,attribute_form,node in declarations:
        properties=[];seen=set();sequence=False
        for child in node['children']:
            if child['name']=='sequence':
                if sequence:raise ValueError('XDTO: повтор sequence')
                _attrs(child,'sequence',set());sequence=True;entries=child['children']
            elif child['name']=='attribute':entries=[child]
            else:raise ValueError('XDTO: неподдержанный состав типа')
            for item in entries:
                is_attr=item['name']=='attribute'
                if is_attr and child['name']=='sequence':raise ValueError('XDTO: атрибут внутри sequence')
                allowed={'name','type','use','form'} if is_attr else {'name','type','minOccurs','maxOccurs','nillable','form'}
                a=_attrs(item,'attribute' if is_attr else 'element',allowed)
                if item['children']:raise ValueError('XDTO: вложенные определения пока не поддерживаются')
                name=_identifier(a.get('name',''));count+=1
                if name in seen or count>MAX_PROPERTIES:raise ValueError('XDTO: повтор или предел свойств')
                seen.add(name);prop_type=_resolve(factory,item,a.get('type',''))
                if is_attr and type(prop_type) is BSLXDTOObjectType:raise ValueError('XDTO: сложный тип атрибута')
                if is_attr:
                    use=a.get('use','optional')
                    if use not in ('optional','required'):raise ValueError('XDTO: неподдержанный use')
                    lower=int(use=='required');upper=1;nil=False
                else:
                    lower=_bound(a.get('minOccurs','1'));upper=_bound(a.get('maxOccurs','1'),True);nil=_boolean(a.get('nillable','false'))
                    if upper==0 or (upper>=0 and lower>upper):raise ValueError('XDTO: неверные границы свойства')
                form=a.get('form',attribute_form if is_attr else element_form)
                if form not in ('qualified','unqualified'):raise ValueError('XDTO: неверная форма свойства')
                properties.append(BSLXDTOProperty(kind,name,prop_type,kind._uri if form=='qualified' else '',lower,upper,nil,is_attr))
        kind._properties=BSLXDTOPropertyCollection(properties)
    # Acyclic type graph: bounded iterative DFS, before publishing this factory.
    done=set();heights={}
    for kind,_,_,_ in declarations:
        stack=[(kind,False)];active=set()
        while stack:
            current,exit=stack.pop()
            if exit:
                height=1+max((heights[id(p._type)] for p in current._properties if type(p._type) is BSLXDTOObjectType),default=0)
                if height>MAX_DEPTH:raise ValueError('XDTO: превышена глубина типов')
                heights[id(current)]=height;active.remove(id(current));done.add(id(current));continue
            if id(current) in active:raise ValueError('XDTO: рекурсивная схема пока не поддерживается')
            if id(current) in done:continue
            if len(active)>=MAX_DEPTH:raise ValueError('XDTO: превышена глубина типов')
            active.add(id(current));stack.append((current,True))
            stack.extend((p._type,False) for p in current._properties if type(p._type) is BSLXDTOObjectType)
    for uri,node in roots:
        a=_attrs(node,'element',{'name','type','nillable'})
        if node['children']:raise ValueError('XDTO: анонимный корневой тип пока не поддерживается')
        name=_identifier(a.get('name',''));kind=_resolve(factory,node,a.get('type',''))
        if (uri,name) in factory._roots or len(factory._roots)>=MAX_PROPERTIES:raise ValueError('XDTO: повтор или предел корней')
        factory._roots[uri,name]=BSLXDTOProperty(None,name,kind,uri,1,1,_boolean(a.get('nillable','false')))
    packages=[BSLXDTOPackage(XS,[t for (u,n),t in factory._types.items() if u==XS])]
    for uri,element_form,attribute_form,_ in schemas:
        packages.append(BSLXDTOPackage(uri,[t for (u,n),t in factory._types.items() if u==uri],[p for (u,n),p in factory._roots.items() if u==uri]))
        packages[-1]._element_qualified=element_form=='qualified'
        packages[-1]._attribute_qualified=attribute_form=='qualified'
    factory._packages=BSLXDTOPackageCollection(packages)
