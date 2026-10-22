# Exported module variables: local design and checkpoint

The checkpoints below are historical. The runtime follow-up implements the
bounded exported-field and self-module model measured by the recovered native
capture; see the audited observations and runtime scope at the end. The earlier
bootstrap commits remain failed interpreter comparisons, not retroactive parity.

Historical status: local post-Create measurement checkpoint, based on Draft PR89 head
ebe8235bd4a03c06873adce931cfe53adaca093f (tree e09f6ca6). Publication is pending
independent exact-change review. Native run 39856163175 captured all 131 records
on Linux 8.3.27.1508. Native discriminator run 39858423942 then captured all 136
records and passed independent evidence-integrity audit, NOT semantic parity.
During initialization, static and Execute exported-field reads failed with
field-missing, static field write failed with field-missing, and both exported
routine calls failed with method-missing. The controlled member name was present
in each bounded diagnostic. These observations do not establish what becomes
available after Create returns. Export visibility, initial Undefined, references,
Val, exception writeback and collection sharing remain unmeasured in that phase.

## Bounded architecture

Official 8.3.27 developer guide section 4.6.1 documents Export independently on
each comma-separated variable: Var A, B Export exports B only. Object module
variables are available as object properties when exported. Source:
https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293
https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_Development_Standards/Code_conventions/Using_1C_Enterprise_language_structures/Variables/?language=en

Retain ast.Var.names and add per-name export metadata (default empty for existing
AST clients). Parser-only bootstrap accepts this modifier on top-level variable
declarations. Nested/routine placement remains unsupported pending measurement;
reject it explicitly, do not silently create a public variable. Track actual
statement block depth separately from routine context. Existing unexported Var
behavior is unchanged. Do not make declarations first-class values.

After native measurement, add Interpreter.exported_variables and narrowly scoped
_Module field accessors against the owner interpreter's existing variables map.
Register exported declarations before execution just like current module_names.
Explicit import-receiver dispatch handles field reads, assignment and argument
reference binding. Never expose _Module Python attributes or make it a BSLObject.
The current import_receiver traversal must return no module receiver when it
crosses a variable field, allowing collection methods/properties on exported
values while preserving normal directory-qualified module calls. Keep local
shadowing and path cache identity unchanged. Module namespaces are not values.

End-to-end tests: mixed Export lists; bilingual/case-insensitive names; initial
Undefined; internal/external read-write coherence; private and undeclared field
refusal; local shadowing; same file shared through existing diamond imports;
independent root interpreter state; collection-valued exports; directory imports;
by-reference versus Val according to measured native behavior. Import caching is
Yadinassi's documented extension, not a claim about 1C common-module syntax.

## Native measurement route

The original launcher creates an external-processing object from the complete source.
Its object module initialization already runs all functions.bsl observations.
Use ThisObject/ЭтотОбъект property syntax inside guarded Execute strings, with
static declarations at the beginning and helper routines before executable code.
This initial checkpoint made no launcher modification, database module, new
native input, native-only branch, or fabricated expected output. It did not
establish a usable public field context during object initialization. The first test explicitly records
whether the object-context bootstrap works. Property operations then record
success/value or a simple error marker, never source paths or diagnostics.

This is a parser-bootstrap checkpoint, NOT source-only: static Export cannot be
parsed by the old runtime. Minimal syntax acceptance does not make exports
accessible through imports; runtime remains fail-closed until native results.
Guarded native object references are unavailable in Yadinassi and report errors;
those errors are not parity or support evidence. A native run must inspect every
observation and prove object-context availability before interpreting the rest.

Preserve the exact prior 116-record functions source via named additions and an
exact inverse bound to its SHA/blob. Historical full 88-record replay stays bound
to its existing source/output. No fixture rewrites, comparator exceptions or
output truncation. Update tests that explicitly describe the current source to
project the exact prior source for their older checkpoint assertions; add full
current-source bootstrap tests. Existing trusted 24 inputs and six-output plus
provenance contract stay unchanged (functions source contents are the intended
input change). Native observed semantics, especially field reference aliasing and
private visibility, must precede final runtime code and support claims.

Non-goals: object creation API, common-module/global
platform contexts, import redesign, native diagnostic wording, malformed-syntax
exhaustiveness, reload/cycle changes, database object lifetime emulation.

## Scope review

Independent scope review found no blocker to this parser-only checkpoint. Local
Export rejection is a deliberate subset limitation, not a native grammar claim:
the guide calls that modifier meaningless inside routines. Reference semantics
are unmeasured. Existing known_table_receiver limits omitted-argument collection
methods through exported receivers; later runtime must test or explicitly limit
that path. The planned observation matrix has 15 records, including both private
read/write and undeclared read/write, with private storage recorded after errors.

Official object property reference:
https://1c-dn.com/library/using_script_tools_for_working_with_applied_objects/

The bootstrap local suite expects ThisObject-dependent probes to report error.
Fresh native output will differ until the measured implementation is added; this
checkpoint is not a passing native-parity feature and must remain Draft. All
prior records must retain their exact measured values. No native expected file
for the new records is generated by these tests.

## Approved runtime scope amendment, still pending native measurement

The final implementation will also require a narrow self-module receiver named
ThisObject / ЭтотОбъект. It will expose only the measured exported fields and
routines through the same explicit dispatch used for imports. Otherwise the
genuine 131-record native source could never be replayed in full by an import-only
implementation. This is core standalone-module state, not an emulation of a real
ExternalDataProcessor object, metadata context or platform object creation API.
No Python reflection, broad platform members, source adapter or native-only branch
is permitted. Imported module namespaces remain non-values under their existing
contract. The concrete self-receiver representation, unsupported value operations
and property-reference behavior require independent design review after the
native observations. Neither the discriminator nor this post-Create checkpoint makes a runtime change.


## Static versus Execute discriminator

Five additional guarded observations compare static field read/write, static
exported routine call, Execute field read and Execute exported routine call during
the same initialization phase. ErrorInfo().Description is inspected only to emit
fixed `field-missing`, `method-missing`, `other` or `none` classifications and a
boolean indicating the controlled member-name prefix. No raw description, path,
stack or object presentation is emitted. This diagnoses the core access route,
not native error-message parity. Runtime remains unchanged and fail-closed.

An exact inverse restores the entire audited 131-record source, blob
0c0cfae158f10fec2343992fbbc7642cd5ced6bc, SHA256
fe5334993790244908376e2768545b271a36b1a1a63cbf05452ce8be4b79d40c.
The prior116 and prior88 inverses remain exact. All six full outputs and 24 trusted
input bindings are unchanged in shape. Only functions.bsl changes a native input.

If static access works but Execute access fails, investigate the dynamic execution
context. If both fail, a separately reviewed explicit invocation after Create
returns is needed before drawing lifecycle conclusions. That discriminator did not change the launcher or establish a post-Create result.
The independently reviewed follow-on measurement design is described below.


## Explicit two-phase post-Create measurement

The first source line is exactly `// NativePostCreate: ExportProbeAfterCreate`
with LF termination. It is a narrow driver directive, not executable module code.
The complete source still runs its unchanged 136 initialization observations when
the external-processing object is created. Only after Create returns does the
explicit driver call the literal exported entrypoint `ExportProbeAfterCreate`,
passing the actual returned object. The module body never calls that entrypoint.
No generic method dispatch, source adapter, injected BSL suffix, native-only source
rewrite, or inferred public receiver is part of this design.

The entrypoint saves its argument in the private module variable
`ExportProbePublicObject`. It repeats all 15 original core probes through the
existing guarded ObserveExportProbe helper, prefixing each label with
`post-create.` and replacing both ThisObject and ЭтотОбъект receivers with the
passed object. Three independent guarded observations compare receiver identity,
read through ThisObject, and write 61 through ThisObject then read through the
passed receiver. Each observation resets the original scalar and collection
state using the existing helper. Failure of the identity probe cannot suppress
the remaining probes. Diagnostics remain bounded; no raw error descriptions are
printed by these observations.

The driver records a begin witness, then either a success witness after the
entrypoint returns or a bounded failure witness. A complete successful native
invocation has 156 records: the unchanged 136 initialization records, one begin
witness, 18 guarded observations, and one success witness. If the host cannot
access the entrypoint, 138 records are expected structurally: 136 initialization
records, begin, and bounded failure. Success of the invocation does not imply
success of any field/reference probe. These counts describe the measurement
protocol, not fabricated native expected answers. No post-Create native evidence
has yet been obtained; inspect every actual observation before implementing or
claiming runtime parity.

Only narrowly delimited declaration/helper blocks and the directive are new in
functions.bsl. Their exact inverse restores the complete prior 136-record source,
blob `259abc1315cbcca8642e1a49b44f4ac24a33500e`, independently computed SHA256
`c6b33e07818ce7e4abd8153feb3d8538d48737d5a543312b18f1fb8e7c5a65cd`.
Existing historical inverse routes automatically chain through 136 to 131, 116,
and the complete frozen 88-record source. LF/CRLF transport is normalized before
binding; genuine mutations to the old source, directive, or inverse boundaries
are rejected. No frozen source/output fixtures, output prefixes, comparator
exceptions, trusted-input inventory or runtime are changed by these probes.

Local Interpreter.execute of the complete source still emits exactly the old 136
rows for both target profiles because it does not invoke the post-Create entry.
This is only bootstrap evidence, not post-Create support or native semantics.
The explicit two-phase driver must be audited independently and the fresh native
capture checked before drawing lifecycle or public-context conclusions.


### Two-phase driver and security binding

The canonical directive must be the first source line. Both drivers reject a
malformed, unknown, misplaced or duplicate reserved directive before execution.
The native launcher reads the source once and derives both the complete generated
module and an actual JSON boolean from those bytes. It never sends an executable
routine name. The BSL launcher validates the boolean and calls exactly
`ОбъектТеста.ExportProbeAfterCreate(ОбъектТеста)` after successful Create. The host
uses the same persistent interpreter and literal
`ThisObject.ExportProbeAfterCreate(ThisObject);` only after source execution.

At the native ENTERPRISE boundary, the existing no-follow bounded reader validates
exact request keys, module/result paths and the source-derived boolean before the
process is started. No new provenance fields are needed: source/module hashes,
trusted launcher/template hashes, the fresh run nonce and full output hash bind
the deterministic phase witnesses. The 23 core trusted input names (24 with the
client probe), six outputs plus provenance, limits, isolation, cleanup and exact
comparison policy remain unchanged. Four existing trusted input contents change:
functions.bsl, test_launcher.py, the Launcher Form module and full_suite.py. The
host comparison-driver hash also changes. These are explicit reviewed harness
changes, not the earlier source-only discriminator.

A failed host entrypoint emits only its bounded failure witness and exits 3 with
no raw error text. It cannot produce a green comparison even if a native entrypoint
also fails. Unexpected Python failures are not suppressed. Offline mocks validate
control flow and request binding only; they are not native export evidence. The
native-form mock removes its one server compilation annotation solely in the
in-memory test VM, never from any generated/native source or captured artifact.

### Retaining native evidence when the post-Create host fails

The first post-Create checkpoint contained an artifact-export defect: comparison
correctly rejected the host's exit 3, but the later artifact constructor accepted
only matched/mismatched interpreter results. Independent offline reproduction
showed that this discarded otherwise validated native output bytes. A report of
native output hashes or counts alone is not a substitute for the missing rows,
and does not establish the post-Create semantics.

Run `39861289780` confirmed this failure path: its only artifact was the summary,
with `native_artifact_evidence_invalid`; native output upload was skipped. The
summary reported 156 native records and an output digest, but the six captured
outputs and provenance were unavailable. These metadata are not treated as
recovered observation bytes or semantic evidence. A corrected fresh capture is
required; the original run and summary remain part of the audit history.

The correction distinguishes a narrowly verified post-Create interpreter failure
from arbitrary interpreter errors. The finite comparison failure kind
`interpreter_post_create_failed` requires a hash-verified source with the canonical
directive, exit 3, empty stderr, and exact unique ordered begin/final bounded-error
witnesses. It remains an error with rejected acceptance and null interpreter
hash/size, mismatch and semantic evidence. Other interpreter failures, timeouts,
source changes and capture-integrity failures still cannot use this export path.

Artifact construction retains every existing native source/module/output hash,
nonce, provenance, cleanup, byte-limit and exact-inventory gate. The narrow error
path additionally checks the native phase boundaries and, for a completed call,
the eighteen ordered observation labels without assuming their values. It never
relabels failure as mismatch, invents interpreter hashes or accepts semantic
parity. Incomplete or malformed native phase evidence still fails closed.

This is an explicit finite failure-kind and artifact value-domain extension:
`comparison_status` may be this rigorously rejected error and its interpreter
hash/size may be null. The seven artifact files and JSON field layout remain
unchanged. The specific failure kind is present in the comparison summary, not
in the existing provenance case fields; audit both artifacts together with the
exact comparison-driver hash. Export-ready evidence remains independent of the
overall failed comparison and nonzero workflow exit.

## Audited post-Create observations

Fresh native run [39864376445](https://github.com/Atridis/yadinassi/actions/runs/39864376445)
at head `a8a6919a6c73363aa08b17bb9b037d0f1b3c57de`, tree
`163015d1a03b56dd69ca57eeac42c7435a3c5a07`, recovered the actual bytes.
Independent audit verified all 299 source files, synthetic parents/tree, both
artifact ZIP digests, the seven-file inventory, summary/provenance/driver binding,
all 24 trusted inputs, source/module hashes, fresh nonce, client and security/
cleanup witnesses, and existing bounds. Security conclusions are captured
tree-bound evidence, not a claim of independently observing the remote OS.

Linux 1C 8.3.27.1508 produced 156 functions records, 20,326 bytes, SHA256
`fd3ca42572f383cb7b87dad6401005234e2d50f1537753d1228a81ec26f6d6d5`.
The historical 136-record prefix and all other five native outputs were
byte-identical; the full-source inverse chain 136 → 131 → 116 → 88 remained exact.
Only the existing eight approved Map-order differences applied elsewhere.
The post-Create phase has the exact begin witness, eighteen observations, and
successful final witness. All observations retain the private variable at 19:

- The passed public receiver exists, and an unset exported variable is Undefined.
- Public read returns 11; public write/internal read returns 31; internal
  routine write/public read returns 43.
- The unexported first variable in a declaration list and its write both fail;
  the separately exported second entry reads 17. Unknown read/write also fail.
- Local shadowing returns 37 without changing the module's 11.
- Two references to the same public property alias live: after assigning the
  first parameter 23, the second sees 23 and the module holds 23.
- A Val parameter returns 41 while the module remains 11.
- Assignment through a reference survives a raised exception: the observation
  reports an error, but the module holds 53. This is not deferred copy-out.
- A shared collection mutation is visible through its exported field (count 2).
- The actual returned external-data-processor receiver equals ThisObject.
  ThisObject reads 11 and writes 61, visible through the passed receiver.

The same source's initialization observations still reject public fields and
methods. Both direct and Execute access fail there, so the distinction is the
measured lifecycle, not an Execute-only limitation. The callback itself is an
actual exported public method called on the object returned by Create.

This capture workflow deliberately still failed: its bootstrap interpreter
exited 3 with empty stderr, emitted zero post-Create observations, and retained
`interpreter_post_create_failed`, null interpreter hash/size and rejected
acceptance. The valid native artifact establishes semantics, not interpreter
parity or permission to merge that bootstrap head. No fixture or expected native
output was replaced to obtain these results.

## Runtime scope

The runtime uses one stable, opaque self-module receiver and one backing store
for declared variables. Per-name export metadata admits only exported fields
and routines through exact dispatch, including imported modules. Property
references use the measured live storage, including aliasing and exception
mutation. Private and undeclared members remain inaccessible; there is no Python
attribute fallback or general platform-object emulation.

The standalone interpreter models the observed lifecycle explicitly: its own
receiver exists during first module execution, but public access is unavailable
until that execution completes successfully. Later persistent execute calls can
use the ready receiver. Imported modules become ready after their existing
initialization completes; their cache, cycle checks, directory namespaces and
independent root-interpreter state are unchanged. Internal direct names remain
usable during initialization. This model is a deliberate standalone contract,
not a claim about every real platform module type or lifecycle.

ThisObject/ЭтотОбъект denotes the current owner unless explicitly shadowed by
ordinary existing bindings. Its unshadowed intrinsic binding is read-only.
Only exported fields and routines are exposed; platform methods, reflection,
string/type presentation and serialization of the receiver are outside scope.
The existing comment-based file import remains a project extension, not standard
1C import syntax. The native full-source probe and historical fixtures remain
unchanged by the runtime implementation.

Regression tests exercise the real unmodified post-Create source on the host.
They also retain the failed-host capture path using an explicitly test-only
source with the entrypoint's Export removed, rather than assuming that the real
feature must keep failing or fabricating observation rows. Native artifact
capture validity and successful interpreter comparison remain separate gates.

Local runtime replay uses the unchanged real host driver, the measured Linux
target, and the same UTC/locale contract against the independently audited
capture. All 156 functions records, including both phase witnesses, match the
native bytes exactly. The other five scenarios also retain their results.
Across all six scenarios, five whole outputs are byte-exact and collections uses only the eight pre-existing
approved Map-order equivalences. This local replay is not a fresh remote native
execution of the runtime commit; the latter remains a separate publication/merge
verification gate.
