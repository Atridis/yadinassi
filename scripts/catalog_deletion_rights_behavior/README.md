# Deletion mark: Delete-right variant, prepared but not measured

This independent profile is `catalog-deletion-mark-delete-right-v1`. It reuses
exactly the existing BSL bytes and nonce transport, with SHA-256
`6934171e56557c704c2ac95543524199661a624a9a5bc368a7a6703ec7d515b6`.
The same 32 Boolean observations have the interpretation documented in
`catalog_deletion_mark_behavior/README.md`. No original packet, fixture or native
result was changed.

The only intended fixture difference is adding `Delete=true` to the same
bootstrap role's specific owned catalog. Exact admitted catalog grants are
`Read`, `Insert`, `Update`, `Delete`; no extra grants, duplicate rights, false
rights or different target are admitted. The original fixture validates the
baseline first. This variant checks the prepared and re-dumped role rights, then
uses the original full-file/metadata strict official XML redump comparison.
It does not expose XML or private logs. A successful host provenance report
contains the distinct profile, this rights tuple, and `catalog_rights_verified`
only after a valid strict redump and full successful native session. This is
configuration evidence, not proof of every effective runtime permission.

The original reported Boolean sequence is:

    [true,true,false,true,true,false,false,false,true,false,false,false,true,false,false,true,false,true,true,true,true,false,true,true,false,true,true,false,false,false,true,true]

It showed failed `SetDeletionMark(True)` attempts, but the Boolean result carries
no error category. This variant tests whether the additional role grant changes
any observations; neither a changed nor an unchanged result alone proves the
cause, effective permissions, general platform behavior or runtime parity.
Fresh database, exact same platform/image/profile setup, revision/source evidence,
and independent review are required for a meaningful comparison.

## Diagnostics and privacy

The source intentionally catches operation exceptions and outputs only Boolean
success/readback, with no exception text, stack trace, names from arbitrary data,
filesystem paths, or database contents. The owned codes/descriptions are fixed
in source. Existing harness gives a finite failure phase and category, fixed
32-value nonce-bound transport, source/module hashes, native redump flag,
process cleanup signals and finite diagnostics. Compiler/startup failure does
not become a false native Boolean and may prevent all 32 records. More precise
error-cause classification would require a separately reviewed source packet;
it must not emit free-form exception strings or pretend such diagnostics are
part of the current unchanged A/B source.

## Prerequisites and execution

Do not run until offline tests, independent code/fixture review, and explicit
native ACK. Use a clean committed Git checkout and the approved image, registry
access, dependencies and a fresh isolated disposable infobase; comply with the
same one-session-per-infobase boundaries and fail closed on uncertain cleanup.
This new host/profile is not wired into ordinary PR CI. After those gates:

    python3 scripts/native_1c_catalog_deletion_rights_profile.py --execute-approved-image --export-native-outputs

Summary: `native-smoke/catalog-deletion-rights.json`. Successful verified export:
`native-smoke/catalog-deletion-rights-outputs/catalog-object.out` and
`native-smoke/catalog-deletion-rights-outputs/provenance.json`. The older
`catalog-deletion-mark` artifacts remain separate. The existing host pins image,
source and staged helper hashes, verifies module and redump witnesses, destroys
its container and private temporary data before export, and does not claim
interpreter parity. Test command after ACK:

    python3 -m unittest discover -s tests -p 'test_catalog_deletion_rights_packet.py'

No test or native session was run during preparation. Native write, physical
record deletion, object-module hooks, hierarchy, concurrency and rights beyond
the owned catalog role are outside the packet's claims.
