# DL14: last-column Delete measurement

This is a standalone observer/strict contract, not runtime support. The existing
last-column/nonempty-tree guard remains intact. Columns.Clear evidence does not
establish Delete's row lifetime, retained metadata, expression behavior, mutation
ordering or saved collection routing.

## Primary API evidence

The pinned official SyntaxHelper documents
`ValueTreeColumnCollection.Delete(Index)` / `КоллекцияКолонокДереваЗначений.Удалить(Индекс)`.
The required selector is Number or ValueTreeColumn. Availability is since8.0 on
server, thick client, external connection, mobile application server and mobile
standalone server. It describes removing the selected column, without stating
last-column lifetime or retained-reference semantics.

Primary archive:
https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar
SHA256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
Entries `nl/{en,ru}/html/SyntaxHelperContext/objects/catalog234/catalog264/ValueTreeColumnCollection/methods/Delete689.html`:
EN SHA256 `8a95a699f70744c4d00207eb8108a88e10e948cf711c6f05d9e417f640f26e37`;
RU SHA256 `e35044fbc795478044b5c4c915f7aa805cfe1863561e1406c4ea70d19eef7b25`.
The selected8.3.27 overlay archive is
https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_v8_3_27_1.0.400.v202609220822.jar
SHA256 `c140925e80ad3a64b528b70a362ff6709f43e65b3e39e9736bad0d5e482d79f6`.

## Fourteen fixed cases

Every present selected column starts with Name `Key`, Title `P`, Width9. Active
schema and independent retained-column queries establish setup; before/after
metadata are not normalized. The default nonempty shape is two roots and one
child. Cases1/2 have two columns; other nonempty cases have exactly one.

| Case | Operation / shape |
|---|---|
|1|English Delete(0), two-column/nonempty positive control|
|2|Russian Удалить(own column), same positive-control shape|
|3|Last column Delete(0), nonempty|
|4|Last column Delete(own column), nonempty|
|5|Last column Delete(own column), no rows|
|6|Delete(0), no columns/rows|
|7|Delete(foreign column), own nonempty tree observed|
|8|Delete(), missing required selector|
|9|Delete(own column,1), extra argument|
|10|Expression result of Delete(own column), nonempty|
|11|Last Delete, then write Key9 through held original root row|
|12|Last Delete, then Add through held child row collection|
|13|Last Delete, then Add through held root collection|
|14|Last Delete, then rebuild Key; root Add/write5; held child Add/write6|

Follow-ups only run after successful primary deletion. Phases identify the last
attempted rebuild step; errors are captured before nested helpers. A failure does
not imply rollback. Primary/follow-up status and full after state stay separate.
Expression success records the returned finite scalar; procedure rejection is
not assumed. Foreign-selector effects on the foreign tree itself are outside this
bounded observation; own-tree mutation is always recorded.

The immutable CC snapshot grammar is reused, not Clear conclusions. Active row
IDs/topology, independently reported owner/parent/level, positional and named cells,
retained original rows/column, and saved collection Count/Parent remain observable.
Collections are structurally labeled, never assumed equal wrapper objects. The
fixed DL header mapping uses existing ordinary/expression/follow-up/phased shapes.
No old source, contract, profile, fixture, generated module or runtime file changes.

Availability requires successful EN/RU non-last controls with the selected column
absent and exactly one active column left; matched missing-method or no-op output
cannot pass. Row lifetime and remaining metadata are not acceptance assumptions.
All other primary/follow-up outcomes remain observations, including failed or
partially mutating last-column actions. Existing raw-error privacy is unchanged.

## Bounds and integration boundary

Constructive maximum capture is **5140/8192 bytes**; maximum snapshot remains175
bytes (three columns, five active rows,62 shared identities). Case14 can preserve
three rows and add two, reaching the five-row domain. Unsupported larger graphs,
metadata words/scalars or identity exhaustion fail the observer; this is a finite
measurement limit, not evidence that 1C cannot produce such results. Compact
completed-marker framing has a conservative **5352/16384-byte** bound including
ordinary JSON whitespace, escaped slashes and a UTF-8 BOM.

Standalone tests execute actual BSL with distinct synthetic preserved-row,
Clear-like, retained/renamed metadata, partial-error and expression-result models.
These validate distinguishability, not native semantics. Exact native acquisition
is still required before changing the last-column guard.

After standalone review, integration should add one immutable closed profile with
lazy CC decoder dependency and actual emitter admission/dispatch tests. Reuse the
existing tree matrix job and credentials; no duplicated workflow job, full_suite
edit or cap increase. Final23-source closure and complete stage/transport/host
bounds must be proved against the actual integrated envelope before publication.
Do not add old exploratory CL6/CD3 lanes. Native EN/RU controls and exact client/
server parity remain required; only genuine facts can authorize runtime work.

## Closed integrated profile

`tree-columns-delete-v1` registers15 messages (calibration plus14 cases), exact
source/hash, one lazy DL decoder and its unchanged CC basis. The actual cold
staged closure is23 files. The existing Copy matrix gains one literal Delete
entry: one additional job/container execution, not another duplicated workflow
job. Fill and all existing required entries stay intact; CL6/CD3 remain offline.
Both embedded emitter sets and fixed dispatch admit only this new token.

Actual integrated structural majorants remain within unchanged limits:
stage4311/8192; native9437/32768; transport20644/65536; host15098/32768;
provenance14893/32768. Capture5140/8192 and conservative marker5352/16384
remain bounded. All nine old generated client modules and old source/contract
bytes are unchanged. Shared acquisition routing necessarily has new source
hashes, so fresh authenticated native measurement is required. Runtime remains
unchanged; a matched unsupported last-column result is only an observation, not
full Delete support.


## Subsequent native acquisition

The original measurement has since been acquired and authenticated. Its old
interpreter mismatch is preserved. See [bounded runtime support](value-tree-columns-delete.md)
for exact run attribution and the separate implementation; historical preparation
statements above describe the original measurement stage.
