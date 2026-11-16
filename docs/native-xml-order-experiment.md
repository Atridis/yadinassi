# Current scoped entrypoint: A/A diagnostics

The workflow now invokes `native_1c_xml_order_aa.py`, not the eight-case runtime experiment described below. This follows inconclusive run 43914299292 (c0034929): positive runtime witnesses completed, independent redump hashes differed, handler case timed out. There is no repeat of that invalid cross-context handler binding.

A/A creates two independently owned containers/infobases from identical instrumented baseline source hashes. Each performs create/load/check/update/dump1/dump2. No ENTERPRISE or edits/reload/update occur between the two dumps. Four comparisons report within-aa1, within-aa2, cross-dump1 and cross-dump2 raw/strict/permitted equality. Fingerprints include ConfigDumpInfo.xml; legacy_excluded marks that the older aggregate digest omitted it. Known-slot indexes map to sorted packet.baseline input filenames; -1 means a native-added file. Unknown native paths and XML values are not exported.

Output is bounded to 64 files, 1 MiB/file, 8 MiB/tree, depth 64, 8192 XML nodes/file; wire reports to 196608 bytes/container and 524288 bytes/host. Per-file structural component hashes expose differing shape/attributes/text/namespaces; UUID-masked hashes are diagnostics only, never equality or acceptance. External fingerprints receive strict schema/value/hash/slot validation before comparison. Full exact comparisons remain visible even for UUID-only differences. `acquisition_complete` means both six-phase acquisitions completed, even if repeatability fails; it does NOT mean equality or semantic acceptance. semantic_acceptance=NOT PROVEN, visual_ui=NOT RUN, enterprise_executed=false remain explicit.

Only the same owner-bound separate push workflow is changed; main/#336/fixtures and other workflows stay untouched. The outer 45-minute budget covers two 850-second lifecycle deadlines plus bounded image acquisition and cleanup. Artifact: xml-order-aa-summary, containing xml-order-aa-report.json. Native partial-trace helper remains offline; handler follow-up is deferred. A later clean behavioral negative must have compatible context/signature and a distinct effect, with identical authored modules across its baseline/variant.

Local tests: `python3 -B -m unittest discover -s tests -p test_native_xml_order_aa.py -v`, plus test_xml_order_measurement.py and test_native_xml_order.py. Shell syntax: `bash -n scripts/native_1c_xml_order_aa.sh`. This is scoped diagnostics, not the full suite.

---

# Isolated XML order acquisition

Review candidate based on `993190926a0d3adc24f8663b8e404c0c312d7a8c`.
This is an acquisition experiment, not a relaxation of production XML acceptance.
Existing fixtures, launchers, workflows and main-demo source remain unchanged.

## Invocation and admission

The new workflow is `.github/workflows/native-1c-xml-order.yml`. First invocation is an ordinary non-forced **owner-authenticated push** of reviewed code to the separate branch `codex/xml-order-native-reviewed`. No PR is needed. At this source revision, `build.yml` only watches main/tags for push, and native isolated-smoke only watches main/its own reviewed branch; this new branch does not launch the broad suite. Do not open a PR as a substitute: existing PR workflows would run broader profiles.

The pre-checkout eligibility code verifies Atridis login and numeric owner/actor/repository IDs, non-fork repository, triggering actor, event SHA, workflow SHA/ref and exact branch. A second check binds clean checkout HEAD before credentials; the host repeats this binding and rechecks it after collection. Ordinary owner push is the supported initial route because a new manual workflow is not assumed to exist in the default-branch workflow catalog. Dispatch is only a later option once GitHub actually exposes that workflow, with `reviewed_sha` equal to selected branch HEAD. Never spoof owner variables or bypass policy to run locally.

After review, in the isolated candidate checkout (commands are a handoff, NOT already executed):

```sh
# Commit only the new files after reviewing the complete diff.
git add .github/workflows/native-1c-xml-order.yml scripts/native_1c_xml_order.py scripts/native_1c_xml_order.sh scripts/native_1c_xml_order_ci_policy.py scripts/xml_order_packet tests/test_native_xml_order.py docs/native-xml-order-experiment.md
git commit -m "Add isolated native XML order acquisition"
# Requires real Atridis authentication; no force, no PR, no merge.
git push origin HEAD:refs/heads/codex/xml-order-native-reviewed
```

Do not interpret those commands as evidence of a published branch or completed run. Workflow availability/credentials and actor identity must be checked on the resulting push/run. No GITHUB_TOKEN-created push assumption is made: pushes using that token generally do not trigger another workflow.

## What executes

One pinned `ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728` image, expected platform 8.3.27.1508. Login/pull happen on the host; temporary Docker auth is removed before running native. The existing `native_1c_docker_lifecycle.run_owned` owns each container, verifies image/ownership/exit, removes only its owned ID, verifies cleanup and reaps CLI processes.

Eight sequential fresh containers/infobases: baseline, attributes, properties, events, handler_changed, duplicate_property, duplicate_event, ui_childitems. Network none, empty explicit environment, non-root, read-only root and staged source, no token/daemon socket mount, bounded private tmpfs and resources. Each invocation has an 850-second total lifecycle deadline including cleanup; each native process has 120 seconds with kill reserve. Outer job budget is 130 minutes to cover eight worst-case invocations plus image acquisition without clipping normal owned cleanup. Baseline failure stops further cases. Workflow concurrency uses its own group with cancel-in-progress false and does not cancel other CI.

Each container copies the pinned 47-file main demo as the same 46 platform files, excluding InventoryApplication.xml. Before independent mutations it adds identical **authored** instrumentation only in those copies: application startup opens DraftDetails, Created records a marker, Closing records its actual cancellation decision, added OnOpen/OnClose handlers check initialization, record runtime Items enumeration and observe cancelled/allowed close. All added source is reviewable in `scripts/xml_order_packet`. No direct calls to Created/Closing impersonate native dispatch. Every case uses identical executable BSL; only the handler negative changes XML wiring.

Mutations splice original byte ranges, never serialize XML. Unique Properties (Name/FormType) and Event declarations are swapped; name/id attributes of one Attribute are swapped. Namespace scopes, prefixes and QName values stay intact. UI ChildItems are swapped only in the negative control. Other UI controls/columns/metadata enumerations are never sorted. Duplicates are detected before diagnostic normalization. Projection is local to the selected experimental form and metadata, not a production comparator.

Native phases are create, load, check, update, redump, ENTERPRISE. Captured original fixtures are never output destinations. Process code, DumpResult and native quietness are checked. Native output stays in bounded private tmpfs. The redump hash uses conservative tree projection, scoped namespaces, significant text, exact BSL and ordered children except the selected unique properties/events. Designer defaults/version differences may produce inconclusive results rather than guessed equivalence.

The finite JSON artifact includes reviewed source SHA/tree, input/case hashes, phase results, redump hash, finite lifecycle/order result, assessments and cleanup evidence. Unknown/duplicate keys, invalid status sequences, changed input/nonce bindings and oversized payloads fail validation. No native XML/logs/database/screenshots/credentials are exported. Aggregate output is capped at 256 KiB.

## Meaning and limitations

`acquisition_complete` requires the positive redump/runtime comparisons and UI-order negative to be distinguished, and the changed handler to have a native load/check rejection; duplicates require a rejection or a complete validated runtime trace. Missing/invalid/replayed traces remain inconclusive for every negative control. Timeouts never count as a successful negative control. Duplicates and changed wiring are never reported equivalent even if Designer canonicalizes or accepts them.

`runtime_items_order` is an observation of the native Items collection. **It does not establish rendered layout or keyboard tab order.** `visual_ui` remains `NOT RUN` and `semantic_acceptance` remains `NOT PROVEN`, even when acquisition is complete. This candidate does not automate screenshot/tab-order verification, OperationDraft confirmation callbacks or persisted business effects. It measures parameter initialization and real close-cancellation effects in DraftDetails only. Those limits are part of the report, not silently accepted omissions.

Native BSL compilation/execution and image availability on this local host are NOT RUN. The first admitted run may reveal a baseline BSL/platform incompatibility and must then fail/inconclusive, without expanding production acceptance or overwriting fixtures. A failing baseline is not a reason to weaken admission or manufacture markers.

Before a general claim that XML order is semantically irrelevant, complete the outstanding visual/tab-order and broader interaction plan in a separately reviewed native UI observer/manual run. Retain exact mappings and ordered controls/collections regardless of cosmetic XML order.

## Local verification

```sh
python3 -B -m unittest discover -s tests -p test_native_xml_order.py -v
python3 -B -m unittest discover -s tests -p test_native_docker_lifecycle.py -v
python3 -B -m unittest discover -s tests -p test_main_demo_designer_acquisition.py -v
bash -n scripts/native_1c_xml_order.sh
```

These are offline contracts and mocked lifecycle tests, not native semantics. No full CI is needed for this review.

Trigger references checked against [GitHub event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch) and [GITHUB_TOKEN trigger restrictions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
