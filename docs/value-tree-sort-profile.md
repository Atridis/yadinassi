# Fixed Rows.Sort native profile (local integration candidate)

The [standalone observer design](value-tree-sort-measurement.md) is now wired
into the closed `tree-sort-v1` profile. This is **not a native result**, runtime
Sort implementation, full-suite extension, or a shared golden fixture. Native
acquisition has not run. The 21-case scope preserves unknown observations;
real CompareValues instances remain deferred until that runtime type exists.

## Acquisition and acceptance

The fixed registry binds `tree_sort.bsl` SHA-256
`5607a0c42901d624cfae1d166aed8d3ea258a2b0c8e0c894dcd032526a6fb5a3`,
its strict contract, exactly 22 messages, schema, staged target and artifact
identity. Host `--profile tree-sort-v1` maps only to `--tree-sort-suite`;
there are no arbitrary sources or mutable profile globals. The Sort contract
is loaded only when selected; old staged inventories need no new helper.

The existing isolated server/client runners, credential gates, cleanup and
provenance binding are reused. Server/client captures must match exactly.
Parse-valid missing-method observations remain measurements, never availability
success. Runtime acceptance requires both EN-default and RU-explicit-False
positive controls to succeed **and** exact interpreter/native parity. A matched
missing-method capture therefore remains rejected. Generic bounded observer
failure diagnostics reveal no raw exception, path or payload. Capturing the
original action exception and structural Rows-owner labels are unchanged.

## Fixed workflow matrix

The existing `tree_copy_smoke` job retains its permissions, prerequisites and
security admission checks. Its literal Copy/Sort matrix has `fail-fast: false`,
fixed profile/artifact/case tuples and a quoted environment selector. No new
workflow-dispatch input exists; dispatch remains excluded. The unchanged verdict
requires this aggregate job to succeed, so failure of either required profile
fails the verdict. The independent Fill job remains byte-identical.

## Constructive bounds

All existing limits remain unchanged. The integrated tests construct valid
maximum captures and conservative report structures, charging even the full
8,192-byte transport payload cap rather than merely the smaller valid maximum.

| Object | Upper bytes | Existing cap |
|---|---:|---:|
| Full valid capture | 6,443 | 8,192 |
| Completed client marker (BOM, spaces, escaped slashes) | 6,702 | 16,384 |
| Stage report | 4,133 | 8,192 |
| Native report | 9,259 | 32,768 |
| Transport envelope | 20,436 | 65,536 |
| Host report | 14,614 | 32,768 |
| Export provenance | 14,419 | 32,768 |

`full_suite.py` remains byte-identical: 289,493 LF / 294,075 CRLF bytes,
leaving the same 837-byte CRLF margin below 294,912. Its historical inverse
chain and all existing pins remain unchanged. Fill/Copy measurement sources,
contracts, successful grammar and generated client-module hashes are unchanged.

Before publication: independent review, focused normal and optimized tests,
and source-inventory verification. Native acquisition follows closure of the
current PR147/150 work; runtime Sort semantics follow verified real 1C evidence,
not these synthetic tests.

## Review hardening (V2)

The historical EXCLUDE test inverse now uses eight explicit AssertionError
guards rather than optimization-removable assertions. An isolated optimized
subprocess reruns its complete existing drift-negative test; reconstructed
bytes and historical pins are unchanged. This is test-only hardening.

Durable Sort regressions run the real bounded producer serializer and host
validator for server/client process and observer failures, missing/invalid
captures, nonquiet or failed bus cleanup, and parse-valid unavailable methods.
Unavailable captures remain exportable observations but cannot pass parity
acceptance. A synthetic action replaces all 18 rows with new objects containing
the same cells: the BSL observer and strict decoder retain new IDs 23–40 instead
of normalizing them to prior rows. This demonstrates observation flexibility,
not real-platform identity behavior.

## Subsequent numeric runtime candidate

Fresh authenticated Linux acquisition and its bounded implementation are
described in [the runtime scope](value-tree-sort-runtime.md). The preceding
sections retain the integration-preparation history; they are not a statement
that native acquisition is still pending. Fresh runtime acceptance is pending.
