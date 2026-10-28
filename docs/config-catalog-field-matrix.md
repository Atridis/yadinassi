# Owned Catalog standard-field matrix (native acceptance pending)

This experiment extends only the native **measurement fixture**, not the BSL
Catalog manager, application metadata APIs or general CRUD support. It reuses
the bounded identity-prefix reader described in
[config-catalog-identity-prefix.md](config-catalog-identity-prefix.md).
No native evidence for the new matrix is claimed before its separately reviewed,
source-bound run and independent report verification.

## Three fixed profiles

| Owned Catalog | CodeType | CodeLength | DescriptionLength | Data operations |
| --- | --- | --- | --- | --- |
| `NativeOracleItems` | String | 2 | 0 | Existing K1 fixture lifecycle only |
| `NativeOracleStringDescription` | String | 2 | 16 | None |
| `NativeOracleNumberDescription` | Number | 2 | 16 | None |

The second row isolates a nonzero description length; the third changes only
CodeType relative to the second. Whether the pinned native producer accepts
Number with length 2 is a measurement question, not an assumption or a claim
of complete platform validity. No general length ranges are inferred.

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
the NativeOracleItems-only record projection. Native acceptance must confirm
that the fixed matrix fits the existing limits; limits are not raised to make
a failing measurement pass.

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
