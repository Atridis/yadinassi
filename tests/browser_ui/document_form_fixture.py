"""Owned example creation and read-only durability audit, fixed public summaries."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from hashlib import sha256
import json
import sys
from yadinassi.configuration_import import read_configuration_directory
from yadinassi.configuration_document import DocumentObjectSession
from yadinassi.database_context import SQLiteDBContext
from yadinassi.document_backend import DocumentSelection
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

SOURCE=Path(__file__).resolve().parents[2]/'examples/configuration-document-forms'


def create(root):
    SQLiteCatalogBackend.create_document_forms(root/'documents.sqlite',read_configuration_directory(SOURCE)).close()
    return {'created':True}


def audit(root,final=False):
    files=read_configuration_directory(SOURCE)
    database=root/'documents.sqlite';before=sha256(database.read_bytes()).digest()
    with closing(SQLiteDBContext(database)) as context:
        assert context.backend.export_configuration()==files
        view=context.backend.begin_document_read()
        try:
            schema,=view.documents()
            cards=view.select_documents(schema.identity,DocumentSelection())
        finally:view.close()
        by_number={card.number:card for card in cards}
        assert set(by_number)==({'D1','D2','B1'} if final else {'D1'})
        first=by_number['D1'];rows=first.tabular_sections[0].rows
        assert [row.values for row in rows]==[('Second',Decimal('3.25'),False),('Third',Decimal('4.50'),False)]
        assert first.values==(('Updated first',) if final else ('First header',))
        for card in cards:
            owned=DocumentObjectSession(context,schema,files,card.key)
            assert owned.object.get_member('Posted') is False
        result={'durable':True,'records':len(cards),'orderedRows':True,'scalarTypes':True,'notPosted':True}
        if final:
            assert first.deletion_mark is True
            assert by_number['D2'].values==('Sibling draft',)
            assert by_number['D2'].tabular_sections[0].rows[0].values==('Sibling row',Decimal('1'),False)
            bounded=by_number['B1'].tabular_sections[0].rows
            assert len(bounded)==32 and all(row.values==('New line',Decimal('1'),False) for row in bounded)
            result.update(boundedRows=32,marked=True)
        assert sha256(database.read_bytes()).digest()==before
        return result


if __name__=='__main__':
    try:
        if len(sys.argv)!=3 or sys.argv[1] not in ('create','audit-first','audit-final'):raise ValueError('invalid_operation')
        root=Path(sys.argv[2])
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():raise ValueError('invalid_owned_root')
        result=create(root) if sys.argv[1]=='create' else audit(root,sys.argv[1]=='audit-final')
        print(json.dumps(result,sort_keys=True))
    except Exception:
        print('{"error":"owned_document_fixture_failed"}',file=sys.stderr)
        raise SystemExit(1) from None
