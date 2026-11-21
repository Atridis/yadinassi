# Direct: JSON procedures used as values

Top-level direct calls previously discarded `get_method().returns_value` for
JSON handles. `X=W.WriteStartObject()` therefore mutated the writer instead of
raising; the later independent `WriteJSON(W,1)` then failed on corrupted state.
The exact canonical JSONReader/JSONWriter call-site now checks this metadata
before evaluating supplied arguments, only when the call requires a value.
Statements, supported methods, file policy, source-owned handles, and value
functions keep their existing paths. No VM or legacy fallback is introduced.

The metadata read checks the definition-time receiver/base class ABI and rejects
instance method shadows. Foreign classes are not admitted. This is a restriction
on an existing surface, not a new general JSON security adapter: existing codec
state/file validation and ordinary statement dispatch are unchanged. Captured
canonical HostFunction calls already enforce their procedure metadata; tests
retain that distinction and existing revocation/policy behavior.

Evidence: existing `JSONFamilyTests.test_procedure_semantics_and_private_surface`
and compiled-strict controls establish the local contract. The archived native
JSON31 batch does not directly probe procedure-as-value expressions. Its
historical rejected parity status remains unchanged; current direct replay also
has the pre-existing file cases 23/24 mismatches (on both parent and this tree).
This fix does not claim a fresh native run or complete JSON parity.
