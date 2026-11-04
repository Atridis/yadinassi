"""Authored bounded XML fixtures, not evidence of native Designer parity."""
import re
from uuid import uuid4
from sqlite_catalog_fixture import configuration_files


def configuration_files_with_sections():
    files = configuration_files()
    path = 'Catalogs/Products.xml'
    source = files[path].decode('utf-8')
    fields = re.findall(r'<Attribute uuid="[^"]+">.*?</Attribute>', source)
    def fresh(field):
        return re.sub(r'uuid="[^"]+"', f'uuid="{uuid4()}"', field, count=1)
    def section(name, attributes):
        return (f'<TabularSection uuid="{uuid4()}"><Properties><Name>{name}</Name>'
                '<Synonym/><Comment/></Properties>'
                f'<ChildObjects>{attributes}</ChildObjects></TabularSection>')
    sections = section('Lines', ''.join(fresh(field) for field in fields))
    sections += section('Notes', fresh(fields[0]).replace('<v8:Length>32</v8:Length>',
                                                         '<v8:Length>128</v8:Length>'))
    before, after = source.rsplit('</ChildObjects>', 1)
    files[path] = (before + sections + '</ChildObjects>' + after).encode('utf-8')
    return files
