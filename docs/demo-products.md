# Original demo products in the local editor

The fresh `demo_products_v1` profile admits the original **ВидыНоменклатуры**, **Склады**, and **Номенклатура** catalogs from the exact 19-file editable demo archive. Source bytes are retained unchanged. Older kinds-only, directories-only and inert databases are not migrated or silently expanded.

## Create and open an owned database

From the repository checkout, with the project's Python dependencies installed:

```python
from pathlib import Path
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

root = Path("tests/fixtures/demo_cf/source")
files = {p.relative_to(root).as_posix(): p.read_bytes()
         for p in root.rglob("*") if p.is_file()}
backend = SQLiteCatalogBackend.create_demo_products("demo-products.sqlite", files)
backend.close()
```

Run `python -m yadinassi.ui.local_app --f demo-products.sqlite`.
Create a kind (for example, **Товары**) and a warehouse (**Основной склад**), then open **Номенклатура** and create a card. Enter a name, select the kind, add a **Склады** row, select its warehouse, and save. The automatically assigned code, reference, and row identity survive database close/reopen.

## Original behavior exercised

The local editor projects the original object form onto its bounded controls. It executes the original BSL handlers for name, kind, and warehouse changes. The selected warehouse row is identified by its stable UUID, then exposed to the original handler as `Элементы.Склады.ТекущиеДанные` within this one explicit host call.

Save executes the original `ПередЗаписьюНаСервере` over a disposable draft, calling the original object's `ПодготовитьДанныеКЗаписи`. The mandatory original `ПередЗаписью` then runs inside the atomic writer transaction. Kind and warehouse existence/deletion checks use that same writer snapshot, so a target changed after the form check cannot bypass validation.

The original rules require a trimmed name of at least three characters, a live unmarked kind, at least one warehouse, and no empty, duplicate, missing or deletion-marked warehouse references. Original deletion-mark bypass is preserved. Messages are displayed as diagnostics, not executable navigation instructions. Structural row edits clear obsolete positional messages.

Ordinary `CatalogObject.Write`/`Записать` in this exact profile cannot skip the original object validation. This is a host policy for one byte-pinned source, not generic configuration-module activation. Low-level backend transactions remain storage primitives and do not promise business validation.

## Boundaries

- This is a local host form projection, not native 1C managed-form or client/server parity. The product list exposes one bounded **Проверить карточку** command. The host invokes the byte-pinned original `ПроверитьКарточкуНаСервере` handler directly, not native managed-form client/server dispatch.
- Choices are bounded to 64 records per target catalog, with at most 32 editable rows. Unsupported or unavailable selections remain read-only. Existing larger sections remain visible as a read-only summary; this bounded original-form adapter does not save them.
- No arbitrary XML/BSL, modified demo archive, additional form fields, or arbitrary handlers are admitted.
- The existing formatter can render zero as empty for the original `ЧГ=0` expression. A first-row diagnostic may therefore show `Склады[].Склад`; the diagnostic remains visible and saving remains refused. This is not a native formatting-parity claim.
- Source/schema drift fails closed. Uncertain commits retain the exact submitted object and source; receipt recovery does not replay form handlers. Refresh failure is retried without a second write.

See [catalog editor](catalog-editor.md), [tabular sections](catalog-tabular-sections.md), and [original kinds/warehouses](demo-directories.md).

## Check a saved card from the list

Each product row has **Проверить карточку**. An empty list offers the same
command without a selection and shows the original selection diagnostic.
The command reads the saved product, its kind and warehouses, and both original
BSL modules through one read-only SQLite snapshot. It calls the original
`ПроверитьДанные`, not save preparation: names, rows and revisions are unchanged.
Deleted/missing products and invalid referenced records produce the original
bounded diagnostics. Field labels are plain text, not navigation authority.

Checking is unavailable while any editor is open, including a dirty editor.
Return to the list first; no unsaved form buffer is accepted by this command.
Repeated checks read fresh saved data. Navigation clears old messages, and a
failed check clears prior success. Modified source, another catalog/profile,
and products beyond the 32-row check budget fail closed. This is an owned demo
application adapter, not arbitrary list-form activation or native GUI parity.
