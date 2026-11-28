# Existing order workbench

Open an existing database using the sibling `order-intake/configuration` schema:

```sh
python -m yadinassi.ui.form_app examples/forms/order-editor --f orders.sqlite --open-browser
```

Select a result, open its complete header and lines, edit and Save changes. Save
updates that same record and leaves it editable. Discard / Reload abandons local
edits, including invalid raw decimal input. Known conflicts preserve your draft;
an unknown save outcome locks editing. Discard / Reload reads the current
record without repeating the write. After a confirmed save, a failed refresh
can only be repeated as a read. Lost transport never reconnects or replays.

See [the full workflow, limits and recovery guide](../../../docs/order-workbench.md).
This is host-functional application infrastructure, not native 1C parity evidence.
