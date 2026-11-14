"""Authored UI fixture over measured core16 source; not native form evidence.

Uses the existing host editor/command contracts, never native observer modules.
This explicitly authored manifest grants host operations, not 1C parity.
"""
from inventory_application_fixture import source as forms_source
from pathlib import Path


def core_source():
    root = Path(__file__).resolve().parents[1] / 'scripts/inventory_enum_behavior/runtime_source'
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


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
    path='Catalogs/Products/Forms/Card/Ext/Form.xml'
    core[path]=core[path].replace(b'</ChildItems>', b'<InputField name="UnitInput" id="30"><Title>Unit</Title><DataPath>Object.Unit</DataPath><Events><Event name="OnChange">Changed</Event></Events></InputField></ChildItems>')
    for name in ('Receipt','Issue'):
        path=f'Documents/{name}/Forms/Card/Ext/Form.xml'
        core[path]=core[path].replace(b'</ChildItems>', b'<InputField name="StateInput" id="30"><Title>State</Title><DataPath>Object.State</DataPath><Events><Event name="OnChange">Changed</Event></Events></InputField></ChildItems>')
    return core
