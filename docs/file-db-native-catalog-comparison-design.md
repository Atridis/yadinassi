# Minimal native-versus-physical catalog comparison

The original comparison implementation started from PR #102 head `68716d6c4cc6689928deb92775f35b0725148336`, tree `88af273e72e77ab2674019dae51ee5490e30d433`, preserving that frozen 420-file candidate. PR #102 is now merged. The names-only rejected-run diagnostic below is a separate candidate based on the published PR #103 comparison source; it does not modify either frozen predecessor or relax publication and review gates.

## What the next run must establish

Execute the real `filedb_catalog.read_catalog` implementation against an immutable post-audit copy of the disposable native auditor database. Compare its physical table/field names with the names independently returned by the native platform for our own `Справочник.NativeOracleItems`. A pass establishes only exact filtered table/field-name agreement for that measured file, format 8.3.8.0, 8192-byte pages, and platform 8.3.27.1508. It does not establish row decoding, type-code equivalence, index/B-tree correctness, runtime DB globals, general 1CD support, or write compatibility.

The prerequisite observation is run 40116987010, report SHA-256 `ed5e9c7741638065684b7bf1ffc695b8e1822fefe6573a208c6e5dd45837d013`. Its shape provides the real column names and declared types, but no physical-name scalar values. Therefore no `_ReferenceN`, `_FldN`, case conversion, prefix stripping, or field-type mapping may be invented.

## Native projection: only measured columns we need

Keep the existing baseline `audit_contract` operation, Setup identity, nonprivileged module, and exactly one call:

`ПолучитьСтруктуруХраненияБазыДанных(Отбор)`, where `Отбор` is the one-element Array containing `Справочник.NativeOracleItems`.

Check the requisite columns and their declared/runtime types before use. From every returned root row select only `ИмяТаблицыХранения` and the nested `Поля` table; from every nested field row select only `ИмяПоляХранения`. These exact column names are observed, not guessed. Do not read/export `Метаданные`, `Назначение`, tablespaces, index names, logical names, `ТипПоля`, or arbitrary cells. Do not make a second call, use a second Boolean argument, or fall back to an unfiltered call.

Export a small native projection: target plus a list of `{name, fields:[name,...]}`. Require nonempty string names, unique table names, unique field names within each table, nonempty tables/fields, and bounded complete enumeration. Do not silently omit virtual/empty names, deduplicate, truncate, or accept a subset. Unexpected output fails closed with a finite diagnostic.

## Bind the native observation to the actual reader input

The previous schema-3 binding was only baseline ancestry: `audit_contract` runs on a writable `auditor` clone and deletes it before the controller binds its observation to the baseline digest. Native startup/shutdown may change clone bytes. Reading the original baseline would not prove a same-file comparison.

Within the existing baseline stage:

1. Clone the verified frozen baseline using the existing copy-verifying helper. Record/verify the clone's pre-launch digest equals the baseline digest. Bind the fresh operation nonce/token and fixed clone identity to this origin.
2. Execute the filtered native projection on that clone. Require its existing fresh result/completion/identity checks and process-census quiescence. No new native operation or schema/data write is introduced.
3. Before `temporary_clone` removes the auditor, use `freeze_database` to create a fresh private sibling `auditor_frozen` from that exact post-audit clone. Preserve its existing inode/no-follow/inventory/copy/hash/quiescence gates and reserve its bytes under the unchanged live-byte budget. Never launch native 1C against this frozen copy.
4. Open that frozen `1Cv8.1CD` once through the existing hardened no-follow descriptor boundary. On that same descriptor compute the pre-read SHA-256, call the standalone staged `filedb_catalog.read_catalog` with a positioned read callback, and compute the post-read SHA-256. Require both hashes equal the frozen-copy summary and initial/final inode/metadata/size/mode/inventory checks match. Process census must be quiescent before the first payload read and after inspection; the callback checks the existing work deadline. A path reopen through `inspect_catalog` is not the evidence route.
5. Parse the catalog independently of native names. Only afterward project the parsed tables selected by exact native storage names. Retain no raw descriptors, BLOB bytes, index trees, unrelated table/field names, or database bytes in the public report.
6. Remove both private clone/copy through existing cleanup boundaries. They are subordinate baseline evidence, not extra public lifecycle stages or snapshots. Preserve 13 stages, 11 snapshots, all four cleanup gates and opaque CF/DT handling.

Add the reader itself to the exact staged source inventory and bind its SHA-256 explicitly. Stage it as a standalone standard-library module, not via `yadinassi.__init__` or an Interpreter import. Prefer keeping comparison orchestration in existing harness modules; do not change the production reader merely to obtain a pass.

## Comparison and honest outcomes

Validate native and reader projections independently, then sort only for canonical representation. Match names exactly, case-sensitively; do not assume declaration order matters. Every native table must have exactly one parsed table, and each matched table's full parsed field-name set must equal the native field-name set. Extra unrelated catalog tables remain private and are not grounds for failure. Extra/missing/duplicate fields within an owned table are failures, not ignored differences.

This exact-name/set rule is the initial comparison policy, not a claim that every platform/storage layout must use identical naming conventions. An unsupported representation must fail honestly; do not normalize names or omit fields to manufacture agreement.

Use a new schema/lane rather than retroactively upgrading schema-3 shape evidence. Replace the old shape payload with separately encoded native and reader projections and explicit baseline-origin/post-audit-frozen bindings. Success requires all old lifecycle checks, complete parse, exact projection equality, stable input, and verified cleanup. Only then set the narrow reader verdict `filtered_table_field_names_match`. Keep broad `native_compatibility=not_claimed`.

The postimage claim is explicitly the closed post-session image, not byte identity with baseline or the native execution-time file. Reject duplicate parser-side table/field names before set/dict conversion.

Preserve distinct finite reader outcomes for unsupported layout, supported-subset sharing policy, structural rejection, resource limit, I/O/change, and name mismatch. Validate error class and an allowlisted finite code as a pair; never forward an arbitrary CatalogError.code. Do not export exception text, raw descriptor context, or partial successful projections. Failure/cleanup failure cannot retain a successful comparison. Ordinary failures retain only a fixed category/code; the source-bound, names-only rejected-run diagnostic below is a narrow synthetic-fixture exception and is stripped on cleanup failure.

## Bounds and gates

Keep all existing file/live-byte/time/process/transport ceilings and the reader's existing structural budgets. Proposed per-projection bounds: at most 4 owned tables, at most 32 fields per table and 64 total, each name at most 64 printable BMP units, 512 aggregate name units, encoded projection at most 4096 bytes. These are supported-subset output caps, not platform schema limits. Count before allocation/iteration and reject exhaustion without truncation.

Two projections consume at most 8192 bytes, replacing the prior 8192-byte shape allowance rather than adding to it. An independent-maxima serialization of the proposed projection is 3469 bytes; the proposed fixed comparison/binding fields are approximately 554 bytes before final schema spelling. The previous schema-3 whole-envelope proof is 25875 bytes. The exact new source-inventory entries, statuses, fixed keys and binding fields must be included in a new complete-report worst-case test before implementation is accepted, with the unchanged hard limit 32768 bytes. The design arithmetic is headroom planning, not a completed schema-4 universal proof.

Focused tests must prove execution of the real reader on a synthetic frozen descriptor, not a fixture-produced success flag; matching/missing/extra/duplicate names; source/nonce/token/origin/postimage binding; same-descriptor identity and digest changes; cleanup failure; all projection limits; and the exact complete-report maximum. Preserve UTF-8 guards. Independent review and a frozen full suite precede publication. A new real native run after merge is required before claiming even this narrow native-read result.

If it passes, use that measured mapping as the foundation for the next user-visible read-only DB operation. Do not spend this slice on unrelated edge polishing or claim CRUD support from catalog-name agreement.

## Local implementation proof

The implemented schema-4 tests prove a 3469-byte independent-maxima projection
within its 4096-byte cap and a 29821-byte complete-report upper bound including
newline, all 20 staged source entries, and the enclosing 12288-byte capture cap.
This leaves 2947 bytes below the unchanged 32768-byte limit. These local proofs
do not establish a native comparison result; the fresh exact-source native run
and independent artifact audit remain required. The production reader is
unchanged from PR #102.

## Historical 64-table rejected-run names diagnostic

The first native comparison, run 40122436147 at PR #103 head
`85bc9328e2368ca1fd9a8141c8657a109cb71fa6`, rejected with
`name_mismatch/missing_table` after a complete reader return and postimage check.
Its archived finite report does not reveal either table-name representation;
no normalization or root-mapping explanation is inferred from that result.

A separate candidate adds an exact capture-schema-2 failure variant while
preserving report schema 4, strict comparison and production reader bytes.
It retains the complete source/nonce/token/origin/postimage binding and emits
only the selected native table names and complete parsed table-name inventory
from the controlled synthetic disposable DB. The native list is 1..4 names;
the parser list is 0..64 names with duplicates preserved. Both are sorted,
counts must equal list lengths, every identifier matches
`[A-Za-z_][A-Za-z0-9_]{0,63}`, and both lists together have at most 2048 ASCII
characters. No fields, classifiers, candidate selection, raw descriptor bodies,
row values, index bytes or physical offsets are included.

Enumeration is all-or-nothing. Unsupported identifiers and exhausted limits
produce finite bare failures, never a truncated inventory. The names capture
is valid only for the original strict missing-table rejection, after complete
hash/read/hash inspection and successful required cleanup; late host cleanup
failure removes it. It remains failed and `native_compatibility=not_claimed`.
The executable proof must charge the complete report and the enforced 12288-byte
capture ceiling, not only the new name lists. Local tests and review do not
replace a fresh source-bound native diagnostic run.

## Historical counts-only follow-up measurement

The names-only revision at b7dc636317241818871749463419e417d3f28e12 rejected
native run 40123903700 with a bare diagnostic limit. That report cannot choose
between inventory count and aggregate name length or reveal a later hidden
identifier violation. The next separate source candidate therefore measures
all counters and policy blockers in one pass, without changing any cap.

Its active missing-table path emits capture schema 3 with the original strict
name mismatch, existing source/nonce/token/origin/postimage binding, and a
complete counts-only census. It exports no name list even if one would fit.
Native tables remain 1..4; parsed tables are bounded by the unchanged 4096-table
reader limit, each decoded string by 65536 UTF-8 bytes, and total name bytes by
the reader's at-most-16-MiB charged BLOB payload. Character totals, maxima,
identifier-invalid counts and parser/inventory equality are bounded and checked.
Deadlines apply during long scans. No parser, native call, row, field or mapping
behavior changes.

Exact hypothetical schema-2 capture size is derived from a small encoded
binding/count skeleton, each string's incremental JSON escaped length and array
commas, not a large name-list serialization. Tests compare that arithmetic with
the real serializer on valid, escaped, control, BMP and astral examples. All true
policy flags are emitted together: table limit, aggregate characters, native
identifier subset, reader identifier subset and capture bytes. Validators check
all derivable counter/range/flag relationships but cannot reconstruct hidden
names or authenticate producer-only observations from the counters alone.

Only required successful cleanup permits the bound census to survive; otherwise
it is reduced to a bare finite failure. Status remains failed and compatibility
not claimed. Both fixed counter-capture and complete-report maximums must pass
executable proofs under unchanged 12288/32768-byte caps before publication.

The executable independent-maxima proof bounds the counts-only capture at 1491
bytes and its small hypothetical-name skeleton at 1051 bytes. The enclosing
report maximum remains 29821 bytes including newline, within unchanged caps.
These bounds do not establish actual native counts or resolve the mismatch.

## Measured 128-table output policy and conditional names

Independent audit of run 40125667143 at
`9285723e58c3d4a756b59939a3c7dd743622c6b0` measured native/reader/parser counts
1/67/67, combined characters 1033, zero invalid identifiers, and exact hypothetical
names-capture size 2280. Only the prior 64-table policy was exceeded. Its report
SHA-256 is `64df535b4b84a74275e3e596015069da099577e0806ae938e12ee09c7744cf7a`.
No actual name or mismatch cause is inferred from those counts.

The next separate candidate raises only that local diagnostic table ceiling to
128. It leaves grammar, combined 2048 characters, capture 12288 bytes,
report 32768 bytes, all reader budgets, strict comparison, native code and cleanup
unchanged. The complete census runs first. If every policy fits, return the full
schema-2 bound names-only failure; otherwise return the schema-3 bound counts-only
failure with all blockers and no names. Both preserve the original missing_table
rejection, never truncate and never claim native compatibility. Actual encoded
capture size is checked again before releasing a names capture.

This is a measured supported-subset policy, not a universal table-count fact.
Tests cover the observed 67-table shape without inventing names, 128/129 boundaries,
2048/2049 characters, invalid identifiers, complete census fallback, duplicate
preservation, exact computed/encoded sizes, source/postimage bindings and every
cleanup gate. A new maximum names-capture proof and unchanged whole-report proof
are required. Only a fresh independently audited artifact can establish the
actual name spellings before any mapping correction is considered.

The new attainable names-capture maximum is 3491 bytes, while counter/skeleton
bounds remain 1491/1051 and the universal whole-report maximum remains 29821
including newline. Actual encoded schema-2 bytes must equal the complete census
measurement. Historical policy flags are validated with their original source,
never silently reinterpreted under the new 128-table supported subset.
