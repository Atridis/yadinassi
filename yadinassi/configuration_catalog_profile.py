"""Explicit whole-source admission for scalar catalog object forms, version 1.

No ambient importer activation and no native managed-form parity assertion.
The metadata projection removes only separately validated form declarations;
ordinary catalog validation must still succeed without activation issues.
"""
from dataclasses import replace
from hashlib import sha256
import json
import xml.etree.ElementTree as ET

CATALOG_FORMS_PROFILE = 'catalog_object_forms_v1'
CATALOG_FORMS_SOURCE_ISSUE = 'explicit catalog object forms source:v1'


def catalog_forms_configuration(files):
    from .configuration_xml import (MD, V8, _inert_configuration, _object, _props,
        _text, _fail, import_configuration, ConfigurationModule)
    archive, catalogs = _inert_configuration(files)
    source = {f.path: f.content for f in archive.files}
    m = '{' + MD + '}'
    config, _ = _object(source['Configuration.xml'], 'Configuration')
    if any(n.tag != m + 'Catalog' for n in config.find(m + 'ChildObjects')):
        _fail('catalog object forms require catalog-only configuration')
    projected = {'Configuration.xml': source['Configuration.xml']}
    expected = {'Configuration.xml'}
    modules = []
    for catalog in catalogs:
        if not catalog.forms or not catalog.default_object_form:
            _fail('catalog object forms require declared default form')
        obj, namespaces, root = _object(source[catalog.path], 'Catalog', include_root=True)
        props = _props(obj)
        default = props.get(m + 'DefaultObjectForm')
        if default is None or default.attrib or len(default):
            _fail('scalar default object form required')
        obj.find(m + 'Properties').remove(default)
        children = obj.find(m + 'ChildObjects')
        for child in list(children):
            if child.tag == m + 'Form':
                children.remove(child)
            elif child.tag != m + 'Attribute':
                _fail('scalar catalog object forms only')
        # ElementTree changes tag prefixes. Preserve QName value scopes without
        # global namespace registration or accepting caller-controlled schemas.
        for node in obj.iter('{' + V8 + '}Type'):
            value = (node.text or '').strip()
            if ':' in value:
                prefix = value.split(':', 1)[0]
                uri = namespaces[id(node)].get(prefix)
                if uri is None:
                    _fail('unknown field type namespace')
                node.set('xmlns:' + prefix, uri)
        projected[catalog.path] = ET.tostring(root, encoding='utf-8')
        expected.add(catalog.path)
        for form in catalog.forms:
            expected.update((form.path, form.definition_path))
            if form.module_path in source:
                expected.add(form.module_path)
        path = 'Catalogs/' + catalog.name + '/Ext/ObjectModule.bsl'
        if path in source:
            expected.add(path)
            modules.append(ConfigurationModule(catalog.identity, 'ObjectModule', path))
    if set(source) != expected:
        _fail('unexpected catalog object forms source file')
    # Explicit decimal_v1 is intrinsic to this profile, not a native claim.
    ordinary = import_configuration(projected, numbering_policy='decimal_v1')
    if ordinary.activation_issues or ordinary.documents:
        _fail('unsupported catalog object forms metadata semantics')
    if any(s.tabular_sections or any(f.kind == 'catalog_ref' for f in s.fields)
           for s in ordinary.catalogs):
        _fail('scalar catalog object forms only')
    from .configuration_forms import load_configuration_forms
    definitions = load_configuration_forms(source, catalog_schemas=ordinary.catalogs)
    if (len(definitions.forms) != sum(len(c.forms) for c in catalogs)
            or any(d.catalog_schema is None for d in definitions.forms.values())):
        _fail('every declared form must be a checked catalog object form')
    from .catalog_object_preparation import validate_catalog_object_source
    by_id = {s.identity: s for s in ordinary.catalogs}
    for module in modules:
        validate_catalog_object_source(source[module.path].decode('utf-8-sig'), by_id[module.owner])
    manifest = sha256(json.dumps([(f.path, f.kind, sha256(f.content).hexdigest())
        for f in archive.files], ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    return replace(ordinary, files=archive.files, modules=tuple(modules),
                   activation_issues=(CATALOG_FORMS_SOURCE_ISSUE + ':' + manifest,)), catalogs
