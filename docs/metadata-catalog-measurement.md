# Owned Metadata.Catalogs / applied-view measurement

Local candidate based on `8dcb3cf8db01fcced4f1a394fca58de32cefd4ec`.
This is a measurement route, **not a BSL Metadata implementation** and not native
acceptance evidence until a real run passes. No runtime imports or changes.

## Closed entrypoint

From a clean, reviewed checkout, with the same GHCR credentials required by the
existing native file-DB oracle:

```sh
python scripts/native_1c_metadata_catalog_oracle.py --run
```

The only execution flags are `--run` and optional `--ci-report`; no caller
database/configuration/source/path arguments are accepted.
Stdout is a validated JSON envelope (99328 bytes maximum). The host uses the
same pinned image, non-root/no-network/read-only Docker confinement, credential
scrubbing, bounded process execution and verified container/private staging
cleanup as the existing oracle. The existing reviewed-source workflow explicitly selects this route and invokes
`--run --ci-report` in its dedicated job. This writes only the fixed validated
`native-db-oracle/metadata-catalogs.json` artifact and sets readiness after exclusive
publication; success still requires the accepted measurement result. All unrelated
route jobs must be skipped. The same immutable reviewed push/owner/checkout binding
precedes the existing package token. No new event, ref input, credential, permission
kind or raw-log artifact is added. Coordinate the first publication/native run with
the task owner.

The implementation reuses the existing Controller lifecycle, Native process,
authentication, clone/freeze/quiescence/budget/deadline and cleanup primitives.
Old CLI flags, source inventories and baseline-only audit guards are unchanged.
Only the dedicated Native subclass enables a separate source instrumentation
option in `inject_metadata`; ordinary injection remains byte-identical.

## Acquisition and trust boundary

The owned fixture has **one** catalog. Existing general CONFIG projection can
read multiple catalogs; the new acquisition admission intentionally requires one.
There is no row decoder and no oracle UUID/name/version supplied to the byte
reader. It decodes all CONFIG attributes through the existing bounded private
projector and selects Payload from the decoded attribute names.

After each existing `updated`, `loaded`, and `applied` snapshot, the coordinator:

1. Takes a fresh auditor clone for **each** client/server context, verifies its
   origin digest against that snapshot, and creates a fresh token.
2. Runs the fixed 26-case probe through dedicated `metadata_catalog_client` or
   `metadata_catalog_server` operations. Server authorization verifies the exact
   four-field control, setup identity, nonprivileged context and existing owned
   metadata guards. These are not `audit_record_metadata` calls.
3. Requires the exact nonce/token/operation-bound completion and result after
   process exit and quiescence. Result marker is at most 16384 bytes; observer
   wire at most 8192 (rectangular maximum 7148). Errors export no exception text.
4. Freezes **that same clone's postimage**, independently hashes/reads/hashes it,
   and decodes CONFIG from those exact bytes. No baseline XML fallback exists.
5. Records bounded wire observations, origin/postimage/marker digests, actual
   CONFIG count/name/Payload length, and finite comparisons. Each context is
   removed before the next clone. Installed client/server helper module hashes
   are captured and independently reconstructed from pinned sources by the host.

The write attempt is a *fixed literal* `Выполнить` statement so any native
read-only compilation error occurs inside the measured action, rather than
preventing all probe observations. No arbitrary source is accepted. Successful
mutation is not undone or normalized; the independent final name observation
retains it, and the second context starts from a fresh identical snapshot.

Count/name/Payload RU/EN calls are compared against decoded CONFIG. FullName
RU/EN equality is a separate observation: no on-disk FullName field is invented.
Find/index/case/arity/read-only outcomes remain recorded facts, not hard-coded
native expectations. An observer error cannot establish the applied-view verdict.

## Discriminator, not generic metadata acceptance

The verdict requires six captures in fixed snapshot/context order and native
**and** decoded Payload lengths `32 / 32 / 64`:

| Snapshot | Designer config | Applied runtime | Required Payload |
|---|---|---|---|
| updated | v1 | v1 | 32 |
| loaded | v2, not applied | v1 | 32 |
| applied | v2 | v2 | 64 |

A `32/64/64` CONFIG reader versus `32/32/64` native runtime is a real
loaded-view mismatch. The report retains the finite comparisons and fails the
verdict; it must not choose CONFIGSAVE, substitute constants or broaden admission.
The existing CONFIG projector continues to label its own `applied_state` as
`not_observed`; only this separately validated fixture experiment can establish
its narrower discriminator. Rename/add/remove/catalog ordering are not proved.

`measurement_failure` identifies the fixed snapshot, client/server/both context,
and acquisition phase. The ordinary lifecycle carries the finite failure kind.
Raw native logs, source database files and exceptions do not leave the sandbox.

## Current validation boundary

Synthetic checks exercise actual constructed CONFIG bytes with changed names and
lengths, loaded-vs-applied mismatch, source closure/cold staged imports, generated
BSL syntax, LF/CRLF equivalence, separate clones/same postimage, marker binding,
helper capture, complete synthetic lifecycle, malformed captures, confinement,
closed CLI and missing-credential cleanup. Normal and `python -O` are required.
These are **not** native compilation/execution or complete project gates.

Before adoption: independent review; current-head source-bound cold validation;
full required normal/optimized gates under fixture-owner coordination; real
native run; inspect every observed behavior and discriminator; then separately
implement/test a lazy runtime adapter reading the actual offline snapshot.
No BSL API or no-database branch behavior is changed by this measurement lane.

## Constructive transport budget

The cap is `32768 + 65536 + 1024 = 99328` bytes, not a blanket enlarged
lifecycle report. The existing lifecycle encoder retains its <32768-byte limit.
There are at most six captures, each at most `(65536 - 7) // 6 = 10921` encoded
bytes; five commas and two array brackets fit the separate 65536-byte states
budget. The remaining envelope, measured with lifecycle/states replaced by
`null`, is independently capped at 1024 bytes (two fixed helper SHA-256 values,
one finite verdict, and optional finite snapshot/context/phase). The replacement
`null` placeholders overcount the combined result; the final encoder additionally
requires total plus its output newline <=99328. Decoder rechecks all component
caps, not only the outer size. Worst-case wire contains all26 64-unit strings,
which is 7148 bytes before its JSON escaping; it remains subject to both the
per-capture and aggregate caps. No exception text, native log, database payload,
XML, arbitrary source code or unrestricted property is an export field.
