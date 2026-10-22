# Fixed-GMT fractional Date checkpoint

Status: source-only preparation. Native compilation, fresh client/server results,
interpretation of fractional behavior, and runtime implementation are pending.
Local Python tests verify packaging and source preservation, not native behavior.
The runtime deliberately still rejects fractional Date conversions.

## Bounded question and probes

The existing fixed-GMT implementation rejects every nonzero fractional tick in
`date_time_conversions._convert`. Only the already supported explicit
`GMT{+/-}h[h][:mm]` domain is investigated here. Named zones, omitted/default
zones, system clocks and boundary-overflow behavior remain out of scope.

The `dates.bsl` append contains 84 protected numeric observations:

- Four input subtraction witnesses for 0.0001, 0.4999, 0.5 and 0.9999 seconds.
- 48 direct conversion witnesses: both directions, `GMT+0`, `GMT+5:30`,
  `GMT-3:45`, all four fractions, and both 2024-02-29 23:59:59 and
  2024-03-01 00:00:00 source instants. These discriminate both signs of offset,
  non-hour offsets, leap-day crossing and both signs of day crossing.
- 24 inverse-composition witnesses for both composition orders and all three
  offsets/four fractions.
- Eight Russian-alias witnesses with `GMT-0:00`, exercising negative zero too.

Each direct result is a Number: converted Date minus the explicit original
whole-second Date. Thus a whole-second timezone shift and its fractional residue
are both visible in the numeric result. No Date serialization can silently hide
fractional ticks. Inverse results also subtract the original whole-second Date;
no expected native residual is embedded in source or packaging tests.

Every expression is independently protected by the original observer. Error
records and the final sentinel establish reachability, not successful conversion.
No new BSL declaration, module variable, helper name or native form attribute is
introduced; the original two helpers retain their scopes and order.

## Preservation and harness

The complete original 132-line dates source remains an exact byte prefix.
Its 98 observations and two completion messages remain the first 100 messages.
The current complete source has 219 lines and 185 messages, including the new
completion message. The client adapter remains raw-source/template pinned and
performs an explicit inverse reconstruction, changing six verified message call
sites only and preserving all expression strings. Exact source reconstruction
and original observations are tested independently.

Historical Windows replay binds the entire current source and historical output
by Git blob identity, reconstructs the exact original source prefix, and verifies
that prefix identity before execution. It never filters or truncates output.
All six historical Windows captures and their existing assertions are unchanged.
The original calendar/foundation tests continue to cover their exact source and
full historical evidence, independently of the pending append.

No workflow flag, staged input, output artifact member, image, role, networking,
isolation policy, payload cap or runtime budget changes. Existing full dates
client/server parity runs the complete new source in both execution contexts.
The public artifact remains six server outputs plus provenance, not client data.

## Native evidence and runtime gates

1. After the preceding feature merges, reconstruct against verified fresh main,
   reapply this bounded checkpoint and independently review the final diff.
   Recheck hashes and all tests before publishing a Draft PR.
2. Run the existing native six-scenario workflow with its existing client dates,
   values, collections and numbers parity and watchdog options. Bind the exact
   commit/tree, all 24 staged hashes, generated server/client module hashes,
   runtime version/image, provenance and artifact digests to that run.
3. Verify native compilation and completion, all 185 dates messages, the 84
   unique new labels in source order and final sentinel, original 100 messages,
   exact client/server equality and unchanged historical capture fingerprints.
   Inspect every numeric observation or error. A completed run with errors or
   interpreter mismatch is evidence for investigation, not interpreter parity.
4. Only then select behavior supported by actual observations. Do not assume
   preservation, rounding or truncation, even though preservation is the feature
   under investigation. If contexts disagree, stop implementation and investigate.
5. For a native-backed runtime change, test direct tick precision, both aliases
   and directions, offset grammar, zero signs, minute/hour offsets, inverse
   composition, source immutability, catchable errors, dynamic Eval/Execute,
   CLI/import/BOM/console and hostile Decimal/host-timezone independence. Keep
   existing unknown-boundary and range rejections; this does not expand overflow.
6. Require a new exact-commit native run with full interpreter acceptance and
   four-OS build/test results. Merge only under the existing sequential gate;
   verify fresh main and postmerge checks before advancing the next feature.

Publication and actual native/runtime proof are intentionally pending; this
checkpoint alone is not ready-for-review or merge evidence.
