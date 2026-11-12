"""Exact-source main-demo UI admission and document projection.

Original catalog forms remain owned by the existing catalog editor policy. This
module does not turn them into generic forms or grant an old inventory profile.
The complete stored source remains the binding even when only document forms are
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
    from ..configuration_main_demo import canonical
    configuration = canonical(configuration)
    source = dict(configuration.files)
    projected = dict(source)
    _, _, root = _object(source['Configuration.xml'], 'Configuration', include_root=True)
    metadata = '{' + MD + '}'
    owner = root.find(metadata+'Configuration')
    children = owner.find(metadata+'ChildObjects')
    for node in list(children):
        if node.tag != metadata+'Document':
            children.remove(node)
    projected['Configuration.xml'] = ET.tostring(root, encoding='utf-8')
    forms = load_configuration_forms(projected, document_schemas=configuration.documents,
        reference_catalogs=configuration.catalogs, posting_application=True,
        enum_definitions=configuration.enumerations)
    # A structural view is not the source of authority: all 33 original files,
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
