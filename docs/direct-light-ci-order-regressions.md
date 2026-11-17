# Light CI: compatibility gaps and two order-dependent failures

PR #337 run 44179595450, head c6724a2f, tested merge
367a470607ce78d8f4082f820eb20f91d872efd4, genuinely failed Linux light.
Its artifact selects 11,884 of 16,111 discovered tests, with 3,155 unknown IDs.
11,850 tests started; three failing class fixtures account for 34 uncovered IDs.
The report records 1,830 errors and 305 failures. An unmodified local light run
on that exact merge reproduced all counts and identical discovered, selected
and covered ID lists. This is not a green compatibility gate or a runner-only
problem. Switching the whole suite to legacy would hide the transition gaps.

Examples include imports, native list versus legacy `.items` expectations,
unadmitted database receivers, unsupported constructors and contexts. The
accumulation period representative fails before query assertions at
`O.RegisterRecords.OwnedAccumulationRows` on direct, but passes with explicit
compiled-strict. These require separate compatibility/ownership work.

## Ordinary copying versus sealed XML classes

`test_dom_family` invokes ordinary `copy.copy` of XML readers/settings and
`deepcopy` of writer settings. Python's copyreg lazily creates class
`__slotnames__` metadata, after the source XDTO/XML ABI has been captured.
Subsequent strict admission correctly notices changed class dictionaries, but
this bookkeeping was caused by an ordinary supported operation, not new hooks.
The complete light run had 140 `source XDTO class hooks changed` errors.

Reader, writer and both settings classes now declare their empty copy metadata
before definition-time ABI snapshots. These classes/bases have no instance
slots. Existing identity/field/MRO checks remain; new guards also reject any
in-place change to these exact empty lists. Replacement, deletion, extra class
hooks and modified copy metadata are still denied. No successful admission is
cached, and no receiver becomes detached or gains IO authority.

A same-process cohort on the pre-fix 33a0fc61 tree, beginning with DOM tests and
then source XDTO/JSON/XML suites, ran 231 tests with 178 errors. After the fix,
the same 231 tests have only the two pre-existing unsupported DOM constructor
errors; no new failing identities appeared. This is not a claim that all light
failures are resolved. New tests explicitly cover copy, deepcopy, DOM failure
followed by XDTO admission, and hostile mutation of the copy metadata.

## Inherited allocator monkeypatch isolation

The source-reuse security test temporarily patches `ReusableValueCache.__new__`.
Removing the attribute does not restore CPython's inherited allocation slot;
later constructors with keyword arguments fail in `object.__new__`. This caused
22 subsequent cache errors in the complete run. The adversarial allocator
check now executes in an isolated subprocess with the same optimization mode.
Its rejection-before-effects assertions remain unchanged, and the parent
verifies its constructor still works. No production ownership check is removed.
