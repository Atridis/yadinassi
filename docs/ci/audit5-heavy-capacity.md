# Heavy CI capacity after audit5 duration refresh

The measured duration refresh is retained unchanged. On the 13,984-test
candidate discovery, the previous history selected 1,608 heavy tests in 114
fixture groups; refreshed history selects 4,350 in 254 groups. Previously
unknown fixture groups had stayed in light, so this is redistribution rather
than added/removed coverage.

Run 43684304372 reached the 45-minute job limit on Linux, Windows and mac-x86
shard 1. Tests were still reporting progress; no test failures were observed
before cancellation. The resulting verdict correctly rejected cancelled heavy
jobs and skipped packages. This is incomplete evidence, not a passing run.

Every required OS now uses two deterministic fixture-preserving heavy shards.
On this candidate their selected sets are disjoint and their union is exactly
all 4,350 heavy tests (2,225 + 2,125). The unchanged measured Intel estimates
are 2,752.27 and 2,752.53 seconds, approximately 46 minutes each. A bounded
60-minute heavy job allowance provides setup and runner-variance headroom.
It is not a guarantee of duration on every runner.

Light selection, discovery, per-test/resource limits and semantics are unchanged.
The final gate requires both heavy shards for every required platform and still
rejects missing/extra reports, duplicated/uncovered tests, failed results, stale
source bindings and discovery disagreements. Tags/manual runs retain mac-arm;
ordinary PR/main mac-arm policy is unchanged. No failed run is reclassified.
