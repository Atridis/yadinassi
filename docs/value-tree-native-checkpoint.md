# ValueTree initial native checkpoint (unmeasured candidate)

## Scope and route

Append twelve scalar records to the existing `collections` scenario. The four
nodes have depth at most two. This does not serialize trees, transfer trees
between contexts, create application data, or access external resources.
The unchanged normal owner-authored same-repository PR targeting `main` admits
its merge revision to `.github/workflows/native-1c-isolated-smoke.yml`.
The existing server EPF and managed-thick-client adapter execute the whole source.
No dedicated `codex/native-file-db-oracle-reviewed` operation is involved;
that operation was denied and remains pending separate user authorization.

No workflow, package permission, network restriction, mount, image digest,
security gate, output allowlist, timeout or fixed byte cap is changed.
The client-probe marker is not extended: its wire reserve is only seven bytes.
Source hash, exact source line count (4000), and collections record count (866)
are re-pinned together. The original 854-record source is an exact byte prefix.
The existing eight typed-Map exceptions and their ordinals are unchanged;
all twelve tree records require byte equality, not new tolerances.
A separate exact block hash rejects probe edits even if the outer hash is rebased.

## What the twelve native records establish

1. Constructor and four-node setup success.
2. Type names of tree, rows, row, columns and column.
3. Root versus child counts, indexed and method row access.
4. Root/child/grandchild levels, including RU/EN method names.
5. Parent identity and whether row Owner is the tree.
6. Row-collection Parent identity, including root collection.
7. Column added after rows: name, title, width, numeric descriptor and defaults
   observed on existing root/grandchild rows.
8. Typed string assignment and numeric indexed assignment.
9. Cell RU/EN Get/Set and sibling-local IndexOf.
10. Deleting one of two shared columns while preserving another cell.
11. Clearing children without deleting root siblings.
12. Reading a retained grandchild reference after ancestor-collection clear.

Each group catches errors and emits only `error`, never native exception text.
The actual native scalar values are the evidence. The offline candidate output
is neither a native expected result nor proof of API correctness. A native
failure/mismatch remains a failed CI result, never an accepted measurement.
If setup fails, later error records do not establish those APIs. If an individual
group errors, split that group before inferring any finer-grained conclusion.

## Documentation and context limits

Official 1C documentation establishes that ValueTree row/column-related types
are unavailable on the thin client (outside the stated historical compatibility
exception):
https://1c-dn.com/library/v8update_026v8_fbco_changes_that_require_modification_of_configuration_and_administrative_settings/

Official development standards describe value-tree row properties corresponding
to owner-tree columns:
https://its.1c.ru/db/content/v8std/src/400/100/i8100453.htm

Official guidance says ValueTree has no indexes and searches by enumeration:
https://its.1c.ru/db/content/v8std/src/400/300/i8100452.htm

Public primary API pages for exact Owner/Level signatures and default semantics
were not located. Do not promote third-party syntax mirrors to primary evidence.
Those details above remain concrete native observations to collect. Current
harness context is managed-thick-file/Linux 8.3.27.1508; it proves nothing about
thin, web, mobile or external-connection execution.

## Deferred, not guessed

Find/FindRows recursive traversal and Copy parameter semantics are not implemented
or measured by this checkpoint. After exact signatures are available, use a
four-node tree with the same search key in root and descendant, observe default
and explicit recursive search separately; copy full tree then mutate a leaf and
observe structural independence, shared columns and copied row Parent/Owner.
Do not conflate shallow copying of arbitrary cell objects with tree-node copying.
Last-column deletion, columns.Clear, failed typed assignment, cross-tree row
arguments, sorting, generic serialization and tree transport are also outside
this initial checkpoint.

## Acceptance

Offline tests cover source identity, no added unsafe operations, exact adapter
round-trip, tamper rejection, existing finite mismatch schema, fixed limits and
historical replay separation. Historical captures retain their original source
and 854 records through an exact source-only inverse and isolated test contract;
no immutable native bytes or capture metadata are rewritten. Fresh current-head
native server/client outputs and strict interpreter comparison are still required
before acceptance. Existing fixed `/tmp/onec-smoke` preflight must not overlap
another worker's exclusive run.

## Independent main-based candidate

This candidate is based directly on main
`ac9ee48646733a30d00c36bd0f863422fc8a3223`, not on the pending strict
preprocessor feature. Existing main lexer, parser, preprocessor and CLI sources
are unchanged. Package version remains 0.4.2. The provenance implementation
counts 59 files on main and 60 here: the sole added runtime file is
`yadinassi/value_trees.py`.

The test-only harness inverse restores the exact actual-main host and container
harness sources before applying the existing historical inverses. It does not
introduce a preprocessor inverse, fixture or production admission path. Existing
native fixtures, workflows and security limits remain byte-identical to main.

## First capture: rejected comparison, localized correction

[Native run 40221284540](https://github.com/Atridis/yadinassi/actions/runs/40221284540)
produced all twelve tree observations. Record 856 (`tree.core.types`) identified
five spaced type displays, unlike the initial interpreter labels. The remaining
eleven tree records were byte-identical; the final `error` is a rejected detached
grandchild read, not successful access. Only BSLType display labels are corrected;
object displays, aliases, probes, expected captures and comparison gates remain
unchanged. The failed report is not full-core acceptance. Fresh CI is pending.
See [authenticated capture details](value-tree-core.md#first-authenticated-native-capture-and-display-correction).
