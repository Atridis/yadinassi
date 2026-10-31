# Opt-in Metadata Catalogs public-runtime readback

This is a **local prepared lane, not native runtime acceptance**. PR165's
source-bound native measurements establish the owned fixture's observations,
not the new interpreter API. The original metadata measurement CLI, source
inventory, workflow job and historical receipts remain unchanged; its route remains available.

The separate explicit CLI is:

```sh
python3 scripts/native_1c_metadata_catalog_runtime_oracle.py --run --ci-report
```

It requires the existing authorized reviewed-source/native-image process and
existing transient registry credentials; it creates no persistent access. The reviewed-branch workflow selects this CLI through the separate
`metadata-catalog-public-runtime-v1` route and `native_metadata_runtime` job.
The old `metadata-catalog-applied-view-v1` route still selects only the original
measurement job. All unselected native jobs must be skipped for a green verdict. Its fixed finite artifact is
`native-db-oracle/metadata-catalog-runtime.json`. Publishing or launching it is
separate from preparing this source. Before transient registry credentials are
exposed, the immutable checkout is bound and the same full-host Python/dependency
pins are installed. The new job has the same read-only contents/packages grants,
owner/repository/reviewed-push checks, checkout options and fixed-artifact upload
policy as the existing measurement job; no new trigger or credential scope is added.

## What is compared

For each updated / loaded-but-not-applied / applied snapshot and each native
client/server context, a disposable clone runs the unchanged 26-case native
probe. CONFIG/Payload observation and the native output retain the original
32/32/64 discriminator. A second `inspect_frozen_catalog` envelope surrounds
actual `FileDBContext + Interpreter` execution of the same complete source
probe against the same frozen postimage. Its before/after full hash and
quiescence checks must return the original postimage's exact size and digest.
The readback record is bound to that native token, state and context.

All 24 supported cases are compared exactly. Cases 07/08 are explicitly
reported as excluded Attribute API controls; they remain visible, rather than
being filtered from execution or represented as passing runtime results.
A missing readback, mismatch, token/postimage change, observer failure or
cleanup failure cannot produce accepted runtime success. No live database,
universal applied-state or multi-catalog numeric-order claim is made.

## Closed runtime provenance

The container's actual command uses `python3 -I -S -B`: ambient environment
paths and site-packages are disabled. The fixed staged entrypoint bootstraps
only its read-only source directory, verifies the complete inventory, rejects
pre-imported runtime/dependency modules, and adds the verified dependency path.

The bundle includes the entire `yadinassi` Python/text source tree and the
full-host provenance source set, plus complete package/data/dist-info closures
for the exact existing `native_1c_full_host.py` convention:

- `prompt-toolkit==3.0.53`
- `pyuca==1.2`, including its UCA data
- `tzdata==2026.5`, including timezone data
- `wcwidth==0.8.2`

Versions, project requirements, package allowlisted roots, wheel RECORD hashes,
regular files, absence of symlinks, exact staged inventory and per-file SHA256
are checked. This is not a virtual-environment copy or vendoring into the
repository. Bytecode/cache files and private installer provenance are excluded;
`.pth`, outside-root files and unsupported installation metadata are rejected.

A canonical manifest binds every retained file. Its SHA256 is included in the
existing provenance source map, avoiding a thousands-entry lifecycle report.
Bounds are 2048 bundle files, 4 MiB per file, 32 MiB total and 512 KiB manifest.
The 32768-byte lifecycle limit is unchanged. The original measurement envelope
is validated independently; each public readback is capped at 8192 bytes, at
most six readbacks, with a separate aggregate wrapper bound. Dependency and
manifest identity are reconstructed by the report validator, never trusted as
an asserted pass flag.

## Local evidence versus remaining gate

Focused tests include a cold `python -I -S -B` process, with site-packages
unavailable, importing the staged runtime and dependencies and reading a
synthetic CONFIG-only image through the actual public adapter. The unchanged
probe matches all 24 supported native observations and does not modify the
image. Other tests reject source/UCA tampering, unexpected files, symlinks,
wrong dependency versions, forged comparison types, token/postimage changes,
missing records and excessive reports; failures retain cleanup behavior.
These checks do not replace a fresh authenticated native run on the exact
reviewed runtime source and bundle.
