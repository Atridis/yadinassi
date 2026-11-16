# Direct configured startup: narrow common-module slice

The `python-direct` configuration path prepares declaration factories for the
application module and enabled common modules. The metadata interpreter objects
remain owners of existing registries, family lifetime and host bindings; they do
not execute AST bodies. Each invocation creates a new generated closure family
and boundary context. Client/server module storage is not silently shared.

This slice runs the canonical main-demo startup: application event →
`DemoTools.InfoText()` → explicit `DemoService.ApplicationTitle()` transport →
generated server function. The existing InvocationPort performs one packet
exchange and retains scalar encoding, endpoint, sequencing and no-retry rules.
No source text or Python function is sent over that transport.

Before binding a common call and again before invoking it, the adapter checks
application/family lifetime, current module-side resolution and existing call
policy. Only a registered module's exported routine is callable. Host services
use the existing configuration host-service policy before argument evaluation
and immediately before the effect. Arbitrary object members remain denied.
Transactions are disabled during these invocations and the previous flag and
context stacks are restored on all exits. The normal legacy branch is unchanged.

## Explicit limits

This is not general configuration-runtime parity. Session initialization,
reusable common-module caching, async/dual routines, DB-backed configuration,
active restricted/transaction/scheduler contexts, public common-module byref
arguments and implicit same-process cross-side execution remain unsupported.
Cross-side calls require the existing explicit transport binding. General
application command execution, global common exports and platform-object APIs
are not supplied by this adapter. Source errors use existing generated mappings;
application source-line text may be unavailable when only admitted AST was given.
The optional checkpoints are generated call/service/loop boundaries, not the
legacy AST-node execution metric. Registered host implementations remain trusted.

## Verification

`test_python_direct_configuration` plus `test_main_demo_lifecycle`: 11 tests pass
under normal Python and `-O`. The exact demo test patches `execute_program`,
`block`, `_visit`, and `call_routine` to fail: both application sides still start,
produce the expected message, and exchange exactly one packet. Independent cases
cover closed family, unavailable side, unknown receiver, current host-service
policy (including shutdown after a service), transaction no-effects/cleanup and
restricted-context refusal. Host registrations are read live when a service is
bound; argument effects do not reselect an already-bound callee.
