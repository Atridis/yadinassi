# Detached query table protocol

Base e242b35c96af838fa9f1e9eb28571dd1fdbc617d. Native run44098520311,
CatalogQuery job134093310629 accepted24 native observations, but its interpreter
output was empty (summary artifact14335746063). Replaying the unchanged owned
SQLite model failed at generated/observe.bsl:33: `T.Count()` after `R.Unload()`
was rejected by CatalogBoundary._catalog_owner.

The direct bridge now accepts exact ValueTable, row, column and column-collection
public protocols, plus exact TypeDescription and qualifier descriptors. Table
children must have an exact canonical table owner. No subclass, Python attribute,
backend or iterator access was added. Detached tables confer no database authority:
objects extracted from cells still pass current catalog ownership checks. Existing
methods enforce deleted/foreign rows, schema/value coercion and bounded slice
restrictions; boundary checks still run before and after operations. No VM dispatch,
constructor expansion or persistence/schema gate change is included.

`replay.py` runs the original source-bound logical-model replay and compares exact
wire bytes by SHA256 to accepted native artifact14334693411 (513 bytes,24 records).
It does not rerun1C or claim Designer XML import parity. The fixture is unchanged.
ValueTable constructors, indexes and iteration remain separate unsupported areas
of this direct bridge; this slice connects the result protocol needed by Unload.

Validation:116 selected tests PASS on Python3.12 normal and Python3.10 `-O`,
including exact CatalogQuery replay, whole-client native verifier, database owner
checks, form ownership, server/byref and regex lifecycle regressions.
