# Automatic trusted native 1C checks

The native workflow runs the six current regression scenarios on real 1C for
owner-authored pull requests from `Atridis/yadinassi` into `main`, including
Drafts, and owner pushes to `main`. It is separate from the unchanged four-platform
build matrix. No manual 1C launch or saved-output generation is needed for these
supported events. Tags, releases, forks, other authors/actors, arbitrary refs,
manual dispatch and privileged PR triggers are outside this route.

PR events are exactly `opened`, `synchronize` and `reopened`. A title/body edit or
Draft-to-ready transition does not rerun unchanged code. Retargeting an existing
PR into main requires a subsequent push (`synchronize`) or close/reopen to obtain
fresh checks for the new base. Until then, a missing native check is unavailable
evidence, not a pass.

## Identity and honest checks

Admission validates the exact repository and owner identities, event type, main
base/ref, PR author and head repository, original actor and rerunning actor.
Admission and the final verdict have no token permissions and perform no checkout.
Only an eligible native job receives `contents: read` and `packages: read`.
Excluded or malformed events fail admission without native execution. The final
verdict fails when admission or native execution fails, is skipped, is cancelled,
or has not completed successfully. A skipped native job is never a green native
result. A missing workflow run likewise provides no evidence.

Checkout uses the immutable event `github.sha`, without persisted credentials.
For a PR this is GitHub's synthetic merge commit, not its head. Its ordered parents
must match the event's base and head SHAs before registry access. Main pushes must
match the exact event commit. Existing runtime provenance independently verifies
checkout HEAD, tree and run/attempt identity. A rerun certifies its original
revision, not a later head or base; review/merge must compare current identities.
Per-PR/ref concurrency does not cancel an already running native cleanup.

These checks are not repository protection settings. No branch rule or required
check has been installed by this change. The workflow deliberately has no path
filters, so an otherwise eligible change cannot silently avoid its verdict.
There is no tag execution or release dependency in this route; existing releases
continue to depend on the four build jobs only.

## Fresh reference, not cached goldens

Every eligible execution creates a fresh disposable database in the same approved
digest-pinned image, validates the bounded role/user/protection readbacks, observes
the actual platform version and verifies the simple EPF. It then builds and runs
all six current scenarios through the existing launcher. No former database,
output artifact or cached reference can satisfy the current run.

The exact native bytes are transported privately with bounded nonce/hash checks.
The host runs a fresh interpreter process for each current source under UTC and
explicitly selects `linux-8.3.27.1508` / `typed-map-order-v1`. Five current outputs
are byte-exact; the source-bound Map contract may accept only the eight reviewed
payload records without pair order, retaining types, bindings and real roundtrip
checks. All other results remain strict. Raw differences and semantic acceptance
remain separate. See [the full comparison contract](native-1c-full-regression.md).

The registry image can use infrastructure caching, but native outputs are never
cached as an oracle. Historical Windows `8.3.27.2342` outputs remain unchanged for
offline/default-target and frozen-build regression checks. They are not relabeled
as Linux results; removing them requires a separate dependent-test migration.

## Unchanged isolation and artifact scope

The image digest, disposable administrative role, exact 23 read-only inputs,
resource/time bounds, readonly root and tmpfs data/logs remain unchanged. No
container network, exposed ports, token, Docker socket or writable host mount is
added. Authentication uses the existing short-lived job token on the host, with
private registry configuration deleted before native execution. Native-job actions
are pinned to the verified official v7 commits; no new account, credential,
package grant or repository setting is introduced.

The same seven-day public artifacts are retained: the finite summary and exactly
six native `.out` files plus finite `provenance.json`. These test outputs include
intentional error messages. Raw service logs, `.err`, database, XML/EPF files,
image contents and credentials are excluded. Publication requires the existing
source/evidence/cleanup and exact-file export gates. Actual output bytes are never
normalized or replaced to obtain a pass.

## Package privacy and trusted code

The owner explicitly accepted the existing public-repository package access model
for this training image. GitHub documents that granting a public repository access
to a private package can also allow access from forks. A fork's read-only token
can request package read; maintainer approval controls whether a run starts, not
package confidentiality after code runs. The effective repository approval policy
is not established by this workflow.

Fork/actor guards exclude forks from **our native route**, not from every possible
workflow a contributor might propose. Editable YAML, host orchestration and
interpreter code must be trusted/reviewed: container isolation does not sandbox
that host code or guarantee secrecy of the image. No claim of an actual leak is
made. No package visibility/access, Actions approval or branch-protection setting
was changed. Never replace this route with `pull_request_target` or a privileged
workflow that executes an untrusted head.

References:
- [Private package access from workflows](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions#default-permissions-and-access-settings-for-packages-modified-through-workflows)
- [Fork token permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#changing-the-permissions-in-a-forked-repository)
- [PR merge-ref semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
- [Rerun identity and privileges](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
