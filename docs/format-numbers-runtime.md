# Формат / Format: bounded numeric runtime

`Формат / Format(Value [, FormatString])` is a separate presentation function;
`String` and its existing conversions are unchanged. The default is a fixed
standalone Russian presentation policy, not discovered user/OS/infobase locale.
Only explicit `L=ru` / `Л=ru` is supported. There is no locale setter or database
context transport. Native infobase defaults are configurable; see the
[official regional formatting description](https://1c-dn.com/library/formatting_values/).

## Evidence

The first 48 fixed expressions were observed on Linux 1C 8.3.27.1508, with
identical client/server captures, in [run 41184098782](https://github.com/Atridis/yadinassi/actions/runs/41184098782).
`tests/fixtures/format_numbers/provenance.json` binds the capture to its exact
source, PR head, checkout tree, and artifact identities. Tests replay the whole
measurement, not a lookup table of expressions or values. The one action-error
is the third argument; observer failures are not accepted.

Eight additional cases from [run 41185012239](https://github.com/Atridis/yadinassi/actions/runs/41185012239)
are retained as immutable `supplement56.bsl`, native capture and provenance in
that fixture directory. All original 48 native output records are unchanged.
Three distinct unknown names/values are ignored, NG=3,0 repeats groups of three,
and NG=3,2 repeats pairs after the final triplet. Later authenticated parser-family
probes corrected the initial mixed-case inference: numeric aliases are exact-case,
with last-canonical-value selection; lowercase names are ignored. These witnesses support a generic rule, not a dispatch
on the literal names/values of test cases.

The required native runner restores the original 48-case source. Offline tests
also replay the six supported supplemental cases, while explicitly asserting
that ND (native-supported supplemental control52) fails closed. Custom DF
control53 is now admitted by separately measured numeric-mask Date support. This is a documented gap, not claimed 56-case parity.

## Numeric behavior

Supported parameters and Russian aliases are `NFD/ЧДЦ`, `NDS/ЧРД`, `NG/ЧГ`,
`NGS/ЧРГ`, `NZ/ЧН`, `L/Л`. Defaults: decimal comma, NBSP digit separator,
repeated groups of three, only significant fractional positions. Explicit NFD
pads exactly that many places and rounds magnitude half away from zero; a
rounded zero has no minus sign. Decimal coefficient/exponent manipulation uses
strings, never float, host numeric format, quantize, or ambient Decimal context.
Caller precision, exponent range, rounding, traps and flags remain unchanged.

NZ applies to the **original zero**: absent means empty, a nonempty NZ value is
its presentation, and present-empty NZ renders numeric zero. A nonzero input
rounded to zero retains numeric zero, not NZ. An empty NGS means NBSP; a quoted
ordinary space remains U+0020. Explicit decimal/group separators preserve Unicode.

Grouping uses one or two nonnegative widths: single A splits the final A digits
only; A,B repeats B for the remaining digits, or repeats A when B=0. `NG=0`
disables grouping. This generic algorithm follows the
[official grouping specification](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Administrator_Guides/1C_Enterprise_8.3.22_Administrator_Guide/Chapter_6._Infobase_administration/6.5._Regional_infobase_settings/).
Native witnesses establish NG=0, NG=3, NG=3,0 and NG=3,2; broader width checks
are documentation-derived local tests, not additional native measurements.

## Scanner and unsupported directives

The whole mask is consumed. Numeric and locale parameter names use exact uppercase
spelling; lowercase names follow the generic unknown-name no-op rule. Date keys
use their separately documented selection rules. ASCII spaces/tabs around fields and semicolon
separators are allowed. Single- or double-quoted values preserve punctuation and spaces;
doubled matching quotes represent that quote. Bare values trim outer space/tab.
Canonical duplicate aliases use the last value, but every entry is validated;
an invalid overwritten entry is not silently accepted. Malformed quoting,
missing assignments, unsupported locale and out-of-subset parameter values
raise an error rather than a plausible default.

Unknown ASCII/Russian letter-only names use a generic no-op rule; no expression/fixture-name dispatch exists. Recognized but
unimplemented native ND/ЧЦ, NS/ЧС, NLZ/ЧВН, NN/ЧО, NF/ЧФ, DLF/ДЛФ,
BF/БЛ and BT/БИ explicitly fail. This is not complete native numeric, Date,
Boolean or locale formatting support. The NF/ЧФ numeric-template family is
specified in the [official localization guidelines](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_Development_Standards/Localization_requirements/Localization_guidelines_____Dates__numbers__and_Boolean/?language=en)
and must not fall through the unknown-name no-op path.

## Dispatcher and explicit local policies

Exact Number (Decimal), String, Boolean, Date, Undefined and Null values are
accepted. Non-numeric values use their existing String presentation after mask
validation; supported numeric directives do not affect them. Date values now use the separately measured [numeric-mask Date slice](format-dates-runtime.md),
including empty-date presentation. Out-of-range Date states remain rejected.
This does not establish unmeasured Date/Boolean/locale families. Objects and Python primitive subclasses are
rejected without invoking arbitrary conversion hooks.

A missing second argument uses the empty mask. A finite exact Number as second
argument means no directives (measured for 2; generalization is local policy).
Other second-argument types and explicit argument holes are unsupported.

Resource/grammar boundaries are **Yadinassi policy, not measured native limits**:
4096 UTF-16 units for mask/result; at most 4096 input coefficient/expanded integer
digits; fractional exponent no smaller than -324; NFD 0–324; NG at most two
widths, each 0–32 (zero first width only alone). Non-finite Numbers fail explicitly.
Text output is bounded before separator expansion. Wider precision, malformed
masks, escaping extensions and unmeasured combinations have local tests, not a
claim of native equivalence outside the stated slice.
