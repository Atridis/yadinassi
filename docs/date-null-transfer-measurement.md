# Date/Null cross-context measurement checkpoint

Status: uncaptured, measurement-only checkpoint. Native observations and the
expected Date/Null token are unknown. No Date/Null cross-context runtime support,
native parity, or release acceptance is claimed. Local source/schema tests do
not supply native expected results.

The baseline is main `8f8b71d66d080c08f74035fc783b6d29a10e846c`, tree
`6d4e5e0c81027a1185ef249e8157bc88e2e4f20e`. The intended measurement target is
Linux/amd64, 1C 8.3.27.1508, managed thick client, file infobase. Other versions,
operating systems and application modes are not covered by this checkpoint.

## Bounded question

The existing logical client/server packet copier supports a bounded subset of
primitive values and acyclic mutable Array/Structure graphs. This checkpoint
asks how Date and Null leaves behave across that boundary before extending the
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
are questions posed by the probe, not asserted native answers.

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
specific mutations. They do not establish every alias relationship, repeated
child identity, arbitrary graph topology, or an object-identity oracle.

## One independent token, no success exception

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
arbitrary returned values never enter the token. No concrete token is designated
as a native expectation at this stage.

The historical marker helper retains its strict 135-value contract. The ordinary
measurement runner rejects every completed marker, including an omitted-token
135-value marker and the intended 136-value capture; it cannot claim success. The temporary finite `date_null` diagnostic may expose the
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

## Exact source inverse and temporary host preflight

The restored strict135 baseline source SHA-256 is
`c991b9fbf808a59fad6edc10ad9768efe85bc3bd2da9d7b63c1daa5cdb118413`.
The compact measurement source is pinned as
`56dc0e682f31a13e52d3b5d278e1effe20d6899110770b94671dd0ba426aa751`;
its generated native module is pinned as
`840b3d19ef6eb100af3cc685788692eec7f6aec863518b003046beae995b8062`.
These are source identities, not native execution evidence.

While the copier has not been extended, the temporary host preflight executes
only the exact hash-restored baseline. The inverse must require the full new
source hash, the unique exact added helper block and append call, the exact
compact-writer replacement, the unchanged final initializer tail, and the final
restored baseline hash. A modified or partial source is rejected, not repaired
heuristically. This proves the old strict135 behavior independently; it does
not execute or establish host/native parity for the new Date/Null operations.

The native measurement still runs the complete new literal source. Source,
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
format. A source-bound native entered/completed capture is still needed to check
availability and actual bytes on the pinned platform.

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
bound stage wire at 7961/8192 bytes and the public summary at
32147/32768 bytes. Later observations are retained only to make this an upper
bound: the rejected ordinary probe cannot actually reach those later lanes.

## Boundaries and acceptance after measurement

This checkpoint adds no runtime behavior. It does not broaden Date arithmetic,
precision, timezone or range handling; Null operations; supported collection
types; cycles; form/module state; database/query; RPC; NoContext/dual semantics;
Async behavior; non-Val property/index sinks; or exception-copyback rules.
Existing rejection guards outside the measured leaf subset remain in force.

The required next sequence is:

1. Obtain a genuine, source-bound native capture on the pinned target, retaining
   the exact source/module/roundtrip and artifact identities.
2. Independently audit all eight observations and their finite encoding,
   original 135 typed values, writer availability and evidence gates. Do not
   infer missing native answers or convert an error code into a passing result.
3. Implement only the bounded Date/Null transfer behavior justified by that
   audit, with corresponding positive and negative tests and existing guards.
4. Remove the temporary diagnostic and host-preflight exception. Execute the
   complete final source on host and native and require strict **136-value**
   typed equality, including the independently audited token. Recheck native
   evidence, full local tests and required CI against that final source.

A measurement-only rejected capture, synthetic schema token, restored strict135
preflight or historical native run cannot satisfy the final strict136 gate.
