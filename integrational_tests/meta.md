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
