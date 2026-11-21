# Direct FillPropertyValues: structure storage

The direct backend now adapts its own Structure storage to the existing pure
structure traversal algorithm. This does not invoke an interpreter or translate
values into legacy runtime objects.

## Contract

- Exact direct Structure and canonical Structure/FixedStructure endpoints are
  supported in any pairing. Raw storage shape is checked without receiver or
  payload protocol calls. Nested values are shared, not cloned.
- Target spelling, composition, aliases and enumeration version are preserved.
- INCLUDE validates tokens lazily: earlier writes survive a later invalid or
  missing field. Windows traverses left-to-right; the measured Linux target
  traverses right-to-left, skips raw empty tokens and trims ASCII spaces.
- EXCLUDE retains its existing upfront validation and measured Linux mutable
  source-only missing-field partial-write order. Fixed targets retain the
  existing no-op/no-list contract.
- Only the registered canonical function identity is adapted. Custom functions
  remain custom. Optional omissions, procedure checks, lifetime and policy
  checks are retained; implementation rebinding during argument evaluation or
  policy callbacks is rejected before writes.

A call involving direct storage never enters object/row/database adapters.
Calls containing no direct storage retain the previously registered canonical
host contract, including its existing bounded object/row adapters. This preserves
an existing capability, rather than granting new endpoint families.

## Evidence and limits

`test_python_direct_fill_structure` compares 176 combinations with the
compiled-strict semantic oracle and replays the pinned native INCLUDE and
EXCLUDE observations (13 each). These are historical native checkpoints, not a
fresh native run or proof of unrestricted endpoint support. The existing
`test_native_target_fill` also exercises its 72-case absence/order matrix per
target. Its spelling assertion now uses BSL enumeration rather than assuming
that Python iteration exposes the same representation in both backends.

Mixed direct Structure and database/row/foreign endpoints remain unsupported.
Full historical collection replay has independent gaps; this slice does not
claim to fix them or make the full light CI green.
