# Main demo browser evidence v2

The source inventory grew with the direct backend. On the PR #337 integrated tree,
559 tracked files already consume 59579 bytes before execution evidence is added.
The final compact report exceeded its 65536-byte cap, so the browser job failed
at publication and only screenshots were uploaded. Screenshots alone do not
prove that all smoke assertions or cleanup succeeded.

Keep the execution report cap unchanged. Evidence v2 moves the complete path-to-
SHA256 inventory into `source-binding.json` (separate 1 MiB hard cap), not a reduced
or sampled list. `result.json` retains every execution/status/failure field and
binds this inventory by filename, exact bytes, file count and SHA256 under
`binding.sourceArtifact`. The inventory repeats the source commit and tree.
The manifest schema 2 includes the same descriptor plus the hash of result.json.
Both ordinary CI and the opt-in workflow explicitly upload the new artifact.
Existing source-change checks still compare every source byte before PASS.

To verify downloaded evidence: check result.json against manifest.resultSha256,
check the identical sourceArtifact descriptors, and use
`verifyMainDemoSourceBinding(result, sourceRaw)` from the harness helper (or check
its digest, bytes, file count, commit and tree equivalently). Missing/substituted
source inventory is not valid evidence. No repository code consumes the old
embedded source field; external consumers must use evidenceSchema 2 explicitly.
The old schema remains readable as historical evidence, not silently rewritten.

This fixes evidence sizing, not runtime behavior. It does not convert a failed
scenario or cleanup into PASS and does not claim a successful browser rerun.
Synthetic tests cover full roundtrip, current tracked tree, mutation, replacement,
limits, capability scanning of both artifacts, and early failures.
