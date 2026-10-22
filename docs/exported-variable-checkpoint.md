# Exported module variables: local design and checkpoint

Status: parser bootstrap published as Draft PR89, head
412582452f765839d2b99fdae1705cef067dcafe, tree
b362aa69ee4eff0313c48ec36ed6f49c82b63a77, based on merged main
7ca49d6725100f30afc5a24c14fb23e2cf7cfd3c. The present discriminator is local only.
Native run 39856163175 captured all 131 records on Linux 8.3.27.1508 and passed
independent evidence-integrity audit, but NOT exported-variable semantic parity.
ThisObject existed; every exported-field access failed. Internal routine writes
and local shadowing worked. Thus export visibility, initial Undefined, references,
Val, exception writeback and collection sharing remain unmeasured.

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

Current launcher creates an external-processing object from the complete source.
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
native observations. The present checkpoint makes no runtime change.


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
returns is needed before drawing lifecycle conclusions. This local source-only
discriminator does not change the launcher or invent that post-create result.
