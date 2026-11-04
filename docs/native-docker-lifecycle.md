# Owned native Docker lifecycle

This change applies only to `scripts/native_1c_catalog_deletion_mark_profile.py`.
Other native entrypoints still use their existing lifecycle and have not been
migrated or certified by this work. It does not authorize a new native run,
including a tabular-section experiment: that requires a separate complete
source, harness and permission review. Native observation sources and expected
results are unchanged.

The deletion-mark host now constructs `docker create` with its existing isolation
flags, an exact nonce-bound name, and the `org.yadinassi.native.invocation` label.
Docker documents that [create does not start the container](https://docs.docker.com/reference/cli/docker/container/create/).
The host admits only a completed successful response containing one full
64-character lowercase hexadecimal ID. Before `docker start --attach ID`, a
bounded inspection must match that ID, exact name, ownership label, pinned image
reference and resolved image ID, and a nonrunning `created` state. No lookup by
name grants authority to start or remove a container.

The attached CLI result must match an independently inspected, nonrunning
`exited` state and exit code. Before removal, ownership is checked again by full
ID. Cleanup uses only `docker rm --force ID`, requires that exact ID in its
successful response, and then a successful empty full-ID filtered listing.
A name reused by another container is never a removal target. No prune, broad
filter deletion, or retry of create is supported.

An incomplete, invalid or lost create response leaves container cleanup
**unverified** and never starts a container. Reaping the Docker CLI or seeing an
empty listing cannot prove that the daemon will not finish a delayed create.
The harness deliberately leaves such a possibly created, unstarted container
for separately authorized investigation, without retrying or deleting by name.
This uncertainty prevents native evidence acceptance and artifact export.

Image inspection, create, ownership/exit inspection, attachment and cleanup
share one 2,400-second monotonic deadline. The final 30 seconds are reserved for
cleanup; short commands are capped at 30 seconds within that same deadline.
Each command reserves its last two seconds for bounded direct-child reaping.
After Popen returns its process handle, the explicit I/O, wait and reap calls
use that deadline. There is no Popen context-manager exit or subprocess.run
cleanup wait in this module. OS process creation inside Popen is not bounded by
this Python deadline; interruption before it returns a handle leaves CLI reap
unverified. The deadline is not a guarantee of an absolute container lifetime or
termination during daemon/OS failures. Deadline exhaustion fails closed, even
when that means cleanup remains unverified. Registry login
and image pull precede this lifecycle and retain their existing separate
acquisition behavior; this is not a claim of one deadline for the entire host.

`docker_cli_reap_verified` proves only reaping of the direct CLI processes.
`container_cleanup_verified` proves removal of the admitted container. Neither
substitutes for the other, and CLI process-group or descendant absence is not
claimed. A primary timeout, output-limit or interruption reason and its stage
are preserved when later reap, pipe-close or container-cleanup checks also fail. Private payload cleanup remains a separate existing gate. The daemon
and host are trusted; protection against an administrator concurrently changing
containers is outside this contract.

Offline tests use synthetic Docker replies and mocked subprocesses, never a
Docker daemon or 1C. They cover identity/state rejection, lost responses, full-ID
cleanup, independent CLI/container outcomes, deadlines, and host export gates.
Passing them is not native platform evidence or permission to launch native work.
