# Columns.Move boundary clarification: fixed measurement, no runtime change

## Why a separate capture

The authenticated initial 28-case measurement from
[run 41030064575](https://github.com/Atridis/yadinassi/actions/runs/41030064575)
(head `e8c02167fb3dd522541927bc96aafb3deaaf424b`) supplied identical server/client
7480-byte captures, SHA256
`2a691dda9e209583781d356a142f8866e057400bebfc6f83a5d39581d27b727c`.
Acquisition, provenance and cleanup passed; runtime parity correctly failed
because the method is absent. This is not runtime acceptance.

Those cases show last-column +1 and same-tree deleted-column +1 succeeding
without changes, negative fractional selector -0.5 selecting index zero, and
string-name/string-offset/Boolean-offset successes. They do **not** establish a
universal clamping rule or whether deleted selectors bypass offset conversion.
The separate probe avoids a runtime implementation with fixture-specific rules.
The documented API membership is unchanged; see the primary SyntaxHelper
references in [the initial observer](value-tree-columns-move-measurement.md).

The original 28-case BSL, decoder and generated modules remain byte-identical.
No Clear, last-column deletion, runtime type, runtime method or numerical
conversion implementation changes are included.

## Exact fresh cases

Every case uses the initial three-column, five-row fixture (two roots, two
children and one grandchild), with distinct numeric cells, and a retained
same-tree deleted column. Every probe calls the normal fixture explicitly;
case numbers do not select the initial observer's empty/singleton variants.
All cases independently record schema/identities and positional **and** named
cells before and after; neither sequence is normalized to the other.

| Case | Operation |
|---|---|
| 1 | EN Move(1,1), availability control |
| 2 | RU Сдвинуть(retained middle column,1), control |
| 3 | first column +3: destination equals column count |
| 4 | middle column +2: destination equals count |
| 5 | last column +2: destination equals count+1 |
| 6–10 | deleted column with 0, -1, 1000000, string bad, Undefined |
| 11 | middle column -1.9 |
| 12 | first column -0.5 |
| 13 | last column +1.9 |
| 14 | middle column, string 2 (paired with case 4) |
| 15 | middle column, string bad (paired with deleted case 9) |
| 16 | middle column, string -1.9 (paired with case 11) |
| 17 | middle column, Boolean False (initial capture already measures numeric 0) |

These are questions, not expected native answers. Independent snapshots retain
post-error mutations and newly observed identities. Original exception capture
precedes every helper; output contains only the finite bounded vocabulary, not
raw exception text. The same strict graph/identity/cell decoder is reused by a
thin fixed sibling adapter; no old decoder grammar is modified. S/M/A/O are valid
action outcomes. E is not part of this probe. Both first controls must be S;
matching missing-method output is never availability evidence.

## Closed integration and measured resource bounds

Profile `tree-columns-move-boundary-v1` fixes source, hash, decoder, 18 messages,
case `tree_columns_move_boundary`, and distinct artifact namespace. The source
inventory has exactly **23** entries: the usual 22 plus the explicitly bound
unchanged initial CM contract needed by the adapter. Imports are fixed-path and
lazy; old staged inventories do not acquire an unused new dependency.

One literal matrix entry reuses the existing job definition and security gates.
It **does run an additional job/container**; no claim of zero execution
duplication is made. This exploratory lane is justified to obtain missing
semantics; ongoing coverage can be reconsidered after the facts are known,
without weakening the present acquisition or parity gates. No dispatch input,
arbitrary path, alternate credentials or enlarged report cap is introduced.

Constructive capture maximum: **4779/8192** bytes. Completed marker:
**4950 compact; 5031 escaped/spaced/BOM upper /16384**. Registered generated
server/client modules are 14329/18530 bytes. The absent-method local capture is
4779 bytes; it is not native evidence.

| Integrated structural majorant | Bytes | Existing cap |
|---|---:|---:|
| Stage | 4352 | 8192 |
| Native | 9478 | 32768 |
| Transport (reserves 8192-byte capture) | 20706 | 65536 |
| Host | 15186 | 32768 |
| Provenance | 14974 | 32768 |

The actual embedded Python emitter is exercised for every fixed mode, including
the new boundary token. Omitting either its admission set or routing set is a
negative control. Unknown, duplicate and mixed routes reject; old false/Fill/
Copy/Sort/Columns.Move routes retain their output. Actual producer-to-host tests
cover failures, unavailable controls, CRLF/hash rejection and canonical UTF-8
synthetic fixtures. No shared native fixture is executed by these tests.

All four existing tree observer/client modules, full_suite.py, runtime source
inventory (78), cleanup and security settings remain unchanged. Fresh native
acquisition and independent review are required before any runtime conclusion.
