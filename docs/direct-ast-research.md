# Direct AST lowering: bounded, unselected research

This is **not a production compiler switch**. No public API selects
`experimental_direct_ast.compile_module`; tests replace the private compile
function explicitly. Unsupported whole modules fail before source effects,
without replay or fallback to another runtime.

## Why this direction

The current text emitter creates full strings for nested expressions. SourceMap
parses overlapping strings again to recover their structure and rewrites Python
AST positions before final compilation. Long expression chains can therefore
have quadratic preparation work and temporary memory. ErrorInfo lookup is
already lazy, but the expensive reconstruction is not.

The prototype constructs Python AST nodes directly from BSL nodes. Each newly
created node receives its BSL position immediately, with no recursive subtree
copying, full-subtree strings, SourceMap, structural index, `ast.parse`, hidden
code cache, or error-path recompile. There is no separate map to rebuild on
success or failure. One real `compile(Module)` produces the executable code;
`exec` creates a fresh function namespace. Existing direct admission, current
registry/owner checks, Decimal context, Program execution, handled-error state
and exception conversion are reused.

## Explicit scope and complexity limits

Implemented generic forms: literals, names, scalar operators and conditionals,
name assignments, client Var, If/For/While, Break/Continue, Try/Raise and zero-arg
named service calls. Source routines, DB/import contexts, constructors,
collections/member/index lowering and parameterized calls are unsupported.

Iterative preflight bounds this research to 10,000 BSL node occurrences, depth
80 (including container nesting), and source line 50,000. Unsupported or
malformed control flow is rejected before execution. Node creation is linear in
supported input occurrences and does not call `fix_missing_locations` afterward.
The BSL parser, ordinary admission/snapshot traversal and CPython compiler still
have their own traversal/recursion costs. **The whole public path has not been
proved linear or suitable for million-line modules.**

Regression counters for 8/16/32 operand subtraction chains are 42/74/138 emitted
Python nodes; wide 8/16/32 assignments are 63/119/231. These are lowering counts,
not timing or peak-memory claims. No runtime speed claim is made; some generic
operations still use semantic helpers instead of current specialized lowering.

## Production blocker: audit contract migration

The current compatibility compiler produces source-byte parse audit events
(including filename and auxiliary fragments) and a final AST compilation event.
The prototype produces one genuine AST compilation event before BSL effects.
CPython reports this event as `(Module, None)`, even when `compile` receives a
filename. Thus old policies selecting auxiliary bytes **or the filename on the
source-byte event** are not equivalent. A newly installed policy rejecting the
actual AST compilation correctly aborts before effects, but that does **not**
prove equivalence to existing hooks.

A new voluntary callback or a new honest `yadinassi` audit event could supply
BSL source, filename and a compiler profile, but cannot automatically restore
an existing hook's enforcement. Such a protocol requires explicit host-policy
migration and independent security review; it is not implemented here. No fake
`compile` events are emitted.

Possible designs to evaluate separately:

* direct AST: one real AST compilation, cheap positions, changed audit contract;
* one generated-source parse plus AST compilation: two genuine events retain
  whole-code source/filename and AST inspection, while auxiliary-fragment
  policies still need migration;
* generated text compiled once with a lazy span resolver: source/filename audit
  remains, but raw Python traceback coordinates and AST-inspection policies
  change. Python 3.10 needs special line-level provenance because it lacks
  expression columns.

No one-call design can transparently preserve arbitrary policies that require
both distinct source-byte and AST compile events. This is an architectural
contract choice, not permission to silently bypass an existing policy.

## Verification so far

Paired tests compare normal execution, partial effects, actual escaping errors,
caught/nested/reraised ErrorInfo, source positions (including Unicode), service
shadows and current registry changes, owner close/restricted callbacks, constant
fold order, prepared source ownership and native exception trace coordinates.
They run on Python 3.12, optimized 3.12 and Python 3.10. An isolated audit test
verifies a fresh real AST compilation on every call and denial before source
effects. This bounded evidence is not whole-language equivalence or production
security approval.

The addition lowering retains the ordinary compiler's left operand temporary
until module return. A helper-only implementation released a host operand too
early, making its finalizer (including owner close) observable before subsequent
assignments. Paired finalizer tests cover both operand positions and owner close;
the corrected lowering emits each operand once and chooses the operation before
evaluating the right operand. This illustrates why lowering lifetime, not only
returned values and error coordinates, is part of the research proof.

## Named host calls with arguments (research extension)

The direct emitter now supports non-omitted positional arguments for named host
services, including grouped/name reference arguments. It uses the existing
`resolve_service` crossing, `requires_reference`, `prepare_named_value` when
provided, and canonical live host references. Resolution precedes all argument
effects; the callable is retained in a module temporary as in ordinary lowering.
Non-name argument subtrees are emitted once, after the existing reference-mode
query, rather than copied into two conditional arms. Constructors, member/index
calls, omitted arguments, source routines and DB/import contexts remain outside
the bounded subset. No production entry selects this compiler.

## Index-read research slice

Index reads select their exact native or host callable before evaluating one
index subtree. List bounds use the existing checked-index helper; map `get` is
bound before index effects; other exact native receivers use builtin indexing;
host receivers use the existing `resolve_member` authority crossing. Receiver
lifetime follows the ordinary temporary; no index/result local is introduced.
Nested reads are supported without recursively duplicating index subtrees.
Index/member call arguments are explicitly rejected until reference lowering
exists, even for a callee that might not request references. Writes, attribute
reads and member calls are not implemented by this slice. Finalizer/order and
error tests are bounded evidence, not general host-object equivalence.

## Property and write research slice

Property reads retain exact dict/list/map/structure/map-entry dispatch and the
existing host `get_member` crossing. Index and property assignments preserve
receiver evaluation, host write resolution, index (where applicable), RHS, then
write. Receiver/writer/index/value temporaries deliberately match ordinary
lowering lifetime. Canonical ValueTable/ValueList constructors use their existing
registered service crossing, including argument effects and failures. Other
constructors and direct member calls remain unsupported. This slice has bounded
scalar/native tests; independent adversarial host/property review is required.

## Direct collection method research slice

Direct Add (zero/one argument), Count and Clear (no arguments), including Russian
aliases, now retain native dispatch and host `resolve_member_call` before argument
effects. Unsupported method/arity/omission forms reject before any BSL effects.
This is not method extraction followed by `resolve_callable`. Native non-list Add
fails before argument effects; callable selection precedes one argument subtree.
Method diagnostics use the receiver root token, matching ordinary SourceMap.
Small ValueTable/ValueList construction/build/read/count/clear scenarios now run
through the prototype without private graph mutation or alternate backend.
Property byref, other methods and collection-loop specializations remain future
work; this slice makes no new performance claim.

## ForEach research slice

ForEach keeps the ordinary receiver, bound iterable and iterator temporaries.
Exact native collections use the existing map-entry generator shape; host
collections resolve `__iter__` through the existing authority crossing. Only
`next` and loop-variable publication sit inside the StopIteration/RuntimeError
handlers, not the user's loop body. RuntimeError conversion applies only to
exact native map receivers. Break/Continue and the live last element follow the
ordinary loop path. No extra checkpoints or collection-loop fast path are added.

## Property name-output reference slice

Property/Свойство supports one key argument and an optional name/grouped-name
output. Native direct structures use canonical structure_property with a source
reference; host receivers use resolve_member_call and canonical Reference wrapping.
Address-only slots are created once at module entry and reused by casefolded name;
source_reference still reads the current binding and forwards existing Reference
values. The receiver is resolved before key/output effects, and missing output
names keep their own source location. Index/member output positions and omitted
arguments remain explicitly unsupported. No generic host_reference substitution
or new source-routine crossing protocol is introduced.

## Property index/member output references

Property output arguments also admit index and member locations. Exact native
receivers use the existing IndexRef/AttributeRef eager binding semantics; host
locations use the existing reference_index/reference_member crossings. The output
subtree is emitted once, with native/host conversion selected before evaluation.
Property's existing special diagnostic convention is retained: location-binding
errors use the call's opening-parenthesis token, while missing name references and errors in
index expressions retain their own token. Ordinary named host calls with dynamic
index/member argument modes still reject these shapes; adding them by duplicating
entire expression subtrees would reintroduce the architectural problem.

## Dynamic host index/member argument modes (bounded)

Named host calls can now choose by-value or canonical by-reference member/index
arguments using the current requires_reference result for each argument. Receiver
subtrees are emitted once; member reads and reference binds retain their separate
error locations. Dynamic index arguments currently require a literal/name leaf
index (groups allowed): by-value indexing and reference binding need different
CALL locations, so two constant-size leaf forms are emitted, never two arbitrary
nested index subtrees. Complex index arguments reject before effects rather than
silently losing error coordinates or reintroducing quadratic expression copying.
Property output references do not have this restriction because their mode is
statically known. This is not complete general argument-mode coverage.

## First source-routine lifecycle slice

Zero-argument client procedures/functions now compile to genuine nested Python
FunctionDef nodes. The bounded body admits straight-line local assignments/Var,
Return and calls to sibling routines; parameters, control flow, and host/member
calls within routines currently reject before effects. Routine locals remain
Python locals; declared module globals use the existing live module dictionary.
Possible reads of an assigned local before definite initialization reject rather
than guessing at unbound-local diagnostics. Routine-as-value errors and module
shadow values retain their ordinary behavior.

Declarations are available before textual calls. The generated `_bind_only`
entry returns fresh routine closures without rerunning module statements, using
the existing python_direct_routines persistent registration/rebinding and call
validation. Subsequent execute and execute_prepared calls exercise this lifecycle.
This does not add server/import/NoContext routine support, parameter defaults or
byref parameter Cells, and does not select the prototype in production.

## By-value routine parameters

Straight-line client routines additionally accept required by-value parameters.
They are lexical Python argument slots, excluded from module-global resolution;
local Var does not reset an already-bound parameter. Direct sibling calls check
procedure-value use and arity before evaluating arguments. Persistent calls retain
the existing signature validation and activation-local rebinding. Defaults,
omissions and by-reference parameters are still outside this slice.

## Literal defaults and direct routine omissions

By-value parameters additionally support literal default values. Python function
defaults contain only the existing omission sentinel; BSL defaults are selected
inside each routine activation, in parameter order. Direct source calls retain
the highest-required-position arity rule and explicit omission sentinels.
Persistent calls with trailing omitted arguments use the existing routine
signature resolver. Explicit omission slots through a separately declared host
call remain unsupported by the general host-call emitter in this slice.

## By-reference routine parameter slice

Source routine parameters may now be by-reference. Existing `_as_ref`, `_Cell`,
`_bound_ref`, source slot references and host/index/member references are reused.
Parameter reads and writes address the reference value; forwarded parameters keep
the same target, including aliasing two parameters to one variable. Literal
fallbacks are chosen before reference wrapping, in parameter order. Direct source
calls resolve argument references before entering the callee; persistent calls
retain the existing canonical Reference forwarding protocol.

Passing an unboxed routine-local/by-value parameter onwards by reference remains
explicitly unsupported until local Cell analysis is implemented. Existing boxed
parameters and declared module globals can be forwarded. Control flow and host
calls within routine bodies remain outside this slice.

Direct Get with one argument (and Russian alias) follows the existing list/map
native receiver restriction or host resolve_member_call. Getter selection occurs
before the single argument evaluation. This small extension permits unchanged
public ValueTable/ValueList reference workloads for honest preparation/runtime
comparisons; it does not add their existing collection-loop specialization.

## AST collection-region lowering (on current baseline)

This research port reuses the existing analyze/admitted/helpers implementation
unchanged. Admission remains before each proved For; constructor/schema and loop
exit resets are retained. Per-operation helper entry/finally liveness and exact
canonical graph checks are not removed. Ordinary direct operation selection is
the pre-effect alternative, never replay after a failed optimized operation.

Rather than copying fast/ordinary expression subtrees, the AST chooses a bound
callable before emitting each argument once. Fast setters use a C partial of the
existing canonical helper; ordinary setters preserve their earlier resolution
before RHS. Read-property alternatives share one captured receiver. This adds a
small partial allocation whose cost must be measured, but avoids reinstating the
old recursive whole-subtree text/mapping duplication. An AST-node growth test
covers nested tracked Get(...).N expressions at depths 4/8/12. This is not proof
of whole-parser/compiler linearity or unlimited-depth handling.

The 31 applicable existing collection-region security tests are rerun with this
research compiler selected. Two suffix tests use Owner/Delete methods outside
its syntax subset and are explicitly excluded, not reported as passes. Paired
reference workload graph/partial-error checks compare against the current direct
compiler. The compiler remains unselected by production APIs and its previously
documented audit-contract incompatibility is unchanged.

The imported partial factory is an additional public dependency. Before compiling
this research route, it must be the immutable native CPython partial type: exact
metaclass, builtin __new__ bound to that same class, native __call__ descriptor
owned by that same class, immutable-type flag and exact metadata are checked
without invoking host descriptors. An import-time replacement rejects before
BSL effects, rather than introducing a callback inside an admitted region. Tests
cover a replaced factory, a name/module-spoofed Python class and hostile metaclass.
This is a research platform restriction, not a guarantee for arbitrary runtimes.

The imported `_operator.add` and `getitem` functions must also be native builtin
functions with their exact readonly name and owning `_operator` module identity
before compilation. The writable `__module__` attribute is not provenance: a
bound `set().add` can spoof it and is explicitly rejected. In
particular, an import-time replacement of add must not become an unproved Python
callback inside numeric expressions in an admitted region. A separate subprocess
regression verifies rejection before collection construction or operator effects.

## Source-routine branch slice

Client routines now admit nested `If`/`ElsIf`/`Else` with the existing scalar,
assignment, declaration, return and direct source-call subset. This also admits
bounded examples of source recursion using conditional returns. Runtime emits
native Python `if`/`return`; definite-initialization analysis is compile-only.
Lexical local declarations and assignments are collected once with an explicit
stack, including declarations in branches. Each branch journals only newly
initialized local names, rolls them back before compiling its siblings, and
commits the intersection after all branches (including an absent `Else`). It does
not copy all existing local facts or duplicate expression subtrees per branch.
Nested journals propagate only newly proved names to their enclosing branch.

Unknown initialization remains an explicit pre-effect research rejection; paths
that return are not specially excluded from the intersection, so some valid
programs remain conservatively unsupported. Routine loops, Try, host/member calls,
and passing unboxed locals onward by reference are still outside this slice.
Tests pair default/prepared results, nested lexical paths, by-reference writes,
recursion, exact errors, and uncertain-read rejection. This is not production
approval and does not resolve the audit migration contract.

## Source-routine numeric loop slice

Routines now emit native `For`/`While`, nested `Break`/`Continue`, and conditional
returns through the same loop lowering used at module scope. Counted-loop start
and end expressions are evaluated before assigning the counter; that counter is
initialized even on zero trips. New body-local initialization facts are journaled
and discarded after the loop, since its body may execute zero times. Existing
local/by-reference assignments retain their runtime representation. No runtime
fact checks or tracing wrappers are added. Nested `For`/`While` and `If` journal
boundaries compose without copying all existing local bindings.

Routine `For Each`, `Try`, and loop-local `Var` remain explicitly unsupported in
this slice. In particular, repeated conditional initialization of a local Var
needs a separate proof rather than a Python assignment at each iteration. Tests
compare default/prepared values, partial exceptions, nested break/continue,
by-reference writes, zero-trip counter behavior, and pre-effect rejection of
unproved post-loop reads. Audit compatibility remains unchanged/unresolved.

## Source-routine iterator loop slice

Routines can use the existing `For Each` lowering over supported native and host
collections. Iterator acquisition retains the original receiver and selected
iterator, and the narrow next/StopIteration/RuntimeError handling remains outside
user body execution. The loop counter and newly initialized body locals share one
compile-only journal: both are discarded as definite facts after a potentially
empty traversal. A previously initialized counter remains readable. Numeric and
iterator nesting, break/continue and by-reference counters use their existing
runtime representations. Loop-local Var and routine Try/host calls remain outside
scope. No production selection or audit-contract change accompanies this slice.

## Source-routine Try/Raise slice

Source routines can emit the existing narrow BSL `Try` and `Raise` lowering.
Normal body and handler are compiled from the same incoming initialization facts;
only newly initialized names common to both successful exits become definite
facts afterward. A handler may not assume that an earlier body assignment ran
before an exception. This is conservative and may reject valid code, but does not
add runtime probes. Existing `_handled_error` activation, exception-class filter,
bare rethrow and BSL source positions are reused unchanged; no blanket catch or
retry is introduced. Return/break/continue unwind the existing handler context.
Routine host/member calls and optional Raise arguments remain outside this slice.

## Source-routine member and collection slice

The previously checked module-level member/index readers and setters, canonical
ValueTable/ValueList constructors, and finite Add/Count/Clear/Get/Property method
lowerings now operate on routine lexical receivers as well. Receiver binding,
method resolution before arguments, setter binding before RHS, and authority
checks are unchanged; only the routine preflight admits these constructs. There
is no new generic callable dispatcher or collection-region admission for routines.
Thus this adds language coverage, not a claim of faster collection execution.
By-reference Property output through an already boxed parameter is supported;
unboxed local output still rejects before effects pending separate lexical-ref
lowering. Named host calls inside routines remain unsupported in this slice.

## Source-routine zero-argument service slice

Zero-argument named services (including ErrorInfo/ErrorDescription) now use the
same current-context service resolver within source routines. Lexical fallbacks
use the existing runtime `slot in locals()` check, not static initialization
facts: a conditional assignment may have run, and the locals snapshot itself can
retain values observed by finalizers. Missing slots use the existing sentinel;
declared module globals keep their live module lookup. Source-defined routine symbols still use the prior direct-call path.
No new helper frame or per-call policy wrapper is introduced. Existing bound-call
entry/finally checks preserve owner close/revoke behavior. Named host calls with
arguments remain rejected until lexical by-reference argument helpers are proven.
## Whole-source audit lane with paired structural walk

An unselected alternative now emits the whole executable Python text once,
performs a genuine `ast.parse(text, filename)` before any BSL execution, checks
parsed structure against the emitted AST with one explicit paired stack, copies
BSL positions to the parsed nodes, and compiles that actual parsed AST. No ignored
"authorization parse", fake audit event, subtree dump, backward text matching,
or cross-execution cache is used. The pairwise pass visits every field/list/node
once. Generated source and both trees exist simultaneously during preparation.
CPython `unparse`/`parse`/`compile` and the BSL parser have their own costs and depth
limits; this is not a claim that the whole pipeline is linear for arbitrary input.
The existing bounded input/depth limits remain.

Emitter-only constants use syntax-canonical negative integer and tuple nodes,
which CPython folds as before, and Python 3.12 FunctionDef explicitly has empty
type_params. Other unparse normalizations are not accepted heuristically: any
structural discrepancy rejects before BSL effects. Original token positions are
copied while checking corresponding nodes, without locating text fragments.

This lane restores genuine source-byte/filename and executable-AST audit gates
before execution, including repeated default calls. It does NOT preserve old
hooks that specifically reject an obsolete auxiliary source fragment, nor exact
old generated-source bytes. Those policies need an explicit migration decision.
The pure direct-AST lane remains separate; neither lane is selected in production.

## Dynamic host arguments from routines (bounded research)

Routine named host calls can use the existing dynamic requires_reference and
prepare_named_value protocol. A pre-scan creates ordinary nested lexical getter/
setter closures only for local names actually passed to those calls; all locals
are not boxed. Unboxed setters use Python nonlocal storage, boxed parameters
forward `.value`, and the existing `_host_name_reference` helper creates canonical
host references with its original eager validation and name-sink flags. Helpers
are created once per routine activation, not per loop iteration. Module-global
arguments retain live module references; indexed/member actuals retain their
previous address/evaluation lowering. Unknown or not-definitely-initialized named
locals remain conservatively rejected before effects. Explicit omitted host
arguments and unboxed direct-source byref calls remain outside this slice.

## Addressable routine locals and Val forwarding

Names actually passed to direct source-routine by-reference parameters, or used
as a Property output, now receive the existing `_Cell` representation. This is a
single pre-scan of call actuals, not boxing all locals: unrelated variables retain
ordinary Python slots. Val parameters needing an address are wrapped in `_Cell`
after their default is resolved; non-Val parameters retain `_as_ref`. Other
addressable locals receive one initially unset cell per activation, in the same
order as the current compiler. Existing `_bound_ref` still rejects missing
actuals before entering a callee; no write is assumed merely because a reference
was passed. Host lexical helpers forward the same cell when both kinds of calls
use a name. This supersedes earlier slice exclusions for initialized local/Val
source-byref and local Property output. Other uncertain-read restrictions remain.

### Native collection constructors

The bounded research emitter also constructs native Array, Map and Structure
storage with the same canonical factories as the current direct compiler.
Array dimensions use `bounded_array`, maps use `_TypedMap`, and valid literal
structure schemas are prepared once with the existing schema helper. Invalid
or dynamic field lists retain the runtime constructor path, including supplied
argument effects before a field-validation error. Omitted constructor slots
remain explicitly outside this research subset. No new collection wrapper,
policy relaxation or production selection is introduced.

### Two-argument collection writes

Research Set(index, value) and Insert(key/index, value) select the same native
array/structure helper or bound map setter before argument evaluation. Set is
restricted to native arrays; unsupported native receiver methods fail before
arguments as in the existing direct compiler. Host receivers keep the ordinary
member-call boundary. One-argument Insert and omitted argument forms remain
outside this incremental slice; no synthetic argument is added to host calls.
### Activation-local first-loop collection region (research candidate)

The first straight-line `For` in a source routine can use the unchanged
canonical collection gate and leaf operations. Analysis-only literal seeds
mark Val parameters as potential numeric inputs; actual admission still checks
their current values. No synthetic assignment is executed. The first version
excludes boxed/byref cells, host-reference lexical helpers and nested loops;
the remainder of the routine stays on the ordinary direct path.

Each activation initializes its own fast flag. Immediately before the loop,
an ephemeral dictionary contains only relevant currently bound local slots and
live module slots, including old values of every overwritten name. It is an
inline argument, not a saved local or `locals()` snapshot. Constructors/schema
operations remain ordinary before this gate. No potentially initialized local
from an earlier loop enters this first-loop slice. A failed gate chooses the
ordinary arm before source effects; failures after effects never replay work.
Per-operation liveness and canonical graph/budget checks remain unchanged.

This is a bounded optimization experiment, not production activation or a
claim that all routine collection code is specialized. It does not change the
explicit audit contracts of either research compiler lane.

### Successive nonnested routine regions

The research prefix may now contain several straight-line loops. A separate
compile-time definite/possible binding lattice tracks old local slots: a loop
whose relevant overwritten/read local may be bound but is not definitely
bound stays ordinary. A later unconditional assignment proves binding again.
Never-bound slots may be omitted from the ephemeral gate snapshot; possibly
bound slots are never silently omitted. The fast flag is reset after every
loop, including a declined loop. Nested loops remain excluded in this stage.
This adds no runtime local-presence observer or replay path.

## Working-branch replacement milestone

The standalone default `python_direct._compile` now calls the whole-source AST
compiler directly. There is no compiler selector and no retry/fallback to the
text emitter. The former standalone compiler entry is temporarily preserved
only in `tests/direct_ast_text_oracle.py` for differential tests. The legacy
interpreter is deliberately retained as an independent backend.

This is an in-progress branch switch, not a release/parity declaration. Full
existing direct tests must run against the new default and unsupported forms
count as failures to fix, not skips. Remaining source/configuration entry
points and shared canonical helpers are inventoried separately; removing their
still-used code before porting the contracts would not be a valid replacement.
Research-only limits of 80 depth, 10000 AST nodes and 50000 source lines were
removed. Actual parser/CPython limits still apply; this is not an unbounded
resource or million-line performance guarantee.

Canonical service, ValueTree and UUID constructors now route through existing
live constructor boundaries; native Array/Map/Structure retain their explicit
factories. Unknown generic canonical members use the same live member boundary.
No constructor authority, object identity, validation or liveness check is
replaced with an unvalidated surrogate.
