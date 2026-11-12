"""Отдельный authored сценарий, не grant основной демо и не native evidence."""
from pathlib import Path


def sources(root=Path(__file__).resolve().parents[1] / "examples" / "demo"):
    # Только шесть новых форм; минимальный root создаётся в памяти.
    root = Path(root)
    paths = [f'CommonForms/{name}{suffix}' for name in ('OperationDraft', 'DraftDetails')
             for suffix in ('.xml', '/Ext/Form.xml', '/Ext/Form/Module.bsl')]
    files = {path: (root / path).read_bytes() for path in paths}
    files['Configuration.xml'] = b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" version="2.20"><Configuration uuid="5d8e26b4-e168-4ee1-8c79-e470a517c721"><Properties><Name>OperationDraftWorkshop</Name></Properties><ChildObjects><CommonForm>OperationDraft</CommonForm><CommonForm>DraftDetails</CommonForm></ChildObjects></Configuration></MetaDataObject>'
    return files
