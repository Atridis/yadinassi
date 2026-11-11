"""Explicit application host source grant: forms, modules and scalar catalogs.

Separate from all historical profiles. Projection is possible only after every
removed form/object source is independently validated; unknown issues survive
as a rejection, never as an activation exception.
"""
from dataclasses import replace
from hashlib import sha256
import json
import xml.etree.ElementTree as ET

APPLICATION_PROFILE = 'configuration_application_v1'
APPLICATION_SOURCE_ISSUE = 'explicit configuration application source:v1'


def application_configuration(files):
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
    seen = set()
    for child in list(declarations):
        if child.tag not in (m + 'Catalog', m + 'CommonForm', m + 'CommonModule'):
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
        else:
            has_catalogs = True
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
    for prefix in form_prefixes:
        expected.update((prefix + '.xml', prefix + '/Ext/Form.xml'))
        path = prefix + '/Ext/Form/Module.bsl'
        if path in source: expected.add(path)
    if set(source) != expected:
        _fail('unexpected or missing application source file')
    ordinary = import_configuration(projected, numbering_policy='decimal_v1', module_runtime=MODULE_RUNTIME)
    if ordinary.activation_issues or ordinary.documents:
        _fail('unsupported application metadata semantics')
    if any(s.hierarchy != 'none' or s.tabular_sections or any(f.kind == 'catalog_ref' for f in s.fields) for s in ordinary.catalogs):
        _fail('scalar application catalogs only')
    from .configuration_forms import load_configuration_forms
    definitions = load_configuration_forms(source, catalog_schemas=ordinary.catalogs)
    if len(definitions.forms) != len(form_prefixes):
        _fail('unbound application form declaration')
    # All metadata owners share one UUID domain, even across module/form loaders.
    identities = [ordinary.config_uuid, *(s.identity for s in ordinary.catalogs),
                  *(m.identity for m in ordinary.common_modules),
                  *(f.identity for s in ordinary.catalogs for f in s.fields),
                  *(d.identity for d in definitions.forms.values())]
    if len(identities) != len(set(identities)): _fail('duplicate application metadata identity')
    from .catalog_object_preparation import validate_catalog_object_source
    by_id = {s.identity: s for s in ordinary.catalogs}
    for module in object_modules:
        validate_catalog_object_source(source[module.path].decode('utf-8-sig'), by_id[module.owner])
    manifest = sha256(json.dumps([(f.path, f.kind, sha256(f.content).hexdigest())
        for f in accepted], ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    return replace(ordinary, files=accepted, modules=ordinary.modules + tuple(object_modules),
                   activation_issues=(APPLICATION_SOURCE_ISSUE + ':' + manifest,)), catalogs


def import_application_configuration(files):
    """Opt in to the full checked application source, without executing it."""
    return application_configuration(files)[0]
