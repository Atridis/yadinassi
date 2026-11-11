# Configuration enumeration language block (work in progress)

This block adds configuration enum constants as typed application values,
not strings or invented UUID wire encodings. It is under implementation;
this document is not a claim of native acceptance or released support.

## Integrated outcome

* Closed, bounded XML declarations for enums and their ordered values.
* Application-owned `Enums` / `Перечисления`, per-enum manager, declared values
  and typed empty reference. Case-insensitive RU/EN access, immutable identity.
* Type/TypeOf, bound TypeDescription, metadata lookup and ordered inspection.
* Shared values across common modules in the exact application family;
  independent applications/contexts/generations retain isolation.
* Native observation of manager lookup/order/empty, type and metadata behavior,
  before asserting parity. Presentations and order are measured, not guessed.

## Deliberate boundaries

An enum XML declaration does not grant arbitrary manager module execution,
forms, stored fields, Query comparison, client/server serialization or native
GUID codecs. EnumRef fields must remain rejected by existing field admission
until a separate explicit persistence contract is implemented. No storage
schema version or migration is added by a runtime namespace.

The current database reference block independently admits CatalogRef fields
with its own source profile and version. Neither profile expands the other.

## Verification plan

Local focused suite: source admission (duplicate/malformed/oversize/unknown
nodes), runtime references and family identity, immutable metadata, type
composition, common module use and explicit persistence/codec denial.
Then affected configuration/type/lifecycle suites normal and optimized.
Announce exact collected counts before running them. Publish one coherent
Draft with bounded owned native acquisition, not per-method micro-PRs.
Do not change a candidate already in heavy CI.
