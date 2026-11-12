# Bounded regex extensions with source-bound native calibration

This recovered candidate extends the existing bounded engine with leading and
scoped `i`, `m`, `s` flags (including `-` overrides), atomic positive/negative
lookahead and numeric references to previously closed capture groups. Matching
uses an iterative VM, not Python `re`. Assertion frames and backtracking states
share the caller's work/state budget; lookahead does not reset search budgets.

Positive lookahead retains the first successful capture state without consuming
input. It does not backtrack into that assertion when later matching fails.
Negative lookahead discards captures and succeeds only after all internal paths
fail. Backreferences use the flags active at the reference and fail when their
capture did not participate. Supported composition and the explicit refusal
boundary are described below; general regex-engine equivalence is not claimed.

Named groups/references, lookbehind, arbitrary inline flags, mid-pattern bare
flag declarations, Unicode-property extensions, atomic groups, conditionals,
possessive quantifiers and octal escapes remain explicitly unsupported.

Native acquisition PR #298 now has verified output from run 43178980355.
The old orphaned run 43095625553 is not used. Old pre-rollback test results do
not certify the reconstructed implementation.

## Native calibration and explicit limitation

Run 43178980355 (1C 8.3.27.1508) supplied twelve source-bound observations.
Eleven match the runtime replay. Case 7 remains in the immutable native fixture
but is intentionally host-closed: a numeric reference cannot escape the lexical
lookahead scope that declared its capture. The native search returned no match
where the previously authored VM found a later candidate; a special-case result
or a guessed general search rule would be misleading.

This boundary does not close ordinary backreferences, references inside their
own assertion, references from nested assertions to an outer declaration, or
reading lookahead captures via GetGroups/replacement output. Only references
crossing outward from their capture's declaring assertion are rejected. No
12/12 runtime-parity claim is made; coverage is eleven native replays and one
explicit refusal regression. Wider assertion-reference composition is deferred.
