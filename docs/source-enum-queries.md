# Source-owned enum queries

Source scratch profiles can project and filter enum-valued constants, catalog
records, documents and document sections without obtaining an inventory/native
query capability. An enum-bearing schema no longer prevents scalar projection
or COUNT(*).

Equality, joins, DISTINCT/grouping and existing enum membership semantics use
canonical application-owned enum identities. Ordering remains unsupported.
An unrelated owned enum compares as a nonmatch; foreign or forged references
are refused. Query result Unload and temporary-table packages preserve the
owner/domain binding and reissue lexical descriptors on the next execution.
Closing the application invalidates these bindings. Retiring an individual
query scope does not invalidate a legitimate detached result while its owner
remains alive.

This is the existing bounded source-memory/scratch relational contract, not
native 1C parity, a legacy inventory grant, document posting or a general query
engine. No database migration or full CI is implied by focused tests.
