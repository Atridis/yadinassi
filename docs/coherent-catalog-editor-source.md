# Coherent catalog editor source reads

`SQLiteCatalogBackend.read_catalog_editor_source(catalog_id, expected=...)`
returns `(CatalogFormSource, optional_object_module_text)` from one current SQL
read transaction and one verified source snapshot. It does not cache source
permission. Every invocation still reads and hashes current configuration data
and uses the existing profile-specific schema/DDL checks.

The original `read_form_source` keeps its form-only result and does not request
an object policy. The new pair reader reuses its implementation rather than
copying the large snapshot validator. MainDemo object source requires its existing
catalog handler grant and matching digest. Other supported profiles retain the
existing policy allowlist; inert sources have no object policy. The base backend
capability refuses with `unsupported`, rather than silently assembling two
unverified reads for custom adapters.

Catalog editor initialization and verification consume the pair. All existing
before/after checks around detached source execution remain, including pinned
form and object source equality. The writer, its atomic source/schema checks,
receipt resolution and transactions are unchanged. Returning source bytes is not
a lasting execution grant, and the SQL read transaction ends before returning.

Tests cover one snapshot per pair, fresh verification on the next call, exact
expected identity, MainDemo DDL rejection, inert source drift, policy drift and
custom backend refusal. Existing imported product/kind editor fault injections
now target the new source-pair seam; receipt no-replay assertions are retained.

Measurement uses the unchanged original UI Description/Save harness from
`experiments/canonical_validation/measure.py`, copied into
`experiments/coherent_editor_source`. Baseline 01306fc2 is tree-equivalent to
public 07d52635. Results describe these real UI actions, not all database work.

Verification now also rejects an unexpected `None` → object-policy transition,
instead of checking object policy only when one was originally present. This is
a stricter current-binding check, not permission to activate a newly found policy.

Five paired UI measurements: product Description **17.507 → 11.844 ms**, product
Save **50.720 → 46.595 ms**. The no-policy kind control was **4–6% slower**; it
already skipped the second policy read during verification, so it has no claimed
speedup. Complete timings and controls are retained with the experiment.
