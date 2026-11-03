# Deletion-mark behavior packet

This is a new observation source for a disposable, freshly installed, flat owned
catalog with no object module or hierarchy. It reuses the original fixture's
`generated/setup.json` and `generated/Catalog.xml` byte-for-byte. The exact
source SHA-256 is `6934171e56557c704c2ac95543524199661a624a9a5bc368a7a6703ec7d515b6`;
setup and XML hashes are pinned in `route.py`. The original CatalogObject packet
and its fixture are unchanged. Native acquisition is reported below; no general
platform or runtime parity is claimed.

One ENTERPRISE session emits exactly 32 nonce-bound, ordered Boolean observations:

1–5: existing object's direct assignment success, detached mark, reloaded mark
before Write, Write success, reloaded mark afterwards.
6–10: SetDeletionMark(true) success, detached mark, reloaded mark, detached and
reloaded dirty Description respectively. 11–12 repeat true and reread;
13–15 call false and read detached/reloaded marks; 16–17 repeat false and reread.
18–24: new object's direct assignment, mark, IsNew, Write success, IsNew,
existence by code and stored mark. 25–32: independent new object's method-call
success, IsNew, empty reference, mark, existence and stored mark, followed by
Write success and existence. When a lookup finds no row, the stored-mark result
is false as a sentinel; interpret it together with the preceding existence bit.
All `Try` outcomes report only success, not exception text. Setup writes fail
closed rather than producing partial observations. A compiler-level rejection
of direct assignment could abort the session before any observations; in that
case the packet is a failure, not evidence of the runtime assignment outcome.

## Acquisition gate and launch

The new host `scripts/native_1c_catalog_deletion_mark_profile.py` stages a separate
`catalog_deletion_mark_suite.py` using the old shell dispatch slot only inside
the isolated container. It stages the new route and source along with the
unchanged XML fixture, verifies original fixture and new source hashes, checks the
official redump and module witness, and emits 32 Boolean values. Its native
result is acquisition only: `runtime_parity_accepted` stays false and no old
interpreter replay is invoked.

Before acquisition, review the source and adapter, run the offline tests and
obtain the required approval for the native run. Use a clean source-bound
checkout, approved image and a fresh isolated container and infobase. Designer
and ENTERPRISE operations must run sequentially, with cleanup verified before
the next operation. The training version permits only one concurrent session
with an infobase, so concurrent writers against the same infobase cannot be
measured. Separate isolated runners use distinct databases; that fact does not
establish any cross-session behavior. See the official [training-version limits](https://1c-dn.com/library/tutorials/mobile_application_1c_enterprise_8_training_version/).

After approval, the host entry point is `python3 scripts/native_1c_catalog_deletion_mark_profile.py
--execute-approved-image --export-native-outputs`. It requires registry access,
the approved image and a clean Git checkout. The host retains only bounded
observations and provenance after cleanup. Runtime parity requires independent
comparison.

The dedicated offline command is `python3 -m unittest discover -s tests -p
"test_catalog_deletion_mark_packet.py"`. This command validates the host packet
contract, not native behavior.

Not covered: object-module hooks, form/UI event order, transactions and
concurrent sessions, hierarchy/cascades, referential integrity, deletion itself,
error categories or messages, rollback after faults, access-right failures,
other configurations/platform versions, or repeated acquisition. This packet
alone cannot establish any of those behaviors or full 1C compatibility.

## Acquired evidence

[Run 41645005336](https://github.com/Atridis/yadinassi/actions/runs/41645005336)
used source `41a6cf7a1d82ed5855c11150ee00000ae1ba3d54` and returned 32
source-bound Boolean observations with cleanup verified. Direct property
assignment and Write succeeded for existing and new objects. The method call
with True failed in both. A second [run with a Delete grant](https://github.com/Atridis/yadinassi/actions/runs/41647274341)
returned the same Boolean sequence. A third [finite diagnostic](https://github.com/Atridis/yadinassi/actions/runs/41649545810)
classified both exceptions as `other`, without matching its rights/lock/method
patterns. These observations do not establish the exception cause or general
semantics. The separately created baselines were not proved identical in all
respects. Captured artifacts are bounded and retained under GitHub's 7-day policy.
