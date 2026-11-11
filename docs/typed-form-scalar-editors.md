# Typed scalar editors for declared forms

This local UI block exposes existing trusted scalar qualifiers in ordinary form
fields and table columns. It does not add BSL types, change assignment semantics,
extend generic Invocation, convert a source profile, or change a stored schema.
The runtime remains authoritative after each ordinary OnChange and server call.

## Exact input, not browser coercion

- DateTime: `YYYY-MM-DDTHH:mm:ss`; Date: `YYYY-MM-DD`; Time: `HH:mm:ss`.
  Input is an exact text grammar, independent of browser timezone and locale.
  Gregorian calendar validation and tick arithmetic use integers, not JS Date.
- Blank date input writes the existing typed empty Date (`ticks=0`). Midnight
  Time and `0001-01-01` share this same runtime identity, not a separate null flag.
- Editing is restricted to whole seconds in the conservative private form
  envelope ending at `9999-12-31T23:59:58`. Existing fractional or upper-bound
  table values stay visible without rounding and remain read-only.
- Number/String input checks the trusted qualifier before sending. Overlong
  UTF-16 strings, negative Nonnegative values, magnitude overflow and nonzero
  fractional digits beyond scale are refused rather than silently truncated,
  clamped or rounded. `1.2300` fits scale 2; digits/length zero mean unqualified.
  Short Fixed strings may be padded by the existing server assignment.

This loss-prevention policy belongs to the local editor. It is not a claim that
native 1C input masks use the same grammar or rejection rules. Direct BSL
assignment retains its existing native-backed normalization and limits.

## Draft and ownership rules

An invalid raw draft blocks subsequent commands, selection and reference choice.
It is retained for correction instead of being sent as an empty/default value.
Drafts bind to the control, value and editor metadata that produced them; table
drafts also bind to table and row identities. An incompatible authoritative
update moves raw text to copy-only recovery, not to another field or row. A lost
mutation reply is never an invitation to replay it. Explicit refresh/discard is
separate from ordinary close, which still runs the authored close handlers.

## Authored configuration example

`examples/configuration-scalar-editors` uses the existing explicit reference
application profile, including its fresh-v7-only admission. Products have an
editable AvailableDate. Orders have an editable standard Date and a DeliveryDate
in each line, alongside existing typed reference, Number, String and Boolean
values. The source must remain unchanged after creation.

```sh
python - <<'PYTHON'
from pathlib import Path
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
root = Path('examples/configuration-scalar-editors')
files = {p.relative_to(root).as_posix(): p.read_bytes()
         for p in root.rglob('*') if p.is_file()}
SQLiteCatalogBackend.create_reference_application('scalar-editors.sqlite', files).close()
PYTHON
python -m yadinassi.ui.configuration_app examples/configuration-scalar-editors --reference-application --f scalar-editors.sqlite
```

Create a product and enter its AvailableDate. Create an order, set its date/time,
add a line, set DeliveryDate and Quantity, then write. Reopen the saved records
to inspect the exact stored values. Invalid dates, negative Quantity and a Note
longer than its declared limit should remain editable drafts, not stored data.

Stored XML schemas still admit DateTime only. Date/Time qualifiers are supported
only where the existing pure-form TypeDescription already admits them. No
posting, migration, transaction authority or native FormWrite parity is added.

## Validation status

Implementation is in progress in a separate branch. The first 17 Python
projection/event checks passed; expanded identity, frontend and real-browser
acceptance are pending. No full CI or completed acceptance is claimed here.
