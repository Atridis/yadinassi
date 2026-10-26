# CONFIG/root failure-only delimiter diagnosis

This separate experimental lane answers one bounded question on a **new
witness**: which mandatory delimiter gate rejects the fixed selected CONFIG/root
under the existing literal grammar? It does not broaden the accepted language,
resolve the GUID target, accept native metadata, or establish applied state.

The earlier root-reference observation failed with the generic
`config_root_grammar` code. That report cannot identify the failed delimiter.
Without postimage equality, a later diagnostic result cannot retrospectively
identify the guard hit by that earlier run. Source-informed grammar is not a
universal statement about native file-database syntax.

## Separate failure-only mode

- Host/container flag: `--config-root-diagnostic-observation`.
- Lane: `owned_config_root_diagnostic_v1`.
- Report/capture/invocation schemas: **21 / 22 / 15**.
- Policy: `scripts/native_1c_db_oracle/config_root_diagnostic.py`.
- Profile: `config_root_diagnostic_8380_8192_v1`.
- Literal recipe SHA-256:
  `200fad1e58775d99e94b5d3b649aff6fcd042b5d1aad71639f4f8b55f12cb131`.

The previous parser, observers, profiles and policy modes are unchanged. A
private sibling scanner recognizes the same initial UTF-8 BOM, permitted ASCII
whitespace, opening brace, canonical `2`, comma, bare GUID, closing brace and
end-of-input. It does not call the old parser or create a GUID lookup key.
Only three old generic delimiter sites acquire separate fixed codes:

| Category | Code | Meaning on the new witness |
|---|---|---|
| `structural_rejection` | `config_root_open_brace` | Opening-brace gate rejected |
| `structural_rejection` | `config_root_comma` | Comma gate rejected |
| `structural_rejection` | `config_root_close_brace` | Closing-brace gate rejected |
| `diagnostic_stop` | `config_root_diagnostic_complete` | Literal syntax completed; intentionally stopped before target lookup |

Completion is an exact private `CatalogError` subtype with a no-argument,
fixed-code constructor. Only this policy maps its exact type and code; subclasses,
mutated codes and use of the new codes by old policies reject. Completion is
**still failure, not acceptance**, and does not reproduce the earlier rejection.
The finite stage reveals bounded parser progression, not the unexpected token.

## One budget, one root, no successful continuation

One inherited CatalogReader construction performs its existing charged bounded
setup. New operation/context reservations then precede new allocation/work;
there is no claim of reservation before that inherited constructor.
The same cumulative budget and ownership graph serve the full selected-row
name/part/dynamic/duplicate guard scan, fixed-root lookup, one root chain and one
unchanged strict decode. The operation stops after one syntax scan. No target
lookup, target chain, remaining-chain read, second parse, reset, refund, fallback
or private cache is allowed. Every stop poisons constructed chains and decoder.
Root-only diagnosis is not an all-selected transport or no-sharing witness.

All inherited ceilings remain unchanged/lowerable only, with exact integer
(non-Boolean) validation. The root syntax ceiling remains 1024 bytes **after**
the unchanged decoder's 4 MiB per-entry limit; there is no early inflate-cap claim.
Existing context output weight 1024 is retained, plus diagnostic output 256 and
work 128. Output 4096 for the finite failure record is reserved upfront on the
same budget. Map weight is output `512+8*units`, work `4*units+32`; lookup is
output 128/work 256; parser is output 512/work `4*L+128`. These are conservative
policy weights, not measured heap usage. Resource-limit failure is never bypassed
to guarantee a more informative diagnostic.

## Closed evidence and unchanged isolation

The capture contains exactly schema, failed status, finite category and finite
code. No payload, GUID, selected private name, key, hash, length, offset, snippet,
token class, root counter, target relation, projection or success binder exists.
The inherited source/image/provenance bindings remain mandatory.
The closed vocabulary has **137** category/code pairs: the prior 136 minus
generic root grammar and two target-only failures, plus the four outcomes above.

The container's intermediate transport can prove its native-process/raw-file
cleanup gates only. It is never accepted. Final retention requires **all four**
native-process, raw-file, container and private-staging cleanup gates. Any final
false gate discards the finite capture. Malformed/unknown fields, success-looking
reports, wrong source closure/schema/provenance, and mismatched transport exit
status reject. Both syntax rejection and syntax completion leave the host and
workflow nonzero; authenticating the finite observation is not a successful CI
or root-reference acceptance result.

Cold staging is exactly **23** sources: the existing 21 metadata sources,
common reader and this replacement policy. No old CONFIG policy, broad PARAMS,
DBNames/named-file or record reader is imported. Default mode, credentials,
pinned image, UID/GID, read-only mounts, isolation, 2400-second execution limit,
13 stages, 11 snapshot slots, 5 comparisons, 3 artifact slots and 4 cleanup gates
are unchanged. The dedicated workflow selects this failure-only flag; its
nonzero outcome is not native acceptance or successful CI.

## Local finite proof and stopping condition

Focused synthetic tests cover all 137 allowed failed/nonaccepted pairs and wrong
pairings; exact completion typing; no successful producer/controller path; all
cleanup gates; host transport rejection; all four scanner outcomes through an
anchored frozen postimage; and exact23 cold producer/final-validator imports.

The complete report rectangle retains every lifecycle/source/context/artifact
field at its independent maximum, even though baseline failure cannot realize
all those maxima together. With the full unchanged 12288-byte capture allowance
and final newline it is **31387 / 32768 bytes**, margin 1381. This is tighter than
the 31468 design rectangle because failure-only verdict fields need no old
success strings; no field or cap was removed. Valid-pair capture maximum is 110
bytes; the independent category/code rectangle is 118 (119 with newline).

No native result is supplied by these tests. Any separately authorized genuine
execution must stop after one terminal source-bound report and cleanup audit.
A delimiter code justifies investigating that source assumption; another finite
error is inconclusive; completion means the earlier rejection was not reproduced
on the new witness. None authorizes an automatic retry or wider grammar.
