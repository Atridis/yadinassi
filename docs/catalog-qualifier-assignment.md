# Catalog metadata qualifier assignment

This bounded profile converts values when assigning Code, Description, scalar
owner attributes and scalar tabular-row attributes. Reading the detached object
immediately returns the converted value, before `Write()`. Persistence still
requires an explicit successful write.

## Conversion and evidence

The [1C:Enterprise 8.3.27 Developer Guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293), section 4.7.10 (type conversion when
assigning infobase object attributes), describes right truncation of strings,
fraction rounding according to the configured rounding mode, integer overflow
saturation with nines, and negative-to-zero conversion for nonnegative numbers.
The repository's separate TypeDescription and ValueTable native observations
support the half-up checkpoint and UTF-16 unit counting. For example, the
Number(5,2) checkpoint maps `1.245` to `1.25` and `-1.245` to `-1.25`, while
Variable(3) maps `Я😀AB` to `Я😀`.

Those observations do **not** independently prove CatalogObject assignment or
tabular-section `Write()` behavior. This implementation applies the documented
conversion model with the existing measured half-up numeric checkpoint. It does
not claim other rounding modes, regional settings, event/module execution or
complete native catalog parity. Native observation files are unchanged.

- String values are exact Python/BSL strings, right-truncated by UTF-16 units.
  This is Variable length only; there is no padding or new Fixed-string support.
- Numbers are exact finite Decimal values, rounded symmetrically half away from
  zero at the declared scale. Overflow saturates at the declared maximum with
  the original sign; negative Nonnegative values become zero. No float or text
  conversion is admitted. Arithmetic is independent of ambient Decimal context.
- Boolean, whole-second DateTime and declared same-database CatalogRef retain
  their existing validation. There are no new types or coercions.
- The XML importer still refuses zero-length scalar String metadata. The
  programmatic backend's existing length-zero bound means empty-only, not a new
  unlimited-string mode. A zero-length Description likewise becomes empty.

## Explicit representation and resource boundaries

UTF-16 truncation can split a supplementary character. For example, limiting
`Я😀Z` to two units would leave an unpaired surrogate. The native TypeDescription
checkpoint can represent that result; this backend's strict UTF-8 storage cannot.
The assignment therefore refuses before changing the value. It never substitutes
U+FFFD, drops another character, or silently shortens to a different boundary.
Malformed Unicode anywhere in the input, including a discarded suffix, refuses.

Each input String is capped at 65,536 Python characters before conversion. The
Decimal coefficient must fit the existing 2,048-byte CPython allocation bound
before `as_tuple()` or rounding. Unsupported allocation accounting refuses.
Huge positive/negative numeric exponents are compared or rounded without
expansion proportional to the exponent. These are local budgets, not native
1C limits. Existing row-count, section-buffer, canonical-payload and transaction
budgets remain in force. A failed conversion or section-buffer budget check does
not change row bytes, dirty flags, owner revision or pending write identity.

## Backend writes and strict reads

Direct backend callers receive the same conversion as runtime assignments.
Create/update normalize a fresh owner draft and encode rows incrementally before
any SQL mutation. Caller-owned frozen draft/row objects are unchanged. All scalar
and reference validation completes before owner/row replacement. Code uniqueness
is checked on the converted code, so two distinct long inputs can conflict.

An unknown commit outcome freezes the write buffer. Optimistic revisions,
atomic owner/section rollback and significant row order are unchanged. SQL
mutations and staged revisions share one savepoint; allocation failures,
interruptions and RELEASE failures restore both. Failed physical cleanup
poisons the transaction and blocks further commit. Read the current row with a
fresh object instead of resubmitting the frozen write.

The persisted-data codec does **not** normalize. Out-of-range, noncanonical,
wrong-type and invalid-Unicode stored values still fail. String validation now
counts UTF-16 units rather than Python code points, so a legacy stored value that
only fit the old code-point check fails closed; opening does not rewrite it.
No migration or repair is silently performed. The project's pre-public-release
internal storage is not a public compatibility contract.
The offline v1-to-v2 migration applies the same strict Code/Description validation
before dropping source records or committing. Legacy supplementary-character
values outside the UTF-16 bound abort and roll back migration rather than
truncating source values.

`!todo`: acquire source-reviewed native CatalogObject and tabular-section
assignment/Write observations for rounding ties, overflow, negative sign,
UTF-16 boundaries, duplicate normalized codes and failure state before claiming
direct parity. Do not reinterpret the TypeDescription/ValueTable observations
as that missing measurement.
