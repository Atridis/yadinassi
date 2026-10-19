1c-version: 8.3.27.2342  
os: Windows  
infobase-mode: файловая база  
infobase-locale: русский (Россия)  
session-locale: русский (Россия)  
compatibility-mode: НеУказан  

## XML checkpoint timezone (2026-10-19)

Owner-confirmed `Get-TimeZone` output for the XML checkpoint run:

- Id: `Central European Standard Time`
- DisplayName: `(UTC+01:00) Варшава, Загреб, Сараево, Скопье`
- StandardName: `Центральноевропейский (зима)`
- DaylightName: `Центральноевропейский (лето)`
- BaseUtcOffset: `01:00:00`
- SupportsDaylightSavingTime: `True`

The exact Windows identifier is **Central European Standard Time**, not
Central Europe Standard Time. Unicode CLDR maps its global (`001`) and Polish
(`PL`) entries to `Europe/Warsaw`:
[official Windows timezone mapping](https://github.com/unicode-org/cldr/blob/release-48/common/supplemental/windowsZones.xml).
This is the replay mapping for this fixture, not a claim that Windows and IANA
historical rules are identical at every date. A fixed `+01:00` offset is not an
adequate replacement for this seasonal timezone. The production interpreter's
host-local policy is separate from the recorded test environment.

Fixture replay uses `YADINASSI_TIMEZONE=Europe/Warsaw` and bundled
`tzdata==2026.5` (IANA `2026e`). This changes only the execution environment;
all output bytes remain compared without timezone normalization.

## TypeDescription checkpoint pending (2026-10-19)

`tests/values.bsl` now appends 146 guarded `types.*` observations for
TypeDescription, scalar/binary qualifiers and their system enums. The existing
Null/XML blocks and all saved output files are unchanged. `output/values.out`
contains only the previously confirmed 784 lines, ending at
`xml.checkpoint.complete: [ok]`; there is no owner output for the new tail yet.

Run the normal launcher against the owner's real 1C platform and return the
actual `values.out` (and `.err`, if present). The new source must reach
`types.checkpoint.complete: [ok]`. No expected native answers, type GUIDs, or
runtime support are supplied by this checkpoint. Local pending-tail framing
checks are packaging checks only; they must be replaced by full native
comparison when the genuine output is received and implementation is ready.

BinaryDataQualifiers is inspected without BinaryData runtime values. Binary
value coercion is neither probed nor claimed. Official names/signatures are
from the verified EDT 2026.2 generic documentation package described in
`features.md`; runtime details require this native run.

The original strict full-output comparator is unchanged and currently fails on
values.bsl, as expected for this native-pending draft. Separate prefix/framing
checks do not replace that gate. Full unittest and release build remain blocked
until genuine output and the corresponding runtime implementation are present.

## Owner TypeDescription output and receiver supplement (2026-10-19)

Owner commit `e745497fc9a46d5c8b18817347010dfb6a2acbe3` supplied the genuine
5,182-line `values.out`, blob `db5180be398036d259dc91650ea2dc4a7d88d601`.
SHA-256: `0b80e880cde1ba4a9e189e3ed1cd36e2560f27efa374b0853a839d245e3608b2`.
All 146 labels and final marker match the source order; the prior 784-line
prefix and the other five outputs are unchanged, with no `.err` file.

Fourteen direct constructor/member expressions produced `[error]`; these do
not establish the behavior of ContainsType, default AdjustValue, or aliases.
A 23-observation `types-extra.*` supplement invokes methods through parameter
receivers, adds four syntax controls, and observes full qualified descriptor
streams/inverse reads plus scalar qualifier fields. The existing owner output
is untouched. No supplementary output has been generated locally.

Please return real launcher output ending in
`types-extra.checkpoint.complete: [ok]`. Full native comparators remain strict;
packaging checks and preserved-prefix checks do not replace them.
