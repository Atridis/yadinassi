"""Fresh source composition only; this does not install or execute a database.

The input must be the existing owned NativeSmoke baseline. No user directory or
arbitrary configuration is admitted. Installation/redump/lifecycle acceptance is
not implemented by this preparation helper.
"""
from pathlib import Path
import re
from inventory_enum_behavior import fixture as core

ROOT = Path(__file__).resolve().parent
OWNERS = (('Catalog', 'Products'), ('Document', 'Receipt'))


def prepare(files):
    setup, result = core.prepare(files)
    original = core.original
    rights = original.ROLE_FILES[1]
    result[rights] = grant_owned_form_view(result[rights])
    from .route import packet
    assets = packet()
    module = assets['lifecycle.bsl']
    if not 0 < len(module) <= core.MAX_FILE or b'ObservedCreate' not in module or b'ObservedOpen' not in module:
        raise ValueError('owned lifecycle source required')
    for kind, name in OWNERS:
        owner = kind + 's/' + name
        result[owner + '.xml'] = original._append(result[owner + '.xml'],
            (original.MD + '}MetaDataObject', original.MD + '}' + kind,
             original.MD + '}ChildObjects'), lambda p: '<' + p + 'Form>Card</' + p + 'Form>')
        result[owner + '/Forms/Card.xml'] = assets[name+'/Card.xml']
        result[owner + '/Forms/Card/Ext/Form.xml'] = assets[name+'/Form.xml']
        result[owner + '/Forms/Card/Ext/Form/Module.bsl'] = module + b'\n' + assets[name+'/observer.bsl']
    core._files(result)
    identities = []
    for path, raw in result.items():
        if not path.endswith('.xml'): continue
        root, scopes = original._xml(raw)
        for node in root.iter():
            if 'uuid' in node.attrib:
                identities.append(node.attrib['uuid'].casefold())
    if len(identities) != len(set(identities)):
        raise ValueError('duplicate configuration/form metadata identity')
    return setup, result


def grant_owned_form_view(raw):
    """Only View for the two objects whose forms this isolated packet opens."""
    core.original._xml(raw)
    for name in (b'Catalog.Products', b'Document.Receipt'):
        pattern = rb'<(?P<p>(?:[A-Za-z_][A-Za-z_0-9.-]*:)?)name>' + re.escape(name) + rb'</(?P=p)name>'
        matches = list(re.finditer(pattern, raw))
        if len(matches) != 1:
            raise ValueError('owned form rights identity')
        match = matches[0]; prefix = match['p']
        right = (b'<' + prefix + b'right><' + prefix + b'name>View</' + prefix
                 + b'name><' + prefix + b'value>true</' + prefix + b'value></'
                 + prefix + b'right>')
        raw = raw[:match.end()] + right + raw[match.end():]
    core.original._xml(raw)
    return raw
