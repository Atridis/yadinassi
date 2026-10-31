# Metadata Catalogs runtime replay

`native_observations.json` is the unchanged normalized 156-row owned-fixture
capture from PR165 head `1590b573619e38861a3b6ec97f91d334185fe827`, tree
`50d533404bb8418d830df08006009e34a882ee05`, successful native run 41193004501,
artifact 13039712291 (Linux 1C 8.3.27.1508). SHA256:
`e7a54e3ed988c32ecf897710c32e7c6c32a46b906009c846a34970b3f497b124`.
Independent review receipt SHA256:
`f93dce3a8f9f27b7ffb43acf9bb414d719642637f47444bf5a3af591eb4b3cff`.

The stub-context test establishes only BSL surface replay of the exact source
probe. It does not establish public file adapter or native integration success.
Cases 07/08 are retained and explicitly excluded: the Attributes API is not
implemented, and their native 32/32/64 values discriminate the owned applied
CONFIG view. The other 24 cases are compared exactly in all six state/context
captures (144 supported comparisons). A fresh public-adapter same-postimage
native readback is still required before runtime acceptance. No universal
applied-state, multi-catalog numeric ordering or live database claim is made.
