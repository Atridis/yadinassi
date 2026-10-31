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
