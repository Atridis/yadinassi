# Date/Null transfer: audited measurement and strict136 migration

Status: the native measurement is captured and independently audited. The
bounded runtime extension and strict136 migration are a separate candidate;
its exact whole-source strict136 host preflight has passed. Fresh native and
required CI acceptance gates are still pending.
The rejected measurement is not a runtime parity or release acceptance result.
The expected token below comes from the native artifact, not local execution.

The baseline is main `8f8b71d66d080c08f74035fc783b6d29a10e846c`, tree
`6d4e5e0c81027a1185ef249e8157bc88e2e4f20e`. The measured target is
Linux/amd64, 1C 8.3.27.1508, managed thick client, file infobase, locale `ru_RU`
and timezone `Etc/UTC`. Other versions, operating systems and application modes
are not covered by this capture.

## Audited native capture

[Draft PR99](https://github.com/Atridis/yadinassi/pull/99), native
[run 40078699477](https://github.com/Atridis/yadinassi/actions/runs/40078699477),
produced **`dn.v1:22222277`**, or `[2, 2, 2, 2, 2, 2, 7, 7]` in slot order.
All six scalar predicates completed true. Both graph cases completed with all
three checked facts true. This establishes the bounded observations described
below, not a universal transfer model.

- Head: `0fe70b6e66dbb4a397344d76a537a1b755e515cf`.
- PR checkout: `c20971ce26073484c7b3c758b28f40ac02da1503`, with ordered parents
  main `8f8b71d66d080c08f74035fc783b6d29a10e846c` and the measured head.
- Tree: `f82478356de78eb31244e0199212584dbb80fb9d`.
- Invocation nonce: `5a3306010b114c9893cb42d412a23729`.
- Summary artifact: `12554442911`, ZIP SHA-256
  `d784b49699b81dd3ebd518fe2a6081c7a0f412d7071bf5989f4bf5d1e1df28b9`.
- Report SHA-256:
  `184e6b5e4180a3bc7fd9c152bcd3ecdbc223494187acb207b7b599b4bad70b2a`.

The independent audit bound all 384 source blobs, 24 staged input hashes and
52 interpreter/provenance files to this tree. All preceding 135 values matched
by exact type and value. The six fresh server-case metadata records matched
audited actual main run 40054174322; fresh raw six-case output was intentionally
not exported by the failed measurement. Historical output replay is not a new
full-parity result.

The ordinary probe and enclosing stage remained `failed` / `invalid_result`.
`entered`, `process_exited` and `quiet` were true; `completed` and
`witness_verified` were false. Actual completed-marker evidence was the
source-bound diagnostic `phase=completed`, `kind=count`, `ordinal=135`,
`error_stage=0`, with the observed token. Final cleanup passed. Later full-client
adapters and watchdog were not started; no Date/Null Async run was claimed.

## Bounded question

The existing logical client/server packet copier supports a bounded subset of
primitive values and acyclic mutable Array/Structure graphs. The measurement
asked how Date and Null leaves behave across that boundary before extending the
copier. It does not derive native expectations from the interpreter, a generic
serializer, or the platform guide.

The native client executes the complete literal source in
`scripts/native_1c_bootstrap/client_probe.bsl`. `DNCollect()` makes exactly eight
direct client-to-server calls, not calls through `Execute(text)`. Helpers have
explicit local variables, no module variables or initializers, and precede the
existing final module initializer. `DNAppend(Значения);` appends one independent
token after the existing dual-directive append. All preceding 135 typed values,
including the complete dual token, stay unchanged.

The two test dates are ordinary whole-second values:

- A: `Date(2024, 1, 2, 3, 4, 5)`.
- B: `Date(2031, 6, 7, 8, 9, 10)`.

A date predicate checks exact Date type before value. A Null predicate checks
`TypeOf(value) = Type("Null")`, never Null equality. Boolean acknowledgments
must have exact Boolean type and be true.

## Eight finite observations

The token fields have the following zero-based order. The described predicates
are the exact probe predicates. The captured token reports true for each scalar
predicate and all three bits in each graph case.

1. **Slot 0, `DNEchoDate`.** Send A as Val. The server checks its exact type and
   value, then returns it; an invalid input returns a non-Date sentinel. Observe
   whether the client receives exact A.
2. **Slot 1, `DNEchoNull`.** Send Null as Val. The server checks exact Null type
   and returns it; an invalid input returns a non-Null sentinel. Observe whether
   the returned value has exact Null type.
3. **Slot 2, `DNDateToNull`.** Send a named non-Val variable containing A. The
   server validates A and assigns Null. On normal completion, observe whether
   the caller variable has exact Null type.
4. **Slot 3, `DNNullToDate`.** Send a named non-Val variable containing Null. The
   server validates its type and assigns B. On normal completion, observe
   whether the caller variable contains exact B.
5. **Slot 4, `DNValDate`.** Send a named Val variable containing A. The server
   validates A, rebinds its local parameter to Null and returns true. Observe
   the conjunction of the exact true acknowledgment and unchanged caller A.
6. **Slot 5, `DNValNull`.** Send a named Val variable containing Null. The server
   validates Null, rebinds its local parameter to B and returns true. Observe
   the conjunction of the exact true acknowledgment and unchanged caller Null.
7. **Slot 6, `DNValGraph`.** Send a Val mutable Structure whose `Leaves` property
   is a mutable two-element Array `[A, Null]`. The server records whether it
   received those exact leaves, changes them to `[Null, B]`, stores its input
   observation in `Seen`, and returns the graph. Observe three separate facts:
   bit 1 is the server's exact true input observation; bit 2 is the returned
   graph's exact Structure/Array shape, length and swapped leaves; bit 4 is the
   original caller graph's unchanged shape, length and leaves.
8. **Slot 7, `DNRefGraph`.** Pass the same initial graph shape non-Val, retaining
   an unpassed old-root alias before the call. The server records its input
   predicate, swaps the leaves and returns the predicate. Observe bit 1 for the
   exact true server input result, bit 2 for the copied-back caller graph's
   exact swapped shape/leaves, and bit 4 for the retained old-root alias's
   unchanged shape/leaves.

These graph facts distinguish return/copyback contents from isolation in these
specific mutations. The graph input bit checks indexed leaves, not server-side
container identity or length. Client shape checks require a Structure, a Leaves
Array of length two and the specified leaves, not the complete property set or
original Seen metadata. They do not establish every alias relationship, repeated
child identity, arbitrary graph topology, or an object-identity oracle.

## Historical measurement encoding, no success exception

The complete token grammar is `dn.v1:[0-2]{6}[0-8]{2}`, matched as a whole string.
It contains eight ASCII digits after `dn.v1:` and is exactly 14 ASCII bytes.
It is the 136th typed value, not part of or a replacement for the dual token.

For slots 0 through 5:

- `0` means a caught error or incomplete operation.
- `1` means normal completion with the tested predicate false.
- `2` means normal completion with the tested predicate true.

For slots 6 and 7, values `0` through `7` preserve the three independent facts
as a bitmask with weights 1, 2 and 4. `8` means a caught error or incomplete
operation. It is not a mask of three false facts; that mask is `0`. Any exception
in the call or its required client checks yields the error/incomplete code,
not a partially completed semantic observation. Raw error descriptions and
arbitrary returned values never enter the token. The independently captured
`dn.v1:22222277` is now the strict136 migration oracle. Error codes identify
neither a failing phase nor whether mutation occurred before the error.

In the measured PR99 checkpoint, the marker helper retained strict135 and the
ordinary runner rejected every completed marker, including an omitted-token
135-value marker and the intended 136-value capture. It could not claim success.
The temporary finite `date_null` diagnostic could expose the
token only for a source/module-bound, nonce/schema/phase/witness-valid, complete
136-value marker whose first 135 values match exactly by both type and value.
The extra field must satisfy the whole token grammar. This is only the expected
count-mismatch diagnostic, never a successful probe or an alternative mismatch
classification. An invalid prefix, partial marker, wrong type/count/token,
changed source, wrong nonce/witness, error phase, malformed or oversized report
exports no Date/Null observation. Export additionally requires a verified entered
marker, clean process exit, a quiet immediate process census, nondecreasing marker
timestamps and unchanged staged source, generated module and dumped roundtrip
bytes. The independent host requires the exact source/module identities, these
completion flags and rejected-count classification before admitting the token.

The deliberately rejected capture also undergoes the existing final process
census after owned session-bus teardown. A failed final census or bus teardown,
or a nonquiet final native-process check, removes only the optional token and
clears the client's quiet/witness proof. The generic count diagnostic remains
available in a host-valid failed report. Unreached later lanes are not marked as
having run. The host also rejects a retained token if the enclosing stage is not
the exact `failed` / `invalid_result` outcome with established input identities.
There is no successful-result exception and no fallback around cleanup gates.

A valid diagnostic therefore establishes only that the finite observation was
captured under those gates. It does not turn the rejected run into parity,
validate an unimplemented copier, or imply that later full-client/Async lanes
ran. Missing or failed observations must remain visible as such.

## Exact source identity and migration of host preflight

The restored strict135 baseline source SHA-256 is
`c991b9fbf808a59fad6edc10ad9768efe85bc3bd2da9d7b63c1daa5cdb118413`.
The compact measurement source is pinned as
`56dc0e682f31a13e52d3b5d278e1effe20d6899110770b94671dd0ba426aa751`;
its generated native module is pinned as
`840b3d19ef6eb100af3cc685788692eec7f6aec863518b003046beae995b8062`.
These exact source/module identities are bound to the audited capture above.
The semantic core SHA-256 is
`1b6c51fba57161907d26d78b3c96d317ff1f4b65098d6bf5a0815ed5fb575a70`.

The measured checkpoint's temporary host preflight executed only the exact
hash-restored strict135 baseline. The inverse must require the full new
source hash, the unique exact added helper block and append call, the exact
compact-writer replacement, the unchanged final initializer tail, and the final
restored baseline hash. A modified or partial source is rejected, not repaired
heuristically. That proved old strict135 behavior independently; it did not execute or
establish host/native parity for the new Date/Null operations.

The strict136 host preflight now executes the exact whole staged BSL bytes,
including all Date/Null helpers, the append call and the unchanged native compact
writer definition. `ВычислитьПробу()` does not invoke the marker writer body, so
no source stripping, writer replacement or new interpreter API is needed.
Local comparison of all 136 typed values, including the observed token, passed.
Fresh native strict136 acceptance remains pending. The measured BSL and native
generated module stay exact. `date_null_shared_source` is retained only as the
exact historical four-adapter/source-archaeology inverse, never for preflight.

The native measurement ran the complete literal source. Source,
generated module and native roundtrip identities remain part of evidence
binding. The four historical full-client adapter modules must be regenerated
from the exact restored baseline and remain byte-identical. The Async8 template,
all eight generated identities and their existing comparisons remain unchanged.

## Native-only compact marker writer

The sole writer change selects the native platform's compact JSON settings:

```bsl
Перем ПараметрыJSON, Запись;
ПараметрыJSON = Новый ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет, " ", Истина);
Запись = Новый ЗаписьJSON;
Запись.ОткрытьФайл(Путь, , , ПараметрыJSON);
```

This is `JSONWriterSettings(JSONLineBreak.No, " ", True)`, supplied as the fourth
argument of `JSONWriter.OpenFile`. The existing `WriteJSON`, fields, nonce,
phase, witness, values and `Close` are unchanged. The host defines but does not
invoke the native marker callback. No JSON writer settings, enum or other new
interpreter API is implemented.

The [official 1Ci 8.3.23 guide, section 16.2.5.2](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_8.3.23_Developer_Guide/Chapter_16._Operations_with_various_data_formats/16.2._JSON_operations/16.2.5._Stream_method/)
documents these settings and the fourth `OpenFile` argument; the
[official downloadable guide](https://1c-dn.com/download-trial/files/guides/developer_guide.pdf)
contains the same example. The
[official Russian reference](https://its.1c.ru/db/content/metod8dev/src/developers/dataexchange/esb/i8105993.htm)
documents the Russian settings and enum names. Documentation predating the
target version is not execution evidence for Linux 8.3.27.1508.

The native entered-marker write exercises this dependency before measurement.
If the constructor, enum or argument is unavailable, the run cannot produce the
required valid entered/completed evidence. There is no fallback to the default
format. The audited source-bound entered and completed marker paths establish
that this native dependency executed on the pinned target and both markers
passed the unchanged bounded reader. The private marker bytes and exact byte
length were not exported; the audit does not report a measured compact size.

The private read cap remains **2048 bytes**. A compact Python model of all
135 baseline values plus the token is 1359 bytes, whereas the conservative
two-space pretty model is 2063 bytes. These are serialization models, not measured
native output sizes. Real bytes must pass the existing capped reader and strict
decoder. No cap increase, post-read whitespace stripping, control-character
removal, file rewrite or alternative transport is permitted. Stage/public report
caps remain 8192/32768 bytes; source binding, security checks, process limits,
credentials and existing comparator exceptions are not relaxed. Current production
serializers with a schema-valid finite capture or a discarded-token record with
maximum existing process diagnostics, plus conservative later-data majorants,
bounded the measurement stage wire at 7961/8192 bytes and public summary at
32147/32768 bytes. The actual capture report is 19424 bytes; re-encoding its
stage with the production wire serializer gives 6749 bytes. These are public
report sizes, not the private marker size. Later observations were retained only
to make the model an upper bound: the rejected ordinary probe could not reach
those lanes. The final strict136 candidate needs its own unchanged-cap checks.

## Bounded runtime policy and pending acceptance

The separate runtime candidate may extend only the existing packet copier's
leaf cases:

- Preserve the exact canonical `NULL` singleton. Do not admit arbitrary Null-like
  objects or additional platform-object types.
- Admit exact `BSLDate` values only when `boundary` is false, ticks are an exact
  integer with `0 < ticks < MAX_TICKS`, and ticks represent a whole second.
  Fractional ticks, either endpoint (even without a boundary flag), boundary
  sentinels, subclasses and malformed date-like objects remain outside this
  local transfer subset.

This is a deliberately bounded **local transfer policy**, not a claim that native
1C rejects those excluded dates or that every interior date has been sampled.
It is not a year whitelist: interior whole-second values are not restricted to
2024 and 2031. The native evidence covers the two stated values and graphs;
additional allowed years/range limits require local tests, not invented native
observations.

Existing Array/Structure graph-copy invariants and guards remain unchanged,
including cycle/repeated-identity handling and unsupported object rejection.
The slice does not broaden collection types, Date arithmetic/timezones/precision,
Null operations, property/index copyback sinks, exception copyback, module state,
database/query, or transport. There is no separate native Date/Null proof for
NoContext, dual, or Async. Reusing the packet copier must not be represented as
such a measurement, and existing Async8 sources/identities must remain unchanged.

The remaining acceptance sequence is:

1. Complete and independently review the bounded copier and its positive/negative
   local tests. The native measurement and its audit are already complete.
2. Keep temporary diagnostic acceptance and baseline-only preflight removed.
   The exact whole-source **136-value** host preflight has passed without any
   source transformation or suppression of Date/Null operations or definitions.
3. Obtain fresh native strict136 acceptance against the final runtime/harness
   tree; require the original 135 typed values plus the captured token exactly.
   Preserve all four full-client adapters, Async8 identities, security limits,
   cleanup gates and historical comparison exceptions.
4. Pass the complete local aggregate, binary smoke and required native/OS CI.

Fresh native and final acceptance gates remain pending. Neither the rejected
PR99 capture, a synthetic token, restored strict135 preflight nor historical
main acceptance satisfies them.
