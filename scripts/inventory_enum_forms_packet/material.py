"""Closed material redump acceptance for the NEW owned form composition.

Designer presentation/default XML is not an oracle. Executable files, form
identity, object type, attribute set and actual event bindings remain exact.
The existing enum/schema projection remains authoritative. No runtime evidence here.
"""
import xml.etree.ElementTree as ET
from . import configuration
from inventory_enum_behavior import fixture as core
original = core.original
MD = '{'+original.MD+'}'
FORM = '{http://v8.1c.ru/8.3/xcf/logform}'
V8 = '{'+original.V8+'}'
XSI = '{'+original.XSI+'}'


def _one(node, name):
    values = node.findall(name)
    if len(values) != 1: raise ValueError('owned form material singleton')
    return values[0]


def _sig(node, scopes):
    def qname(text):
        pieces=text.split(':')
        if len(pieces) not in (1,2): raise ValueError('owned form QName')
        prefix,local=('',pieces[0]) if len(pieces)==1 else pieces
        if prefix not in scopes[id(node)] or not local: raise ValueError('owned form QName')
        return '{'+scopes[id(node)][prefix]+'}'+local
    text=(node.text or '').strip()
    if node.tag==V8+'Type' and text: text=qname(text)
    attrs=tuple(sorted((name,qname(value) if name==XSI+'type' else value) for name,value in node.attrib.items()))
    return node.tag,attrs,text,tuple(_sig(c,scopes) for c in node)


def _without_form_declaration(raw):
    root,scopes=original._xml(raw)
    children=_one(root[0],MD+'ChildObjects')
    forms=[n for n in children if n.tag==MD+'Form']
    if len(forms)!=1 or forms[0].attrib or len(forms[0]) or forms[0].text!='Card':
        raise ValueError('owned Card declaration required')
    children.remove(forms[0])
    # Preserve the meaning of QName-valued metadata when serializing a copy.
    for node in root.iter():
        values=([node.text or ''] if node.tag==V8+'Type' else [])
        if XSI+'type' in node.attrib: values.append(node.attrib[XSI+'type'])
        for value in values:
            if ':' in value:
                prefix=value.split(':')[0]
                if prefix not in scopes[id(node)]:raise ValueError('owned metadata QName')
                node.set('xmlns:'+prefix,scopes[id(node)][prefix])
    return ET.tostring(root,encoding='utf-8')


def _closed_children(node, allowed):
    seen=set()
    for child in node:
        if child.tag not in allowed or child.tag in seen:
            raise ValueError('unknown or duplicate form material')
        seen.add(child.tag)


def _empty(node):
    if node.attrib or len(node) or (node.text or '').strip():
        raise ValueError('nonempty passive form default')


def _literal(node, value):
    if node.attrib or len(node) or (node.text or '').strip()!=value:
        raise ValueError('noncanonical passive form default')


def metadata_form(raw):
    root,scopes=original._xml(raw)
    if root.tag!=MD+'MetaDataObject' or len(root)!=1:raise ValueError('form metadata envelope')
    form=root[0]
    if form.tag!=MD+'Form' or set(form.attrib)!={'uuid'}:raise ValueError('form metadata identity')
    original._uuid(form.get('uuid'))
    props=_one(form,MD+'Properties')
    # Captions, help flags, comments and Designer internal defaults do not
    # establish identity or execution semantics of these observed forms.
    return form.get('uuid'),tuple(_sig(_one(props,MD+n),scopes) for n in ('Name','FormType','UsePurposes'))


def managed_form(raw):
    root,scopes=original._xml(raw)
    if root.tag!=FORM+'Form':raise ValueError('managed form envelope')
    attributes=_one(root,FORM+'Attributes');events=_one(root,FORM+'Events')
    if len(attributes)!=1:raise ValueError('owned Object attribute only')
    attribute=attributes[0]
    if attribute.tag!=FORM+'Attribute' or attribute.attrib!={'name':'Object','id':'1'}:
        raise ValueError('owned main attribute')
    typed=_one(attribute,FORM+'Type');main=_one(attribute,FORM+'MainAttribute')
    if typed.attrib or len(typed)!=1 or typed[0].tag!=V8+'Type' or typed[0].attrib or len(typed[0]):
        raise ValueError('owned attribute type shape')
    _literal(main,'true')
    bindings=[]
    for event in events:
        if event.tag!=FORM+'Event' or set(event.attrib)!={'name'} or len(event):raise ValueError('owned event shape')
        bindings.append((event.get('name'),event.text or ''))
    if sorted(bindings)!=[('OnCreateAtServer','ObservedCreate'),('OnOpen','ObservedOpen')]:
        raise ValueError('owned event bindings')
    # These observers do not use controls, commands or caller parameters.
    # No extra event/attribute may hide in a passive/default subtree.
    if sum(n.tag==FORM+'Event' for n in root.iter())!=2:raise ValueError('extra form event')
    if sum(n.tag==FORM+'Attribute' for n in root.iter())!=1:raise ValueError('extra form attribute')
    if any(n.tag==FORM+'Command' for n in root.iter()):raise ValueError('extra form command')
    for section in ('Commands','ChildItems','CommandInterface','Parameters'):
        for node in root.iter(FORM+section):_empty(node)
    return _sig(typed,scopes),tuple(sorted(bindings))


def verify_redump(expected,actual):
    core._files(expected);core._files(actual)
    if set(expected)!=set(actual):raise ValueError('owned configuration inventory')
    left=dict(expected);right=dict(actual)
    for kind,name in configuration.OWNERS:
        owner=kind+'s/'+name
        left[owner+'.xml']=_without_form_declaration(left[owner+'.xml'])
        right[owner+'.xml']=_without_form_declaration(right[owner+'.xml'])
        for suffix,project in (('/Forms/Card.xml',metadata_form),('/Forms/Card/Ext/Form.xml',managed_form)):
            path=owner+suffix
            if project(left.pop(path))!=project(right.pop(path)):raise ValueError('owned form material mismatch')
        path=owner+'/Forms/Card/Ext/Form/Module.bsl'
        original.verify_redump({path:left.pop(path)},{path:right.pop(path)})
    return core.verify_redump(left,right)
