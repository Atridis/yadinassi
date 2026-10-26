# НСтр / NStr: bounded standalone compatibility profile

`НСтр / NStr(Template [, Language])` selects multilingual text through a generic
scanner in the existing `yadinassi/strings.py`. This is a bounded local policy,
not a complete native grammar, coercion or configuration-language model.

```bsl
Message(NStr("en='other';ru='выбрано'"));             // выбрано
Message(NStr("ru='первый';en='selected'", "EN"));    // selected
Message(NStr("ru='first';RU='second'", "ru"));      // first
Message(NStr("en='not a fallback'"));                // empty
```

## Fixed default, not discovered metadata

The immutable standalone NStr default code is explicitly **`ru`**. Omitted
language, the exact empty String, Undefined and Null use this code. Explicit
nonempty language is independent; a missing code returns empty, never the first
entry or another available language. Whitespace-only language is not omitted.
There is no setter, new Interpreter option, CurrentLanguage API, configuration
manager or context transport object. Imports, fresh logical server activations
and dual contexts use the same stateless builtin.

This is a deliberate Yadinassi policy consistent with the finite witnesses,
**not** an observed native configuration-language metadata value and **not** a
claim that 1C always defaults to Russian. Native configuration language is
distinct from platform language and formatting locale; omitted NStr language
uses the current user's configured language, otherwise the configuration
default. [Official 1C documentation](https://1c-dn.com/library/parameters_that_affect_user_interface_language/).
Yadinassi's NStr performs no OS, `/L`, locale, environment, metadata or database
lookup. Russian number/Boolean presentation does not infer configuration language.

## Implemented local grammar

- Consume the **whole template**, even after the first match. A malformed later
  entry invalidates an earlier selection and returns empty.
- Entries are `code=value`, separated by semicolons. Empty separator segments
  and trailing separators are admitted. ASCII space/tab are grammar whitespace.
- Codes contain only ASCII or Russian Cyrillic letters, including Ё/ё. Matching
  ignores case within that alphabet. The first duplicate wins, including an
  empty first value. Digits, underscores, locale tags and broader Unicode
  identifier classes are outside this slice; they do not enable fallback.
- Single quotes delimit values; doubled apostrophes encode one apostrophe.
  Quoted content preserves whitespace, double quotes, semicolons, equals signs
  and Unicode units. After the closing quote, only grammar whitespace and a
  separator/end are admitted.
- Bare values extend to the next semicolon/end, cannot contain apostrophes, and
  remove only outer ASCII space/tab. Double quotes have no quoting role.
- Missing `=`, invalid keys, unclosed quotes and quoted-value trailing junk
  return empty. There is no evaluation, interpolation or output lookup.
  Payloads are not Unicode-normalized; UTF-16 units are preserved.

The native witnesses support the measured shapes, not every extension above.
Bare-value trimming, all alphabet combinations, leading empty segments and other
unmeasured combinations are explicit local policies, not further native proof.

## Scalar boundary and evidence limits

Only exact String, Number (`Decimal`), Boolean, Undefined and Null are admitted.
They use the existing bounded `String` presentation before parsing/selection.
Undefined/Null templates become empty; a numeric template has no valid
assignment. Non-finite/excessive Numbers retain existing presentation failures.
Objects, arrays, structures, dates, UUIDs and arbitrary Python values/subclasses
are rejected before invoking their string hooks.

True agrees with its **positive** `String(True)` language control on a `Да` key.
Number(1) and `String(1)` controls are both empty, so they **do not** establish
numeric language coercion. Numeric codes are invalid in this local grammar.
False and other numeric/null combinations follow the stated primitive policy;
they are not additional independently observed native coercion families.

## Resource limits

Explicit Yadinassi limits, not inferred native platform limits:

- template: **1,000,000 UTF-16 units**;
- each key and supplied language presentation: **128 UTF-16 units**.

Excess produces a local resource error, not truncation. The iterative scanner
is linear in input length, keeps only the first selected payload, and validates
later entries without collecting every translation. Tests check work growth by
line-event counts, not wall-clock thresholds. No regex backtracking or recursion
is used. The measurement observer's **64-unit** limit is not a runtime output
limit; longer valid results are supported.

## Evidence and unchanged acceptance boundary

[Native run 40268511954](https://github.com/Atridis/yadinassi/actions/runs/40268511954)
executed the exact values534 source on Linux 1C 8.3.27.1508, server and managed
client. All **49** NStr observations returned Strings. The original 36 and full
521-message prefix were unchanged. Reordered omitted/empty/Undefined/Null cases
selected the Russian entry; en-only counterparts were empty while explicit en
selected positively. No configuration-language code was observed.

Source SHA-256:
`16bd5c91f17225906ef9e9e579371b8884eff74dafd67167b06e5a2dda2e55d5`.
Final audited 49-record ledger SHA-256:
`a506d12a8fff44bbb7ee8ddfbbebbfa49022d5cf09db23e0f5eed954b36a5d0c`.
Final audited 13-record ledger SHA-256:
`11599292635bc7a77f5755c80642648ccfe328ff931971346f657596a73410b1`.

`tests/test_nstr_native.py` contains only finite fixed public expressions/results
transcribed from that audit, with direct raw String/UTF-16 checks and a complete
534-message digest check. It loads no private capture, log or archive. The whole
scenario test sets the existing driver's explicit UTC policy for unrelated date
probes; this does not supply or infer NStr's language.

That measurement run failed host parity because NStr was then unimplemented.
The original failed final envelope is not promoted. Fixture replay is not fresh
native acceptance of this runtime: a new exact-head six-scenario comparison and
four-OS gates remain required. No full138 success is inferred.

All 49 probes, complete values534 source, live admission, source-only
534→521→485→441→402 inverses, historical captures and comparators stay unchanged.
Runtime inventory remains 63, staged inventory 24 and six scenarios/caps stay
unchanged. Rerun the full finite serializer proof with the new runtime provenance;
this builtin does not authorize an extra runtime module.
