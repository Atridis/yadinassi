# Owned Catalog standard-field matrix — accepted narrow native evidence

This experiment extends only the native **measurement fixture**, not the BSL
Catalog manager, application metadata APIs or general CRUD support. It reuses
the bounded identity-prefix reader described in
[config-catalog-identity-prefix.md](config-catalog-identity-prefix.md).
The dedicated source-bound run below has accepted native evidence for exactly
these three owned metadata profiles. It does not establish general field ranges
or additional Catalog data operations.

## Three fixed profiles

| Owned Catalog | CodeType | CodeLength | DescriptionLength | Data operations |
| --- | --- | --- | --- | --- |
| `NativeOracleItems` | String | 2 | 0 | Existing K1 fixture lifecycle only |
| `NativeOracleStringDescription` | String | 2 | 16 | None |
| `NativeOracleNumberDescription` | Number | 2 | 16 | None |

The second row isolates a nonzero description length; the third changes only
CodeType relative to the second. The pinned native producer accepted the empty
Number/length-2/description-16 profile in the run below. No general length
ranges, arbitrary configurations or Number-code data operations are inferred.

The existing Catalog, Payload/Amount attributes, physical record decoder and
logical K1 checks are unchanged. The two extra Catalogs have empty ChildObjects
and independent generated identities. They receive no additional CRUD rights;
existing `setForNewObjects=false` grants, users and role boundaries remain.
The native module's fixture Catalog-count guard changes from one to exactly
three only in this fixed matrix. All metadata is synthetic and owned, and all
database activity remains inside the disposable oracle fixture. No external
credentials, production databases or caller-supplied schemas are accepted.

## Evidence boundary

Each of the three internal CONFIG UUIDs must match its external declaration and
its independently verified canonical owned XML UUID. Name and all three scalar
properties must also match. The reader completes all selected entries before
comparison; expected XML values are never parser inputs. Missing, duplicate,
extra, swapped or later-failing identities must fail the complete measurement.

Public evidence contains finite verdicts and bounded counts/hashes, never raw
UUIDs, metadata names, XML or CONFIG contents. The source inventory and fixed
matrix recipe bind the aggregate verdict to these three reviewed profiles.
The prior one-Catalog lane and its accepted evidence retain their original
source identity and scope. The matrix must not relabel that earlier run.

Existing lifecycle, source admission, report budgets and cleanup are retained.
Extra physical tables may change bounded aggregate counts; they do not expand
the NativeOracleItems-only record projection. The accepted run below completed
inside the existing limits; no limits were raised.

## Closed lane and local envelope checks

The selector is `--config-catalog-field-matrix`, lane
`owned_config_catalog_field_matrix_v1`, invocation schema 21, report schema 33
and capture schema 34. Its fixed matrix policy recipe is separate from the
unchanged identity reader recipe; this does not change the reader grammar.
The earlier identity lane retains its original selector, schemas and policy.
The dedicated workflow activation changes only the selected lane token.

Synthetic encoded majorants are 2015/2048 bytes for the projection,
3092/12288 for capture and 31953/32768 for the complete report, with 27 staged
sources. All 13 stages, 11 snapshots, 5 comparisons and 4 cleanup steps remain
required. These local checks establish bounded protocol construction only,
not platform behavior or successful native execution.


## Accepted owned native evidence (original source identity)

Dedicated [run 40759955663, attempt 1](https://github.com/Atridis/yadinassi/actions/runs/40759955663)
was accepted for original source commit
`f4ed7c9e49e735a5056c3758185299e3dbe55c64`, tree
`aee83d2f36fd8eb0c97f48523a2170e871dd237d`. Cold production FINAL validation
passed first, followed by the unchanged independently prefrozen checker and
source/Git-graph/run/job/artifact checks. The bound inventory contains 664 source
files and 27 staged files.

Exactly three Catalog declarations, resolutions, positive entries and names
matched, with finite verdict `owned_matrix_uuid_fields_matched`: internal UUID,
external declaration and canonical owned XML UUID, Name, CodeLength, CodeType
and DescriptionLength agree for each fixed profile. All 16 selected entries
completed, with 13 stages, 11 snapshots, 5 comparisons, 3 artifacts and all four
cleanup checks successful. The existing K1 CRUD fixture was preserved; the two
additional Catalogs remained metadata-only fixtures without extra CRUD grants.

The 18807-byte report has SHA-256
`dc559f351050f0008e4ebfda4600051ae2f5665cd36f70337b37e7e12d197fbc`.
Actual public projection/capture sizes were 1939/2981 bytes. No raw UUID, Name,
XML or CONFIG content is exported by this evidence.

This accepts only the fixed owned matrix through the pinned producer. It does
not establish arbitrary Catalog grammar, hierarchy, applied CONFIG identity,
BSL Catalog APIs or data operations on the two additional Catalogs. Earlier
one-Catalog evidence keeps its original scope. This prose-only follow-up does
not relabel the dedicated run as executing against a later documentation commit.
