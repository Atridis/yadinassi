"""Owned A fixture with exactly one additional catalog Delete permission."""
from catalog_object_behavior import fixture as original
from catalog_deletion_mark_behavior.fixture import load_saved
from . import route

MAX_FILE = original.MAX_FILE
MAX_TOTAL = original.MAX_TOTAL
_files = original._files


def verify_catalog_rights(files, name):
    """Check exact target and exact true grants; never export raw rights XML."""
    original._files(files)
    rights_path = original.ROLE_FILES[1]
    root, _ = original._xml(files[rights_path])
    rn = '{' + original.RIGHTS + '}'
    if root.tag != rn + 'Rights':
        raise ValueError('invalid catalog rights')
    target = 'Catalog.' + name
    matches = []
    for obj in root:
        if obj.tag != rn + 'object':
            continue
        names = [n for n in obj if n.tag == rn + 'name']
        if any(n.text == target for n in names):
            matches.append(obj)
    if len(matches) != 1:
        raise ValueError('invalid catalog rights')
    obj = matches[0]
    if obj.attrib:
        raise ValueError('invalid catalog rights')
    names = [n for n in obj if n.tag == rn + 'name']
    if len(names) != 1 or names[0].attrib or len(names[0]) or names[0].text != target:
        raise ValueError('invalid catalog rights')
    grants = []
    for node in obj:
        if node is names[0]:
            continue
        if (node.tag != rn + 'right' or node.attrib or
                [n.tag for n in node] != [rn + 'name', rn + 'value'] or
                any(n.attrib or len(n) for n in node) or node[1].text != 'true'):
            raise ValueError('invalid catalog rights')
        grants.append(node[0].text)
    if len(grants) != len(route.CATALOG_RIGHTS) or set(grants) != set(route.CATALOG_RIGHTS):
        raise ValueError('invalid catalog rights')
    return True


def prepare(files):
    setup, assets = load_saved()
    original._baseline(files, setup)
    expected = dict(files)
    md, rights = original.MD, original.RIGHTS
    expected['Configuration.xml'] = original._append(
        files['Configuration.xml'], (md+'}MetaDataObject', md+'}Configuration', md+'}ChildObjects'),
        lambda p: '<'+p+'Catalog>'+setup.name+'</'+p+'Catalog>')
    def grants(p):
        return ('<'+p+'object><'+p+'name>Catalog.'+setup.name+'</'+p+'name>' +
                ''.join('<'+p+'right><'+p+'name>'+r+'</'+p+'name><'+p+'value>true</'+p+'value></'+p+'right>'
                        for r in route.CATALOG_RIGHTS) + '</'+p+'object>')
    expected[original.ROLE_FILES[1]] = original._append(
        files[original.ROLE_FILES[1]], (rights+'}Rights',), grants)
    expected['Catalogs/'+setup.name+'.xml'] = assets['generated/Catalog.xml']
    original._files(expected)
    verify_catalog_rights(expected, setup.name)
    return setup, expected


def verify_redump(expected, actual):
    setup, _ = load_saved()
    verify_catalog_rights(expected, setup.name)
    verify_catalog_rights(actual, setup.name)
    # Compare the entire official XML/redump with the original strict verifier.
    return original.verify_redump(expected, actual)
