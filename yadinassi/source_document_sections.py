"""Owned document section buffers with explicit actual-caller authorization."""
from decimal import Decimal
from .values import BSLObject,HostFunction
from .source_constant_store import _encode
from .source_document_section_store import _MAX_ROWS,_MAX_DOCUMENT_BYTES

_METHODS={'add':'add','добавить':'add','get':'get','получить':'get','count':'count','количество':'count','clear':'clear','очистить':'clear','delete':'delete','удалить':'delete'}

def _index(value,length):
    if type(value) is not Decimal or not value.is_finite() or value!=value.to_integral_value() or not 0<=value<length:raise ValueError('section index requires bounded integer Number')
    return int(value)

class SourceDocumentRow(BSLObject):
    def __init__(self,section,values):self.section,self.values,self.live=section,dict(values),True
    def authorize(self,caller):
        self.section.authorize(caller)
        if not self.live or self not in self.section.rows:raise ValueError('detached section row unavailable')
    def property_read(self,caller,name):
        self.authorize(caller);key=name.casefold()
        if key in ('linenumber','номерстроки'):return Decimal(self.section.rows.index(self)+1)
        if key not in self.section.fields:raise ValueError('unknown section field')
        if key not in self.values:raise ValueError('section field requires explicit assignment')
        return self.values[key]
    def property_write(self,caller,name,value):
        self.authorize(caller);key=name.casefold()
        if key not in self.section.fields:raise ValueError('section field readonly or unknown')
        raw=_encode(value,self.section.fields[key])
        # Bound the entire live owner buffer, including not-yet-written rows.
        previous=self.values.get(key);present=key in self.values
        self.values[key]=value
        try:self.section.buffer_bound()
        except BaseException:
            if present:self.values[key]=previous
            else:self.values.pop(key,None)
            raise

class SourceDocumentSection(BSLObject):
    def __init__(self,owner,definition,rows=()):
        self.owner,self.definition,self.live=owner,definition,True
        self.fields={f.name.casefold():f for f in definition.fields}
        self.rows=[SourceDocumentRow(self,row) for row in rows];self.version=0
    def authorize(self,caller):
        self.owner.authorize(caller)
        if not self.live or self.owner.sections.get(self.definition.name.casefold()) is not self:raise ValueError('detached document section unavailable')
    def invalidate(self):
        self.live=False
        for row in self.rows:row.live=False
        self.version+=1
    def buffer_bound(self):
        total=0;count=0
        for section in self.owner.sections.values():
            count+=len(section.rows)
            for row in section.rows:
                total+=32+sum(len(_encode(v,section.fields[k]).encode())+len(k.encode()) for k,v in row.values.items())
        if count>_MAX_ROWS or total>_MAX_DOCUMENT_BYTES:raise ValueError('document section buffer bound')
    def property_read(self,caller,name):
        self.authorize(caller);return self.get_member(name)
    def property_write(self,caller,name,value):
        self.authorize(caller);raise ValueError('section properties readonly')
    def get_member(self,name):
        if name.casefold() not in _METHODS:raise ValueError('unsupported document section method')
        return HostFunction(name,SourceDocumentSectionCall(self,_METHODS[name.casefold()]))
    def get_index(self,caller,index):
        self.authorize(caller);return self.rows[_index(index,len(self.rows))]
    def iterate(self,caller):
        self.authorize(caller);version=self.version
        for row in tuple(self.rows):
            self.authorize(caller)
            if version!=self.version:raise ValueError('section changed during iteration')
            yield row

class SourceDocumentSectionCall:
    def __init__(self,section,operation):self.section,self.operation=section,operation
    def __call__(self,*args):raise ValueError('section methods require interpreter invocation')
    def invoke(self,caller,values):
        section=self.section;section.authorize(caller);op=self.operation
        if op in ('get','delete'):
            if len(values)!=1:raise TypeError('section method requires one argument')
        elif values:raise TypeError('section method takes no arguments')
        if op=='count':return Decimal(len(section.rows))
        if op=='get':return section.get_index(caller,values[0])
        if op=='add':
            row=SourceDocumentRow(section,{})
            section.rows.append(row)
            try:section.buffer_bound()
            except BaseException:section.rows.pop();row.live=False;raise
            section.version+=1;return row
        if op=='clear':
            for row in section.rows:row.live=False
            section.rows.clear();section.version+=1;return None
        if op=='delete':
            value=values[0]
            if type(value) is SourceDocumentRow:
                value.authorize(caller)
                if value.section is not section:raise ValueError('row belongs to another section')
                index=section.rows.index(value)
            else:index=_index(value,len(section.rows))
            section.rows.pop(index).live=False;section.version+=1;return None
        raise ValueError('unsupported section operation')
