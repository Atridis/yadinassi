# Partial Catalog declaration-reference prototype

This local prototype adds a **declared-reference observation**, not a Catalog
object/property reader. Local runner/CLI wiring uses the explicit
`--config-catalog-reference-observation` selector, invocation schema17, report25,
capture26, lane `owned_config_catalog_observation_v1` and a separate25-source
inventory. All existing lanes/inventories remain unchanged. Native evidence is
subject to the separate frozen-fixture, complete-read, exact-count, cleanup and
report-binding gates below; local tests alone cannot satisfy those gates.

## Source basis and scope

The traversal was designed against DaJet commit
[`6af0c0baab11f9d281ad42a3eb2269d5b113cde5`](https://github.com/zhichkin/dajet/tree/6af0c0baab11f9d281ad42a3eb2269d5b113cde5):

- [`InfoBaseParser.cs`](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/InfoBaseParser.cs):
  top-level child2 component count; following declared component nodes identified
  by child0 UUID, not position. General/Accounting/BusinessProcess metadata count
  is under component child1, child2; Operations adds a child1 nesting level.
  Following declared collection nodes start with type, count and references.
- [`Components.cs`](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/core/constants/Components.cs)
  and [`MetadataTypes.cs`](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/core/constants/MetadataTypes.cs)
  provide public component/type constants.
- [`ConfigFileReader.cs`](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/core/ConfigFileReader.cs)
  motivates positional nulls and doubled-quote strings. Permissive sentinel
  conversion, filtering zero GUIDs and silent premature-read tolerance are not
  adopted. There is no runtime dependency on or execution of upstream code.

The independent bounded event walk retains only private candidate keys and bounded
stack state. It never searches arbitrary bytes for the Catalog UUID. Unknown
components/types and enclosing tails are opaque; structurally skip them only to
reach another declared node. No exact enclosing arity is invented. Processing
stops at a valid comma/close-brace boundary after the last outstanding declared
position; enclosing objects need not close. Neither target suffix nor EOF is
validated, including UTF-8 beyond that boundary. Root prefix/suffix limitations
from the older observer are unchanged.

## Conservative local admission

Visited text is strict UTF-8. One initial BOM is allowed; embedded/repeated BOM,
TAB, other C0 controls and DEL in visited bytes are rejected (CR/LF allowed).
Only boundary SP/CR/LF are skipped; trailing spaces in a started bare value are
not trimmed. Quoted delimiters are inert and doubled quotes escape a quote.
`{}` has one null position, `{,}` two, `{,,}` three. Required counts use canonical
unsigned decimal and UUIDs canonical 8-4-4-4-12 ASCII spelling, quoted or bare.
Quoted required values need a closing quote, optional boundary SP/CR/LF, then a
comma/close brace. A valid UUID prefix followed by junk does not match.

Bounds: input4194304 bytes, events131072, depth64, components16, total declared
collections64, total references256, interested scalar36 ASCII characters.
Duplicate known component kinds, duplicate normalized references and zero GUID
references fail closed. At least one Catalog collection and positive total refs
are required. These are local admission choices, not universal native grammar.

Before walk/state/buffer allocation or scanning the parser charges the existing reader budget for
`3*len(input)` work and212992 representation bytes. Each event charges the same
shared token budget before state growth; depth intersects caller limits. No DOM,
per-token path history, full-text decoding, budget reset/refund or new reader.
The small input-independent immutable default-limits object may be created before
that reservation. These weights bound the admitted representation, not exact Python
VM RSS.

## Integration and finite evidence

The new observer preserves all previous guards and reads selected entries exactly
once: root, target, remaining selected entries. After parsing the already-decoded
target it checks candidate existence in the same selected CONFIG map, rejects
root/target aliases, then recognizes positive complete candidate contents during
the existing remaining-entry validation pass. No reread, reinflate or fallback.
A late invalid noncandidate still fails and poisons chain/decoder; no partial
success is returned. Public output contains only bounded counts and a finite
validation label, never candidate keys, target text, offsets or object names.

Generic success requires declared=resolved=positive in1..256. The separate owned
fixture readiness gate requires all three counts exactly1 because that fixture
contains exactly one Catalog metadata object; zero baseline rows do not mean
zero metadata objects. This does not bind the declaration to injected object
identity, prove properties/applied state, or establish native compatibility.

Actual complete schema envelope (including all25 source paths, full12288 capture
cap and final newline): **31717/32768 bytes**, margin1051. Reader projection
1871/2048; capture with full projection cap2997/12288. Existing caps unchanged.
The exact rectangular envelopes are pinned in
`tests/test_native_1c_db_oracle_catalog_reference_budget.py`.

Focused local gates:

```
PYTHONPATH=tests python -m unittest \
  test_config_catalog_references \
  test_native_1c_db_oracle_catalog_reference_reader \
  test_native_1c_db_oracle_catalog_reference_policy \
  test_native_1c_db_oracle_catalog_reference_budget \
  test_native_1c_db_oracle_catalog_reference_route \
  test_native_1c_db_oracle_config_root_projection_reader \
  test_native_1c_db_oracle_config_root_projection_policy \
  test_native_1c_db_oracle_config_root_projection_budget
```

The50 vector inputs are invented synthetic data, not native captures. Local tests
cannot establish that the real fixture has these declarations inside its
root-selected target. Dedicated native validation requires separate authorization
and must satisfy the exactly-one positive-reference gate, all selected-entry
checks, source/frozen-image bindings and complete cleanup. An empty collection or
structural mismatch cannot be counted as positive evidence. Workflow activation
and fixture changes are separate reviewed actions. Execution status and run
provenance belong in the associated PR/evidence packet, not this stable contract.
