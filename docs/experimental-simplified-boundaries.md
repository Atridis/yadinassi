> Historical research snapshot, not current publication status. Some listed gaps
> were fixed in later experiments. See [current Draft review guide](experimental-naked-review.md)
> and [chronological ledger](experimental-semantic-ledger.md) for current limits.

# Isolated namespace and bind-once experiment

UNSAFE, unpublished, not production-dispatched. Continues the naked experiment,
not a replacement for the VM or proof of a minimal security implementation.

## Restored contracts without reinstating the old dispatch stack

* Source routines have separate immutable generated symbols from BSL variables.
  Assigning `F=7` or `F=Get()` does not replace `F()`. No routine identity registry,
  resolver, or per-call closure is needed for this distinction.
* Invalid static routine arity and using a procedure as a value produce errors
  before argument effects. The compiler knows these facts: valid calls acquire
  no additional dynamic arity guard.
* A named host service is bound before argument evaluation. Re-registration from
  an argument does not change the bound callee. Policy and revocation are still
  checked after arguments; side effects are never retried.
* Dynamic values must be canonical HostFunction objects, not arbitrary Python
  callables authorized by a new identity registry. The wrapper is bound, not a
  snapshot of its mutable implementation field. Variable fallback is secondary
  to a registered named service. Procedure-value rejection precedes arguments.

Source routine entry/exit and pre-argument authority checks remain. Their global
minimality has NOT been established. Member authorization, loop checkpoints,
references, typed keys and other previous experimental repairs also remain.

## Explicit limitations

Dynamic HostFunction reference signatures are rejected before arguments rather
than silently treated as values. InterpreterCall/service-specific protocol
markers, HostFunction subclasses, full VM policy/source provenance/resource
budgets, and general dynamic execution are not established as supported.
Trusted raw host protocols and all earlier BSL operator/collection semantic gaps
still make this unsuitable for untrusted programs or real configurations.

Independent review reproduced a remaining collection-method arity defect:
`a=New Array;a.Get(Host(),Host());` loses the second argument effect in the broad
emitter. This is a known blocker, not a passing integration result. Existing
namespace tests do not cover away that defect. No complete light/heavy suite or
real 1C scenario was run through this experimental backend.

## Evidence

73 focused tests pass on Python 3.12. Tests compare actual Interpreter behavior
for routine/variable namespace separation, static binding, raw-callable rejection
and canonical HostFunction execution; boundary tests cover policy changes,
revocation, private-member denial, no replay and argument-effect ordering.
Error mapping requires Python 3.11+ position metadata and refuses preparation
without it. Python 3.10 execution was not tested.

Frozen paired measurements compare all eight experimental repairs against the
previous isolated registry version, not against production. Seven alternating
pairs across fourteen workloads verify 196 numerical controls. Raw rows and
source hashes are held with the experiment results. Numerical equality is not
security/semantic equivalence. Report per-workload changes and noise; do not
advertise an application-wide speedup.
