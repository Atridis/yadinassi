# Direct configuration commands: bounded scalar lane

`ConfigurationApplication.execute` has a separate direct command runner. It does
not relax `python_direct._admit_vm`, the common-module `DontUse` admission guard,
or dispatch through an older interpreter. The configuration startup adapter and
its explicit transport remain separate capabilities.

## Supported shape

An already-running exact configuration application, with synchronous client-only
common modules, no database, session module/parameters, reusable result cache,
global modules or server transport. All registered routines have explicit
`Val` parameters with optional immutable scalar literal defaults. Commands can assign scalar root variables,
evaluate scalar expressions, handle ordinary errors with nested Try/Except,
raise or rethrow them, call named exported module routines and report
results using canonical `Message`/`Сообщить`. Arguments and results are limited
to exact `None`, `bool`, `str` and `Decimal`; collections and host objects cannot
cross a public command boundary.

Private scalar helpers and repeated nested same-side module calls use existing
generated routine closures. A task-local scope follows those calls and every
host-service boundary. It checks the original application, module bindings,
interpreter family/generation, prepared plans, declaration registries and current
client-side eligibility. Each boundary pins its originating command scope.
The scope is bound to its creating thread and exact ContextVar context, including
rejection of copied contexts; a saved boundary cannot shed restrictions after
scope exit. Token rotation validates context identity synchronously, without a
callback or yield. Existing `check_call`, `check_host_service` and lifetime
checks still run. Message is the only admitted host service in this first lane;
custom callbacks, Eval, imports, platform APIs and persistence services are not
newly exposed. Root variables must remain scalar after execution and callbacks.

Structural unsupported shapes are rejected before source execution with
`PythonDirectUnsupported`. Changed live authority is fail-closed with
`BoundaryViolation`. Command-scope and transaction-activation flags are restored
on failure; this is not a transactional rollback of earlier Message effects.
A trusted output callback is still a host side effect and is not sandboxed.

## Explicit non-goals

This does not make the configuration/reuse CI group green. Existing non-Val
routines, expression defaults, globals, client/server selection, ServerCall,
async/dual calls, session initialization, reusable values and database-backed
applications remain unavailable through this entry. In particular the legacy
`test_named_export_private_routine_and_casefold` uses non-Val parameters and is
not claimed as fixed; a separate by-value analogue verifies the admitted case.
The existing by-value nested-call test is supported.

## Research evidence

A prototype using the existing ConfigurationBoundary already produced 8 and 12
for two nested by-value calls, while public `app.execute` was blocked by the
standalone configuration guard. Merely removing that guard would lose the
finite contract above. Tests cover the separate runner, no legacy evaluator
calls, live policies/owner changes, hostile values, unsupported data/transport,
transitive service restrictions, reentrant execution and cleanup.

## Ordinary error recovery

Command validation descends through both Try and Except branches before any
source effect, including unreachable handlers. Raise accepts an ordinary scalar
description or a bare rethrow in a syntactically valid handler; optional extended
Raise arguments remain outside this lane. Execution reuses the existing direct
error lowering, not an AST evaluator. Its catchable exception set does not
include BoundaryViolation. Active command state is checked before generic
closed-application diagnostics, so closing or failing the application in an
output callback cannot enter an Except handler. Owner, service and command-scope rejections cannot
be swallowed by a BSL handler. A rethrow preserves the original module location;
command scope, context-stack and transaction-activation cleanup still happen on
both caught and escaping errors. This adds no new host service or endpoint.

### Read-only common-module metadata

The scalar command lane accepts finite `Metadata.CommonModules` / `Метаданные.ОбщиеМодули`
lookup chains: `Count()`, `Find(name)`, numeric `Get(index)`, numeric/name indexing,
and a named module member. A lookup must end in a public scalar field (`Name`,
`Global`, `ClientManagedApplication`, `Server`, `ServerCall`, `Privileged`,
`Synonym`, `Comment`, with Russian aliases), or `FullName()`.
The values match the canonical common-module metadata objects. Missing names and
invalid indices are ordinary errors; metadata writes are rejected before effects.

This is not a general reflection facility. Reader intermediates cannot be stored,
returned, passed to routines, enumerated or used to inspect module source/private
state. Other metadata families remain unsupported. Tokens contain no owner or
module payload and are interpreted only by their issuing command scope. Every
read and bound operation validates the live application, original thread/context,
issuer and canonical definition storage. Forged, stale, revoked or cross-scope
readers fail closed. Existing no-database/client/DontUse/scalar restrictions remain
in force; inspecting metadata does not grant execution or host-service authority.

### Scalar conditional commands

`If` / `ElsIf` / `Else` (`Если` / `ИначеЕсли` / `Иначе`) may select scalar
commands, including qualified calls and nested `Try` / `Raise`. All conditions
and all branch bodies are admitted up front, including unreachable branches,
before the first command effect. Only the selected branch is executed, using
the existing direct backend's condition semantics and error lowering. This adds
no loop, constructor, dynamic evaluation or host capability. Fatal scope/lifetime
violations remain outside the catchable error set; captured callables remain
bound to their original active command and exact context.

### Literal defaults for Val parameters

Qualified calls in this lane may omit optional `Val` arguments whose installed
default is an immutable scalar literal (`Undefined`, Boolean, String or Number).
Trailing omissions and explicit comma holes use the recorded default; explicitly
supplied `Undefined` remains `Undefined`, rather than selecting a default. A
comma hole in a parameter without a default binds `Undefined`, matching the
canonical same-side semantics. Missing required trailing arguments and excess
arguments are rejected before evaluating actual arguments. Internal
same-module calls retain the existing generated direct default semantics.

The original parameter identities, literal nodes and values are sealed to the
installed generated function. They are checked at scope admission and again at
call boundaries, including after argument effects. Replacing declaration metadata
or the default snapshot is not authority to alter the installed program.
Expression defaults (including unary expressions), by-reference parameters,
transport, server/global modules, reuse and database access remain outside this
command lane. No evaluator or legacy fallback is used to obtain default values.
