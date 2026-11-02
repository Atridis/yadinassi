"""Ordinary bounded XDTO factories and XML/JSON adapters; no schema resolution."""
import copy
from functools import wraps
from enum import Enum
from .xdto_values import *
from .xdto_schema import load_schemas,_xml_tree,MAX_SCHEMA_BYTES
from .file_io import _FileMethods,_methods
from .values import BSLObject,BSLArray
from .structures import BSLStructure
from .maps import BSLMap
from .xml_io import BSLXMLReader
from .xml_writer import BSLXMLWriter,BSLXMLWriterSettings
from .json_processing import BSLJSONReader,BSLJSONWriter,read_json,write_json
from .dates import BSLDate


class BSLXMLForm(Enum):
    ELEMENT=('Element','Элемент')
    ATTRIBUTE=('Attribute','Атрибут')
    TEXT=('Text','Текст')
    def __str__(self):return self.value[1]


class BSLXMLForms(BSLObject):
    def get_member(self,name):
        for v in BSLXMLForm:
            if name.casefold() in [s.casefold() for s in v.value]:return v
        return super().get_member(name)
XML_FORMS=BSLXMLForms()


def _allocation_transaction(method):
    @wraps(method)
    def run(self,*args,**kwargs):
        previous=self._nodes,self._units
        try:return method(self,*args,**kwargs)
        except Exception:
            self._nodes,self._units=previous
            raise
    return run


class BSLXDTOFactory(_FileMethods):
    _methods=_methods(('type',True,'Type Тип'),('create',True,'Create Создать'),
        ('read_xml',True,'ReadXML ПрочитатьXML'),('write_xml',False,'WriteXML ЗаписатьXML'),
        ('read_json',True,'ReadJSON ПрочитатьJSON'),('write_json',False,'WriteJSON ЗаписатьJSON'))
    def __init__(self,model=None,packages=None):
        if model is not None or packages is not None:raise ValueError('XDTO: используйте СоздатьФабрикуXDTO для поддержанного XSD')
        self._nodes=0;self._units=0;self._types={};self._roots={}
        for name in ('string','boolean','decimal','integer','int','long','date','dateTime','base64Binary'):
            self._types[XS,name]=BSLXDTOValueType(self,name)
        self._packages=BSLXDTOPackageCollection([BSLXDTOPackage(XS,self._types.values())])
    def __str__(self):return 'ФабрикаXDTO'
    def _reserve(self,n,units):
        if self._nodes+n>MAX_NODES or self._units+units>MAX_UNITS:raise ValueError('XDTO: превышен предел ресурсов')
        self._nodes+=n;self._units+=units
    def _kind(self,kind):
        if not (type(kind) is BSLXDTOValueType or type(kind) is BSLXDTOObjectType) or kind._factory is not self:raise TypeError('XDTO: ожидается тип этой фабрики')
        return kind
    def get_member(self,name):
        if name.casefold() in ('packages','пакеты'):return self._packages
        return super().get_member(name)
    def type(self,uri,name):return self._types.get((text(uri),text(name)))
    def create(self,kind,*args):
        kind=self._kind(kind)
        if type(kind) is BSLXDTOObjectType:
            if args:raise TypeError('XDTO: создание объекта без значения')
            return BSLXDTODataObject(kind)
        if len(args)!=1:raise TypeError('XDTO: требуется значение')
        return BSLXDTODataValue(kind,args[0])
    def _value(self,value):
        if not (type(value) is BSLXDTODataObject or type(value) is BSLXDTODataValue) or value._factory is not self:raise TypeError('XDTO: ожидается значение этой фабрики')
        return value
    def _from_tree(self,node,kind,depth=0):
        if depth>MAX_DEPTH:raise ValueError('XDTO: превышена глубина чтения')
        xsi='http://www.w3.org/2001/XMLSchema-instance'
        if (xsi,'nil') in node['attrs']:
            if node['attrs'][xsi,'nil'] not in ('true','1') or node['children'] or node['text'] or len(node['attrs'])!=1:raise ValueError('XDTO: неверный пустой элемент')
            return None
        if type(kind) is BSLXDTOValueType:
            if node['children'] or node['attrs']:raise ValueError('XDTO: неверное скалярное содержимое')
            return self.create(kind,node['text'])
        if node['text'].strip():raise ValueError('XDTO: смешанное содержимое пока не поддерживается')
        obj=self.create(kind);props=kind._properties;seen=set()
        for (uri,name),value in node['attrs'].items():
            prop=next((p for p in props if p._attribute and (p._uri,p._name)==(uri,name)),None)
            if prop is None:raise ValueError('XDTO: неизвестный XML атрибут')
            obj.set(prop,self.create(prop._type,value));seen.add(prop._name)
        last=-1
        for child in node['children']:
            prop=next((p for p in props if not p._attribute and (p._uri,p._name)==(child['uri'],child['name'])),None)
            if prop is None:raise ValueError('XDTO: неизвестный XML элемент')
            order=props._items.index(prop)
            if order<last:raise ValueError('XDTO: нарушен порядок sequence')
            last=order;value=self._from_tree(child,prop._type,depth+1)
            if prop._upper==1:
                if prop._name in seen:raise ValueError('XDTO: повтор одиночного элемента')
                obj.set(prop,value)
            else:obj.get_list(prop).add(value)
            seen.add(prop._name)
        obj.validate();return obj
    @_allocation_transaction
    def read_xml(self,reader,kind=None):
        if type(reader) is not BSLXMLReader or reader._source is None:raise TypeError('XDTO: ожидается открытое ЧтениеXML')
        if reader._position>=0:raise ValueError('XDTO: позиционное чтение пока не поддерживается')
        root=_xml_tree(reader._source)
        if kind is None:
            prop=self._roots.get((root['uri'],root['name']))
            if prop is None:raise ValueError('XDTO: неизвестный корневой элемент')
            kind=prop._type
            if ('http://www.w3.org/2001/XMLSchema-instance','nil') in root['attrs'] and not prop._nil:raise ValueError('XDTO: корень не допускает nil')
        elif ('http://www.w3.org/2001/XMLSchema-instance','nil') in root['attrs']:
            raise ValueError('XDTO: nil требует известного корневого свойства')
        self._kind(kind);value=self._from_tree(root,kind)
        staged=copy.copy(reader)
        while staged.read():pass
        reader.__dict__.update(staged.__dict__)
        return value
    def write_xml(self,writer,value,local_name=None,uri=None,form=None,type_assignment=None):
        if type(writer) is not BSLXMLWriter:raise TypeError('XDTO: ожидается ЗаписьXML')
        if (form is not None and form is not BSLXMLForm.ELEMENT) or type_assignment is not None:raise ValueError('XDTO: расширенные формы записи пока не поддерживаются')
        value=self._value(value)
        if type(value) is BSLXDTODataObject:value.validate()
        if local_name is None:
            candidates=[p for p in self._roots.values() if p._type is value._type]
            if len(candidates)!=1:raise ValueError('XDTO: требуется имя корневого элемента')
            local_name=candidates[0]._name;uri=candidates[0]._uri
        local_name=text(local_name);uri=value._type._uri if uri is None else text(uri)
        tmp=BSLXMLWriter();tmp.set_string(BSLXMLWriterSettings('', '1.0',False))
        stack=[('node',value,local_name,uri,0)];count=0
        while stack:
            action,current,name,ns,depth=stack.pop();count+=1
            if count>2*MAX_NODES or depth>MAX_DEPTH:raise ValueError('XDTO: превышен предел записи')
            if action=='end':tmp.write_end_element();continue
            tmp.write_start_element(name,ns)
            if tmp._scope().get('','')!=ns or (depth==0 and writer._scope().get('','')!=ns):tmp.write_namespace_mapping('',ns)
            if current is None:
                tmp.write_namespace_mapping('xsi','http://www.w3.org/2001/XMLSchema-instance');tmp.write_attribute('xsi:nil','true');tmp.write_end_element();continue
            if type(current) is BSLXDTODataValue:
                tmp.write_text(current._lexical);tmp.write_end_element();continue
            children=[]
            for prop in current._type._properties:
                if prop._name not in current._values:continue
                item=current._values[prop._name]
                if prop._attribute:
                    if item is None:raise ValueError('XDTO: пустой XML атрибут')
                    if prop._uri:raise ValueError('XDTO: квалифицированный атрибут записи пока не поддерживается')
                    tmp.write_attribute(prop._name,item._lexical)
                else:
                    items=item._items if type(item) is BSLXDTOList else (item,)
                    children.extend(('node',child,prop._name,prop._uri,depth+1) for child in items)
            stack.append(('end',None,'','',depth));stack.extend(reversed(children))
        result=tmp.close()
        # Reuse the bounded XML writer's staged in-memory commit, never copy fd.
        staged=object.__new__(BSLXMLWriter);staged.__dict__=copy.deepcopy({k:v for k,v in writer.__dict__.items() if k!='_stream'});staged._stream=None
        staged.write_raw(result);stream=writer._stream;writer.__dict__.update(staged.__dict__);writer._stream=stream
    def _plain(self,value,depth=0):
        if depth>MAX_DEPTH:raise ValueError('XDTO: превышена глубина JSON')
        if value is None:return None
        if type(value) is BSLXDTODataValue:
            return value._lexical if (type(value._value) is BSLDate or type(value._value) is BSLBinaryData) else value._value
        result=BSLMap()
        for prop in value._type._properties:
            if prop._name not in value._values:continue
            item=value._values[prop._name]
            if type(item) is BSLXDTOList:
                array=BSLArray();array.items=[self._plain(v,depth+1) for v in item._items];result.insert(prop._name,array)
            else:result.insert(prop._name,self._plain(item,depth+1))
        return result
    def write_json(self,writer,value,type_assignment=None):
        if type(writer) is not BSLJSONWriter:raise TypeError('XDTO: ожидается ЗаписьJSON')
        if type_assignment is not None:raise ValueError('XDTO: явное назначение типа пока не поддерживается')
        value=self._value(value)
        if type(value) is BSLXDTODataObject:value.validate()
        write_json(writer,self._plain(value))
    def _from_plain(self,kind,value,depth=0):
        if depth>MAX_DEPTH:raise ValueError('XDTO: превышена глубина JSON')
        if value is None:return None
        if type(kind) is BSLXDTOValueType:return self.create(kind,value)
        if type(value) is not BSLMap:raise TypeError('XDTO: ожидается JSON объект')
        if len(value._items)>MAX_PROPERTIES:raise ValueError('XDTO: превышен предел свойств')
        obj=self.create(kind)
        for pair in value:
            prop=obj._property(pair.key)
            if prop._upper==1:obj.set(prop,self._from_plain(prop._type,pair.value,depth+1))
            else:
                if type(pair.value) is not BSLArray or len(pair.value.items)>MAX_LIST:raise ValueError('XDTO: ожидается ограниченный JSON массив')
                items=obj.get_list(prop)
                for v in pair.value.items:items.add(self._from_plain(prop._type,v,depth+1))
        obj.validate();return obj
    @_allocation_transaction
    def read_json(self,reader,kind=None,*callbacks):
        if type(reader) is not BSLJSONReader or reader._source is None:raise TypeError('XDTO: ожидается открытое ЧтениеJSON')
        if callbacks or kind is None:raise ValueError('XDTO: требуется явный тип без callbacks')
        kind=self._kind(kind)
        if reader._position>=0:raise ValueError('XDTO: позиционное чтение JSON пока не поддерживается')
        if len(reader._source)>MAX_SCHEMA_BYTES:raise ValueError('XDTO: превышен размер JSON')
        staged=copy.copy(reader)
        # Inspect bounded parsed tokens before map conversion can collapse duplicate keys.
        from .json_processing import T
        probe=copy.copy(reader);objects=[]
        while probe.read():
            token,key=probe._current
            if token is T.START_OBJECT:objects.append(set())
            elif token is T.END_OBJECT:objects.pop()
            elif token is T.PROPERTY_NAME:
                if key in objects[-1] or len(objects[-1])>=MAX_PROPERTIES:raise ValueError('XDTO: повтор или предел JSON свойств')
                objects[-1].add(key)
        staged._tokens=probe._tokens
        value=read_json(staged,True);result=self._from_plain(kind,value)
        reader.__dict__.update(staged.__dict__);return result


def create_xdto_factory(paths,packages=None):
    factory=BSLXDTOFactory();load_schemas(factory,paths,packages);return factory
