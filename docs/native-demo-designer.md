# Demo XML/BSL source → isolated native DESIGNER

This is a separate profile, not fixture injection into a closed catalog suite.
It does not import or execute the supplied `validate_dump.py`, start ENTERPRISE,
create users/roles, change unsafe-operation protection, run external processors,
or modify existing smoke/profile inventories or workflows.

## Source and execution status

Implementation and unit tests are not evidence of native acceptance. Native
runs have reached the strict witness and failed XML equivalence; see the
evidence history below. This export revision has not yet had its own reviewed
native run. Exact CheckConfig options are documented in
the official [1C 8.3.27 Administrator Guide, section 7.4.5](https://1c-dn.com/library/tutorials/1c_enterprise_administrator_guide_file_mode_8_3_27/):
`-ConfigLogIntegrity -IncorrectReferences -ThinClient -Server
-ThickClientManagedApplication -HandlersExistence -ExtendedModulesCheck`.
These select configuration/reference integrity, managed client/server syntax,
handler existence and extended module checks. They do not execute business
scenarios. The image and executable path select 8.3.27.1508; no runtime
`SystemInfo.AppVersion` measurement is claimed because that requires BSL execution.

## Owner-operated CI route

After source review, use **Native demo DESIGNER acceptance** manual workflow
on the reviewed same-repository branch. Supply its exact 40-character commit SHA
as `reviewed_sha`. The workflow must be available in GitHub's default-branch
workflow catalog before its manual action is available. A moving branch is not
an approval token: dispatch SHA, workflow SHA and input SHA must all match.
Only the verified repository owner/account IDs and matching event sender qualify.
Admission runs inline without checkout or permissions; the native job then binds
a clean checkout to the same immutable SHA. Its only grants are `contents: read`
and `packages: read`, matching the existing isolated workflow. This eligibility
is not a defense against an authorized editor changing workflow/policy source.
No automatic pull-request/push trigger and no undocumented dispatch workaround
is provided. Publication, source review and actual dispatch are separate steps.

The host receives registry credentials only for login/pull into an owned private
Docker configuration, removes them before container execution, and passes a clean
environment. The unchanged digest-pinned image uses `network=none`, UID 1000,
read-only root and source bind mount, no capabilities, no-new-privileges, resource
limits, private IPC, no Docker logging and bounded tmpfs. Display authentication
uses a fresh cookie with X11/RFB TCP disabled, as in the existing profile.
A private `dbus-run-session` owns the session bus for the whole sequence without
changing the pinned image's session policy. Container removal remains the final
process-tree cleanup boundary.

## Native stages and evidence

1. Pass only the 19 literal reviewed source paths and the two profile sources.
   There is no archive, manifest or extraction helper. Git exact-source admission
   and before/after SHA-256 checks bind the editable XML/BSL bytes.
2. Read the source tree with bounded no-symlink traversal, reject unexpected or
   missing files, and copy exactly 15 XML and 4 BSL files unchanged into a fresh
   owned directory. Filenames retain the previously normalized UTF-8/NFC spelling.
3. CREATEINFOBASE creates a fresh file database without template/data.
4. DESIGNER LoadConfigFromFiles loads the untouched source.
5. DESIGNER CheckConfig runs the selected documented checks.
6. DESIGNER UpdateDBCfg applies configuration to the disposable database.
7. DESIGNER DumpConfigToFiles emits a hierarchical redump.
8. Compare exact file inventory (only native ConfigDumpInfo.xml is additional),
   BSL source (BOM/CRLF only normalization), expanded XML element/attribute names,
   text and child order (structural indentation only ignored). Namespace prefix bindings
   are retained conservatively, including QName-valued text and attributes. Refuse semantic mutations,
   additional modules, missing fields or native-added defaults until separately
   reviewed. Strict roundtrip may reveal format incompatibility; that is a failed
   witness, not authority to weaken checks.

Each batch must exit zero and produce a fresh zero DumpResult. Surviving native
processes prevent advancing. Each command has a 120-second timeout plus 5-second
kill grace; the host's 900-second lifecycle includes container ownership checks,
execution and cleanup. The reused lifecycle never removes by guessed name and
rejects uncertain create/removal. The finite report is released only after the
owned container ID and private host workspace have been removed. On uncertainty,
no native evidence is accepted and cleanup state is reported separately.

The finite summary contains only fixed enums, hashes, source paths from the
reviewed inventory, nonces, selected image/version and booleans. A separately
validated export can include the exact 15 known XML redumps of this public demo,
as described below. Raw logs, BSL, databases, ConfigDumpInfo.xml, unknown files
and process paths are never artifacts. The workflow always uploads the finite
`demo-native-report/report.json` and uploads the separate XML evidence only
after this invocation reports successful validated publication. A successful report
proves selected Designer acceptance and strict source roundtrip, not functional
MVP acceptance, GUI behavior, storage parity or all twelve demo scenarios.

## Local source verification

`python3 -B -m unittest tests.test_demo_source tests.test_native_1c_demo_designer -v`

Repeat with `-O` to ensure gates do not depend on assertions. These tests never
start Docker or 1C. `bash -n scripts/native_1c_demo_designer.sh` checks shell syntax.
The native entrypoint deliberately requires `--execute-approved-image`; do not
run it as a unit test or substitute it for CI's exact-source admission.

## Diagnostic-only XML mismatch evidence (summary schema v5)

The unchanged strict XML/module witness remains the acceptance decision. The v5
report additionally describes up to 15 mismatching known XML inputs without
exporting XML, names, values, logs or database content. `xml_diagnostics.files`
uses numeric `file` indexes into the profile's fixed `XML_FILES` order. Each item
contains bounded raw-byte SHA-256 pairs, a finite reason/comparison and seven
counts in `DIAGNOSTIC_COUNTS` order: namespace bindings, root expanded name,
root unqualified `version` attribute, nodes with differing attributes, differing
node text/tails, child-count differences, and expanded element-name differences.
Counts overlap, compare corresponding positional nodes only and saturate at 4096.
They are observations, not a structural diff or semantic-equivalence proof.

`namespace_only` means the unchanged signature's namespace-binding map differs
while its expanded tree tuple does not. Even unused declarations remain part of
the strict acceptance signature. QName-valued attribute/text semantics are not
resolved: namespace-only never means harmless or safe to accept. Root/version,
attributes, text and child-shape categories help identify what needs examination;
unknown semantics remain unknown and no normalization is approved automatically.

Analysis is limited to 1 MiB per XML, 4096 nodes/attributes/declarations, 96 levels
and 65536 characters per name/value/text segment. Missing, rejected or excessive
input reports `unavailable` with a finite reason, never raw parser exceptions.
Diagnostic JSON is capped at 6144 bytes and the existing whole native-report
limit remains 16384 bytes. Address records are trimmed first, preserving every
file summary and increasing that file's `omitted` counter. Only if the summaries
alone exceed the budget do diagnostics become `budget_limit` with no entries;
acceptance is never upgraded. `not_reached`
means the witness stage did not produce diagnostic evidence. Host validation
rejects unknown indexes, duplicate files, arbitrary strings, excessive counts,
extra fields and entries not corresponding to known XML mismatches.


### Source-addressed observations

Each file additionally has `addresses` (at most 12 records) and `omitted` (the
number of additional records omitted by the per-file or shared output budget).
A record is `[source_node_id, kind, source_attribute_slot, count]`. Node IDs are
zero-based preorder positions in the exact reviewed source XML's acceptance
signature (`source_nodes(xml_signature(source_bytes)[1])`). Attribute slots are
zero-based positions in that source node's sorted attribute tuple; they are
used only for attribute changes/removals. All other kinds have slot zero. IDs
and slots are decoded only against that run's exact public source SHA, never
against current branch contents. The report contains no path, name, attribute
value, text, native log, or per-field value hash.

Kinds, in their numeric order (`ADDRESS_KINDS`):

0. `attribute_changed`: source attribute slot changed value.
1. `attribute_removed`: source attribute slot absent after redump.
2. `attributes_added`: count of additional attribute names at this source node.
3. `text_changed`: significant node text differs.
4. `tail_changed`: significant text after this source child differs.
5. `children_added`: count of children with names absent among source siblings.
6. `child_removed`: this source child name is absent among redump siblings.
7. `child_order_changed`: sibling name order changed after filtering to names
   present on both sides with equal multiplicity (including repeated groups).
   An unrelated insertion does not hide movement of existing groups.
8. `children_ambiguous`: a changed repeated-name sibling group cannot be aligned;
   the address is its first source child and count is the larger group size.
9. `element_name_changed`: expanded root name changed; no descendant identity
   is asserted across that change.

Kinds 2/5/8 carry bounded cardinalities; all others have count one. Structural
observations are retained before text/ambiguity, other attributes, and root
attributes, so ubiquitous version churn does not crowd out deeper evidence.
Ties retain deterministic traversal order. Omission is explicit, and
counts are not semantic judgements. Unique sibling expanded names are aligned
without positional cascading after an insertion. Repeated names are not matched
by guessed identities, even when an `id`, `name`, or `uuid` attribute exists.
The group is marked ambiguous, rather than reporting invented downstream value
changes. Namespace bindings and QName-valued text remain unresolved as in v3.
Added children/attributes are observations only, not approved default values.

The unchanged seven summary counts are positional and can therefore disagree
with the aligned address interpretation; both describe their respective
comparison method. Neither relaxes the strict witness. Summary schema v5 retains v4 address semantics; its wire envelope and export
are separately versioned and are not interchangeable with v3/v4 wire output. Validation rejects malformed tuples,
boolean integers, duplicate address kinds/slots, unknown kinds, invalid source
node/attribute indexes, inconsistent empty tree-difference records, excessive
omission counts and all added arbitrary strings.

Offline address tests are included with the existing gates:

```sh
python -B -m unittest tests.test_native_1c_demo_designer tests.test_native_1c_demo_xml_diagnostics tests.test_native_1c_demo_xml_addresses tests.test_demo_source -v
python -O -B -m unittest tests.test_native_1c_demo_designer tests.test_native_1c_demo_xml_diagnostics tests.test_native_1c_demo_xml_addresses tests.test_demo_source -v
```

Native run `42109829153` on source `57b06142640a507534eaa78237ad6d397184cc79`
reached the witness after successful create/load/check/update/redump checks,
but all 15 XML witnesses differed (`namespace_and_tree`). It remains failed
native evidence, not an accepted roundtrip. Its four BSL witnesses did not
differ. Source binding and owned-container/Docker CLI cleanup were verified.
Adding the XML-export code does not itself acquire new native evidence; this
revision requires a new exact-source reviewed dispatch.


## Reviewed public-demo XML export

This narrowly scoped route exports only the 15 `XML_FILES` from the reviewed
public demo. It is not a general configuration/data export or a sensitive-data
sanitizer. Native output may include generated UUIDs, platform metadata and
inserted defaults. That output remains untrusted data; do not execute it, apply
XSLT, resolve external references, or load it into an existing database. The
approval relies on exact public source, a newly created empty database and the
unchanged isolated pinned container. It does not cover private configurations.
Registry credentials are removed before the container starts and are never
passed into it. No arbitrary native filename or path crosses the export boundary.

The container sends a versioned wire object containing the independently capped
16 KiB strict summary plus a separate export state. An available export must
have all 15 numeric indexes in fixed order, canonical base64, exact decoded
lengths and full-file SHA-256 hashes. Each XML is at most 256 KiB; the decoded
aggregate is at most 1 MiB; the complete encoded wire is at most 1.5 MiB. This
uses the existing lifecycle's 3 MiB maximum without changing lifecycle code,
900-second execution/cleanup budget, workflow permissions or container flags.
The existing summary cap and 6144-byte diagnostic cap are not increased.

Only a witness-reached dump qualifies. The bounded no-symlink/no-hardlink read
must find all 19 known source files and no unexpected path (the one existing
ConfigDumpInfo.xml exception remains, but is never exported). Every exported XML
must pass bounded safe parsing with DTDs, entities, processing instructions,
invalid UTF-8/XML, excessive depth/nodes/attributes/text and oversized inputs
rejected. There is no partial export: missing, rejected or oversized output
produces an explicit unavailable state with a finite reason and zero files.
This export decision does not change the original strict acceptance result.
A failed witness stays failed even when its XML export is available; an
unavailable export is not evidence of equivalence.

The host independently rejects duplicate JSON keys, unknown fields/reasons,
index disorder/duplication, boolean numbers, noncanonical base64, length/hash
mismatches and phase/state contradictions. It reparses every XML, recomputes XML
mismatches and the full bounded XML diagnostics against exact reviewed source,
and compares those results with the strict summary. Success-case redump hashes
are also checked; native BSL mismatch evidence is preserved without exporting
BSL bytes. A malformed/tampered host wire is a sanitized `host_failed`, not a
partially trusted summary. A legitimate unavailable native export instead
preserves the original finite summary and its explicit export reason.

After validated container removal and Docker CLI reaping, the host rechecks
original/staged input hashes and source revision. Only after the owned temporary
workspace (including authentication configuration) has been removed may it
publish. It exclusively creates a previously absent mode-0700 output directory;
preexisting files, directories or symlinks are neither reused nor removed.
Seventeen fixed files are written exclusively under a private staging child,
then published together by one directory rename to `payload`. Write/rename
failure removes only the newly owned output root; no partial payload is exposed.
This assumes the existing trusted runner/checkout and does not claim protection
against another process with the same user or an administrator mutating files.

`demo-designer-xml-evidence` contains exactly:

- `report.json`: finite source-bound host summary.
- `manifest.json`: export schema, exact source SHA, nonce, input hashes, summary
  hash and the fixed source-index/filename/length/hash map.
- `xml/00.xml` through `xml/14.xml`: exact bytes, indexed by `XML_FILES` at that SHA.

The upload action lists these 17 paths literally, with no glob or directory
upload. Its gate is an output emitted from this invocation's sanitized report
only after host publication succeeds, not the presence of a possibly stale
manifest. A failed strict witness can therefore upload useful validated XML
while the job remains failed. Earlier failures or uncertain cleanup cannot
publish XML. The ordinary summary upload remains separate and finite.


### Prior v4 address run

Run `42114875178` on exact source
`d15f8b02635774b15b7bacf1b8bd58ef58d1d92f` also failed the strict witness:
15 XML mismatches, four BSL files without mismatches, and no address records
omitted. Source hashes and cleanup were verified. It exposed a text change at
`ConfigurationExtensionCompatibilityMode` (the source value is `Version8_3_14`),
property additions, a ContainedObject group changing from six to seven entries,
and ambiguous panel groups. It did not disclose the exact new values. Fourteen
of fifteen XML after-hashes matched the preceding run; only Configuration.xml
changed. This is the reason to acquire a reviewed XML export, not a basis for
accepting or normalizing any change.
