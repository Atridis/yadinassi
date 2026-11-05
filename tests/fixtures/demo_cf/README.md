# Demo configuration: MVP acceptance target

`original.zip` preserves the user-supplied `demo_cf.zip` byte for byte.
Publication of the demo in this public repository was explicitly authorized by
the owner on 2026-11-05. The archive has been inspected as data: it contains a
synthetic configuration, no catalog records, credentials or observed personal
data. The bundled `validate_dump.py` has not been executed by this workflow.

SHA-256: `a2ee9c12d9a91000b282ce3ed5c9ec3936e38bdcb4d57ac4ee11871aa9c6799f`.
Size: 33,250 bytes. Inventory: 40 ZIP entries, 21 text files, including 15 XML,
four BSL, the original README and its unexecuted validator.

## Working copy

From the repository root, with an owned existing output parent:

```sh
python scripts/demo_cf_fixture.py /path/to/new/demo_cf
```

The helper verifies the whole pinned archive and every manifest entry before
writing. It copies only the 15 XML and four BSL files; it never evaluates BSL,
imports the bundled Python script or starts 1C. An existing destination refuses.
Keep the output parent private from concurrent modification. A failed write may
leave an incomplete destination; do not use it for validation.

The archive stores UTF-8 filename bytes without the ZIP UTF-8 flag. The helper
decodes them explicitly, checks paths and normalizes filenames to NFC. The only
NFC change is `Languages/Русский.xml` to `Languages/Русский.xml`, matching metadata.
File contents are unchanged. `manifest.json` records original decoded names,
normalized relative paths, lengths and hashes, including omitted entries.
The working copy is generated, not committed a second time.

## Evidence boundary

This is a manually prepared hierarchical Designer XML configuration, format 2.8,
compatibility 8.3.14. Its README requires actual 1C load and compilation checks.
Well-formed XML and fixture tests do not establish native acceptance or runtime
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
