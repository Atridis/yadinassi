# Direct source common resources and TextDocument

The source host admits its exact owned GetCommonTemplate marker before argument
effects and revalidates owner, binding, canonical hooks and factories at invocation.
Standalone interpreters reject source markers, including captured HostFunction
values, rather than evaluating their arguments first. This is not an ambient
resource or filesystem capability.

The existing lazy resource loader remains authoritative: declared metadata only,
text/binary kinds, encoding checks, per-resource/count/aggregate byte bounds and
fresh returned values. Cache inventory and accounting are validated. Missing,
undeclared, malformed and over-budget resources keep their original failures.

Source execution and source forms support the exact TextDocument constructor and
its finite bilingual methods. Text/span/UTF-16-unit invariants and canonical
class/instance hooks are checked; captured methods retain the same checks and
arity/return contract. BinaryData gains only Size in this source adapter. Private
members and other binary operations are not exposed through a generic object path.

TextDocument Read/Write still use the original bounded file_io implementation,
encoding validation and safe-mode effect guard. No path permission, cross-context
resource transport or native platform capability is added. Constructor availability
is source-only; the standalone direct constructor inventory is unchanged.

The existing common-template native observations and nested source modules replay
under lifetime VM-dispatch poison. Additional tests cover fresh resource values,
saved methods, bilingual text construction, form safe-mode file denial, foreign
markers, owner-pointer/inventory changes and factory-hook tampering. Text invariant
validation deliberately recomputes spans and units for correctness with mutable
host-visible fields; this slice makes no performance improvement claim.
