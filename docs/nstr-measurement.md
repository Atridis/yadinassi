# НСтр / NStr: explicit-language measurement plan

This revision is **measurement-only**. It does not implement either function,
claim native behavior, or add a supported syntax entry. It adds 36 independent
input-only expressions to the existing complete values scenario, taking its
message count from **485 to 521**. Native observations must be captured and
audited before selecting any runtime grammar, language-selection rule, fallback
or coercion. A failed measurement comparison is not implementation acceptance.

## Candidate runtime boundary, not a platform specification

The intended later slice is bounded multilingual string selection through
`НСтр / NStr` with an explicit String language argument. Its implementation, if
justified by evidence, belongs in the existing `yadinassi/strings.py`; this
measurement changes no runtime file and keeps the runtime inventory at 63.
Locale-dependent implicit selection, omitted/empty/non-string language arguments,
non-string templates, malformed grammar and duplicate-key rules may remain
unsupported even when this matrix observes their native behavior. No filesystem,
UI, database, metadata, environment lookup or cross-context transport API is added.

## Fixed input matrix

Each row invokes the function independently. There is no shared parsed template,
expected selected value, native error text or interpreter-derived native golden.
All normal rows explicitly pass a language; the six argument-policy rows are
clearly separated from the prospective explicit-language subset.

| Labels | Question, not an expected answer |
| --- | --- |
| `alias.ru.ru`, `alias.ru.en`, `alias.en.ru`, `alias.en.en` | Both function aliases, each selecting `ru` and `en` from the same two entries |
| `order.ru`, `order.en` | Same entries in reversed order |
| `spaces`, `tabs` | Spaces around grammar, preserved interior spaces, fixed U+0009 around `=` |
| `empty.template`, `empty.ru`, `empty.en` | Empty source and independent empty selected entries |
| `separator.trailing`, `separator.double` | Terminal and doubled separators |
| `quote.apostrophe`, `quote.double`, `content.semicolon.equals` | Doubled apostrophe, double quote, and `;`/`=` inside an entry |
| `unicode` | Cyrillic, astral character and decomposed combining sequence |
| `language.upper`, `language.mixed` | Language argument case |
| `language.missing`, `language.missing.reordered` | Absent language, with entry order reversed independently |
| `duplicate.first`, `duplicate.reordered`, `duplicate.case` | Duplicate entry order and identifier case |
| `malformed.unquoted`, `malformed.unterminated`, `malformed.no.equals`, `malformed.trailing` | Independent malformed-string discriminators; BSL expressions themselves remain valid |
| `language.omitted`, `language.empty`, `language.undefined`, `language.number`, `language.boolean`, `language.null` | Omitted/empty/non-string language, observation-only |
| `template.number`, `template.undefined` | Non-string template, observation-only |

These templates are fixed public test strings, not user data. Their string-input
lengths are independently pinned in the tests: **0–27 UTF-16 units**, including
the tab-composed input; language strings use zero or two units. These are INPUT
bounds, not a prediction that NStr returns a substring or a particular length.

## Independent action and observer stages

`НаблюдатьНСтр` evaluates one fixed expression and emits exactly one record:

- `action-error` if expression evaluation fails;
- `observer-error` if evaluation succeeds but the returned value cannot be
  projected as an exact String of at most 64 UTF-16 units;
- `ok|S<length>:<hex units>` for a successfully observed string, including empty.

The observer never converts arbitrary values to strings, normalizes text, emits
raw text or truncates oversized text. Its four-hex-digit-per-unit encoding is
lossless for whitespace, quotes, delimiters, combining sequences and surrogate
units. An observer failure is not an observed NStr error. Every following probe
still runs after either failure. Host-injected functions in unit tests exercise
instrumentation only; they never parse or model NStr grammar.

With the independent label bound of fewer than 40 ASCII characters, the complete
record including LF is at most **312 bytes**. All 36 additional records therefore
fit in 11,232 bytes even at that deliberately loose maximum. The existing full
one-megabyte output bound is unchanged and still applies to the entire scenario.

## Exact source, historical replay and live admission

- Current values521 source SHA-256:
  `9e1af33c93352aebf9166bf5f702f526f221df7e9945ba139ccbc3d1fd0a34e4`.
- It has 1,210 lines, 51 helper declarations and 34 message-call sites. The source
  hash, shape, message count and server/client admission pins advance together.
- The exact source-only inverse reconstructs every byte of values485, SHA-256
  `be2cdd08643e14747c4375d6f2f8a9f995c88e8ef028470fc29066329eeece76`.
  Its existing independently bound inverses then reconstruct values441 and402.
- Test-only harness inverses reconstruct the prior complete client adapters.
  Historical captures and finite native TextDocument witnesses keep their
  original identity. No output prefix is accepted, stripped or regenerated.
- The current live adapter rejects values485,441,402, altered helper/call shapes,
  changed input bytes, BOM and CRLF. Historical replay never changes live globals.
- The server and managed-client routes execute the full staged values521 source.
  There is no new scenario, observation channel, transport field or exception.

## Resource proof and validation boundary

The staged source inventory (24 files), six scenarios, historical captures, other scenario sources,
workflows, images, permissions, timeouts and all transport caps remain unchanged.
The existing finite production-serializer proof was rerun with values521 and
63 runtime members. Its conservative maxima remain **8,185 / 8,192 bytes** for
async stage wire and **32,531 / 32,768 bytes** for public summary. It also checks
all 32 parity subsets, 240 client failure frontiers, 224 early/server frontiers,
18 async majorants, exceptional invalidation, complete marker and provenance.
These are structural bounds, not native captures or permission to add a module.

Local parsing, observer controls, exact inverse/admission tests and structural
budgets do not establish native NStr results. The next externally authorized
step is a same-repository measurement PR and fresh native capture on its exact
head. Audit source/input/module/roundtrip identity, every independent record,
server/client agreement and failure cause before implementing a bounded subset.
That implementation then needs its own complete fresh native and four-OS gates.
