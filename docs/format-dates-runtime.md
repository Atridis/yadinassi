# Bounded numeric-mask Date Format and family-specific parameters

`Format` / `Формат` now admits explicit numeric Date masks `DF/ДФ` and empty-date
presentation `DE/ДП`. This does not alter `String(date)` or numeric arithmetic.
It is not full native date, Boolean, locale or numeric-template formatting.

## Evidence and separate required contract

Original40, supplemental56 and parser28 were independently authenticated on
Linux1C8.3.27.1508, configured UTC, in runs
[41197040716](https://github.com/Atridis/yadinassi/actions/runs/41197040716),
[41197666432](https://github.com/Atridis/yadinassi/actions/runs/41197666432) and
[41198252916](https://github.com/Atridis/yadinassi/actions/runs/41198252916).
All captures, original sources and source/run/artifact attribution remain under
`tests/fixtures/format_dates/`. These measurement revisions had accepted native
acquisition but rejected interpreter parity; their historical red gate remains
truthfully attributed. The implementation's fresh native acceptance is pending.

The final mandatory `supported56.bsl` is a **different, explicitly scoped**
source, byte-identical to the active closed-lane `format_dates.bsl`. Each case
maps to an exact authenticated expression/source/capture in
`supported56-mapping.json`: original40 cases1–34,37–40; parser28 cases
2,4,6,8,10,12,14,16,18,20,22,23,24,25,26,28; supplemental56 cases44,47.
Its rectangular maximum is8170 bytes inside the unchanged8192-byte limit.
The mandatory parity validator is unchanged. Full archived offline replay
also includes supported cases outside this required probe, including standalone
lowercase `nfd`. Original numeric48 remains the required numeric lane unchanged.

Explicit excluded policy controls: original40/supplement56 cases35 (MMMM) and36
(hh tt), and parser28 case27 (L=en). Tests require local rejection separately
from matching every supported archived observation; they do not rewrite the
stored captures or call the complete historical probes runtime parity.

## Parameter families

Numeric keys (`NFD/NDS/NG/NGS/NZ` and their Russian aliases) and locale keys
`L/Л` use exact uppercase spelling. Lowercase numeric/locale names are ignored
by the generic unknown-name rule. The former blanket uppercasing was incorrect:
parser28 plus supplemental56 establishes this for each supported numeric
family. Repeated numeric aliases retain the last canonical value. Existing
numeric48 and all previously supported supplemental numeric56 cases still replay.
The archived numeric56 Date control53 is now supported; its ND control52 remains
an explicit unsupported policy boundary.

Date aliases are case-insensitive, first occurrence wins within each alias,
and the Russian alias takes priority over the English alias regardless of order.
DF and DE each use this distinct rule; there is no shared global last-wins map.
Quoted parameter values accept single or double quotes, with doubled matching
quotes inside a parameter value. This parameter grammar is separate from
single-quoted literals inside a Date mask. Unknown names remain no-ops, while
recognized unsupported native families remain explicit errors even in lowercase
as a deliberate conservative local policy. Every supplied directive is validated,
including overwritten/ignored duplicates; malformed syntax cannot hide behind
selection order. Resource/grammar restrictions are Yadinassi policy, not claims
about all native behavior.

## Date rendering

Supported tokens are exactly `d dd M MM yy yyyy H HH m mm s ss`. Numeric fields
are built from existing validated Date components, not host locale or strftime.
Year1/year9999 are supported; fractional ticks use the existing whole-second
component policy. Out-of-range boundary states remain rejected.

A quoted multiword mask is rendered; a bare mask containing spaces/tabs uses
the default existing Russian date presentation. Bare no-space masks render.
Unsupported tokens are rejected before this fallback: `MMMM`, weekday names,
12-hour `h/hh`, AM/PM and DLF are not accidentally enabled. Single-quoted Date
literal spans are copied; adjacent apostrophes delimit an empty literal, not
SQL apostrophe escaping. Nonletter separators and numeric tokens are handled
by a bounded scanner; unquoted unsupported letters and unterminated literals fail.

For exact empty Date (known ticks0), absent DE returns empty text; nonempty DE
returns that presentation; present-empty DE renders the actual first-day Date
using the selected numeric mask or default. First-day plus one second is not
empty. Non-Date scalar values retain their presentation after supported DF/DE
validation; custom Boolean formatting remains unsupported.

Locale policy remains standalone Russian presentation: exact `L=ru` / `Л=ru`
only. Observing native L=en does not enable it locally. Mask/result bounds remain
4096 UTF-16 units; allocations are checked before returning expanded output.

Official [localization guidance](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_Development_Standards/Localization_requirements/Localization_guidelines_____Dates__numbers__and_Boolean/?language=en)
distinguishes custom date format DF, empty-date presentation DE and localized
DLF. Only the first two bounded families are implemented here; the regional
[infobase settings](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Administrator_Guides/1C_Enterprise_8.3.22_Administrator_Guide/Chapter_6._Infobase_administration/6.5._Regional_infobase_settings/)
remain configuration-dependent native behavior, not host locale inference.
