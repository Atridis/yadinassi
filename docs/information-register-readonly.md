# Bounded independent InformationRegister reading

The read-only offline path adds one end-to-end workflow: a nonperiodic,
independent register keyed by a fixed catalog reference and an integral Number
can be read with `InformationRegisters.<name>.Get(key)` or selected with
`Select()` / `Select(referenceFilter, "Desc")`, then traversed with `Next()`.
The reference dimension dereferences through the existing named Catalog manager.
Russian namespace/method aliases are provided. No native session is opened.

## Evidence and scope

Native run **41353896285** observed two independently named configurations,
reordered dimensions/resources, empty and three-record states, server and thick
client: 32 blocks of 24 observations. The source-bound original report stays
private. Minimal regression fixtures retain only needed generated CONFIG, table
bytes, BSL programs, outputs and source/report hashes; no installation, audit,
authentication or session material is included.

The admitted CONFIG profile has exactly two dimensions (one fixed CatalogRef and
Number9.0), three resources (Number9.2, Boolean, DateTime), and one String32
attribute. Names and identities come from the complete bounded CONFIG snapshot,
not fixture literals. Generated manager/selection type UUIDs are distinct from
metadata UUIDs and record/reference UUIDs. Fixed references resolve only through
the same complete Catalog identity map. Both observed field orders are supported;
this is not arbitrary register/schema support.

The ordinary scenario exposes:

- `Get(Structure)` requires the complete dimension key, regardless of property
  order. It returns a fresh mutable Structure containing **only resources**.
  An absent key returns Number0, False and the empty date, not Undefined.
- `Select()` follows the measured composite dimension ordering; the reference
  component uses its stored binary key, not UUID text or insertion/slot order.
  Filtering supports the one indexed fixed-reference dimension. Numeric keys
  are nonnegative integral values within the admitted Number9 precision.
- Before the first successful `Next()`, fields are Undefined. Exhaustion returns
  False and retains the final row; subsequent `Next()` stays False, unlike the
  previously measured Catalog cursor restart.
- Selection fields include dimensions, resources and the attribute. Reference
  values retain their Catalog type/snapshot and support existing target reading.
- `TypeOf` and bounded named manager/selection `Type` lookup use snapshot-scoped
  dynamic descriptors. Cross-snapshot keys are refused. Dynamic construction,
  internal codecs and TypeDescription consumers of these service types remain
  explicitly unsupported rather than exposing Python objects.

## Storage and integrity

The six-field table is independently compiled from CONFIG roles and DBNames.
The measured InfoRg rows are 101 bytes, without a document/catalog record UUID.
Empty data and reserved-plus-active records are supported within existing reader
budgets. Duplicate composite keys, declaration drift, ambiguous DBNames aliases,
missing Catalog targets and unknown layouts fail closed before partial results.
The auxiliary `ByDims` identity observed beside a dimension `Fld` is not mistaken
for a second value field. All reads share the existing bounded CONFIG/PARAMS/row
ownership graph; a caller must supply a consistent offline copy.

No register writes, RecordSet/RecordManager, query runtime, slices, periodic or
recorder-bound modes are implemented. Negative/fractional key normalization,
other filter/order forms, composite fields, free-list/deleted-slot profiles and
broader metadata service APIs remain deferred (`!todo` beside relevant paths).

Local verification includes native-program replay on explicitly synthetic
transport with all five **actual captured** CONFIG descriptors, record/mutation
and API/type guards, plus retained Catalog/Document/Items checks. This is not a
claim that synthetic transport is a native `.1CD` cursor. Final source-composed
actual frozen-`.1CD` parity and CI remain required before acceptance.
