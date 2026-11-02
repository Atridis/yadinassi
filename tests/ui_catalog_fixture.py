"""Independently authored official XML and real owned SQLite test databases.

No native binary captures, physical schemas, SQL or storage-private API here.
"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import tempfile
from uuid import UUID

from yadinassi.catalog_backend import CatalogDraft, CatalogKey
from yadinassi.configuration_xml import import_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.catalog_view import CatalogRepository

PRODUCT = UUID('10000000-0000-0000-0000-000000000001')
CATEGORY = UUID('10000000-0000-0000-0000-000000000002')
CONFIG = UUID('10000000-0000-0000-0000-000000000003')


def configuration_files():
    prefix = ('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" '
              'xmlns:v8="http://v8.1c.ru/8.1/data/core" '
              'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
              'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" version="2.20">')
    fields = (
        ('Text', 'xs:string', '<v8:StringQualifiers><v8:Length>32</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'),
        ('Amount', 'xs:decimal', '<v8:NumberQualifiers><v8:Digits>12</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>'),
        ('Active', 'xs:boolean', ''),
        ('Moment', 'xs:dateTime', '<v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>'),
        ('Category', 'cfg:CatalogRef.Categories', ''),
    )
    attributes = ''.join(
        f'<Attribute uuid="20000000-0000-0000-0000-{i:012d}"><Properties><Name>{name}</Name><Type><v8:Type>{kind}</v8:Type>{qualifiers}</Type></Properties></Attribute>'
        for i, (name, kind, qualifiers) in enumerate(fields, 1))
    files = {'Configuration.xml': (prefix + f'<Configuration uuid="{CONFIG}"><Properties><Name>OwnedUI</Name></Properties><ChildObjects><Catalog>Products</Catalog><Catalog>Categories</Catalog></ChildObjects></Configuration></MetaDataObject>').encode()}
    for name, identity, content in (('Products', PRODUCT, attributes), ('Categories', CATEGORY, '')):
        files['Catalogs/' + name + '.xml'] = (prefix + f'<Catalog uuid="{identity}"><Properties><Name>{name}</Name><CodeLength>8</CodeLength><DescriptionLength>64</DescriptionLength><Hierarchical>false</Hierarchical><CodeType>String</CodeType><Autonumbering>false</Autonumbering><CheckUnique>true</CheckUnique><CodeSeries>WholeCatalog</CodeSeries></Properties><ChildObjects>{content}</ChildObjects></Catalog></MetaDataObject>').encode()
    files['Ext/ManagedApplicationModule.bsl'] = b'// Owned fixture code retained; opening metadata must not execute modules.\n'
    return files


def repository(test, *, empty=False):
    temporary = tempfile.TemporaryDirectory()
    test.addCleanup(temporary.cleanup)
    path = Path(temporary.name) / 'application.sqlite'
    # Import source disappears before reopen, so metadata cannot come from it.
    with tempfile.TemporaryDirectory(dir=temporary.name) as source:
        for name, content in configuration_files().items():
            target = Path(source) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        configuration = import_configuration({name: (Path(source) / name).read_bytes()
                                               for name in configuration_files()})
        writer = SQLiteCatalogBackend.create(path, configuration)
    try:
        if not empty:
            tx = writer.begin_write(UUID('30000000-0000-0000-0000-000000000001'))
            category = CatalogKey(writer.database_id, CATEGORY, UUID('40000000-0000-0000-0000-000000000001'))
            tx.create(CatalogDraft(category, '10', 'Owned category', False, ()))
            for i, code in enumerate(('30', '10', '20'), 1):
                key = CatalogKey(writer.database_id, PRODUCT, UUID(f'50000000-0000-0000-0000-{i:012d}'))
                tx.create(CatalogDraft(key, code, 'Owned product ' + code, False,
                    ('typed text', Decimal('12.50'), True, datetime(2024, 2, 29, 12, 30, 45), category)))
            tx.commit()
    finally:
        writer.close()
    before = path.read_bytes()
    repo = CatalogRepository(SQLiteCatalogBackend(path, read_only=True))
    test.addCleanup(repo.close)
    return repo, path, before, {'product': str(PRODUCT), 'category': str(CATEGORY),
                              'source_removed': not Path(source).exists()}
