# General plain Python Map: work-in-progress transition

Ordinary direct New Map constructs `PlainMap(dict)`; finite dynamic construction
produces the same storage after existing constructor registration and owner checks.
Insert/Get select the subclass bound __setitem__/get after one exact receiver check.
Rebound host receivers continue through the existing authority resolver. Index
reads use get; foreach consumes insertion-ordered items. No token conversion, value wrapper, private-region admission, or per-operation
authority checker is added. Each subclass operation has one flat exact scalar-key
validation before native hashing, with no nested key helper call.
Legacy interpreter and canonical public BSLMap classes are unchanged.

Intentional/investigated differences, not hidden parity claims:
- bool True and Decimal(1) collide (Python equality), rather than distinct tags;
- non-scalar/opaque keys are explicitly rejected before hashing, not identity keys;
- dictionaries are visible to host callers; TypeOf/FixedMap adapters still need
  migration. Existing FixedMap constructor rejects these raw dictionaries;
- missing index returns None and deletion of absent keys is idempotent;
- opaque host keys cannot run __hash__/__eq__: get/set/index/delete/contains
  validate exact type using identity IDs before native hash. Public update and
  setdefault preserve this domain too. Deliberate `dict.__setitem__(map, ...)`
  base-method bypass by trusted Python host code is outside the storage contract;
- existing owned service constructor profiles have not all switched to dict.

FixedMap copy accepts only the canonical exact source class and exact private
storage shape; arbitrary iterable expansion is not introduced. Its destination
uses Python keys, so formerly rejected UUID/date/descriptor domains may work.
No claim of complete compatibility or readiness. New map-focused tests record
supported simple behavior and two intentional Python-key differences. Existing
compatibility tests stay unchanged and their failures are recorded separately.

The unsafe raw-dict comparison is frozen separately at d6a37725; its demonstrated
opaque-key close/revocation callback is NOT accepted for this successor. Numeric
Decimal, str, bool, int, float and None are the permitted exact key domain. Decimal
NaN/hash/trap errors remain Python behavior; subclasses are not accepted.

Map equality is identity, implemented at the subclass and existing scalar
comparison selection (both operand orders). It must not compare opaque stored
values or invoke a foreign left-hand operand comparison method. These exact
checks are critical callback-boundary regressions, not waived compatibility.
Inherited Python pop/copy/operator APIs are not claimed universally callback-safe;
BSL native-member selection exposes only its explicit supported methods.
