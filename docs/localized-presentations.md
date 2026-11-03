# NumberInWords and PeriodPresentation: bounded standalone workflows

`ЧислоПрописью / NumberInWords` and `ПредставлениеПериода / PeriodPresentation`
provide two further localization operations without a database or host locale.
The default standalone language is Russian; explicit `L=ru`, `L=ru_RU`,
`L=en` and `L=en_US` are bounded local policies derived from the observed
Russian and English cases, not automatic inference from the user's machine.
Unsupported locales and format options fail explicitly.

## Native evidence

The fixed source packets were acquired on Linux 1C 8.3.27.1508 in
[run 41668287234](https://github.com/Atridis/yadinassi/actions/runs/41668287234),
head `d92a5ff8e40fd2ff51224c46be753c1fc3c74496`, merge checkout
`fbfe11093ff3265300d4510d913537c6b4ef4cc3`, tree
`405d2799e019b9e94d4d9e53077ce28bd46e4050`. The 29 NumberInWords and 28
PeriodPresentation observations (including expected errors and controls) are
retained verbatim with their exact sources and provenance under
`tests/fixtures/localized_presentation`. Server/client source, digest, size and
message counts agreed; the server output was exported, but the raw client output
was not separately retained. The original acquisition had failed runtime parity
because neither function existed then. Offline tests replay all records against
the current implementation; that replay is not a fresh native acceptance run.
Original Format measurement sources, contracts and fixtures remain unchanged.

## NumberInWords

The normal bounded path accepts exact finite Numbers with at most nine integer
digits and at most two fractional digits. It uses integer/decimal decomposition,
not binary floats or the caller's Decimal context. Russian cardinal morphology
and three singular/few/many noun forms, masculine/feminine unit gender, and
English singular/plural subject forms support common whole/fractional amounts.
The observed empty subject, 2-digit fraction, a spelled Russian fractional part
(`ДП=Истина`), negative sign and case-preserved initial capital are included.
Both Russian and English public names are registered.

Russian subject input is `one, few, many, gender`, optionally followed by
`fraction-one, fraction-few, fraction-many, gender, 2`. English subject input is
`one, many, fraction-one, fraction-many, 2`. Empty subject has no unit name.
The parser accepts only the bounded forms above and explicitly supported
`L/Л` and `ДП` options. Duplicate options fail closed until precedence is measured;
a finite Number as second argument follows the observed
numeric-format control as a local generalization. Locale, grammatical form and
case beyond the acquired witnesses and official documentation are not a universal
1C claim. Other scales, higher precision/rounding, other genders, more languages,
English fractional words and other format grammar remain `!todo` and fail closed.

## PeriodPresentation

Exact whole-second Date values support the measured empty period/open start,
whole day, calendar month, quarter, year, month ranges, financial first half-year
and Russian nine-month period, plus Russian partial-day/date ranges. Russian and
English output use fixed month/day names, not OS locale. An earlier start than
end is required; unsupported partial English ranges, fractional ticks, open end,
financial or calendar variants outside the stated rules, additional locales and
format options remain `!todo`. Finite observations support the measured shapes;
the calendar algorithm for other dates is a bounded generalization, not additional
native observations.

Text inputs and outputs are capped at 4096 UTF-16 units. These are Yadinassi
resource limits, not claimed platform limits. Hostile Python subclasses and
untrusted conversion callbacks are rejected by exact-type gates. NumberInWords
requires CPython C Decimal coefficient-allocation checks before tuple expansion;
it fails closed on implementations where that guard is unavailable. No external I/O,
physical 1C storage format, database, GUI or configuration locale is introduced.

Official references: [NumberInWords](https://v8.1c.ru/platforma/chislopropisyu/),
[subject and localization parameters](https://v8.1c.ru/obuchenie-programmistov/primery-razrabotki/sistemnye_protsedury_i_funktsii/kak_vyvesti_chislo_propisyu_po_angliyski.htm),
[PeriodPresentation](https://its.1c.ru/db/content/metod8dev/src/platform81/transitq/common/i8102417.htm).
