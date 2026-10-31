# Explicit date Format measurement (preparation only)

This adds a separate closed `format-dates-v1` native profile. It does not implement
DF/ДФ or DE/ДП and contains no predicted native expected strings. It is based on
the numeric Format runtime candidate c1dea2e0/tree8fb97c99 and was subsequently
composed onto the reviewed PR163 joint head c3dea7ba/tree5bda45bb, preserving the
zero-code measurement additions and merged zero-code reader runtime. Publication still requires a fresh actual-main binding. The original numeric48 required profile and archived
numeric56 observations remain unchanged, with their own original attribution.

## Forty fixed expressions

- 1–8: composed formats, EN/RU controls, one-digit components, leap day, midnight,
  year1 at one second (nonempty), year9999, and half-second date arithmetic.
- 9–20: d, dd, M, MM, yy, yyyy, H, HH, m, mm, s, ss individually.
- 21–26: zero date with absent/empty/word DE, mask and mask+DE, and nonempty year1.
- 27–34: single/double outer quotes, literal word/apostrophe/semicolon, RU aliases,
  duplicate and mixed-case parameter names. These are observations, not assumed
  grammar or success cases.
- 35–40: month-name and 12-hour controls, arbitrary unknown parameter, and numeric,
  Boolean and String arguments with date parameters. They do not extend the
  proposed numeric date-token implementation scope automatically.

The first four composed EN/RU cases are availability controls; all must succeed.
A matching unsupported-method result cannot pass. Other actions may succeed or
fail, and remain observations. Exceptions from the action and the observer are
separate finite statuses. Neither raw error strings nor arbitrary output escape
the observer. UTF-16 calibration includes NBSP, quotation, semicolon and a surrogate
pair. Every output string is captured losslessly up to32 UTF-16 units; an excess
rejects this bounded observer rather than asserting a native length restriction.

The fixed wire contains40 records and2 calibration lines. Maximum is5850/8192
bytes, with unchanged per-record/capture/transport limits. The profile stages22
files and captures helper-procedure messages through the established source-pinned
Format client transform. LF is explicit for the BSL source, tested through a real
Git autocrlf checkout. Future retained captures use byte-preserving attributes.

## Intended next runtime slice, subject to native facts

Explicit numeric date tokens and DE only; no DLF, localized names of months/days,
12-hour clock/AM-PM or general locale implementation. The parameter scanner must
be measured for single/double quotes and literal delimiters before being extended.
Do not use Python strftime or infer that every year1 date is empty. The half-second
case observes existing date arithmetic as part of the fixed expression; it is not
an independent native claim about sub-second storage.

Primary references (API design only, not native output evidence):
- https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_Development_Standards/Localization_requirements/Localization_guidelines_____Dates__numbers__and_Boolean/?language=en
- https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_8.3.23_Developer_Guide/Chapter_4._1C_Enterprise_language/4.3._Data_types_and_variables/4.3.4._Date/

No true native run, full aggregate, cross-platform CI or runtime parity is claimed
by local synthetic tests. Actual source-bound client/server acquisition is required.

## Authenticated original40 and bounded supplemental56

[Run41197040716](https://github.com/Atridis/yadinassi/actions/runs/41197040716)
on head `1eaf2de6b60e199f21debc3d182b779b4a74b153`, tree
`5b26651439777397d8d70e8598c23f501c37bd63`, acquired40 successful observations
with identical client/server bytes and no observer errors. Native acquisition
was accepted; interpreter parity was rejected and its required red gate is
retained. Exact original source, capture and attribution are archived under
`tests/fixtures/format_dates/original40*`; this is not date runtime support.

Quoted multiword date masks differed from bare multiword masks in these
witnesses. Empty DE differed from absent DE. Same-name duplicate DF and mixed
lowercase/Russian aliases gave different observations; these do not establish
a general alias/case precedence rule, and numeric parser behavior is unchanged.

The current temporary source appends16 discriminator cases41–56 after the
byte-identical original40 prefix: identical NFD/DF duplicates in both orders,
RU/EN aliases in both orders, standalone lowercase/uppercase names, and
bare/single/double-quoted multiword masks plus a no-space control. No new
expected native answers are supplied. All56 maximum-length records plus two
calibrations occupy8170 bytes within the unchanged8192-byte cap. The new native
acquisition is pending; original40 evidence must not be attributed to56 cases.

## Separately attributable parser-family28 measurement

Supplement56 was acquired by [run41197666432](https://github.com/Atridis/yadinassi/actions/runs/41197666432)
on head `13d06c4e603a02fcde0358bc33617bb29a67adfb`, tree
`d5d6d47375ab62ed88ad2df0eaf18b24ec716bd6`:56 successful native observations,
zero observer/action errors, original40 capture an exact byte prefix. Its source,
capture and provenance remain immutable as `supplement56*` fixtures. Native
acquisition accepted, interpreter parity rejected. In these witnesses NFD
duplicates/uppercase aliases select last, identical DF repeats select first,
mixed DF/ДФ chooses the Cyrillic value in both orders. Lowercase nfd differs
from uppercase NFD, but lowercase df works; blanket uppercasing is not justified.

The active closed lane now runs a **different28-case probe**, named
`tests/fixtures/format_dates/parser28.bsl`, byte-identical to its staged
`integrational_tests/measurements/format_dates.bsl` copy. It is not an extension
of56 nor a reinterpretation of those observations. Cases1–18 compare exact and
lowercase Latin NDS/NG/NGS/NZ and Russian numeric aliases;19–26 measure DE/de/ДП/дп
and DE duplicate/alias order;27–28 compare L/en and l/en. The maximum is4110
bytes within the unchanged8192-byte cap. No parser/runtime policy is changed.
Parser28 native acquisition is pending and cannot be inferred from prior runs.
