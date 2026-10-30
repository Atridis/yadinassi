# Final six-case Columns.Move clarification — measurement only

## Evidence and remaining question

The initial 28 cases and subsequent 17 cases have authenticated acquisition,
positive EN/RU availability, exact server/client output and cleanup. Runtime
parity remains rejected because Columns.Move is not implemented.

* Initial run 41030064575: 7480 bytes, SHA256
  `2a691dda9e209583781d356a142f8866e057400bebfc6f83a5d39581d27b727c`.
* Boundary run 41034467262, head `72f16f84cd46c4c69e71c199bf669e92329bf4b9`:
  4779 bytes, SHA256
  `f19dee0a3f8ec4cb718902b2e259ee8c269ffd4d89803289dce73e5c62b150ad`.

A live destination equal to Count succeeds without reordering, while Count+1
fails. Fractional numeric/string offsets truncate in the observed pairs.
A same-tree deleted column with offset +1 succeeds without changes, but its
0/-1/1000000/bad-string/Undefined offsets fail. A plausible unified model uses
an index of -1 for the owned deleted column, validates destination in 0..Count,
and only permutes live source columns. This is a hypothesis, not established
behavior for deleted +2/+3/+4/+5. The tail measures those remaining boundaries
instead of adding a hard-coded exception for +1.

## Exactly six independent cases

Every fixture has the same three remaining columns and five rows as the first
observer; a temporary fourth column is deleted and its reference retained.
No native outcome is assumed.

| Case | Call |
|---|---|
| 1 | EN Move(1,1), positive availability control |
| 2 | RU Сдвинуть(retained middle column,1), control |
| 3 | deleted column,+2: hypothetical destination 1 |
| 4 | deleted column,+3: hypothetical destination 2 |
| 5 | deleted column,+4: hypothetical destination Count |
| 6 | deleted column,+5: hypothetical destination Count+1 |

Snapshots independently retain actual schema/column/row identities, hierarchy,
positional values and name-resolved values before and after. Post-error changes
are recorded; rollback is not assumed. Fixed scalar/schema bounds remain those
of the unchanged initial CM grammar: at most three columns and five rows.
A hypothetical reinsertion producing four columns is **outside this observation
domain**, yields a rejected observer failure, and cannot be interpreted as proof
that native reinsertion is absent. Synthetic tests cover that fail-closed path,
as well as observable no-op versus rejection and changed identities/cells.

Both first controls must have S status; identical missing-method results never
pass availability. Original exception capture precedes helpers, and raw errors
are never exported. Unsupported observations stop acquisition instead of being
normalized into expected answers.

## No additional exploratory job

The immutable `tree-columns-move-tail-v1` registry entry binds its own source,
contract, six cases plus calibration, schemas and artifact namespace. It replaces
`tree-columns-move-boundary-v1` in the literal existing CI matrix: Copy, Sort,
original Columns.Move, and tail remain the four matrix entries, with Fill's
separate job unchanged. **The job/container count does not increase.**

The old 17-case source, decoder, generated modules and authenticated capture are
preserved for offline exact runtime regression; the original 28-case lane stays
active. The old boundary profile remains a closed known identity, not an arbitrary
dispatch option or a second scheduled exploratory lane. No full-suite duplication,
new credentials, security refactor or dynamic source selection is introduced.

The fixed sibling CM decoder is an explicit dependency in the 23-file staged
inventory. All six registered tree routes are lazy and finite. Actual embedded
emitter tests cover admission and emission sets separately, unknown/duplicate/
mixed modes, byte-identical prior modes, and producer-to-host transport. Source
hash guards remain strict; Windows tests use explicit UTF-8 and canonical LF
synthetic fixtures without normalizing production inputs.

## Proven bounds and next gate

Capture maximum **1691/8192 bytes**; completed marker **1836 compact /1873
conservative escaped+spaced+BOM /16384**. Actual registered modules are 13447
server /17643 client bytes. The local unimplemented capture has 1691 bytes of
missing-method observations; it is not native evidence.

| Integrated structural majorant | Bytes | Existing cap |
|---|---:|---:|
| Stage | 4328 | 8192 |
| Native | 9454 | 32768 |
| Transport, reserving full 8192-byte capture | 20670 | 65536 |
| Host | 15134 | 32768 |
| Provenance | 14926 | 32768 |

All five preceding tree observer/client modules, runtime inventory (78), and
full_suite.py remain unchanged. No Clear or last-column deletion guard changes.
After independent review and this last acquisition, implement the evidence-backed
general model and replay the complete old 28, old 17 and new six captures.
Contradictory or unsupported observations must be investigated, not guessed.
