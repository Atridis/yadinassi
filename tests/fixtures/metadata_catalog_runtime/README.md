# Metadata Catalogs runtime replay

`native_observations.json` is the unchanged normalized 156-row owned-fixture
capture from PR165 head `1590b573619e38861a3b6ec97f91d334185fe827`, tree
`50d533404bb8418d830df08006009e34a882ee05`, successful native run 41193004501,
artifact 13039712291 (Linux 1C 8.3.27.1508). SHA256:
`e7a54e3ed988c32ecf897710c32e7c6c32a46b906009c846a34970b3f497b124`.
Independent review receipt SHA256:
`f93dce3a8f9f27b7ffb43acf9bb414d719642637f47444bf5a3af591eb4b3cff`.

The replay test executes the unchanged official BSL probe against an authored
SQLite catalog configuration. It establishes offline logical surface replay,
not a new native run or native physical-file equivalence. All 26 cases are now compared exactly across six state/context captures
(156 comparisons), including attribute qualifier cases 07/08. Independent authored
SQLite schemas use Payload length 32 for updated/loaded and 64 for applied,
matching the historical configuration changes without changing any capture bytes. The
native acquisition and physical reader were retired; no capture bytes were
rewritten or relabeled as evidence for the new backend. No universal applied-state,
multi-catalog numeric ordering or live native database claim is made.
