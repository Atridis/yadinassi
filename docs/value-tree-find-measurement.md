# ValueTree Rows.Find: bounded measurement inputs

This document describes the **measurement-only input layer** of 44 fixed
observations, not a native expected-output fixture. The subsequent bounded
implementation and its separate acceptance gates are documented in
[value-tree-find-runtime.md](value-tree-find-runtime.md). `ValueTreeRowCollection`
is the receiver, through root or child `Rows`; `Columns.Find` is a different API.
Existing FindRows behavior and package source/data files remain unchanged by this
measurement. The candidate incorporates main ca76e247 (PR #129), including its
standalone storage projection; the current runtime provenance inventory is 66.
The measurement also changes its aggregate digest through the pinned host and
comparison adapters. The initial 42-record capture used the older 65-file runtime.

## Primary usage evidence and open questions

1Ci-Company/Jet at commit `80884def67e2a75185452a6a13ff394075e457e0`
[constructs a ValueTree in MetadataTree](https://github.com/1Ci-Company/Jet/blob/80884def67e2a75185452a6a13ff394075e457e0/cf/Reports/RolesRights/Ext/ObjectModule.bsl#L1858-L1862)
and [calls Rows.Find with value, column name and True](https://github.com/1Ci-Company/Jet/blob/80884def67e2a75185452a6a13ff394075e457e0/cf/Reports/RolesRights/Ext/ObjectModule.bsl#L875-L878).
This establishes real API usage, not default recursion, traversal order, column
selection/coercion, scalar equality, invalid-input outcomes or reference lifetime.
Those questions require genuine native observations; FindRows and ValueTable
semantics are not substitutes.

## Fixed input matrix

The 44 records occupy ordinals 903–946. Every record creates a fresh six-node tree
using the unchanged existing TreeSearchFresh helper. Creation order is A, B,
B1, A1, A2, A11, whereas hierarchy is A→A1→A11/A2 and B→B1.
The descendant variant leaves A, B and A1 nonmatching, distinguishing traversal
orders without stating the answer. Cross-column input places a match in A.Group
and B.Key, distinguishing row-major from column-major search.

- RU/EN aliases; root and child receivers; explicit true/false and omitted flag;
  empty leaf; no match; descendant-only root/child search.
- Omitted, empty and Undefined columns; case-varied name; ordered/reversed
  two-column lists; whitespace; duplicate and empty tokens; unknown names on
  nonempty/empty receivers; known+unknown list and numeric column argument.
- Separate Number 1/Boolean True queries; string case/trailing-space queries;
  Undefined and Null cell values.
- Both result→original and original→saved-result mutation, using known ID 4.
- Missing value; Undefined/Number 1/String True recursion flags; invalid tree/row
  receivers; a genuinely empty tree and empty schema.
- Two supplementary descendant-only Number 1 / String "True" flag cases. These
  distinguish acceptance of the argument from its actual recursive effect.

No expected success, error, result ID or traversal order appears in these inputs.
Accepted native forms must be accounted for later, not dropped to obtain green CI.

## Observation and resource boundaries

The helpers distinguish setup-error, action-error, change-error and observer-error.
An action error still records source state. A successful action followed by a
mutation or observer error remains visibly different from a failed action.
No exception text, arbitrary object presentation or tree serialization is emitted.

A row result projects ID 1–6, parent ID, level, same-tree owner and bounded mark.
Other types retain explicit tags via the existing bounded observer. Source state
records all six known Id/Key/Group/Mark cells and seven collection counts. The two
empty setups use explicit rows/schema counts instead of reading detached rows.
Mutations prove live-reference behavior in both directions; ID equality alone
does not establish reference identity.

Each complete ASCII record has a conservative 2048-byte bound including label,
worst-case bounded cell state, result and status delimiters. Local instrumentation
uses an explicit stub returning the known A1 input node independently of query,
columns and recursion. It tests routing/observation, not a search algorithm or
native parity. Unimplemented local Find errors are not golden answers.

## Exact source and historical evidence

The baseline collections902 is 327655 bytes / 4241 lines, SHA256
`5468d16850a9774251d4ef80ae5e938afdfabef69fe496cb3a6cb579d0564782`.
New helpers are inserted before the executable body and calls appended. The
exact source-only inverse removes precisely those two blocks and restores every
baseline byte; an old-source byte-prefix claim would be incorrect.

Current collections946 has 4360 lines, SHA256
`9de2d85c0b8409b83ccf62e4824ef7a8186518d0bdffc92b53bd98b1f98da0b3`.
The pinned adapter has 126 declarations/endings, 16 message sites and zero-based
body line 3099. Independent helper/call hashes reject altered probe text even if
the outer source hash is rebased. Generated full-client module SHA256 is
`9edae1c1032ef2e98895e53269a7e4be294a282b42ce4abddcf3b65f44dc0035`.

A new isolated test-only harness inverse restores the unchanged main 4267 harness
before the existing FindRows and older history layers. Old inverse files, native
fixtures and the 36 FindRows native literals remain unchanged. Historical sources
do not become live-admissible. All 44 new records, including result ID/order
changes, are byte-exact; the existing eight Map-order exceptions are unchanged.

Current runtime inventory is 66; staged inputs 24 and scenarios 6 remain unchanged.
The 8192-byte
finite wire and 32768-byte public report caps are not raised. Complete serializer
matrix validation remains a required local gate, not an inferred consequence of
the three-digit message count.

## Acceptance gate

Obtain genuine native server/client output for this exact source, authenticate
run/head/tree/input provenance and all output bytes, and inspect every new record.
An expected comparison failure while Find is absent is still a failed workflow,
not measurement acceptance or runtime parity. The subsequent bounded implementation
must pass fresh native and four-platform checks. No Copy/Sort, schema broadening,
indexes, detached-row lifetime, codecs, transport or workflow changes belong here.

## Initial 42-record capture and supplementary flag inputs

Native run 40461349726 at head e77c74fd7a3457f09f0c018ead102488c0449d7b
(test merge aa44eb78d61784b5f4f2f280fa8432afee4717c8) captured all 42 original
records: 34 successes and 8 action errors, with no setup/change/observer failure.
The authenticated workflow failed only the collections host comparison; it is
not runtime acceptance. The old 902 native prefix is unchanged, but that fact
alone does not independently replay old host parity.

Both numeric 1 and string "True" recursion arguments were accepted; their original
inputs immediately matched a root row and therefore did not prove recursive
behavior. The two new descendant-only inputs close precisely that coverage gap.
They require a fresh capture at the new 44-record source; old 42 output may not be
relabeled as evidence for them. Original 42 helper/call inputs remain unchanged.
