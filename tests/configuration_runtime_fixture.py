"""Authored XML-shaped modules for the explicit local host profile, not native evidence."""
from uuid import uuid4
from sqlite_catalog_fixture import configuration_files


def module_files(modules=(), *, application=''):
    files = configuration_files()
    for name, source, flags in modules:
        files['Configuration.xml'] = files['Configuration.xml'].replace(
            b'</ChildObjects>', ('<CommonModule>' + name + '</CommonModule></ChildObjects>').encode())
        values = {'Global': 'false', 'ClientManagedApplication': 'true', 'Server': 'false',
                  'ServerCall': 'false', 'Privileged': 'false',
                  'ClientOrdinaryApplication': 'false', 'ExternalConnection': 'false',
                  'ReturnValuesReuse': 'DontUse', **flags}
        properties = ''.join('<' + key + '>' + value + '</' + key + '>' for key, value in values.items())
        files['CommonModules/' + name + '.xml'] = (
            '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" version="2.20">'
            '<CommonModule uuid="' + str(uuid4()) + '"><Properties><Name>' + name + '</Name>'
            + properties + '</Properties><ChildObjects/></CommonModule></MetaDataObject>').encode()
        files['CommonModules/' + name + '/Ext/Module.bsl'] = source.encode()
    if application:
        files['Ext/ManagedApplicationModule.bsl'] = application.encode()
    return files


CLIENT = ('Tools', 'Function Double(Val X) Export Return X * 2; EndFunction', {})
SERVER = {'ClientManagedApplication': 'false', 'Server': 'true', 'ServerCall': 'true'}
