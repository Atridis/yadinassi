# Experimental partial Catalog standard-property projection

The explicit oracle lane has accepted source-bound native evidence for the
existing owned Catalog fixture: external declaration key, Name, CodeLength2,
CodeTypeString and DescriptionLength0. See the original run/source identity below.
This remains a partial-prefix parser, not Interpreter or ordinary BSL CLI
database-object support.

The separate [identity-prefix experiment](config-catalog-identity-prefix.md)
adds opt-in embedded UUID parsing and its own owned binding lane. It does not
change this standard lane's contract or extend the native evidence recorded here.

`yadinassi.storage.config_catalog_name.project_catalog_standard_prefix(data, *,
budget, limits=None)` returns an immutable private `CatalogStandardPrefix` with:

| Field | Zero-based position | Admitted representation |
| --- | --- | --- |
| `name` | `[1][9][1][2]` | Existing nonempty Name scalar rules |
| `code_length` | `[1][17]` | Canonical bare nonnegative ASCII integer |
| `code_type` | `[1][18]` | Bare `0` (Number) or `1` (String) |
| `description_length` | `[1][19]` | Canonical bare nonnegative ASCII integer |

Only immutable decoded bytes and the caller's cumulative budget enter this
function. Expected XML values, names, declaration keys, UUIDs, paths, readers,
and platform APIs are not inputs. It performs no I/O and emits no public report.
The separate lane below compares independently verified XML. Its accepted native
evidence is limited to the original source and owned fixture below; synthetic
acceptance alone is not platform compatibility.

## Source facts and interpretation boundary

The three scalar positions are executable callbacks in pinned
[CatalogParser.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/CatalogParser.cs),
blob `67d3a6a23973301317c7d160e1adc35c41983e51`. They call `GetInt32()`.
Pinned [CodeType.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/model/enums/CodeType.cs),
blob `8af7c88bad2a9871e7618210d4f5f32e2c3f7483`, maps Number to0 and String to1.
These are implementation facts, not an official platform format specification.
This code was independently written; upstream implementation is not copied,
translated, adapted, or executed.

The numeric grammar is deliberately narrower than a general integer reader:
`0` or `[1-9][0-9]*`, at most10 digits, value at most2147483647. Quoting, signs,
leading zeros, fractions, exponent notation, non-ASCII digits, nulls, and
trailing whitespace are rejected. SP/CR/LF before a scalar are boundary
whitespace consumed by the walker. `max_length` can lower the admission bound
for the two lengths, including to0; it does not restrict the enum. This is not
an assertion that every admitted length is valid in1C, that2147483647 is a
platform field-length maximum, or that every excluded spelling is platform
invalid. Unknown enum values are outside this supported subset.

No claims cover embedded UUID, hierarchy, CodeAllowedLength, uniqueness,
autonumbering, arbitrary properties, full Catalog schema, applied CONFIG state,
references, object managers, or CRUD.

## Shared implementation, unchanged old contract

The existing Catalog metadata module owns both partial-prefix entrypoints.
The new cursor shares strict UTF-8 decoding, opaque scalar validation, Name
retention, and cumulative event charging with the old cursor. Its separate
fixed-path iterative walk visits all four fields once; it never first calls
the Name-only parser, never searches contents, and never constructs a DOM.
Opaque branches do not retain paths or scalar contents. Positional nulls are
not dropped.

The old `project_catalog_name_prefix`, its result/error/limit types and limits,
and its early stop after Name are unchanged. In particular, malformed later
fields can still be accepted by the old partial contract and rejected by the
new one. New limits are not silently accepted as old limits.

The new parser stops as soon as the actual comma or close-brace delimiter after
DescriptionLength is established, without consuming that delimiter. Remaining
bytes, parent closes and EOF are unvalidated. Missing earlier target fields,
wrong containers, or malformed visited text fail; invalid suffix bytes do not.
A returned result never certifies a complete well-formed Catalog document.

## Resource and privacy accounting

`CatalogStandardLimits` retains the old lowerable ceilings:4MiB input,
131072 events, depth64,1024 UTF-8 bytes and256 code points in Name. Effective
depth also intersects the shared budget's `max_tree_depth`. Length bound defaults
to2147483647; it accepts only exact integers, not bools.

Before cursor/stack/result allocation, the same caller budget is charged
`4 * len(data)` processing units and131072 representation bytes. Each opening,
closing, scalar or null event charges the cumulative token counter before
frame/scalar growth. Failed calls retain successful charges. No budget is
reset, replaced or refunded. The retained state is at most64 frames, a fixed
four-target path table with depth4,256 Name characters, four result values,
and bounded integer accumulators; skipped strings are not retained. The
representation reservation is conservative admission accounting, not measured
Python heap usage. The larger reservation is separate from the old Name
reservation of65536, which remains unchanged.

`CatalogStandardError` contains only a closed finite code, never raw input,
field values, paths or offsets. New diagnostics distinguish unsupported integer
syntax, integer admission overflow, and unsupported CodeType. The result and
source bytes are private; the separate oracle compares them privately and emits
only finite statuses/counts/hashes.

There is no added runtime file: the actual-main runtime inventory remains68.
No ordinary wire fields or caps change. The explicit DB lane has its own versioned
report and staged inventory below; old lane contracts and inventories remain closed.
Only the dedicated workflow selector changes. Combined core/DB acceptance is not established.

## Local synthetic acceptance

`tests/test_config_catalog_standard.py` uses invented positional inputs only.
It covers all four fields, both enum values, null positions, immutable results,
canonical grammar and admission limits, missing/wrong-type fields, UTF-8 and
Name bounds, opaque nesting, exact token/input/depth limits, retained failure
charges, reservation-before-allocation, suffix stopping, finite errors,
expectation-free signatures, and the old/new stopping-boundary difference.
Run it together with the unchanged Name and Catalog-reference tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_config_catalog_*.py' -v
```

## Explicit standard-binding lane

`--config-catalog-standard-binding` selects only
`owned_config_catalog_standard_binding_v1`, invocation19/report29/capture30.
It stages26 sources, replacing the Name policy with
`config_catalog_standard_binding.py` while keeping the same runtime parser
module. Other lane flags are mutually exclusive. The dedicated workflow selects this flag. The accepted run below, rather than
selector presence alone, supplies the bounded native evidence.

`ConfigCatalogStandardProfile` has recipe
`config_catalog_standard_8380_8192_v1`, SHA256
`984cd24e251525d9d4a11dcad373344ce95bd6af0d6b33d77f472e2d8922f0e4`.
One shared private lifecycle performs all reference guards, root/target reads,
and each remaining selected entry's chain/decode exactly once. The standard
parser receives that reader's existing budget, never expected XML facts.
Up to256 private key/result associations reserve262144 bytes before allocation,
in addition to each standard parser reservation. The Name-only wrapper retains
its original131072 association and65536 parser reservations. All late entry
failures poison chain/decoder state and prevent any returned partial evidence.

After native redump verification, the manifest independently extracts exact
namespace-qualified direct Name, CodeLength, CodeType, DescriptionLength nodes
and the external declaration key. Missing/duplicate nodes, attributes/children,
foreign-namespace shadows, unsupported scalar spellings and noncanonical length
values are rejected. It compares whole canonical XML, validates version/nonce,
and rechecks expected source-tree hashes. Raw metadata never reaches the parser.
The comparator receives the completed reader result only after all selected
entries finish, requires exactly one owned Catalog, and checks key, Name and
each of the three standard fields. Changing any one field rejects the result.

The existing owned fixture is only2/String/0. The accepted measurement establishes
that combination through the original source-bound producer; it does not establish
every length/enum combination merely because synthetic tests cover them. The old
Name-only run is not evidence for this new path.

Public projection adds only
`catalog_standard_validation="owned_code_description_matched"` alongside the
existing finite key/Name verdict. Raw key, Name and standard values are not
exported. Capture carries source/recipe/manifest hashes, not replayable XML or
a self-contained equality proof. All existing13 stages,11 snapshots,5
comparisons and4 cleanup gates remain mandatory. Failures discard captures
under the same lifecycle rules.

## Integrated serialized upper bounds

Measured using the production encoder and actual field/recipe/lane names:

| Envelope | Bytes | Existing cap | Margin |
| --- | ---: | ---: | ---: |
| Rectangular projection |2015|2048|33|
| Capture with full projection-cap allowance |3096|12288|9192|
| Complete report with full capture-cap allowance and newline |31852|32768|916|
| Finite failure-capture rectangular bound |118|12288|12170|

These are conservative structural upper bounds, not simultaneously valid native
observations. Full report accounting includes source26 inventory, all lifecycle
collections, optional diagnostics and their128-byte domain allowance, and the
existing full enclosing capture cap. Tests enumerate every policy diagnostic
and map every parser diagnostic, including new mismatch/resource/syntax paths;
all diagnostic/context domains fit their charged widths. No cap is raised, no
field is removed to fit. Integrated independent review, ordinary gates and the
frozen readiness/acceptance checker remain part of the acceptance process. The
dedicated result below satisfies only its stated original-source/fixture claim;
future changes need their own impact assessment and applicable gates.

## Narrow workflow-selector activation

The dedicated reviewed-branch workflow replaces exactly one
`--config-catalog-name-binding` token with `--config-catalog-standard-binding`.
Nothing else in that workflow changes: permissions, image access, exact-SHA
checkout binding, owner/repository/reviewed-branch admission, command ordering,
readiness gate and finite-report-only artifact publication are preserved.
The ordinary smoke and six-output workflows remain untouched.

Offline activation tests reverse that single selector replacement and require
the complete previous workflow SHA256
`17f9855ec28d8e09e0cc1e21f34e5901769f9ea2eec089850eaee93298e68b9c`.
They pin the reviewed standard policy/parser/reader source bytes, cold-import
the actual recipe, require schemas29/30 and26 staged files, preserve old
Name schemas27/28/recipe, and pin the approved image digest. Existing CI-policy
tests still assert exact job permissions, reviewed-ref/exact-SHA admission,
readiness and artifact gates.

## Accepted native evidence and exact scope

[Dedicated run40589978091](https://github.com/Atridis/yadinassi/actions/runs/40589978091)
was accepted at original source commit
`026bb4d6c28ae72f4178226c9e0243da80bde528`, tree
`58b68846e62c374b793bc7315382e48ee56ea1f7`. All619 source blobs and26 staged
sources were verified. Production final validation ran first, the independently
frozen checker second;413 actual-report negative controls were exercised.
All14 selected entries completed, with13 stages,11 snapshots,5 comparisons,
3 artifacts and all4 cleanup gates. Report SHA256:
`d99f44ffde394cc2ae39d95867dc9a5e79d306a8dcfbdc9f94a11498894b3870`.

The accepted claim is only the owned external declaration-key/Name binding plus
CodeLength2, CodeTypeString and DescriptionLength0 matched to independently
verified canonical owned XML through that pinned producer. No embedded UUID,
full Catalog schema/grammar, general length/enum coverage, arbitrary applied
configuration, runtime Catalog manager, or BSL CRUD support is established.
Manifest hashes are provenance, not separately replayable equality proofs.

[Ordinary run40589739416](https://github.com/Atridis/yadinassi/actions/runs/40589739416)
was independently accepted at the same original source with runtime inventory68
and whole138 values coverage. It is separate ordinary-runtime evidence, not an
expansion of the dedicated Catalog claim.

This documentation-only follow-up does not relabel either run as having executed
against a later commit. The local5666-test result (one unavailable-UNIX-socket
skip),17 launcher checks and fresh isolated wheel proof also belong to the
original executable inputs. Their applicability here rests on unchanged code,
tests, fixtures, build inputs, workflows and staged/runtime source inventories;
this paragraph does not claim those gates were rerun for the prose-only change.
