# Collection/tree tests after engine retirement

Base tree: `98afd4e8d2a11a357db0d36845e0d14b29223d35`.
This is a test migration only. No product code, native scripts, expected native
output, discovery filtering, skips or fallback backends are changed.

- `test_python_direct_collection_values`: removed. Its entire fixture instantiated
  the deleted `python_translation_collections.CollectionRegion`, pinned leases and
  private constructor ABI. These are not a second supported collection API.
- `test_python_collection_regions`: replaced old compiled engine counters,
  `ClosedLease`, ABI instrumentation and backend comparisons with execute/prepared
  public tests: array aliases/live iteration, partial errors, Structure casefold,
  native Map numeric-key collisions, hostile keys and shallow fixed snapshots.
  Native Map's existing Python numeric-key semantics are asserted explicitly, not
  described as preservation of the retired typed-token map.
- `test_reference_visit_boundary`: removed generator suspension/visitor engine
  instrumentation; tests now assert retired visit/block calls fail before effects,
  custom visitor cannot override direct admission, and supported direct execution.
- Three tree diagnostic/measurement modules retain actual direct observer packets
  and their existing availability distinction. Both 81-vector packet tests remain.
  Equality instrumentation targets the direct compiler's equality binding rather
  than imports from the deleted translation engine. Synthetic replacements of
  ValueTree classes/methods are not admitted by the existing direct receiver seal;
  their old success/error-packet expectations are replaced by explicit fatal
  BoundaryViolation tests, without invoking those hooks or bypassing the seal.
  Shared measurement helper names remain available to existing importers.

This does not claim all historical native observer/collection behavior is now
supported. In particular native-coercion and old backend-specific measurement
consumers outside these six modules require separate work; they are not skipped.
