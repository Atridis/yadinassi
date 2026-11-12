# Light development CI and exact-candidate premerge CI

## When jobs run

- Each Draft PR commit runs **light tests** on Linux x64, Windows x64 and
  macOS Intel x64, the existing launcher checks and the small actual-Python-3.10
  compatibility checks. It does not build binaries or run heavy partitions.
- `ready_for_review`, opening/reopening a non-Draft PR, and each subsequent
  `synchronize` while non-Draft run **light + heavy + packaged binary smoke** on
  those same three platforms. Draft is development; Ready is a premerge candidate.
- Pushes to `main` use the same three-platform light/heavy/package path.
- **Temporary macOS ARM pause:** ordinary PR and `main` runs do not allocate
  macOS ARM runners for light tests, heavy tests or packaging. Their verdict
  explicitly reports `excluded_platforms=["mac-arm"]` and `full_coverage=false`.
  All required tests on the other three platforms remain mandatory.
- **Every tag push**, including non-`v` and slash-containing tags, and every
  manual `workflow_dispatch` retain all four platforms for light, heavy and
  packaging. Only `v*` tag pushes release, after all full-coverage gates.
- Existing native-1C workflows, permissions and evidence requirements are unchanged.
  This pause does not bypass a native gate or promise those jobs are lightweight.

Admission derives both JSON job matrices from its validated event binding;
there is no input, environment flag or caller-provided platform list to select a
smaller scope. Light and package jobs share exactly the same matrix. Heavy keeps
two Windows shards, two Intel shards and one shard for every other included platform. The existing
success-only light → heavy → package sequence remains intact. Ordinary PR/main
macOS runner demand is 1 → 2 → 1; tags/manual remain 2 → 3 → 2.

GitHub has no literal “just before merge” event. The available repository
connector can mark a PR Ready; it does not expose workflow_dispatch. Accordingly
Ready is the normal trigger, with no new credential/browser service. A new head
requires a new accepted candidate run.

## Automatic classification and whole-group balancing

`scripts/test_durations.json` is reviewed **data**, initially derived from all
four completed main-accepted PR182 runs at head `8cd19562`, run41332191450. The
profile stores each full test ID's maximum measured platform time and Intel time.
It contains no test code and is never used to skip discovery.

`python -m scripts.test_partition --tier light` performs ordinary unittest
`discover('tests')`. A complete original module suite is heavy if its summed
worst-platform weights exceed **3 seconds**. Module/class fixtures remain intact;
custom `load_tests` suites spanning modules are coalesced rather than flattened.
Unknown/new IDs force their complete group into light, so they run immediately.
Missing history means all-light; malformed history is a failure, not an empty
suite. Thus stale history may make a light run slower, but cannot omit tests.

Heavy Windows and Intel groups are sorted longest-first and deterministically assigned to
whichever of two jobs currently has the smaller estimated total (stable ID and
job-index ties). No manually maintained shard membership lists exist. Other
platforms use one heavy job. Windows reuses the same deterministic Intel-weight
placement; it does not acquire a second independent classification. Each matrix job has its own runner/workspace/temp;
no concurrent shard shares a fixed `/tmp/onec-smoke` fixture directory.

A plan-only discovery on the initial split candidate `63499ae1` found **7866 IDs**: 5403 light,
1085 Intel-heavy-0 and1378 Intel-heavy-1, with exact disjoint union. The26 new
instrumentation tests are unknown/light. Recorded historical Intel weights are
275.134 seconds light and1400.880/1401.016 seconds heavy; known light weights on
Linux/ARM/Windows are131.508/141.194/188.452 seconds. These are predictions, not
new full-suite measurements; unknown tests and job bootstrap add time.

Every partition emits full discovered/selected/executed IDs, actual durations,
result counts and fixture skips. A class/module `SkipTest` is accounted for as
covered-but-not-executed, never fabricated execution. Failed class fixtures,
missing/duplicate IDs or incomplete coverage cannot produce a passing full gate.

## Required-platform recalibration from accepted #293

The checked-in data now comes from accepted full run **43130946906, attempt 1**,
exact merge source `0a1c06a47d719e94c82df270e9b4604a2085a77e` (head `e424d842`,
base `8f936780`). All seven original partition archives were downloaded and
checked against API size/SHA; the source-bound verdict covered 10,896 IDs on each
required Linux/Windows/Intel platform. macOS ARM was excluded under the existing
policy, not measured or treated as zero-cost. The profile is deliberately schema
2: it records that historical matrix, not the new Windows shard configuration.
It was generated with the pre-change `refresh_test_durations` implementation at
public ancestor `799e4d3cc2924d15ce745faede1c9fba10510bae` (the producer,
partition validator and CI gate are byte-identical to the local recovery
candidate), using `--scope required-platforms`.

Plan-only discovery on that presentation candidate found 10,912 IDs in 694
whole fixture groups: 7,412 light, 3,500 heavy and 17 unknown/light IDs. Evaluating
these groups against the accepted per-test durations gives the following
**counterfactual sums, not new wall-clock measurements**:

| Platform | New light | One/two heavy sums | Heavy plus all observed fixture overhead per shard |
| --- | ---: | ---: | ---: |
| Linux | 2m13s | 31m02s | 31m18s |
| Windows, one shard (rejected) | 4m17s | 45m47s | 46m09s |
| Windows, two shards | 4m17s | 24m49s / 20m58s | 25m11s / 21m20s |
| macOS Intel, two shards | 4m55s | 39m55s / 39m54s | 40m32s / 40m31s |

The one-shard Windows plan exceeds the unchanged 45-minute job cap before setup
or upload, so the profile and Windows two-shard policy are one coherent change.
The conservative column charges **all** original platform fixture overhead to
**each** proposed shard; it is not measured fixture-group attribution. Bootstrap,
upload, later source changes and runner variance are not predicted. New CI
contract tests remain unknown/light, so final counts can increase. The future
source-port optimization is not assumed in these estimates. A real candidate
full run must still validate the new schedule; local data analysis cannot claim
that run has passed. No test coverage, native gate or timeout is reduced.

## Source binding and mandatory merge procedure

Admission checks the live open PR's head and main base, the event's head/base,
and the immutable tested merge commit's ordered parents. Binding schema 2 adds
the exact GitHub ref. PR refs must be `refs/pull/<number>/merge`. Push payload refs
must equal trusted `GITHUB_REF`, must not be deleted, and must be either
`refs/heads/main` or a valid nonempty `refs/tags/...`. Main's payload `after` must
also match `GITHUB_SHA`; annotated tags are bound to the trusted checked-out
commit without confusing a tag-object SHA with that commit. Manual runs use the
trusted full branch/tag ref and always keep all four platforms.

All jobs explicitly check out that admitted commit with credentials persistence
disabled. Checkout, stamp and verdict commands also regenerate the binding from
the current GitHub event/context and compare it exactly, including phase, ref,
source/head/base/run/attempt. These comparisons are local and do not add API
calls. A well-shaped forged tag-to-main binding or heavy-to-light downgrade is
not accepted. Unknown binding fields, including scope overrides, are rejected.

Partitions are stamped with that binding; the final verdict downloads only that
attempt's artifacts. For ordinary PR/main heavy runs it requires exactly three
light and five heavy reports. Tags/manual require four light and six heavy
reports. Missing or extra platforms/partitions fail. Heavy runs must prove exact
disjoint full-discovery coverage on **every required platform**, retain all
package/compatibility job requirements, then reread current PR head AND main.

The verdict lists `required_platforms`, `excluded_platforms` and per-platform
coverage. `required_coverage=true` means the heavy suite covered every required
platform; `full_coverage=true` additionally requires all four platforms. A Draft
light-only run sets both booleans to false. The temporary three-platform result
is never represented as full four-platform coverage. Release still waits for
build, compatibility and the complete four-platform final verdict.

**Before an autonomous merge, the maintainer/root must:**

1. Require the current run's successful `Exact-source test coverage verdict`,
   all required native gates and any other repository gates.
2. Inspect its `test-verdict-<attempt>` artifact: `phase=heavy-premerge`,
   `required_coverage=true`, correct repository/PR/ref and current head/base,
   run/attempt. During the temporary pause, a PR must list exactly Linux, Windows
   and macOS Intel as required, only macOS ARM as excluded, and honestly set
   `full_coverage=false`. This is acceptance under the explicit ARM exception,
   not evidence that ARM passed. A successful `light-only` verdict is NOT merge
   approval. Tags/manual require all four platforms and `full_coverage=true`.
3. Reread the live PR head and `main` immediately before merge. Both must still
   equal the accepted binding. `python scripts/ci_test_gate.py fresh --binding
   binding.json` performs the same read-only check; a connector GET comparison
   is equivalent when executing the reviewed helper is inconvenient.
4. If head or base changed, reject the old green. Prepare a fresh candidate
   (including merging the new main if required) and trigger a new Ready/head
   event. Simply rerunning a job with stale event SHAs cannot make it current.

No branch-protection/admin settings are changed here. This procedure makes the
heavy gate mandatory for the autonomous merge owner; it does not claim GitHub
prevents a separately privileged human from bypassing it. CI uses ordinary
`pull_request`, never `pull_request_target` or `workflow_run` execution of a PR
with elevated credentials. Only the release job retains contents-write access.

## Refresh data, not code

Partition artifacts contain actual timings. Download and independently verify
all partitions from one accepted heavy run before calibration. To retain the
four-platform requirement (the default), use a complete tag/manual run:

```sh
python -m scripts.refresh_test_durations --reports downloaded-partitions \
  --source TESTED_MERGE_SHA --run RUN_ID --attempt RUN_ATTEMPT \
  --output scripts/test_durations.json
```

An ordinary PR/main run can instead calibrate **its three required platforms**
explicitly, without claiming macOS ARM passed:

```sh
python -m scripts.refresh_test_durations --reports downloaded-partitions \
  --source TESTED_MERGE_SHA --run RUN_ID --attempt RUN_ATTEMPT \
  --scope required-platforms --output scripts/test_durations.json
```

Scope is derived from the exact event binding, never a caller-supplied platform
list. The first form requires ten successful reports and full four-platform
coverage. The second requires every report selected by that event: eight for
ordinary PR/main, still ten for tag/manual. Both require disjoint complete
coverage on each required platform, exact source/head/base/run/attempt binding,
and finite bounded durations for every executed ID. Light-only, missing, extra,
failed or mixed-attempt reports are rejected.

New history schema 3 records the complete binding, actual required/excluded
platforms and SHA-256 of each canonical parsed partition JSON. These fingerprints
support later review; they do not authenticate artifacts or authorize merging.
The existing schema 1 bootstrap data remains readable. Schema 2 retains its
original one-Windows/two-Intel fingerprint layout; schema 3 requires the new
two-Windows/two-Intel layout. Historical data never authorizes an old or partial
CI verdict. The current refresh command requires the current complete matrix;
for historical reproduction use the reviewed producer from that source.
Calibration stores the
maximum measured platform duration and Intel duration, not job upload/setup time.
Wholly fixture-skipped IDs remain unknown rather than acquiring fictional zero
measurements. Unknown IDs still keep their entire fixture group in light.

This command only parses local JSON. It does not execute artifact contents,
download, run tests, commit, publish or change CI gates. Review the data diff and
plan-only discovery's exact disjoint union before publication. Per-test history
excludes class/module fixture time and is not a production benchmark or a wall
clock prediction. Recalibrate after substantial runtime changes; do not lower
coverage or skip tests to make a slow light partition appear faster.

Check policy changes with focused synthetic normal/-O regressions. Actual
Windows/macOS and Python 3.10 behavior must still pass the relevant CI jobs; local
synthetic results do not replace that evidence.

## First Ready-run cleanup regression

The first Ready run41342376001 exposed an existing Windows floating-point edge
in the synthetic native-host child cleanup tests: `(255.1 + 5) - 255.1` is
`5.000000000000028`. `_finish_child` now caps its final reap wait at the unchanged
`CHILD_CLEANUP_SECONDS=5`, while preserving the existing remaining-deadline and
minimum-wait behavior. The normal interpreter execution timeout is unchanged.
A deterministic clock regression checks the exact cap, elapsed time and expired
floor; original failed CI evidence is retained. This is a one-line native HOST
change, not an interpreter/runtime change, so the corrected Ready head requires
fresh automatic native and complete CI gates. Earlier green evidence is not
reused as acceptance of the corrected source.

## TODO: restore ordinary macOS ARM CI

- [ ] Restore macOS ARM light/heavy/package jobs for ordinary PR and `main` runs
  when runner capacity is available. Remove the temporary exclusion from
  `required_platforms`, update route/coverage tests and these instructions, then
  require a fresh four-platform heavy verdict for the exact current source.
- Until restoration, preserve every tag/manual ARM job and report the missing
  ordinary ARM coverage explicitly. Do not weaken timing-profile refresh,
  release requirements, Intel shards or native-1C evidence requirements.

## Failure diagnostics and bounded jobs

Light/heavy partition failures keep their original nonzero step and job status.
If the runner wrote `test-results/partition.json`, the stamp step still verifies
its admitted checkout and event binding after an ordinary test failure. Only a
successfully stamped report is uploaded. No `continue-on-error`, retry-to-green
or success fallback is used. Cancellation, a killed process, discovery exceptions
before report creation, or a failed stamp do not promise a diagnostic artifact.
Missing reports and failed job results still fail the final verdict. Heavy and
package jobs still require their successful predecessor matrices.

Job timeouts are 30 minutes for light, 45 for heavy and 40 for package. These
bounds include dependency setup and post-test report handling, not runner queue
wait. The initial limits leave headroom over the audited Windows heavy step
(24m10s) and package step (17m31s); they are operational limits, not performance
budgets. Revisit them using subsequent successful runs rather than weakening a
failing test or masking an ordinary test failure.

The existing JavaScript client and browser-support unit tests run in a separate
five-minute Linux Node 22 job on every admitted event, including Draft PRs. It
checks out the same admitted source, installs no npm packages, starts no browser,
and is required by the final verdict. This closes the missing existing JS unit
coverage only. It does not claim an actual browser regression or a rebuilt bundle.

## Additive timing diagnostics

Plans/reports list the real unknown IDs, their count and fraction of discovery,
the selected unknown count, and discovered/unknown/selected fixture-group counts.
Empty custom suites remain unknown groups but never fabricate unknown test IDs.
Unknown IDs still keep their complete original group in light. History schema,
classification threshold, balancing, coverage and original suite execution are
unchanged.

Reports also measure discovery wall time separately and partition wall time
around the complete runner invocation. Partition wall includes class/module
fixtures, cleanups, custom suites and runner reporting; per-test durations retain
their existing narrower scope. GitHub Step Summary displays these diagnostics.
Neither wall value is apportioned across tests or used to refresh history.

Per-group wall time is deliberately not claimed. unittest may run a previous
group's teardown while entering a later group, and coalesced custom groups can
occupy noncontiguous positions. Wrapping/reordering groups or forcing fixture
teardown just for measurement would change execution semantics. A future design
must prove unchanged custom-suite ordering, module/class fixtures and cleanup
before using group wall measurements for placement. The existing four-platform,
full-success refresh requirement remains unchanged.
