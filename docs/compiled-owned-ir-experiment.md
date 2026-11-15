# Owned semantic IR experiment: design and contract boundaries

Status: implemented isolated experimental prototype, not production-ready. The existing strict backend remains the default implementation when explicitly selected; owned execution is disabled by default and has no UI/CLI selector. The sections below retain architectural rationale and outstanding qualification gates, not claims that those gates have passed. Python compilation, host callbacks and diagnostic stack collection are not a sandbox.

The frozen broad strict run is **INCOMPLETE**. A slow real native-values replay was diagnosed in `signature → verify_node → verify_all → inline_enter`; repeated whole-origin walks are a confirmed performance blocker. No full-suite success, native parity or owned-snapshot speedup is claimed. Short isolated probes qualify only the cases named below.

## 1. Measured problem and what cannot be promised

Current `Engine.verify_all()` walks every admitted node and block before/after opaque operations. Refresh also scans keys of variables, imports, module names and locals. `compiled_inline.Emitter.block()` checks a complete statement identity tuple repeatedly. These produce costs proportional to program size times callbacks, and potentially block size squared for straight-line blocks. Pure arithmetic benchmark improvements do not establish acceptable mixed-program performance.

There is no portable O(1) way to detect arbitrary changes to *all* externally held mutable Python dataclasses/lists after an arbitrary callback. Preserving immediate whole-unit mutation rejection requires either inspecting that unit or controlling all mutation through tracked/sealed storage. A counter incremented by the engine cannot detect arbitrary untracked Python writes.

Therefore distinguish:

* Real BSL and supported host behavior: call/argument order, references, live object state, configuration authorization, safe-mode/transfer checks, budgets, events, async suspension, diagnostics and terminal host faults. Preserve these in every variant.
* Explicit current AST embedding contracts: changed AST validation before a new root/call; existing compiler's active-unit mutation rejection and its timing. Do not silently replace these contracts with snapshots.
* Unsupported arbitrary Python attacks on engine internals: this project does not promise a sandbox against unrestricted Python, `object.__setattr__`, mutable function globals, or native memory writes.

## 2. Isolated experimental variants

Keep current `compiled-strict` behavior and tests unchanged until a reviewed migration decision. Introduce an isolated owned-IR experiment, not a fallback to the tree interpreter.

1. **Owned execution + full origin mutation monitor**: execute owned descriptors, but run origin fingerprint checks at the same current checkpoints. Preserve rejection classes/timing and terminal-fault precedence. This variant is for differential qualification, not an expected performance fix.
2. **Owned execution + explicitly disabled origin monitor**: execute the same descriptors without scanning originals around every callback. Changes to original syntax during an active admitted unit do not change the running program. This is an explicit snapshot contract, not equivalent active-mutation behavior and not a drop-in optimization claim.

Both variants must report mode/monitor setting, actual compiled entry counters, node instrumentation status, rejected units, and zero interpreter fallback. Results from monitor-off cannot be reported as proof of monitor-full parity.

A third option, local just-in-time guards, can reject mutation before each *affected* operation with lower cost. It still changes the current immediate-global rejection timing and may allow unrelated earlier effects. Do not pass that change off as unchanged semantics.

## 3. Owned representation

Build a frozen descriptor graph once per admitted unit/generation:

* Exact enumerated syntax kind, immutable source token coordinates/text.
* Immutable names, operators, routine flags, parameter names/flags.
* Tuple child edges, argument slots, branches, statement order and lexical labels.
* Literal values remain the identical opaque value object. Never deepcopy, traverse, stringify, or invoke equality on host payloads. Mutable runtime objects are intentionally live.
* A separate origin handle/map exists for authority and optional monitoring. Execution must not read mutable syntax fields through this handle.

Current `NodeIR` is insufficient: its `.node` is still the mutable original consumed by semantic adapters. Merely freezing the outer dataclass does not make semantic execution immutable.

One feasible implementation is registered immutable AST-shaped descriptor classes plus a closed `canonical_syntax_kind()` mapping. `isinstance` compatibility alone is insufficient: several policy/validation paths use exact `type(node) is ast.X`. Never accept arbitrary objects merely because they advertise a kind attribute. Existing context allowlists must continue to distinguish exactly supported syntax through the closed mapping.

An alternative is explicit operation descriptors passed to adapter methods, keeping policy-facing metadata separate. It is cleaner but requires more runtime adapter signatures. Do not use transient mutable originals as adapter arguments and then claim full snapshot semantics.

## 4. Authority identity must not be cloned away

Concrete identity-dependent paths include:

* `configuration_runtime.py`: `_declared_routines`, `_common_routines`, `_reuse_routines`; `check_program`, `check_call`, common-module checks and reuse lookup.
* `configuration_source_runtime.py`: reuse entries keyed by `id(routine)` plus object identity.
* `runtime.py`: `_invocation_bindings` checks that its original routine object `is function`.
* Invocation endpoints and form server registries retain routine objects.

Keep the original routine as an **authority handle only**, verified against the existing owner's registry. Keep executable name/flags/parameters/defaults/body in the immutable plan. A trusted mapping ties origin and owned descriptor to owner and generation; never trust an origin pointer supplied by arbitrary host data.

Authority checks remain live: configuration `check_assignment`, object lifecycle guards, safe-mode transfer checks, source/host call permission, reference get/set, receiver guards and context restrictions. No permission decision is cached just because execution syntax is immutable.

Blindly replacing registry objects with cloned AST objects breaks legitimate identity checks. Relaxing `is` checks to name equality would weaken authorization and is unacceptable.

## 5. Adapter field inventory

| Operation | Owned fields needed | Live operations that remain authoritative |
|---|---|---|
| Name | identifier, token | scope/module resolution, reference getter, configuration globals |
| Attribute | receiver edge, member name, token | receiver/get-member policy and result guards |
| Index | receiver/index edges, token | supported indexing, host callbacks, bounds/errors |
| Assign | typed target descriptor, receiver/index/member edges, RHS edge | ordering, set_variable, configuration checks, reference setter, object write guards |
| Call | callee descriptor, exact argument/omitted slots, token | resolution, original routine identity, parameter binding, refs, contexts, host function authority |
| Routine activation | name, flags, params/defaults, body, source | caller/owner identity, reuse/invocation binding, lifecycle and transfer policy |
| New | type name, ordered arguments | factory selection/authority and callbacks |
| DynamicNew | type-expression and parameter edges | type validation and permitted factory behavior |
| Import | filename/token and unit identity | filesystem/module authority, cycle checks, explicit child admission |
| Raise | value/optional slots/token | diagnostic construction, current handled-error stack |
| Execute/Eval | source expression/token | fresh parsing, limits, source context, explicit new-unit admission |
| Await | operand/source | transfer prohibition, pending/settled scheduler behavior, context restoration |
| Control flow | frozen edges/order/names/labels | exact Decimal semantics, mutable counter storage, lexical unwind/cleanup |

Read source helpers carefully rather than assuming this table proves their entire contract. Child evaluation must remain compiled and preserve before/after/error policy ABI order.

## 6. Admission and entry-point inventory

All of these need explicit owned-unit translation, not lazy interpreter fallback:

1. `Interpreter.execute()` parsing and `execute_program(program)` public AST entry.
2. `Interpreter.visit(node)` embedding entry and engine direct node/block admission APIs.
3. `call_routine`: routine/default/actual materialization and owner/caller handoff.
4. Eval/Execute fragments and imports, including child VMs.
5. `configuration_runtime` / `configuration_source_runtime` startup synthetic Calls and session handlers.
6. InvocationPort and form program admission; server endpoint routines.
7. `catalog_object_preparation`, `document_posting`, `form_event_simulation`, source-context policy subclasses.
8. `source_constant_managers` direct `_execute_program` path.
9. Async continuation/callback materialization after the initial root returns.

Perform existing label, async, context and admission validators before effects and before actual argument evaluation where currently required. Use owned descriptors for execution only after this admission succeeds.

## 7. Generations and legitimate source changes

A whole application must not be frozen forever. Use family/root generations with active-unit retention:

* Quiescent new `execute_program` admits a new snapshot of supplied syntax.
* Previously registered routines first called in a new quiescent generation are validated and snapshotted before evaluating actual arguments.
* A new synthetic Call/fragment is explicitly admitted without changing the existing active unit.
* Reentrant admission of a known active origin must not silently bless altered syntax. Preserve current rejection in both initial experimental variants.
* Suspended frames retain their owned plans until settlement/reset; no eviction while active.

Concrete existing non-compiler tests matter:

* `tests/test_goto.py::test_execute_program_revalidates_mutated_ast_before_effects`: caller changes a parsed Goto before root execution; invalid target must fail before output.
* `tests/test_goto.py::test_mutated_routine_cannot_leak_control_flow_into_callers_labels`: caller edits a registered routine between `vm.execute` requests; next call must fail label validation before actual-argument or body output.
* `tests/test_form_app.py::test_server_error_keeps_authoritative_state_and_finite_reason`: host test replaces an endpoint routine with a newly parsed routine between events, expects partial state/error, then restores the original object.
* `configuration_runtime.py` marks a fresh InvocationPort stub exported before its first compiled call. Capture after that legal setup.

Targeted source inspection plus inventory agent found no production in-place post-admission edits to AST bodies/callees/parameters. That is an audit observation, not proof that every external embedding avoids them.

## 8. Exact mutation-monitor contract matrix

Full monitor must retain existing expectations, including:

* Known changed node cannot be silently late-preflighted.
* A changed existing descendant in a fresh wrapper cannot be readmitted.
* Callee edits cannot redirect a routine; target edits cannot change the write destination.
* Parameter/default mutations cannot change binding after argument effects.
* Appending a body statement during a callback rejects before subsequent body effects.
* Reentrant declaration-only execution cannot bless a changed active routine.
* Mutation plus terminal RuntimeError preserves that exact terminal fault, not a catchable replacement.
* Mutation plus catchable BSL error is checked before entering its handler.
* Decimal subclass comparison/increment and host equality mutations are observed at the same current checkpoints.

Monitor-off needs **different explicit expectations**, not deleted tests:

* During an active unit, original callee/target/body/default edits do not affect execution; it follows its admitted snapshot.
* Unrelated earlier effects may occur because no global-origin rejection is performed. Report that difference.
* Terminal host failures and BSL error handler semantics remain otherwise identical.
* New quiescent entry revalidates new originals, including the Goto and form endpoint tests above.
* Explicit reentrant changed-origin admission remains rejected according to the chosen admission rule.

The current `test_host_equality_invalidates_future_metadata_before_write` and similar tests assert stronger immediate-global rejection (even suppressing an unrelated earlier assignment). Monitor-off must not claim these same assertions passed.

## 9. Broad implementation sequence

1. New isolated owned-syntax module and origin/owner/generation mapping, with identity and opaque-literal tests.
2. Owned adapters and original-identity authority bridge. Audit all exact-type checks before enabling contexts.
3. Full-monitor owned execution differential: existing language, context, async, reference, configuration and mutation suites; poisoned legacy visitors; exact before/after/error traces.
4. Explicit monitor-off differential matrix and snapshot behavior tests, with no change to frozen/current strict defaults.
5. Complexity tests: same callback work with increasing unrelated syntax size; count visited origin nodes rather than trusting wall clock only. Owned monitor-off should perform no per-callback origin walk.
6. Small broad benchmarks (numbers, strings, binary streams, mixed calls, forms), separate admission/compile/execution, same machine and exact source. Only then larger timing.

## 10. Test matrix / acceptance gates

* All executable syntax kinds and direct dynamic-unit entrypoints, no interpreter fallback.
* By-reference actuals, default evaluation order, object property/index ordering and captured method checks.
* Configuration/common/reuse/invocation original identity: accepted legitimate origin, rejected forged clone, live revocation after callback.
* Source budgets and before/after/error hook traces, including custom contexts and class/instance instrumentation.
* Await settled/pending/rejected, cancellation/reset, multiple VMs/family owners, lexical Goto through Try, diagnostic source.
* AST mutation full-monitor exact timing matrix and monitor-off documented snapshot matrix, both retained.
* Opaque Literal identity and cyclic payloads; no arbitrary equality/coercion while snapshotting.
* Memory lifetime: suspended plan retention, quiescent release, no cycles retaining completed requests.
* Resource bounds for admission nodes/depth/generated bytes and owned origin monitor metadata.
* Native evidence remains separate: source binding, backend/monitor witness, actual compiled entries and honest node coverage. No native parity claim from unit tests or local smoke.

## 11. Remaining non-AST performance issue

Removing origin walks does not eliminate `fast_available` O(number of VM keys) refresh. Live arbitrary Python dictionary/set mutation cannot be cheaply versioned portably either. Initial owned experiment may retain these scans to preserve authority behavior. A later validated string-key storage abstraction can provide an engine-owned generation, but changing public storage containers needs its own compatibility review. Never replace live authorization with a stale cache to gain speed.

## Prototype implementation update (experimental only)

The selected prototype preserves exact AST classes using weak identity sealing,
not immutable subclasses. Only registered owned clones reject normal writes via
an `ast.Node` setter/deleter guard. Ordinary source ASTs remain mutable. Guard
installation is process-global and adds a lookup to subsequent parser field
writes; it must run only in a disposable isolated subprocess. It refuses any
preexisting AST mutation-hook customization rather than replacing it.

Enabling requires both a launcher acknowledgement environment variable
`YADINASSI_OWNED_IR_EXPERIMENT=isolated-process-v1` and an explicit call to
`enable_isolated_process_experiment()`, recorded against the current PID. An
Engine flag alone cannot install the guard. This cannot itself prove OS isolation;
the trusted developer launcher owns that requirement. There is no UI/CLI/default
selector. All prototype tests launch subprocess probes; ordinary test processes
must not install sealing. Unrestricted Python `object.__setattr__` is outside the
immutability contract, as with Python frozen dataclasses: still no sandbox claim.

`Engine.execution_view(original)` is identity when disabled; with the experiment
it returns the owned execution object. `origin_node(view)` uses closed weak
provenance to recover the original authority object. Runtime routine registries
retain original objects. Configuration `check_call` specifically reads execution
flags and therefore receives the execution view with live application state;
`is_common_routine`, invocation identity and reuse registration use the origin.
Both reuse APIs accept separate execution metadata so mutable original name/flags
cannot alter shutdown policy or cache behavior in monitor-off mode.


## Current implementation and evidence

`compiled_backend.Engine` captures the experimental mode per instance. `OwnedStore`
freezes admitted syntax using the same exact AST dataclass types, immutable owned
lists, frozen token objects and identity-preserved opaque Literal values. Original
syntax stays mutable; weak identity provenance supplies original authority handles.
There is no wrapper attribute an arbitrary host object can forge to obtain ownership.

Creation fingerprints belong to each owned node/list, not to each receiving VM.
A full-monitor foreign-view admission compares the current original against that
creation fingerprint before publishing plans. It cannot rebaseline a changed original
and bless stale owned code. Monitor-off imports intentionally keep the old snapshot.
Known active re-admission still checks prior admission; new quiescent entries validate
current source. Admission is transactional on rejection. Node/depth, aggregate sequence
entry (before cloning), generated-code and registry limits bound the experiment.
Unknown host-valued syntax metadata is rejected without repr/equality/coercion;
Literal payloads remain opaque. The process-global sealing lookup adds parser-write
cost and ownership cloning/compilation adds admission cost, not yet measured broadly.

The isolated probe suite currently contains 12 top-level subprocess cases. They cover
flag-alone rejection; exact types/read-only owned fields/lists and original mutability;
custom setter refusal; existing codegen/mutation/policy ABI/reentrant suites; configured
callbacks and quiescent form replacement; concurrent VM identity handling; immutable
foreign provenance; prefreeze bounds and host-field rejection; forged reuse execution
views; explicit monitor-off snapshot behavior; and between-call invalid Goto rejection.
They do not constitute the full existing suite or a native witness. Future runs must
record source, monitor setting, actual compiled entries and instrumentation status.

Default ordinary tests do not install the AST seal. Only disposable subprocesses with
both launcher acknowledgement and explicit capability activation may run the experiment.
The experimental API is not authorization to enable it in a concurrent application host.


### Collectible ownership provenance

The global provenance registry contains only weak view identities. Original authority
and immutable creation fingerprints live on the owned view itself, including an owned
list private slot. This is important when an opaque Literal payload points back to its
owned view: the resulting original/payload/view cycle is collectable after engine release,
not rooted globally. A surviving external view still retains its original authority for
foreign-engine admission. Normal owned-list attribute writes/deletes reject; only registered
owned ASTs receive the private-field admission exemption. Ordinary originals cannot forge
ownership by defining that field. Unrestricted object-protocol bypass remains outside this
experimental immutability contract. Eight cyclic VM/view samples and surviving-view authority
are covered by a subprocess GC regression.

## 14. Bounded generated-code reuse

Repeated form admission also repeats Python parsing/compilation. The inline emitter
now reuses only immutable code objects keyed by exact generated Python source,
compiler flags and effective optimization level. Each admission still validates
its original syntax, policies and per-function/per-unit source budgets before
lookup; execution gets a fresh namespace containing that VM's bindings. No VM,
AST, authority grant, literal payload or host receiver is stored in the cache.

The process-local LRU admits at most 256 entries and 16 MiB of weighted retained
source/code/constants/bookkeeping. This is a weighted cache bound, not an exact
RSS ceiling. Oversized entries are compiled but not retained. Concurrent misses
may compile twice; insertion publishes complete code objects under a lock.
Default compiler flags are explicitly pinned, not inherited from a caller.

Focused tests cover isolation, budget rejection on a hit, optimization keys,
eviction/bypass and concurrency. They do not establish a whole-suite performance
improvement or change the separate origin-monitor contracts described above.

## 15. Registered immutable execution-view checkpoints

In the isolated prototype, execution checkpoints no longer recursively hash the
already sealed owned shape. They verify closed ownership registration and the
exact original/view pair in the executing engine's admission map. An unregistered,
foreign-but-unadmitted, or forged view still fails before execution. Normal owned
field/list writes remain rejected; unrestricted Python protocol bypass remains
outside this experimental contract, not a sandbox guarantee.

Full-monitor mode continues to verify original fingerprints, including original
block membership and active semantic-helper ancestor metadata before a child
value reaches its adapter. Snapshot mode explicitly does not perform these
original mutation checks. Ordinary mutable-AST execution retains structural
checks. Live authority, VM epochs, permission checks and resource limits are not
replaced by the immutable-view identity check.

The frozen 60ce508a diagnostic full run predates this optimization and is kept
unchanged. Focused regressions and independent review are not a substitute for a
fresh complete run, native evidence, or a paired performance measurement.

Snapshot/OFF additionally omits redundant scans of already-active ancestor plans:
those plans were admitted before entry and their metadata stays sealed and retained.
This does not omit current node/block admission, own-node exit checking, opaque
boundaries or live policy checks. FULL and ordinary mutable-AST modes retain the
ancestor scan. Mode-specific spies and nonfast live module-revocation probes cover
this distinction; it remains the explicit OFF contract, not mutation parity.

## 16. Changes-only admission journals

Experimental owned admission uses temporary changes-only overlays for the ownership,
original fingerprint, node-plan and block-plan registries. Existing entries remain
in the base maps; reads consult the overlay first. Cached sizes preserve constant-
time size checks. Rejection discards inserts, replacements and provisional clears;
success publishes internal integer-key changes. Normal preparation no longer copies
all five existing registries merely to admit one materialized expression.

This is registry rollback, not a general reentrant compiler transaction. The tests
inject nested preparation to verify registry restoration, but compiler hooks are
not a supported host extension point; unit-byte counters and telemetry are not
transactional under such injected hooks. Publishing uses internal maps without
user callbacks; atomic recovery from MemoryError or arbitrary replaced mapping
implementations is not promised. Ordinary non-owned admission is unchanged.

## 17. Engine-local immutable lowering descriptors

Registered owned nodes reuse their immutable NodeIR snapshot within one engine.
Every hit still verifies exact owned/admission identity; ordinary mutable nodes
are never cached. The descriptor cache holds the same opaque Literal objects and
source tokens, not copies or cross-engine replacements. It participates in the
admission journal, has its own MAX_REGISTRY_ENTRIES bound, and is cleared on fresh
root reset or release. Failed admission cannot publish retained new descriptors.

This cache removes repeated recursive descriptor construction, not code generation
or authority checks. Each emitter still enforces generated function/unit byte
budgets even on descriptor and generated-code cache hits. Focused probes cover
recursive hit behavior, payload/source isolation, rollback, bounds and GC; broad
qualification and measured end-to-end speed remain pending.

## 18. Structural versus explicit metadata-list entry

Whole-unit admission still traverses argument/metadata lists and admits their
children. Only structural statement blocks receive dedicated inline functions.
Metadata lists retain shape/provenance plans and a shared precompiled entry for
the existing public expression-list block API. That entry dispatches admitted
compiled children and preserves lexical Goto; it never uses old AST visitors.
Aliased lists promote to structural roles and retain that role on later reuse.

The shared entry's source is charged once per admitting unit, including reuse;
its executions have separate metadata counters rather than pretending to be
inline-generated blocks. Unknown nodes, changed blocks and budget violations
still reject. This reduction applies to the explicitly selected strict compiler,
not just owned mode. Focused role tests are not full-suite or speed evidence.

## Production-candidate ownership revision (after 0e966da6)

The next candidate replaces process-global AST mutation hooks with private,
sealed subclasses for each concrete syntax kind. Original parser classes and
ordinary AST instances are never patched. Private views preserve `isinstance`
relationships and canonical display names, but their exact Python types differ.
Only registered private view identities normalize to canonical syntax kinds;
arbitrary subclasses and forged provenance do not gain admission or authority.
Original routine handles remain the authority keys. Runtime values and literal
payloads retain their existing live identity rather than becoming frozen data.

The earlier isolated-process requirement and measurements above describe the
historical global-hook experiment, not certification of this replacement.
Snapshot mode intentionally executes admitted metadata when the original AST is
changed during execution; this differs from immediate live-AST mutation rejection.
The known raw mutation assertion failures remain recorded, not deleted or silently
reclassified as passing. The interpreter is the transition's primary differential
oracle. Inherited native-1C mismatches are separate issues rather than a demand for
new blanket native parity certification. Required repository gates, authority and
data protection still apply. Unrestricted Python is not sandboxed by either form
of ownership, and passing focused tests does not make this candidate the default.

Private subclasses still inherit Python class behavior. Trusted embedding Python
that replaces AST class descriptors or `__getattribute__`, or directly uses
`object.__setattr__`/`list.__setitem__`, is outside the ownership protection
contract. This change guarantees that the backend itself does not alter those
public class hooks; it does not isolate execution from arbitrary later Python
class monkeypatching. BSL code does not acquire access to these Python operations.

This is an observable Python embedding API change, not merely a private-field
implementation detail: a host can retain parser AST objects passed through public
`execute_program` and mutate them from callbacks. Snapshot execution continues the
admitted version instead of immediately rejecting that mutation. Ordinary BSL
assignment and dynamic source compilation do not grant access to these Python AST
handles. Dynamic Eval/Execute/imported source still receives fresh admission before
its own effects; application authority and permissions remain live independently
of the immutable syntax representation.
