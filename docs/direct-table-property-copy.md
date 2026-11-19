# Property copies into current positional table rows

The table branch of property_transfer now admits canonical positional rows:
exact row/table/column/storage types, live owner membership, bounded shape,
column offsets/metadata and schema epoch. It retains readonly-slice rejection
for destinations and descriptor checks. Writes still call the canonical row
setter, so lazy indexes are invalidated through the existing schema epoch.
No index declarations, cached keys or buckets are read by this endpoint.
Tree rows and other property endpoint families are unchanged.

This change adds no conversion envelope and no endpoint family. In particular,
python_direct_fill's direct-Structure-to-object boundary remains closed.
Ordinary default BSL can copy between its canonical table rows through the
already registered FillPropertyValues service. Both execute and prepared tests
warm an index, copy a property, verify old miss/new hit and mutate the returned
live row. Host Structure-to-row copies retain their existing admitted route.

Baseline ad3c165's historical
`test_table_indexes_are_updated_by_existing_setter` errors at column-container
validation. The candidate proceeds through copying, then fails its old coercion
assertion (9.876 is retained, rather than rounded to 9.88). The historical test
is unchanged; coercion is outside this patch. The new current-semantics test
verifies both exact stored value and correct lazy-index invalidation.
