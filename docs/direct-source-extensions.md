# Direct source scratch extension registry

ConfigurationExtensions and ConfigurationExtensionsSource expose the existing
source host's finite read-only registry protocol through the direct backend.
Get and GetSessionApplicationIssuesInformation call the canonical implementation
with the actual executing caller. Optional omitted arguments retain their
Undefined/None meaning, including saved methods.

This is not extension activation, installation, editing or an inventory of a
remote information base. The source scratch database must have been explicitly
created; schema/file integrity must hold and its extension/issue registries must
actually be empty. Missing, unknown or populated state still fails rather than
being presented as an empty list. Filters remain unsupported and source values
are not coerced from strings.

Ownership and synchronous server context are checked before argument effects and
again at invocation. Safe mode and database validation remain in the canonical
read. Bound/captured methods recheck their manager and operation; foreign or
retargeted markers cannot use another application's authority. Canonical method
identities are checked before callbacks. No VM dispatch or mutation fallback is
introduced.

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_extensions_no_vm \
  test_python_direct_source_extensions_security
```

Final evidence: 913 focused/compiler tests pass on Python 3.12; Python 3.10
`-O` passes with the existing SQLite limit-API skip. The final source-wide
1,228-test run remains red at 112 errors and 6 failures, 11 fewer failing
outcomes than the enum checkpoint and no newly failing identities. A review
regression explicitly rejects an ExtensionCall forged with the stateless source
enum namespace as its manager, before any substituted read callback runs.
