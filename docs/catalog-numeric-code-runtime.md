# Numeric Catalog Code: bounded read-only runtime

This extension provides CONFIG-derived read-only binding, not a write API or a
Catalog BSL manager. The bounded public-reader native parity described below was
authenticated at its original source; it is distinct from the measurement lane.
The original [measurement](catalog-numeric-code-measurement-plan.md) at6ed1f845
verified lengths3/6, positive committed values and Payload32/64 only.

## Closed admission

The original `owned_catalog_string_code_two_attributes_v1` compiler profile still
rejects Number code. The new explicit
`owned_catalog_string_or_number_code_two_attributes_v1` profile admits CodeType0
(Number) or1 (String); the public raw/typed coordinator selects it consistently.
`CatalogBinding.code_type` is keyword-only with default1, preserving existing
positional construction and String behavior. Exact primitive types and profile,
qualifier and limit domains are revalidated; frozen objects are not trusted merely
because their constructor once ran.

Number CodeLength supplies N precision, with scale0, CS, nonnullable, ordinal4,
width `(CodeLength+2)//2`. String remains NVC/CI with width `2+2*CodeLength`.
The Number ceiling38 is the existing local numeric decoder/resource grammar,
not a claim about native metadata maximum. Other precision values are structural
generalization, not additional native observations. Description0 retains seven
fields; positive Description retains the independently admitted NVC placement.

The record boundary independently reconstructs declarations, widths and offsets
before DATA. It reuses the strict N decoder: sign nibble0/1, decimal digits and
zero unused even-precision padding. Number Code values are exact `Decimal` with
exponent0, independent of the caller's decimal context. The typed wrapper joins
code_type/code_length to CONFIG and projects the UUID only after full admission.
Both APIs use the same single CONFIG/PARAMS/records owner graph and cumulative
budgets; failure poisons the graph, with no fallback or second read.

This read grammar does not establish native assignment behavior for zero,
negative, fractional, overflowing or autoallocated codes. Fractional physical
Code descriptors are rejected (scale must be0). No String-to-Number conversion,
uniqueness/write behavior, arbitrary qualifiers, extra fields or hierarchy is
introduced. Fixed lengths3/6 and fixture values are not runtime selectors.

## Validation

Synthetic tests cover nonfixture odd/even precisions, lowered bounds, forged
profiles/limits/bindings, Number/String descriptor mismatch, Decimal values,
Description0/positive, Payload32/64, one graph and exact/one-less budgets.
Current compatibility-integrity source pins track changed files directly; they
are not historical activation receipts. The original measurement receipts remain
bound to their original source. The separate public-reader acceptance lane reads
each present postimage once and requires actual Code/UUID/Description/metadata
parity in both cases and all created/updated/applied states.

## Integrated public-reader acceptance lane

`catalog-numeric-code-rows-v1` is separate from the original observation lane.
It uses invocation31/report62/capture63/aggregate64 and an exact43-source closure.
Its adapter calls the actual public `read_catalog_rows` once per present frozen
postimage and constructs a bounded private view from that returned result. It
never calls `read_numeric_code`, recompiles metadata or opens another graph.
Native witness values remain private and are not selectors. Successful capture
requires every Code, UUID, Description and metadata comparison to match in all
created/updated/applied states; differences or unresolved layouts fail closed.
Baseline is absent. Old measurement outcomes and original receipts are unchanged.

The same schema1 private witness, metadata rendering and native commands/stages
are reused. The same two credential jobs use separate fixed artifacts
`numeric_code_rows3.json`, `numeric_code_rows6.json` and
`numeric-code-rows-aggregate.json`, with exact same-run precredential handoff.
All three paths are explicitly admitted by the existing exclusive no-follow
exporter; foreign paths, links, existing files and identity drift still reject.

Independent rectangular serialized maxima are5985 capture,28691 full report
(including the entire8192-byte capture reservation),610 aggregate and1207 private
witness bytes. Existing8192/32768/2048 caps are unchanged. The conservative public
`runtime_support=not_claimed` wire label remains unchanged; bounded parity does
not establish arbitrary layouts or write semantics.

## Authenticated public-reader parity

[Run41103649225](https://github.com/Atridis/yadinassi/actions/runs/41103649225),
at commit `17f29e0acf3348f5b2a74c48bac8fe911506f6d4`, tree
`3cf841fbc0404bd7cfa6588c5d0de1565a9da805`, verified both fresh cases through the
actual public reader. All six created/updated/applied states matched actual
committed Code, UUID, Description and metadata; baselines were absent.

| Configured CodeLength | Admitted descriptor | Width | Offset | Record sizes: created / updated / applied | Payload lengths |
| --- | --- | --- | --- | --- | --- |
| 3 | N(3,0) | 2 | 50 | 141 / 141 / 205 | 32 / 32 / 64 |
| 6 | N(6,0) | 4 | 50 | 143 / 143 / 207 | 32 / 32 / 64 |

DescriptionLength8 and one active row were verified throughout. The exact43
source closure, both cold FINAL/checker modes, eight fresh observe tokens,
precredential same-run handoff and all four cleanup gates were authenticated.
Private values are not included in this evidence summary.

Audit RESULT SHA256:
`7295d4f004b5b846efceefe29667702ed0be03b10991757fe0c7a7ce0dcc73f2`;
audit seal:
`0b29669668fbecc49432ab018a3cda0a89e01f33cd13d31937643b8496ac98d4`.
The earlier42-source measurement at6ed/run41069562516 retains its original
attribution. The later Core+DB union preserves these exact43 bytes, but has a new
whole-runtime inventory: this receipt is not a combined-head CI/native receipt.
Other code lengths remain structural generalization, and the deferred assignment,
autonumbering and platform/layout scopes above are unchanged.
