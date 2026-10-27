# ValueTree Rows.Find: bounded measurement inputs

This is a **measurement-only** addition of 42 fixed observations, not a Find
implementation or a native expected-output fixture. `ValueTreeRowCollection`
is the receiver, through root or child `Rows`; `Columns.Find` is a different API.
Existing FindRows behavior and all 59 package source/data files remain unchanged.
The runtime provenance inventory count stays 65, but its aggregate digest changes
because the pinned host and comparison adapters are updated.

## Primary usage evidence and open questions

1Ci-Company/Jet at commit `80884def67e2a75185452a6a13ff394075e457e0`
[constructs a ValueTree in MetadataTree](https://github.com/1Ci-Company/Jet/blob/80884def67e2a75185452a6a13ff394075e457e0/cf/Reports/RolesRights/Ext/ObjectModule.bsl#L1858-L1862)
and [calls Rows.Find with value, column name and True](https://github.com/1Ci-Company/Jet/blob/80884def67e2a75185452a6a13ff394075e457e0/cf/Reports/RolesRights/Ext/ObjectModule.bsl#L875-L878).
This establishes real API usage, not default recursion, traversal order, column
selection/coercion, scalar equality, invalid-input outcomes or reference lifetime.
Those questions require genuine native observations; FindRows and ValueTable
semantics are not substitutes.

## Fixed input matrix

The 42 records occupy ordinals 903–944. Every record creates a fresh six-node tree
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

Current collections944 has 4358 lines, SHA256
`d94101cf391fa84668b7f94bb9295655d62d3ff6baa084de17a48b62966a0901`.
The pinned adapter has 126 declarations/endings, 16 message sites and zero-based
body line 3099. Independent helper/call hashes reject altered probe text even if
the outer source hash is rebased. Generated full-client module SHA256 is
`a5baef77652eb400fb871c820d48ac5497cbec4fac6559dffc74128e01aa6a7d`.

A new isolated test-only harness inverse restores the unchanged main 4267 harness
before the existing FindRows and older history layers. Old inverse files, native
fixtures and the 36 FindRows native literals remain unchanged. Historical sources
do not become live-admissible. All 42 new records, including result ID/order
changes, are byte-exact; the existing eight Map-order exceptions are unchanged.

Runtime inventory 65, staged inputs 24 and scenarios 6 remain unchanged. The 8192-byte
finite wire and 32768-byte public report caps are not raised. Complete serializer
matrix validation remains a required local gate, not an inferred consequence of
the three-digit message count.

## Acceptance gate

Obtain genuine native server/client output for this exact source, authenticate
run/head/tree/input provenance and all output bytes, and inspect every new record.
An expected comparison failure while Find is absent is still a failed workflow,
not measurement acceptance or runtime parity. A subsequent bounded implementation
must pass fresh native and four-platform checks. No Copy/Sort, schema broadening,
indexes, detached-row lifetime, codecs, transport or workflow changes belong here.
