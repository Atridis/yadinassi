# Bounded regular-expression family native measurement

Status: local source-bound packet only. No native acquisition or semantic parity
is claimed by this document. Local interpreter output and synthetic wire records
are test inputs, not fabricated 1C answers.

The closed `regex-family-v1` profile observes forty short ordinary cases through
four APIs introduced in 1C 8.3.23: `StrLikeByRegularExpression`,
`StrFindByRegularExpression`, `StrFindAllByRegularExpression`, and
`StrReplaceByRegularExpression`. It also observes the two read-only result/group
types (`Value`, `Length`, `StartIndex`, `GetGroups`). Primary source: thirteen
official EDT pages in archive SHA256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`,
`Global_context/methods/catalog4838` and `catalog63/ResultOfSearchByRegularExpression*`.
The globals' server/thick/external availability does not establish thin/web
availability merely because result objects are documented there.

## Closed observation map

| Cases | Ordinary workflow / unresolved native semantics |
|---|---|
| 1–6 | Like exact vs substring; classes; Cyrillic word class/boundary, Arabic digit, NBSP space class; default/case/numeric-Boolean flag; default versus multiline anchors; astral dot matching units |
| 7–15 | First/missing find; forward start/nth; reverse default/start/nth; alternative priority; forward and reverse greedy/lazy; UTF-16 positions and astral match length |
| 16–21 | All matches/no matches; empty pattern; terminal anchor; nullable quantifier; empty text |
| 22–28 | Group count/order/group0 inclusion; optional missing group; nested/repeated/noncapturing groups; Unicode group offsets; returned Array independence |
| 29–35 | Replace all; `$0`; `$1`/`$2`; `$$`; `$10` with two versus ten captures and missing `$9`; zero-width replacement; Cyrillic case+multiline flags |
| 36–40 | Invalid pattern/start/occurrence; numeric-string and fractional start observations; result/group mutation rejection; exact result/group/Array identities |

The fixture does not assume answers to these questions. The ASCII envelope
records bounded UTF-16 code units, so a non-BMP result is retained exactly rather
than normalized. No native exception descriptions are exported. Deliberate
ordinary error probes return fixed status strings; unexpected action/observer
errors remain explicit and reject availability rather than masquerading as
semantic equivalence.

## Resource and authority boundaries

* All pattern and text arguments are short fixed source literals. The packet
  invokes no file, temporary-file, stream, network, credential, shell or dynamic
  evaluation API.
* Two fixed calibration records plus forty numbered records. Each value is at
  most forty UTF-16 units; bounded array observation admits at most five results
  or groups. The complete rectangular encoded bound is 7,130 bytes inside the
  existing 8,192-byte output limit.
* Source SHA is pinned in the closed profile registry. Existing module hashes,
  client/server comparison, subprocess/input/output caps, nonce, cleanup and
  provenance validation remain unchanged. One additive workflow matrix entry;
  no trigger, permission, credential or timeout changes.
* Native tests contain no catastrophic backtracking, resource-exhaustion or
  unsupported-positive syntax probes. Backreferences, lookaround, named/inline
  and Unicode-property extensions are outside this initial bounded engine.

`!todo`: Native acquisition and immutable failed/successful captures are still
required. Platform semantics are not inferred from the local engine. Resource
limits are separately tested locally; this packet is ordinary semantic coverage,
not a performance or adversarial-engine safety certification.

## Evidence minimization

When calibration is authorized, public regression fixtures must contain only the
fixed measurement source, bounded observation bytes and minimal source/version
identity needed to reproduce semantics. Original acquisition envelopes/reports,
installation paths, audit/session identifiers, credentials and private launcher
metadata stay outside the repository. An absent original transport envelope is
reported as a limitation, not replaced with an invented acquisition claim.

The first native40 acquisition is retained in minimal `original40` fixtures.
All observations were available, but parity differed at18,21,32,33. The original
report and transport metadata stay private. Empty FindAll/literal dollar fixes
are established; revised RF33 separately observes reference fallback, a genuine
tenth capture and a missing reference, within the same40record and8192byte limits.

The revised RF33 capture is retained as minimal `references40` fixtures: native
value `a0|j:a|` distinguishes fallback, group10 and missing-group empty output.
Original acquisition parity failures remain historical evidence; local exact
replay after the measured parser correction is not a fresh native acquisition.
