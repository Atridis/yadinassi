# Native 1C Docker validation

The owner's private training image is
`ghcr.io/atridis/onec-ubuntu20:8.3.27.1508`. The owner identifies its training
executable as `1cv8t`, rather than the production edition's `1cv8`.

This first stage only checks package access and image metadata. It does not run
any process from the image, create a database, build an EPF, or claim native test
success. Existing Windows reference outputs remain unchanged.

## Image metadata preflight

The manual **Inspect native 1C image metadata** workflow is restricted to the
repository's default branch. GitHub requires a `workflow_dispatch` workflow to
exist on the default branch before it can be dispatched. The job checks out no
repository code, accepts no image or ref input, and pulls only the fixed image
above on an ephemeral Ubuntu runner.

In the package's settings, **Manage Actions access** must grant
`Atridis/yadinassi` **Read** access. The package can remain private. The workflow
uses its short-lived `GITHUB_TOKEN` with `packages: read`, not a personal access
token or a new repository secret. No write permission is requested.

Authentication is kept in an isolated temporary Docker configuration on the
runner and removed on exit. No token is passed into an image. The workflow does
not use `docker run`, `docker create`, a privileged container, a Docker socket
mount, or host filesystem mounts. It reports an immutable image reference, ID,
platform and limited configuration flags. It deliberately omits environment
values, labels, history and entrypoint/command text, because a private image can
accidentally contain sensitive details.

Docker command output and error text are kept in temporary private diagnostics,
not echoed into public logs, and removed on exit. Failures report only a fixed
stage description and numeric exit code; no raw registry error is published.

The workflow's metadata result is a prerequisite for a separately reviewed,
digest-pinned native execution stage. A successful pull is not a successful 1C
launch, license validation, or integration test.

## Explicit training executable

The launcher now accepts either its original `--path-1c` directory selector or
`--executable-1c` with the exact installed executable path. The latter selects
`1cv8t` explicitly without renaming it or guessing the platform edition. Paths,
Designer availability and Enterprise capabilities still need verification in
the image; accepting a path is not a capability check.

The standalone mock suite runs with:

```sh
python integrational_tests/check_launcher.py
```

These are Python protocol tests and do not execute real 1C.

## Required next-stage evidence

Before replacing manual native runs, verify a digest-pinned image can:

1. Provide the claimed training platform version, executable, license mode,
   Python 3.10+ and a working headless graphical display.
2. Create a disposable managed file database without prompts or production data.
3. Compile the existing launcher and every test module through Designer, with
   process success, `/DumpResult` equal to zero and a nonempty EPF.
4. Run Enterprise and return valid `result.json` for every scenario, preserve
   diagnostics, reject any `.err`, and prove completion instead of accepting a
   partial output or exit code alone.
5. Record exact scenario/source hashes, image digest, platform/version/edition,
   locale, database compatibility and timezone, then execute the interpreter
   against the same sources and compare complete outputs without broad
   normalization.

The existing launcher runs test object modules inside one
`&НаСервереБезКонтекста` call. A Linux training run therefore establishes that
server-context behavior, not every possible client context.

Linux training 8.3.27.1508 is a separate provenance from the recorded Windows
8.3.27.2342 reference. Fresh Linux output must be kept in a separate disposable
capture. Do not overwrite or relabel the Windows goldens. The current saved-output
comparator fixes `Europe/Warsaw` to replay that Windows fixture; a live differential
runner must explicitly record and match both runtimes' timezone instead of
silently inheriting this historical setting.

References:

- [Manually running a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [Container registry authentication](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub-hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
