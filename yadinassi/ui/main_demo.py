"""Exact-source main-demo UI admission and document/common-form projection.

Original catalog forms remain owned by the existing catalog editor policy. This
module does not turn them into generic forms or grant an old inventory profile.
The complete stored source remains the binding even when document and declared common forms are
projected for the document/report surface.
"""
from dataclasses import replace
from hashlib import sha256
from types import MappingProxyType
import xml.etree.ElementTree as ET

from ..catalog_backend import BackendError
from ..configuration_forms import load_configuration_forms
from ..configuration_xml import MD, _object


def document_forms(configuration):
    from ..configuration_main_demo import canonical, _runtime_metadata_projection
    configuration = canonical(configuration)
    source = dict(configuration.files)
    projected = _runtime_metadata_projection(source)
    _, _, root = _object(source['Configuration.xml'], 'Configuration', include_root=True)
    metadata = '{' + MD + '}'
    owner = root.find(metadata+'Configuration')
    children = owner.find(metadata+'ChildObjects')
    for node in list(children):
        if node.tag not in (metadata+'Document', metadata+'CommonForm'):
            children.remove(node)
    projected['Configuration.xml'] = ET.tostring(root, encoding='utf-8')
    forms = load_configuration_forms(projected, document_schemas=configuration.documents,
        reference_catalogs=configuration.catalogs, posting_application=True,
        enum_definitions=configuration.enumerations)
    # Generated object-table columns otherwise expose stable schema identifiers.
    # Main-demo presentation only: names/types/slots remain unchanged; this is
    # not a global importer rule or a claim about native generated forms.
    titles = {'Product':'Номенклатура', 'Quantity':'Количество', 'Amount':'Сумма',
              'Unit':'Единица измерения', 'Warehouse':'Склад', 'State':'Состояние',
              'Lines':'Товары'}
    localized = {name: replace(definition, tables=tuple(
        replace(table, title=titles.get(table.title, table.title), columns=tuple(
            replace(column, title=titles.get(column.title or column.name, column.title))
            for column in table.columns)) for table in definition.tables))
        for name, definition in forms.forms.items()}
    forms = replace(forms, forms=MappingProxyType(localized))
    # A structural view is not the source of authority: the complete canonical envelope,
    # including the untouched catalog handlers, stay in the source witness.
    digest = sha256()
    for path, raw in sorted(source.items()):
        digest.update(path.encode('utf-8') + b'\0' + raw + b'\0')
    return replace(forms, source_sha256=digest.hexdigest(),
                   source_files=MappingProxyType(source))


def require_backend(backend):
    from ..configuration_main_demo import MainDemoConfiguration, PROFILE, canonical
    from ..sqlite_catalog import SQLiteCatalogBackend
    if type(backend) is not SQLiteCatalogBackend:
        raise BackendError('unsupported')
    if backend._closed:
        raise BackendError('closed')
    configuration = backend.accumulation_configuration
    if (backend.format_version != 16 or type(configuration) is not MainDemoConfiguration
            or configuration.profile != PROFILE):
        raise BackendError('unsupported')
    try:
        configuration = canonical(configuration)
    except ValueError:
        raise BackendError('schema_changed') from None
    if backend.export_configuration() != dict(configuration.files):
        raise BackendError('schema_changed')
    return configuration


def form_family(configuration, *, side, **kwargs):
    """Memory-only scheduler/enum family, never a projected database grant.

    Form programs still come from the full canonical envelope. The small ordinary
    configuration below contains only exact-source lifecycle/modules and enums,
    never forms or storage schemas.
    Common-form interpreters must also remain database-less; document interpreters
    retain their separately validated object-session admission.
    """
    from ..configuration_main_demo import canonical
    from ..configuration_modules import MODULE_RUNTIME
    from ..configuration_xml import import_configuration
    from ..configuration_runtime import ConfigurationApplication
    configuration = canonical(configuration)
    if kwargs.get('database_context') is not None:
        raise ValueError('main demo form family is memory-only')
    metadata = '{' + MD + '}'
    root = ET.Element(metadata+'MetaDataObject', {'version':'2.20'})
    owner = ET.SubElement(root, metadata+'Configuration', {'uuid':str(configuration.identity)})
    props = ET.SubElement(owner, metadata+'Properties')
    ET.SubElement(props, metadata+'Name').text = configuration.name
    children = ET.SubElement(owner, metadata+'ChildObjects')
    source = dict(configuration.files)
    projected = {}
    for enum in configuration.enumerations:
        ET.SubElement(children, metadata+'Enum').text = enum.name
        path = 'Enums/'+enum.name+'.xml'
        projected[path] = source[path]
    # Every byte was admitted by canonical() above; this is not a generic module grant.
    for name in ('DemoTools', 'DemoService'):
        ET.SubElement(children, metadata+'CommonModule').text = name
        for path in ('CommonModules/'+name+'.xml', 'CommonModules/'+name+'/Ext/Module.bsl'):
            projected[path] = source[path]
    projected['Ext/ManagedApplicationModule.bsl'] = source['Ext/ManagedApplicationModule.bsl']
    projected['Configuration.xml'] = ET.tostring(root, encoding='utf-8')
    imported = import_configuration(projected, module_runtime=MODULE_RUNTIME)
    return ConfigurationApplication(imported, side=side, **kwargs)
