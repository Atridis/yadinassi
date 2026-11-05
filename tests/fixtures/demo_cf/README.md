# Demo configuration: MVP acceptance target

The editable Designer source is in `source/`: 15 XML and four BSL files.
It preserves the supplied demo content byte for byte. Filenames use UTF-8 and
NFC; `Languages/Русский.xml` matches the metadata name. No archive or extraction
helper is needed. The supplied validator is not included or executed.

Publication was explicitly authorized by the owner on 2026-11-05. The demo
contains a synthetic configuration, not catalog records or observed secrets
or personal data.

## Evidence boundary

This is a manually prepared hierarchical Designer XML configuration, format 2.8,
compatibility 8.3.14. Its README requires actual 1C load and compilation checks.
Well-formed XML and source structure tests do not establish native acceptance or runtime
compatibility. This change does not activate the configuration, execute its
modules, alter importer policy or extend an existing native CI profile.

The three catalogs are ВидыНоменклатуры, Склады and Номенклатура. Номенклатура
has a kind reference and warehouse-reference tabular section. Three custom
managed forms and four BSL modules define the business behavior. Warehouses are
allowed storage locations, not quantities or balances. Names need not be unique;
codes are automatically numbered with uniqueness control. There are no seed data.

## Twelve acceptance scenarios from the supplied README

1. Create kind «Товары» and warehouses «Основной склад», «Резервный склад».
2. Create «Кабель USB-C», select the kind and both warehouses. Save succeeds and
   assigns a code automatically.
3. Kind name «  » or «АБ»: form save refuses. This rule is form-only; the demo
   does not validate programmatic writes of kinds.
4. Clear the product kind: show a hint and refuse save.
5. Remove all warehouse rows: refuse save.
6. Add an empty row: report the corresponding row/field error.
7. Select the same warehouse twice: show a hint and refuse save.
8. Mark the referenced warehouse or kind for deletion, then save the product:
   refuse and explain which reference must be replaced.
9. Save «  Кабель USB-C  »: persist «Кабель USB-C».
10. Run «Проверить карточку» without selection and for a valid selected card:
    request selection / report success. The command is read-only and checks saved
    data, not unsaved changes in another form.
11. Programmatically write a product without kind and warehouses: its object
    module sets cancellation and no object is persisted.
12. Mark the card for deletion after its warehouse is marked: marking remains
    possible, but unmarking requires fixing the card.

For each save/refusal verify durable state after reopening. Rejected writes must
preserve the editable buffer and not partially change saved rows. The final MVP
must execute the supplied logic, including programmatic write validation, rather
than substitute equivalent-looking JavaScript rules.

## Next native gate (separate reviewed change)

Prepare a source-bound Designer-only profile: fresh isolated owned database,
LoadConfigFromFiles, supported-version CheckConfig, UpdateDBCfg, hierarchical
DumpConfigToFiles and bounded source/metadata comparison. Preserve existing
isolation, timeouts and cleanup. Do not inject this fixture into another suite's
closed input inventory, publish raw native diagnostics, or run ENTERPRISE here.
Actual GUI/BSL scenarios require separate execution and evidence after that gate.
