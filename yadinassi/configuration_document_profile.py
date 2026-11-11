"""Explicit non-posting document-form source grant, never an inert activation.

Version 1 is document-only. Common modules/application and catalog composition
require a separately checked future profile, not a relaxation of old grants.
"""
from dataclasses import replace
from hashlib import sha256
import json
import xml.etree.ElementTree as ET

DOCUMENT_FORMS_PROFILE = 'configuration_documents_v1'
DOCUMENT_FORMS_SOURCE_ISSUE = 'explicit document object forms source:v1'


def document_forms_configuration(files):
    from .configuration_xml import (MD, V8, _accept_source_files, _object, _props,
        _text, _name, _fail, import_configuration)
    from .configuration_document import require_document_form_schema
    from .configuration_forms import load_configuration_forms
    accepted = _accept_source_files(files)
    source = {f.path: f.content for f in accepted}
    m = '{' + MD + '}'
    config, _ = _object(source['Configuration.xml'], 'Configuration')
    children = config.findall(m + 'ChildObjects')
    if len(children) != 1 or children[0].attrib or (children[0].text or '').strip():
        _fail('document inventory required')
    names = []
    for child in children[0]:
        if child.tag != m+'Document' or child.attrib or len(child) or (child.tail or '').strip():
            _fail('document forms profile is document-only')
        names.append(_name((child.text or '').strip()))
    if not names or len(set(n.casefold() for n in names)) != len(names):
        _fail('invalid document inventory')
    expected = {'Configuration.xml'}
    projected = {'Configuration.xml': source['Configuration.xml']}
    form_names = set()
    for name in names:
        path = 'Documents/'+name+'.xml'
        obj, namespaces, root = _object(source[path], 'Document', include_root=True)
        props = _props(obj)
        default = props.get(m+'DefaultObjectForm')
        if default is None or default.attrib or len(default):
            _fail('document default object form required')
        default_name = (default.text or '').strip()
        obj.find(m+'Properties').remove(default)
        inventory = obj.find(m+'ChildObjects')
        if inventory is None: _fail('document child inventory required')
        owned = []
        for child in list(inventory):
            if child.tag == m+'Form':
                if child.attrib or len(child): _fail('invalid document form declaration')
                form = _name((child.text or '').strip())
                public = 'Document.'+name+'.Form.'+form
                if public.casefold() in form_names: _fail('duplicate document form')
                form_names.add(public.casefold()); owned.append(public)
                prefix='Documents/'+name+'/Forms/'+form
                expected.update((prefix+'.xml',prefix+'/Ext/Form.xml'))
                module=prefix+'/Ext/Form/Module.bsl'
                if module in source: expected.add(module)
                inventory.remove(child)
            elif child.tag not in (m+'Attribute',m+'TabularSection'):
                _fail('unsupported document child semantics')
        if default_name not in owned: _fail('undeclared default document form')
        for node in obj.iter('{'+V8+'}Type'):
            value=(node.text or '').strip()
            if ':' in value:
                prefix=value.split(':',1)[0]; uri=namespaces[id(node)].get(prefix)
                if uri is None: _fail('unknown document field namespace')
                node.set('xmlns:'+prefix,uri)
        expected.add(path); projected[path]=ET.tostring(root,encoding='utf-8')
    if set(source) != expected: _fail('unexpected or missing document forms source')
    ordinary=import_configuration(projected,numbering_policy='decimal_v1')
    if ordinary.activation_issues or ordinary.catalogs or ordinary.common_modules or ordinary.information_registers:
        _fail('unsupported document source semantics')
    for schema in ordinary.documents: require_document_form_schema(schema)
    definitions=load_configuration_forms(source,document_schemas=ordinary.documents)
    if set(definitions.forms) != form_names or any(d.document_schema is None for d in definitions.forms.values()):
        _fail('unbound document object form')
    identities=[ordinary.config_uuid,*(d.identity for d in ordinary.documents),
        *(f.identity for d in ordinary.documents for f in d.fields),
        *(s.identity for d in ordinary.documents for s in d.tabular_sections),
        *(f.identity for d in ordinary.documents for s in d.tabular_sections for f in s.fields),
        *(d.identity for d in definitions.forms.values())]
    if len(set(identities))!=len(identities): _fail('duplicate document metadata identity')
    manifest=sha256(json.dumps([(f.path,f.kind,sha256(f.content).hexdigest()) for f in accepted],
        ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
    return replace(ordinary,files=accepted,activation_issues=(DOCUMENT_FORMS_SOURCE_ISSUE+':'+manifest,)), ordinary.documents


def import_document_forms_configuration(files):
    return document_forms_configuration(files)[0]
