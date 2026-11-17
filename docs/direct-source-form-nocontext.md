# Bounded direct source-form NoContext

Source forms can call declared synchronous NoContext routines with required Val
scalar arguments. Client calls retain the existing InvocationPort/InvocationServer
wire protocol, sequence and no-replay behavior. Same-server calls use a separate
formless invocation, not a fabricated client context or a second form activation.
The result must pass the same scalar codec on both paths.

Original declarations remain marked NoContext and their current signatures and
bindings are checked. They are removed from contextual generated handler plans,
so lexical calls cannot inherit a form's closure or attributes. An isolated private
compiler view generates the NoContext closure; each invocation gets an empty state
and a fresh boundary. No interpreter routine dispatch or AST evaluator is used.

The formless boundary exposes source metadata and its explicitly admitted services,
not a form session, Parameters, ThisObject, Items, attributes, bound UI callbacks
or contextful common modules. Unsupported capabilities fail during invocation,
without preventing a valid form from opening. There is no database activation:
transaction admission remains disabled and existing source/safe-mode scopes apply.

Direct checkpoints enforce the existing 100,000-step invocation budget, including
loop backedges and nested routines. Success and failure restore side/module stacks,
message routing and busy state. Host registrations, prototype identity, live
signatures and port bindings cannot be silently retargeted into another grant.

Tests replay existing source NoContext cases with legacy dispatch poisoned for the
whole test. They cover client and same-server isolation, scalar attribute inputs,
non-scalar result rejection, bounded loops, repeated failures, signature/host-hook
tampering and scope cleanup. This is a bounded source-host implementation, not a
native form RPC or general NoContext parity claim.
