# Typed table snapshots and Deflation

This block makes `ХранилищеЗначения / ValueStorage` useful for ordinary typed
table results and compressed local caches. It extends the existing immutable,
bounded snapshot traversal; it is not a second BSL interpreter, a database
field format, a transport codec or an implementation of 1C's physical storage.

## Public contract

```bsl
Compression = New Deflation(9);
Saved = New ValueStorage(Value, Compression);
Copy = Saved.Get();
```

The documented English name of `СжатиеДанных` is **Deflation**, not
DataCompression. The optional constructor argument is an integer Number from
−1 to 9. Omission means −1 (default compression); 0 means no compression and 9
means maximum compression. There are no public properties or methods. The
settings object and its type are available through `Type`/`TypeOf`, but object
and type string presentation, serialization and storing the settings themselves
remain unsupported.

`ValueStorage(Value, [DataCompressionAlgorithm])` still requires a value. Its
second argument is either omitted/Undefined or an exact Deflation object;
omission means **no compression**, unlike constructing default Deflation.
An omitted second positional slot is admitted, but the first slot remains
required. Dynamic New uses the same constructors. Explicit Undefined for the
Deflation degree is treated like omission as a local optional-argument policy.
Fractional numbers, Boolean/string coercion and out-of-range levels are rejected.

Every Get creates independent mutable objects. Source mutation after capture,
or mutation of one Get result, cannot change another result. Existing cycle
rejection and copying shared children separately per occurrence remain in force.
Compression does not make an otherwise unsupported object storable.

## Typed ValueTable profile

Ordinary supported scalar column TypeDescriptions, their number/string/date
qualifiers, column names/order/title/width and ordered index definitions are
retained. Get builds fresh columns and rows, then rebuilds index caches from
validated definitions. It never copies source owner pointers or cached buckets.
Nested tables use the same global snapshot budgets as their parent values.
The existing table limits remain 64 columns, 1,024 rows and 4,096 cells. Index
definitions add local limits of 64 definitions, 256 total positions (an empty
definition counts one) and 16,384 row-by-position work. Titles share the
1,000,000 UTF-16 text budget; width is a bounded unsigned 32-bit integer.

The implementation preserves the existing supported nullable query-result
descriptor profile without broadening its conversion/default rules. UUID typed
cells, catalog/document references, arbitrary host types and malformed owner
graphs remain unsupported. Existing table cell coercion, query restrictions and
index key admission are not changed by storage.

Preserving title/width, qualifiers and index definitions is a deliberate local
snapshot policy. Official documentation says ValueTable is serializable and
documents those properties, but does not specify their individual storage
round-trip behavior. No new native parity is claimed for these details.

## Compression and resource integrity

Nonzero levels compress string and BinaryData payload leaves with the host zlib
implementation. The private immutable tuple graph and its existing validation
remain in place. Scalar numbers, dates and schema framing do not acquire a new
wire representation. −1 is passed to zlib's default; no fixed mapping to a
particular platform algorithm/level or byte-identical output is claimed.
Small/incompressible payloads can grow, so compression is not a size guarantee.

Capture always admits and charges the uncompressed logical content first.
Every Get again enforces the existing depth, occurrence, text, binary and number
budgets. A compressed leaf declares its expected byte length; restoration bounds
that length against the remaining logical budget **before** decompression and
also caps actual output. Truncated, concatenated, trailing or malformed streams
are rejected, as are invalid UTF-8 text payloads. UTF-8 surrogatepass preserves
the existing exact string model, including isolated UTF-16 surrogate values.

An additional aggregate compressed-byte bound allows the existing 16 MiB binary
budget, at most three bytes per allowed UTF-16 text unit and conservative per-node
deflate framing overhead. No logical cap is raised. Compression/restore errors
are catchable through ordinary BSL exception handling and publish no partial
result. Snapshots remain private in-process state; Get validation does not imply
that arbitrary bytes from external sources are an admitted import format.

## Evidence

The existing immutable native27 fixture remains unchanged. Case 17 observes one
untyped table cell's independent capture/Get behavior. Case 18 observes
`Новый СжатиеДанных(0)` with storage/Get of the number 1. The complete 27-case
historical capture can now be replayed without substituting a local expected
error for case 18. Replay is not a fresh native run. The established continuous
native value-storage-v1 profile still contains its original 26 cases and is not
rewritten or relabeled to cover compression or typed schema metadata.

Official EDT 2026.2 archive:
https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar
SHA-256: `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
Matching RU/EN members under `nl/{ru,en}/html/SyntaxHelperContext/objects/`:

- `catalog63/Deflation.html` and `Deflation/ctors/ctor36.html`.
- `catalog63/ValueStorage.html`, `ValueStorage/ctors/ctor1.html` and
  `ValueStorage/methods/Get589.html`.
- `catalog234/catalog236/ValueTable.html`.
- `catalog234/catalog236/ValueTableColumnCollection/methods/Add575.html`.
- `catalog234/catalog236/ValueTableColumn/properties/ValueType1027.html`,
  `Title1028.html`, `Width1029.html`.
- `catalog234/catalog236/ValueTable/properties/Indexes4720.html` and
  `CollectionIndexes/methods/Add2380.html`.

Full platform serialization, arbitrary configuration types, cross-context
transfer, exact compression ratios/bytes, concurrent source mutation and native
metadata/index retention calibration remain out of scope.
