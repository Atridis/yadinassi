# ValueTree.Copy: proposed native measurement (not native evidence)

Status: the closed profile is published as a Draft; native runs have diagnosed
an observer Rows-access equality assumption, not completed Copy semantics. See
[the current versioned profile contract](value-tree-copy-profile.md). The original preparation did not implement Runtime Copy. The design below records the historical preparation sequence;
The subsequent [runtime follow-up](value-tree-copy-runtime.md) now has genuine
nine-case evidence; its fresh runtime gates remain required. This plan and
its standalone bounds are historical, while the current TC-C2 contract uses
structural Rows-owner labels and a separate authenticated access probe.

## Source and supported question

Official EDT 2026.2 primary documentation:
<https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar>

Archive SHA-256:
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
Pages `nl/{ru,en}/html/SyntaxHelperContext/objects/catalog234/catalog264/ValueTree/methods/Copy671.html`.
The documented method is `ValueTree.Copy()` / `ДеревоЗначений.Скопировать()`:
no parameters, result type ValueTree. Documentation describes a full tree copy;
it does not settle identity/aliasing of mutable objects stored in cells.
Do not import ValueTable.Copy parameter/filter semantics. Sort is a separate task.

Preparation baseline: PR145 head
`2f7c77369b2c41bdfda9bc5d6c0bef38e38cdd22`, tree
`d6da4f24b33cd4cc2f74c7d528aa52b7240a8bf0`.
The existing tree-v1 observer, its 34 records, and negative FillValues API
controls must remain byte-identical. Rebase/integrate after PR145 merges.

## Smallest useful closed scope

Use fresh input per case, one invocation under measurement, and separately
recorded observation/mutation failures. Never turn observer failures into Copy
exceptions. The standard fixture has two root rows, one child and grandchild,
and three columns: untyped Payload, typed Number, typed String with non-default
qualifiers. Distinct small integer/string sentinels encode every row and column.
All calls use zero arguments except the explicit arity probe.

| Case | Input and action after Copy | Required observations |
| --- | --- | --- |
| 1 | Empty tree, English alias | Result type, tree/Columns identity, structural Rows-owner label, empty shape |
| 2 | Schema-only tree | Ordered names, titles, widths, type sets and qualifiers; distinct column objects |
| 3 | Standard hierarchy, no mutation | Preorder/order, values, Owner, Parent, Level, collection parents, pairwise row identity |
| 4 | Standard hierarchy; change copied then source scalar cells | Both trees after each write; retain original node handles |
| 5 | Standard hierarchy; add copied child, delete copied other root; add source root, delete source child | Both shapes after each operation; survivor identity; descendant deletion |
| 6 | Schema-only; change copied column name/title/width, then source metadata; add/delete columns each side | Both ordered schemas and retained column identities at every step |
| 7 | Shared Array in two source rows and a distinct equal-content Array in a third | Registry identities before/after Copy; mutate through copied shared cell then original shared cell; all cells each time |
| 8 | Standard hierarchy, Russian alias | Same complete observation as case 3, independent source |
| 9 | Standard hierarchy, `Copy(1)` | Original-handler classified outcome and source unchanged; unexpected success fully observed |

Case 7 must include an Array nested inside the shared Array and mutate that
nested object separately. This distinguishes copying the outer mutable value
from recursively copying its contents. Record both outer and nested identities.
The result must not be pre-labelled shallow or deep. These bounded observations
support only the tested mutable types; do not generalize them to every 1C object.
A later separate Structure/Map/native-reference probe may be needed if runtime
implementation would otherwise generalize beyond the measured Array behavior.

Both aliases have positive zero-argument coverage. The extra-argument case is
not a documentation-derived expected result: native behavior is the oracle.
Copy return type and receiver non-mutation are observed even on failed calls.

## Positive calibration and exception boundaries

Before measurements, exercise existing Count/Get, typed column construction,
Owner/Parent/Level and scalar writes. Calibrate equality using same-object aliases
and distinct objects with equal contents, for trees, rows, columns, Arrays and
nested Arrays. Source fixture snapshots must match a fixed baseline before Copy.
Calibrate metadata setters and row add/delete on an independent known tree.
Failure of these controls invalidates the run rather than proving Copy semantics.

Within the original Copy exception handler, immediately assign
`PrivateDescription = ОписаниеОшибки()` before entering another try block or
calling any helper. Classify that captured string to a small public enum; never
publish raw localized exceptions, filesystem paths, configuration or user data.
Observation and mutation each have a separate status and fixed diagnostic site.
A failure reading the result is not allowed to look like an unsupported method.

## Bounded transport proposal

Do not append this to the existing 6107-byte tree-v1 capture (2085 bytes remain).
Introduce a separate fixed `tree-copy-v1` profile, source path and SHA pin. Keep
old `tree-v1` available and run it unchanged as a regression. Reuse staging,
server/client execution, provenance and cleanup machinery; do not accept an
arbitrary source path, user-supplied module, profile name, or runtime code.

Proposed wire budget, to be enforced by the observer and strict decoder:

- 1 calibration record, at most 128 bytes including framing/newline.
- 9 numbered case records, at most 768 bytes each including framing/newline.
- At most 7040 output bytes (128 + 9 * 768), below existing MAX_OUTPUT 8192.
- Values use a closed scalar vocabulary and append-only identity registries.
- Fixed ordered fields: invocation outcome, observation status/site, return type,
  before-source, after-source, after-result, then explicitly ordered mutation
  snapshots as applicable. No JSON/free text/private error messages in BSL output.
- Case-specific record grammar; exact record count/order and one trailing LF;
  reject CR, duplicate/missing records, non-ASCII, malformed/unknown enums,
  identity references preceding allocation, impossible lengths and trailing data.
- At most four rows initially, five transiently, four columns transiently, and
  six mutable-cell identities. No truncation or digest-only replacement for
  observable values/identity. Every growth must fail closed at the declared cap.

These are proposed bounds, not a verified encoded observer size. Before a
native submission, generate actual maximum valid records, prove each fits 768,
then prove the rendered server/client modules, input inventory, complete report
(32768), marker (16384), and transport envelope (65536) retain their existing
limits on LF and CRLF sources. If concrete records cannot fit without losing
observations, split Copy into two fixed shards; do not raise caps or omit fields.
Metadata qualifiers and all mutation snapshots are specifically non-negotiable.

## Local and native acceptance sequence

1. Implement standalone BSL observer and strict decoder; keep runtime Copy absent.
2. Unit-test valid synthetic records and negative grammar, identity, size and
   provenance cases under normal Python and `-O`. Synthetic data is not native
   evidence and must be named accordingly.
3. Run the local interpreter only to verify parsing/calibration and honest
   unsupported Copy outcomes. Do not require equality to fabricated native data.
4. Integrate the closed profile through staged runner/host/workflow and prove
   source inventory, server/client modules, raw CRLF budgets, isolation and cleanup.
5. Parent publishes only after PR145 integration and authorized gates. Obtain
   native server/client outputs, exact current source/run/artifact provenance,
   cleanup and independent validation. Retain raw private data only in existing
   protected artifact handling; expose only bounded public records.
6. Use genuine accepted observations to design the runtime Copy implementation
   as a separate logical follow-up after measurement review. The required Copy
   job stays red until positive availability and runtime parity are proven; the
   parent may add follow-up commits to the same Draft before merge. Replace the
   existing Copy rejection test only with that implementation. Add identity,
   hierarchy, qualifiers, mutation isolation, arity and resource-limit regressions.
   Rerun unchanged FillValues negative controls and ordinary six-output suite.

No local full suite or shared `/tmp/onec-smoke` reservation is claimed here.

## Standalone prototype checkpoint (local, not native)

The standalone `integrational_tests/measurements/tree_copy.bsl` and
`scripts/native_1c_tree_copy_contract.py` now implement the nine cases. Structural
add/delete operations each have a separate source/result snapshot, as do source
and copied outer/nested Array writes. Cases 1–9 have respectively
3, 3, 3, 7, 11, 15, 11, 3, 3 successful snapshots. Scalars include Number,
String, Boolean, Null and Undefined. Dates and other mutable cell types are not
covered by this prototype.

The earlier uniform 768-byte record proposal is superseded by exact
case-specific bounds. For C columns and R rows, a snapshot occupies
`5 + 13*C + R*(6 + 6*C)` ASCII bytes. Maximum C/R are respectively
0/0, 3/0, 3/4, 3/4, 3/5, 4/0, 3/4, 3/4, 3/4. The complete maximum **accepted
synthetic** output is exactly **6745 bytes**, including all prefixes, separators,
calibration and LF terminators. The tests construct and decode that maximum;
this is not an assertion that a real tree reaches every independent maximum.
No transport or output cap was increased. Compact ASCII JSON marker round-trip
is tested below the existing 16384-byte marker limit. Generated modules, full reports and transport are now covered by synthetic
integration and structural bounds. Actual native serialization remains unverified.

Current runtime legitimately returns missing-method class M for all nine cases
and passes the positive calibration, producing 2002 bytes. Synthetic test-only
method injection exercises successful deep, shallow, outer-only and identical
receiver behavior without changing runtime code. The nested and outer identity
registries and mutation records distinguish those hypotheses. Synthetic success
is not native support or evidence of which semantics 1C uses.

Observer failures emit only bounded `X` plus stage (B/I/O/M), and the decoder
rejects them rather than accepting a Copy error. Wrong documented result type,
unsupported vocabulary, over-cap data or broken collection-parent invariant
therefore make the run inconclusive, not a semantic conclusion. No private
exception description is emitted. Case/source pins, fixed-profile integration
and provenance envelopes are now covered by synthetic integration tests. Genuine
native acquisition and semantics review remain pending; see the current profile
contract for the positive-availability controls and required parity gate.
