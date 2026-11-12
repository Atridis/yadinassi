# Configuration enumeration language block (work in progress)

This block adds configuration enum constants as typed application values,
not strings or invented UUID wire encodings. It is under implementation;
native acquisition and exact sixteen-case replay are now verified, but this
document is not a claim of released or unrestricted configuration support.

## Integrated outcome

* Closed, bounded XML declarations for enums and their ordered values.
* Application-owned `Enums` / `Перечисления`, per-enum manager, declared values
  and typed empty reference. Case-insensitive RU/EN access, immutable identity.
* Type/TypeOf, bound TypeDescription, metadata lookup and ordered inspection.
  Singleton `EnumRef.Name` / `ПеречислениеСсылка.Name` description strings resolve
  in the active application, for both static and dynamic construction. They
  retain the same closed qualifier/union restrictions as arrays of bound types.
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

## Authored full-envelope admission

The local application importer also recognizes a closed declarative envelope
with exactly the Ref/Manager/List generated identities. All six identities are
validated and checked against other metadata identities, but are not used as
native serialized type IDs. Source bytes remain canonical and unchanged.
The current envelope permits only the owned empty-form/default-command profile;
nonempty forms, custom commands, characteristics, manager modules and unknown
properties remain rejected. Optional empty StandardAttributes is not a grant
for behavioral standard-attribute settings. The original acquisition fixture was accepted in native run 43035110558.
This does not admit arbitrary regenerated defaults or behavioral settings.

## Measured Russian presentation profile

The manager string is `ПеречислениеМенеджер.Name`; its Type string is
`Перечисление менеджер: Name`. Metadata FullName is `Перечисление.Name`.
Empty references stringify to the empty string and are not filled. In the
measured Russian UI profile, a value without a Russian synonym presents its
name even when an English synonym exists. Russian synonyms and other UI
languages remain explicitly unsupported, rather than silently guessed.
Reference Type presentation, persistence, Query and native GUID codecs remain
outside the acquired sixteen-case contract. See the owned measurement plan
for immutable run and output provenance.
