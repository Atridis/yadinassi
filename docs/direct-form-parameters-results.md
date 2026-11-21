# Direct form scalar parameters and results

The form input boundaries now accept the exact native direct Structure in
addition to existing BSL Structure/FixedStructure and the existing host dict
parameter input. They copy only scalar fields. No Mapping/duck-typed object,
mutable nested container or arbitrary host handle is newly admitted.

Parameters retain the existing BSLFixedStructure representation: making them a
mutable native Structure would silently weaken readonly semantics. The narrow
`direct_form_parameters` helper exposes field reads, Property(name), Count(),
and deferred readonly writes only for the current `session._parameters` identity.
A bound method rechecks that identity before invocation. Property with an output
reference remains explicitly unsupported in this first direct seam. These helper
hooks are integrated into FormBoundary by the separate callback/lifecycle slice.

Close-result freezing accepts the exact native Structure and preserves the
existing field/byte/scalar codec restrictions. The frozen bytes detach the result
before the sender can mutate it. `result_value(raw, direct=True)` reconstructs a
fresh native Structure for a direct owner callback; the default remains the
legacy BSLStructure. The application delivery site selects this flag from the
owner interpreter, not the child or ambient backend policy. No execution or VM
dispatch is added to encoding/decoding.

Six focused tests pass, including the actual DraftDetails Created source through
an explicitly installed narrow helper seam, without Interpreter block/call
execution. Tests also verify readonly scalar snapshots, source mutation after
freeze, fresh roundtrip results, replaced-parameter rejection, unsupported nested
containers and hostile type equality. Full owned-form lifecycle integration is
measured separately; this commit alone does not claim that complete workflow.
