# Deletion-mark finite exception diagnostic

This separate unmeasured profile (`catalog-deletion-mark-diagnostic-v1`) uses the
same flat owned catalog and the strict Read/Insert/Update/Delete fixture, in a new
disposable infobase. The independently pinned `observe.bsl` SHA-256 is
`83ea20a0c0fd6722431bc1b0638c3e57b112859f0c9ee95708ece09a6dea361f`.
Prior source, captured A/B observations and rights fixture are unchanged.
The test objects and descriptions are fixed, owned fixture data.

## Bounded observations

For each of an existing detached object and an independent new object, call
`SetDeletionMark(True)` once. The observer sends exactly 20 Booleans:

- 1–5 existing and 11–15 new: exactly one of success, rights-pattern,
  lock-pattern, method-missing-pattern, other exception, in that order.
- 6–10 existing: local mark, persisted mark, local dirty Description,
  persisted dirty Description, persisted object not-new.
- 16–20 new: IsNew, Ref.IsEmpty, local mark, existence by code, persisted
  mark if found. The last value is false as a sentinel when no row exists;
  interpret it with observation 19.

The transport checks each five-value group is one-hot. An unmatched exception
is `other`, never success. If setup, exception classification or another
uncaught operation fails, the packet has no completed observation: missing data
are not converted to categories. Output is ordered, nonce-bound and Boolean-only.

Inside the source only, `ErrorDescription()` is lowercased and at most the first
2,048 characters are matched against fixed Russian/English substring patterns.
The first matching category wins in this precedence: rights, lock, missing
method, then other. Nothing emits error text. The staged suite keeps temporary
native logs and `result.json` inside the container; accepted artifacts contain
only canonical Booleans and finite provenance. Failure reports use the existing
closed categories and phases, without raw text or paths. New source disclosure
of raw errors, arbitrary messages, tokens or database records is not allowed.

A pattern is a text hint, not a verified exception type or cause. It can match a
negation, quoted text, nested cause or unrelated context (false positive), and
may miss a different language, spelling, wording or a match beyond the prefix
(false negative). Priority can mask additional patterns. The platform may treat
rights differently from the observed XML grant. Output cannot prove the root
cause, all 1C versions, effective access, or behavior of unmeasured contexts.
Classification is not a security decision or permission bypass.

## Evidence and invocation

The reused rights fixture admits exactly the four target-catalog grants and
verifies both prepared and official Designer redump before the action session.
The host has a distinct profile/schema and artifact directory; it pins staged
source/helpers, generated module, nonce, image, checkout and rights witness, and
requires cleanup. `catalog_rights_verified` is configuration/redump evidence,
not an independent check of effective rights. No interpreter parity is claimed.

Offline tests: `python3 -m unittest discover -s tests -p
"test_catalog_deletion_diagnostic_packet.py"`. Before any native acquisition,
review the source and fixture, run and review offline tests, obtain native ACK,
use a clean committed checkout, approved image and a fresh isolated infobase,
and enforce sequential session/cleanup boundaries. Then the candidate entrypoint
is:

    python3 scripts/native_1c_catalog_deletion_diagnostic_profile.py --execute-approved-image --export-native-outputs

Summary: `native-smoke/catalog-deletion-diagnostic.json`; validated successful
output: `native-smoke/catalog-deletion-diagnostic-outputs/catalog-object.out`
and `provenance.json`. Do not overwrite prior artifacts. Failure is not a
measurement. No test or native session was run during packet preparation.
