# Original mini-demo acceptance contract

The one current configuration source is `examples/demo`. It preserves the
original catalog/form/handler bytes and extends the source with inventory
objects. The original nineteen-file envelope is not a second demo directory:
compatibility tests reconstruct it from eighteen canonical files plus the
4,199-byte historical root in `tests/fixtures/legacy_demo_root.xml`, checked
against the original nineteen SHA-256 pins.

Publication of the supplied synthetic configuration was explicitly authorized
by the owner on 2026-11-05. It contains no catalog records or observed secrets
or personal data. The supplied validator is neither included nor executed.

XML structure tests do not establish native acceptance. Current main-demo
Designer acceptance is source-bound load/check/update only; the old historical
redump workflow is retired. Historical comparison tooling remains offline.

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
