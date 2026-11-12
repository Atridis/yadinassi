# Original demo products in the local editor

The historical `demo_products_v1` profile admitted the original **ВидыНоменклатуры**, **Склады**, and **Номенклатура** catalogs from the exact 19-file editable demo archive. Source bytes are retained unchanged. Older kinds-only, directories-only and inert databases are not migrated or silently expanded.

## Create and open an owned database

From the repository checkout, with the project's Python dependencies installed:

```console
python -m yadinassi --create-demo-db demo.sqlite --import-xml examples/demo
python -m yadinassi --ui --f demo.sqlite --open-browser
```

The destination must not exist. For later sessions, run only the second command.
The current command uses the single `examples/demo` source and its explicit
`main-demo-v1` profile, including documents and reports. The older profile is retained
only for compatibility; it is not a second user-facing demo. It does not seed records, rewrite handlers, or upgrade an
existing database. The Python API `SQLiteCatalogBackend.create_demo_products`
remains available. See the [step-by-step quickstart](demo-quickstart.md).

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

## Deletion marks in the local editor

The **Пометка удаления** checkbox in kinds, warehouses and products edits the
current form draft. **Save changes** persists it through the same write/recovery
path as the other fields. The list displays **Помечен на удаление** for saved
marked records. This is a reversible flag, not physical deletion and not an
implementation of native `SetDeletionMark`/`УстановитьПометкуУдаления`.

The host does not invent an original checkbox OnChange handler. Kind Save runs
the original form validation using the draft mark. Product Save runs both the
original form preparation and mandatory object validation. Their original
marking bypass remains intact: an incomplete product or one referencing a
marked warehouse can be marked; clearing its mark requires valid data. A kind
with an invalid short name can likewise be marked, while unmarking requires
fixing its name. Warehouse autoforms have no original handler to execute.

For local demo scenarios 8 and 12, save a valid product, return to its warehouse
or kind, set the checkbox and save. Reopen the product: ordinary Save refuses
with the original reference diagnostic and leaves the saved card and rows
unchanged. Mark the product and save to exercise the original bypass. Clearing
the product's mark is refused until its references are valid again. Restore the
warehouse/kind mark in its own editor, then reopen the product and clear its
mark. Existing unavailable reference choices remain read-only; no record or row
is silently removed or replaced. The existing 32-row editing limit remains.

Dirty Back is refused; Discard abandons the draft flag. A refused Save retains
the checkbox and other edits. Uncertain commit and refresh recovery retain the
submitted flag and do not replay original handlers or write twice. This local
adapter and its tests do not establish native managed-form parity or completion
of the twelve native demo scenarios.

The opt-in source-bound browser harness is
`node tests/browser_ui/reference_rows_browser_qa.mjs --demo-deletion-marks`.
It declares one scenario covering reference marking/unmarking, original refusal,
product marking bypass, failed unmark/discard, restart, and recovery. It uses the
existing sandbox, source checks, bounded RPC/deadline and artifact rules. Merely
adding this harness does not establish a passed browser run.
