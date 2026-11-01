# Light development CI and exact-candidate premerge CI

## When jobs run

- Each Draft PR commit runs four-platform **light tests**, the existing launcher
  checks and the small actual-Python-3.10 compatibility checks. It does not build
  binaries or run heavy partitions.
- `ready_for_review`, opening/reopening a non-Draft PR, and each subsequent
  `synchronize` while non-Draft run **light + heavy + packaged binary smoke**.
  Draft is the development phase; Ready is the premerge candidate phase.
- Pushes to `main`, all tag pushes and the existing manual workflow button keep
  the full coverage/build path. Only `v*` tag pushes release, after all gates.
- Existing native-1C workflows, permissions and evidence requirements are unchanged.
  This split does not bypass a native gate or promise those jobs are lightweight.

GitHub has no literal “just before merge” event. The available repository
connector can mark a PR Ready; it does not expose workflow_dispatch. Accordingly
Ready is the normal trigger, with no new credential/browser service. A new head
requires a new accepted candidate run.

## Automatic classification and Intel balancing

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

Heavy Intel groups are sorted longest-first and deterministically assigned to
whichever of two jobs currently has the smaller estimated total (stable ID and
job-index ties). No manually maintained shard membership lists exist. Other
platforms use one heavy job. Each matrix job has its own runner/workspace/temp;
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

## Source binding and mandatory merge procedure

Admission checks the live open PR's head and main base, the event's head/base,
and the immutable tested merge commit's ordered parents. All jobs explicitly
check out that admitted commit with credentials persistence disabled. Partitions
are stamped with source/head/base/run/attempt; the final verdict downloads only
that attempt's artifacts. It verifies all four light and five heavy reports,
exact disjoint full-discovery coverage on each OS, and all package/compatibility
job results, then rereads current PR head AND main.

Build + packaged smoke are independent jobs on the same admitted source, allowing
the existing binary checks to overlap tests without deleting their coverage.
Release still waits for build, compatibility and the complete final verdict.

**Before an autonomous merge, the maintainer/root must:**

1. Require the current run's successful `Exact-source test coverage verdict`,
   all required native gates and any other repository gates.
2. Inspect its `test-verdict-<attempt>` artifact: `phase=heavy-premerge`,
   `full_coverage=true`, correct repository/PR and current head/base, run/attempt.
   A successful `light-only` verdict is NOT merge approval.
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

Partition artifacts contain actual timings. After downloading all nine reports
from one accepted heavy run to a local directory, use:

```sh
python -m scripts.refresh_test_durations --reports downloaded-partitions \
  --source TESTED_MERGE_SHA --run RUN_ID --output scripts/test_durations.json
```

The command checks complete coverage, same source/run binding, finite bounded
numbers and all partition statuses. It parses JSON only; it neither executes
artifact contents nor downloads, commits or publishes anything. Review the data
change through a normal PR. Light-only/incomplete artifacts cannot replace the
history. Zero weights for skipped cases never authorize skipping future tests.

Local verification is synthetic normal/-O plus plan-only real discovery, not a
second full benchmark. Actual Windows/macOS and Python3.10 behavior must pass CI.

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
