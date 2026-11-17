# Direct Array input to StrConcat

Base3c87900e. Preparing the six unchanged native sources on direct succeeds for
strings/dates/numbers/values; collections still requires FixedStructure and
functions requires Goto. Actual direct strings execution failed before its first
observation: line189 passes a New Array (exact Python list) to StrConcat, which
only admitted canonical BSLArray/BSLFixedArray.

The builtin now also admits exact list, preserving delimiter/scalar conversion,
UTF16 reassembly and existing error/host-boundary behavior. Nested direct Array,
Structure and Map elements use their BSL presentation, including when contained
inside canonical/fixed arrays. No container copy, conversion, mutation, arbitrary
iterable admission or legacy dispatch is added. Native list subclasses remain
rejected; canonical array behavior and registered custom overrides remain.

The unchanged strings source advances from0 to372 observations, then stops at a
separate unknown SearchDirection constructor inside Execute. `replay.py` records
this explicit incomplete outcome and hashes; it is not a385-record/native parity
claim. Original source and fixtures are not edited. Other current gaps include
values stopping at407 on unknown UniqueIdentifier in Execute. Dates185/numbers421
completed locally, but their outputs were not established as native-equivalent.

44 selected normalPython3.12 and44 optimizedPython3.10 tests PASS, including
unchanged client138/HTTP40/CatalogQuery24 replays and string/UTF16 boundaries.
Independent40 optimized tests PASS; review has no blockers.

Separately, exact-head native CI run44107865305 for3c87900e passed all jobs,
including six-scenario and required verdict after the evidence-order fix. That
six-scenario runner explicitly uses the legacy interpreter oracle; its green
result must not be presented as full direct-backend parity.
