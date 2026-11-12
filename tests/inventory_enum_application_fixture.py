"""Authored UI fixture over measured core16 source; not native form evidence.

Uses the existing host editor/command contracts, never native observer modules.
This explicitly authored manifest grants host operations, not 1C parity.
"""
from inventory_application_fixture import source as forms_source
from test_configuration_inventory_enums import source as core_source


def source():
    core = core_source()
    forms = forms_source()
    for path, raw in forms.items():
        if '/Forms/' in path or path == 'InventoryApplication.xml':
            core[path] = raw
    for kind, names in (('Catalog', ('Products', 'Warehouses')), ('Document', ('Receipt', 'Issue'))):
        for name in names:
            path = kind + 's/' + name + '.xml'
            default = ('<DefaultObjectForm>' + kind + '.' + name + '.Form.Card</DefaultObjectForm>').encode()
            core[path] = core[path].replace(b'</Properties>', default + b'</Properties>', 1)
            if b'<ChildObjects />' in core[path]:
                core[path] = core[path].replace(b'<ChildObjects />', b'<ChildObjects><Form>Card</Form></ChildObjects>')
            else:
                before, after = core[path].rsplit(b'</ChildObjects>', 1)
                core[path] = before + b'<Form>Card</Form></ChildObjects>' + after
    return core
