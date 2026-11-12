# Bounded regex extensions, awaiting native calibration

This recovered candidate extends the existing bounded engine with leading and
scoped `i`, `m`, `s` flags (including `-` overrides), atomic positive/negative
lookahead and numeric references to previously closed capture groups. Matching
uses an iterative VM, not Python `re`. Assertion frames and backtracking states
share the caller's work/state budget; lookahead does not reset search budgets.

Positive lookahead retains the first successful capture state without consuming
input. It does not backtrack into that assertion when later matching fails.
Negative lookahead discards captures and succeeds only after all internal paths
fail. Backreferences use the flags active at the reference and fail when their
capture did not participate. These are authored local semantics, **not yet a
claim of measured native parity**.

Named groups/references, lookbehind, arbitrary inline flags, mid-pattern bare
flag declarations, Unicode-property extensions, atomic groups, conditionals,
possessive quantifiers and octal escapes remain explicitly unsupported.

Native acquisition PR #298 has twelve owned observations, but run 43095625553
has not produced accepted evidence. No fixture or expected-answer substitute is
created. Thirteen replay/integrity tests may be added only after the real output
and exact-source/ownership/cleanup evidence are verified. Old pre-rollback test
results do not certify this reconstructed parser/VM.
