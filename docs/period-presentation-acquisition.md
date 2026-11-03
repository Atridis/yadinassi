# PeriodPresentation acquisition-only profile

This temporary source-bound probe replaces the active format-dates matrix without
changing the number of CI jobs or the 8192-byte transport cap. Its 28 fixed
expressions include four existing Format channel controls and 24 independent
`ПредставлениеПериода / PeriodPresentation` observations. It contains no
predicted native answers. The source SHA-256 is
`15d1986a4e9c08d2b0e76fd09f3ed6b6d4a8f0a91364119e1edcb6673ddb3e57`.

The fixed cases cover a day, month, leap February, quarter, full year, adjacent
months, financial half-year and nine months, partial ranges, reversed and empty
dates, times within a day, explicit Russian and English locale and EN/RU aliases.
Their expected outputs, error conditions, locale fallback and precision behavior
must be acquired from the real 1C platform. The observer retains up to 64 UTF-16
units per answer, and distinguishes action-error from observer-error. Four Format controls test the channel; the first Russian and English
PeriodPresentation cases must also succeed for availability. Classify every
observed case before adopting behavior. An action-error does not
identify whether expression syntax, argument or operation caused it.

The server capture is exported; client agreement is established by digest,
length and count, not a second exported raw capture. Authenticate source,
checkout tree, runtime/version, both observations, output and provenance;
interpreter parity is expected to fail on this measurement-only head. Preserve
this source and capture separately and restore the original active profile,
contract and historical tests before merging any runtime implementation.
The existing 1C description of day/month/quarter and financial periods is the
[official reference](https://its.1c.ru/db/content/metod8dev/src/platform81/transitq/common/i8102417.htm).
