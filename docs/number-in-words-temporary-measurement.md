# Temporary NumberInWords native acquisition

This branch temporarily replaces the `format-numbers-v1` source and contract
with a fixed 29-case `NumberInWords` / `ЧислоПрописью` measurement. It does
not add a CI job or claim any native output. Restore the original Format lane,
its profile hash, contract and tests after acquiring and preserving the exact
source and authenticated native output/provenance. Do not amend historical
fixtures. A passing parser or synthetic witness is not native evidence.

The fixed cases cover Russian and English localization, zero and negative
values, Russian 1/2/5 and 11/21/22/25 with a masculine subject, feminine
subject, English currency singular/plural, thousands (1/2/5), millions, decimal inputs, Russian fractional
spelling and currency subject, the documented English currency example, and
arity/type boundaries. Each call is evaluated once. The source uses explicit
locales; no native answer is predicted. See 1C's [English example](https://its.1c.ru/db/content/metod8dev/src/platform81/transitq/value%20types/i8102518.htm),
[subject-parameter examples](https://its.1c.ru/db/content/metod8dev/src/developers/platform/metod/other/i8102317.htm),
and [language overview](https://v8.1c.ru/platforma/chislopropisyu/).

The existing UTF-16-unit hex encoding is lossless and each response is bounded
to 64 code units, never truncated. Two calibration records plus 29 maximum
records occupy exactly 7,967 bytes, below the unchanged 8,192-byte hard cap.
Larger or non-string results are observer errors and reject acquisition; they
must not be interpreted as native action errors. All four initial ru/en
controls must succeed, and any observer error, missing record, invalid wire,
incorrect source hash or incomplete output rejects availability. Remaining
action errors are observations, not asserted outcomes. This measurement is
source-bound and platform/run provenance remains required.

During the temporary swap, the original 48-case replay takes its source from
the SHA-verified prefix of the immutable 56-case fixture and uses a byte-for-
byte copy of the previous validator in `tests/historical_format_numbers_contract.py`.
The extended 48-case replay uses the same historical validator. Their fixtures
and expected native captures remain unchanged. Restore both tests and remove
the temporary helper together with the profile after acquisition.
