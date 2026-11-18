# CI discovery and extended-reference diagnosis

Published `767c685ecfdb8ba645e8a52c39d2e3af4b8a9232`, workflow
[44354190552](https://github.com/Atridis/yadinassi/actions/runs/44354190552):

* Linux, Windows and mac-x86 light jobs aborted in discovery, before running the
  light suite: `ValueError: duplicate discovered test identity`.
* Five differential test modules imported `DirectASTExternalTests` directly.
  `unittest` discovered its two original tests in all six module namespaces.
  Local discovery on the equivalent `46dadd6d` tree reproduced 17,088 instances
  but only 17,078 unique IDs. Imports now retain the fixture module instead of a
  globally discoverable TestCase. Subclass tests and the defining fixture remain.
  The strict duplicate-identity partition gate is unchanged.
* Extended-reference correctness failed for `xml.roundtrip` on both default and
  prepared routes. The new compiler's generic unsupported-constructor message
  omitted `XMLWriter`, so the report's narrow known-capability allowlist could
  not recognize it. The compiler now includes the rejected constructor name;
  the allowlist itself is not broadened and no legacy execution is attempted.
* The decimal-isolation test's failure was secondary: its nested workload suite
  contained the same XML errors. It was not evidence of a changed Decimal context.

The ordinary core performance measurements completed; extended measurements were
skipped after failed correctness, and the paired report was consequently incomplete.
Passing these repairs does not imply the full light/runtime suite is green.
