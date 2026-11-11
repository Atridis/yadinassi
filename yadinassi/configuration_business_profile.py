"""Explicit application host source grant: forms, modules, scalar catalogs and non-posting scalar documents.

Separate from all historical profiles. Projection is possible only after every
removed form/object source is independently validated; unknown issues survive
as a rejection, never as an activation exception.
"""
from dataclasses import replace
from hashlib import sha256
import json
import xml.etree.ElementTree as ET

BUSINESS_PROFILE = 'configuration_business_v1'
BUSINESS_SOURCE_ISSUE = 'explicit configuration business application source:v1'


def business_configuration(files):
    from .configuration_xml import (MD, V8, _accept_source_files, _object, _props,
        _text, _name, _fail, _inert_configuration, import_configuration, ConfigurationModule)
    from .configuration_modules import MODULE_RUNTIME
    accepted = _accept_source_files(files)
    source = {entry.path: entry.content for entry in accepted}
    m = '{' + MD + '}'
    config, _, root = _object(source['Configuration.xml'], 'Configuration', include_root=True)
    containers = config.findall(m + 'ChildObjects')
    if len(containers) != 1 or containers[0].attrib or (containers[0].text or '').strip():
        _fail('application child inventory required')
    declarations = containers[0]
    expected = {'Configuration.xml'}
    common_form_prefixes = []
    has_catalogs = False
    document_names = []
    seen = set()
    for child in list(declarations):
        if child.tag not in (m + 'Catalog', m + 'Document', m + 'CommonForm', m + 'CommonModule'):
            _fail('unsupported application metadata family')
        if child.attrib or len(child) or (child.tail or '').strip():
            _fail('invalid application declaration')
        name = _name((child.text or '').strip())
        key = child.tag, name.casefold()
        if key in seen: _fail('duplicate application declaration')
        seen.add(key)
        if child.tag == m + 'CommonForm':
            declarations.remove(child)
            common_form_prefixes.append('CommonForms/' + name)
        elif child.tag == m + 'CommonModule':
            expected.update(('CommonModules/' + name + '.xml', 'CommonModules/' + name + '/Ext/Module.bsl'))
        elif child.tag == m + 'Document':
            document_names.append(name)
        else:
            has_catalogs = True
    if not document_names:
        _fail('business profile requires at least one document')
    catalogs = _inert_configuration(source)[1] if has_catalogs else ()
    projected = {'Configuration.xml': ET.tostring(root, encoding='utf-8')}
    for path in expected - {'Configuration.xml'}:
        if path not in source: _fail('missing application module source')
        projected[path] = source[path]
    app_module = 'Ext/ManagedApplicationModule.bsl'
    if app_module in source:
        projected[app_module] = source[app_module]
        expected.add(app_module)
    object_modules = []
    form_prefixes = list(common_form_prefixes)
    for catalog in catalogs:
        if not catalog.forms or not catalog.default_object_form:
            _fail('application catalogs require declared object forms')
        obj, namespaces, catalog_root = _object(source[catalog.path], 'Catalog', include_root=True)
        props = _props(obj)
        default = props.get(m + 'DefaultObjectForm')
        if default is None or default.attrib or len(default):
            _fail('scalar default object form required')
        obj.find(m + 'Properties').remove(default)
        children = obj.find(m + 'ChildObjects')
        for child in list(children):
            if child.tag == m + 'Form': children.remove(child)
            elif child.tag != m + 'Attribute': _fail('scalar application catalogs only')
        for node in obj.iter('{' + V8 + '}Type'):
            value = (node.text or '').strip()
            if ':' in value:
                prefix = value.split(':', 1)[0]
                uri = namespaces[id(node)].get(prefix)
                if uri is None: _fail('unknown field type namespace')
                node.set('xmlns:' + prefix, uri)
        projected[catalog.path] = ET.tostring(catalog_root, encoding='utf-8')
        expected.add(catalog.path)
        for form in catalog.forms:
            form_prefixes.append(form.path[:-4])
        path = 'Catalogs/' + catalog.name + '/Ext/ObjectModule.bsl'
        if path in source:
            expected.add(path)
            object_modules.append(ConfigurationModule(catalog.identity, 'ObjectModule', path))
    form_names = set()
    for name in document_names:
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
                form_prefixes.append(prefix)
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
    for prefix in form_prefixes:
        expected.update((prefix + '.xml', prefix + '/Ext/Form.xml'))
        path = prefix + '/Ext/Form/Module.bsl'
        if path in source: expected.add(path)
    if set(source) != expected:
        _fail('unexpected or missing application source file')
    ordinary = import_configuration(projected, numbering_policy='decimal_v1', module_runtime=MODULE_RUNTIME)
    if ordinary.activation_issues or ordinary.information_registers:
        _fail('unsupported application metadata semantics')
    if any(s.hierarchy != 'none' or s.tabular_sections or any(f.kind == 'catalog_ref' for f in s.fields) for s in ordinary.catalogs):
        _fail('scalar application catalogs only')
    from .configuration_document import require_document_form_schema
    for schema in ordinary.documents: require_document_form_schema(schema)
    from .configuration_forms import load_configuration_forms
    definitions = load_configuration_forms(source, catalog_schemas=ordinary.catalogs, document_schemas=ordinary.documents)
    if len(definitions.forms) != len(form_prefixes):
        _fail('unbound application form declaration')
    # All metadata owners share one UUID domain, even across module/form loaders.
    identities = [ordinary.config_uuid, *(s.identity for s in ordinary.catalogs),
                  *(m.identity for m in ordinary.common_modules),
                  *(f.identity for s in ordinary.catalogs for f in s.fields),
                  *(d.identity for d in ordinary.documents),
                  *(f.identity for d in ordinary.documents for f in d.fields),
                  *(t.identity for d in ordinary.documents for t in d.tabular_sections),
                  *(f.identity for d in ordinary.documents for t in d.tabular_sections for f in t.fields),
                  *(d.identity for d in definitions.forms.values())]
    if len(identities) != len(set(identities)): _fail('duplicate application metadata identity')
    from .catalog_object_preparation import validate_catalog_object_source
    by_id = {s.identity: s for s in ordinary.catalogs}
    for module in object_modules:
        validate_catalog_object_source(source[module.path].decode('utf-8-sig'), by_id[module.owner])
    manifest = sha256(json.dumps([(f.path, f.kind, sha256(f.content).hexdigest())
        for f in accepted], ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    return replace(ordinary, files=accepted, modules=ordinary.modules + tuple(object_modules),
                   activation_issues=(BUSINESS_SOURCE_ISSUE + ':' + manifest,)), catalogs


def import_business_configuration(files):
    """Opt in to the full checked application source, without executing it."""
    return business_configuration(files)[0]
