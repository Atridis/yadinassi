# ValueTree.Columns.Clear: standalone lifetime measurement

This is an observer/decoder proposal, **not a runtime implementation or a native
result**. The current nonempty-tree Clear guard and last-column Delete guard
remain unchanged. `ValueTree.CopyColumns` is not part of the pinned API inventory;
it must not be invented by analogy with ValueTable.

## Primary API membership

The official SyntaxHelper specifies `Clear()` / `Очистить()` with no arguments,
available since 8.0 on server, thick client, external connection, mobile
application server and mobile standalone server. Clearing columns also deletes
rows. The documentation does not establish the lifetime of retained row, column
or collection references.

Pinned official archives, inspected directly rather than inferred from Table:

- <https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar>
  SHA256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
- <https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_v8_3_27_1.0.400.v202609220822.jar>
  SHA256 `c140925e80ad3a64b528b70a362ff6709f43e65b3e39e9736bad0d5e482d79f6`.
  This overlay has no ValueTree replacement entries.

Entries under `nl/{en,ru}/html/SyntaxHelperContext/objects/catalog234/catalog264/`:

| Entry | SHA256 |
| --- | --- |
| EN `ValueTreeColumnCollection/methods/Clear690.html` | `98a7a97dd326195fdec20bc641823ea970a77682124c3325d74517e8eb83868e` |
| RU same entry | `f99f862202ea876bda7aefbf6f3ae7370cc92c2f9745c161943f8ccc4a6a687d` |
| EN `ValueTree.html` | `73a96d73e27655d62d87937bd9667c4199f21042427348f8a49fa6cb883bf6f6` |
| RU `ValueTree.html` | `273cd46b6e17d56255a071a03a5ac628d925d909e2668205d4b7519bcab68c1e` |

The ValueTree inventory contains ChooseRow and Copy, not CopyColumns; the latter
exists only in the ValueTable subtree of this archive.

## Twelve fresh fixtures

| Case | Operation |
| --- | --- |
| 1 | EN Clear on two columns and three nested rows; required availability control |
| 2 | RU Очистить on the same nonempty shape; required availability control |
| 3 | Clear an entirely empty tree |
| 4 | Clear a schema-only tree |
| 5 | Clear a one-column nonempty tree; not last-column Delete |
| 6 | Repeat Clear, retaining separate first/follow-up outcomes |
| 7 | Clear with an extra argument |
| 8 | Invoke Clear in an expression and observe any bounded result |
| 9 | Clear, then write through the retained original root row |
| 10 | Clear, then Add through the retained original child collection |
| 11 | Clear, then Add through the retained original root collection |
| 12 | Clear, then rebuild through retained collection handles |

The active tree and retained handles are observed independently before and after
the action. The observer does not assume that old references die, remain usable,
retain their owners, or become reattached. It does not assume rollback after any
error, including a failed follow-up mutation. Fresh fixtures prevent cross-case
state from deciding an outcome.

Each retained query catches its original operation error before any helper runs.
Unsupported serialization is an observer failure, not a fabricated query error.
No raw exception descriptions enter the capture. Collection handles are labeled
by the structure from which they were obtained; native wrapper equality is not
used as collection identity. Tree/row/column identities are bounded registry
observations, and new valid identities are not normalized to old ones.

Only the original root and child have retained-row query vectors; exhaustive
lifetime behavior for every descendant, arbitrary values, UI contexts and
last-column Delete are outside this initial measurement. Active traversal still
records bounded descendants, schema metadata and independent named/positional
cell associations.

## Admission and execution scope

Both nonempty EN/RU controls must succeed. Matching absence or errors never
constitute availability. A decoder accepting a bounded capture is distinct from
native acquisition acceptance and from runtime parity.

This standalone candidate leaves every existing source/profile/runtime byte
unchanged. A future integration requires independent review, exact capture and
complete stage/transport/host/marker bounds, fixed dispatch through the real
embedded emitter, cold staged dependency closure, and Windows synthetic-fixture
checks. Existing limits remain 8192 capture bytes and 16384 marker bytes; no
limit increase or additional credentials are permitted. No native run is claimed.

## Wire and constructive standalone bounds

`CC-C1` calibration precedes exactly twelve ordered case records. Each record
contains separate initial/follow-up statuses, the bounded follow-up phase, an
expression-result token when applicable, and before/after snapshots. Rebuild
phases identify add-column, add-row, write, add-row, write without inferring
rollback. An unattempted follow-up differs from a failed one.

A snapshot admits at most three columns and five reachable rows, complete bounded
column metadata, independent reported Parent/Owner/Level, and independent named
and positional cell sequences. Twenty-four retained queries describe root/child
identity, owner, parent, level, cells and child counts; original-column identity,
name/title/width; and original collection counts/parent or first-column access.
Access/comparison failure `E_`, absent fixture reference `A_`, and actual Undefined
values are distinct. Numbers are bounded integers -9..9; names/strings have fixed
vocabularies. Other values are explicitly unsupported observations, never evidence
of method unavailability or retained-reference invalidity.

A shared, typed per-case identity registry admits up to 62 identities, including
new valid identities and different reported owners. Collections themselves never
enter that identity registry. Active preorder child counts encode reachability;
reported parents/owners/levels are not forced to match traversal position.

For `c` columns and `n` rows, the snapshot majorant is
`3 + 13*c + n*(5 + 4*c) + 48`, at most **175 ASCII bytes**. A constructive maximum
capture is **4406/8192 bytes**. The prospective completed marker is **4559 bytes**
compact, or **4620/16384 bytes** allowing spacing, escaped slashes and BOM. These
are standalone proofs only; complete integrated host/transport/stage bounds must
be recomputed before profile integration. Tests exercise divergent synthetic
lifetimes, partial mutations, replacement identities, equality failures and
unsupported domains; none is labeled a native answer.
