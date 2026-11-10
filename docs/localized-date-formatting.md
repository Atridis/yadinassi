# Localized Russian date Format

This block extends the existing bounded `Format` / `Формат` date pipeline, not
the interpreter. It uses an explicit Russian standalone profile, independent of
host locale and live infobase regional settings. Other locales and localized
parsing remain outside the profile.

## Supported presentation

`DF/ДФ` supports `d dd ddd dddd M MM MMM MMMM y yy yyyy q h hh H HH tt m mm s ss`
and the measured Russian aliases: `д`, `М`, `г`, `к`, `ч`, `Ч`, `в`, `м`, `с`
with the corresponding supported widths. Lowercase `h/ч` is 12-hour time;
uppercase `H/Ч` is 24-hour time. `tt/вв` emits AM/PM. Short/full weekdays use the
native Russian spellings, independently of OS locale.

Full and short month names use the grammatical day context when a real `d/dd`
token is present anywhere in the mask. Weekday tokens and quoted literal day
letters do not trigger it. For example, `MMM` yields `март`, while `d MMM`
yields `2 марта`; this is not a generic truncation rule.

`DLF/ДЛФ` provides five styles: `D/DD/T/DT/DDT` and `Д/ДД/В/ДВ/ДДВ`.
Long local styles preserve the native nonbreaking space before `г.`. Explicit
DF literals retain their exact supplied spaces instead.

The first occurrence wins within each date alias; the Russian alias has priority
over its English counterpart. DF has priority over DLF regardless of ordering,
including a quoted empty DF. DE/ДП retains the existing empty-date policy.
Malformed directives are still validated even when another directive wins;
unmeasured permissive parsing is not inferred from these selection rules.

The existing scanner handles quoted multiword masks and quoted literals. Bare
multiword masks fall back to the existing date presentation. Unsupported widths,
unknown letters/styles and unsupported locales remain explicit errors. Input and
expanded output retain the existing 4096 UTF-16-unit limits. This is not the
complete native formatting grammar.

## Independent native evidence and required comparison

Run [42792967665](https://github.com/Atridis/yadinassi/actions/runs/42792967665),
Linux 1C 8.3.27.1508, acquired **52 month-name/context cases and 56 token/style/
precedence cases**, each with two calibration records. Both logical native
client/server sites produced identical bytes. Source, tree, nonce, cleanup,
archive digests and capture digests were checked before retention.

The captures and exact attribution are in `tests/fixtures/format_dates/`:
`names52-native.out`, `tokens56-native.out`, and `localized-provenance.json`.
The original `*-mapping.json` files are immutable pre-acquisition input maps,
not a mutable declaration of current acceptance. The acquisition revision had
accepted native measurements but rejected runtime parity; that fact remains
recorded, not rewritten as a successful comparison.

The renderer now implements these measured families and offline replay compares
the complete captures, including calibration records. The **same fixed source
profiles** `format-date-names-v1` and `format-date-tokens-v1` now require runtime
parity in CI. There is no measurement-only success bypass. Fresh native
comparison of the aligned implementation is required before Ready/merge.

The original numeric/date source checkpoints and captures remain unchanged.
Native results do not claim arbitrary locale, GUI, infobase-region, timezone or
unmeasured date-boundary compatibility.

Official reference: EDT 2026.2 Syntax Helper archive
https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar
SHA-256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`,
`nl/{ru,en}/html/SyntaxHelperContext/objects/Global_context/methods/catalog20/Format971.html`.
