# Direct source enumerations

Enums/Перечисления now expose the current source application's enum namespace,
managers, references and owned metadata through a finite direct adapter. This
uses the already imported enum definitions and type snapshot, not a new enum
registry or a scratch database capability.

Named/numeric indexing, declaration-order iteration, Count/Get/IndexOf/EmptyRef,
reference Ref/IsEmpty and Metadata retain their canonical implementation.
Mutation remains forbidden. Type, TypeOf and TypeDescription use the existing
source interpreter's enumeration snapshot, including persisted constant values.

Owner checks bind the namespace, manager, type snapshot and metadata to the
current application. Foreign and stale objects cannot gain permissions from a
new caller. Saved methods revalidate at invocation, after argument evaluation;
private names and unsupported operations are not exposed. Neither legacy
program evaluation nor routine dispatch is used by the direct source path.

The existing runtime and constant-persistence tests are repeated with legacy
entry points poisoned. Native enum serialization/presentation beyond the
repository's existing evidence is not claimed.

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_enums_no_vm \
  test_python_direct_source_enums_security
```

The adapter checks definition-time method identities before invoking enum or
metadata callbacks. Named references, empty references, type families, current
metadata maps and value-definition identities are validated without trusting
substituted mappings or equality hooks. Adversarial tests cover changed methods,
foreign named values, forged UUIDs, EmptyRef retargeting and scalar substitution
inside a metadata collection.

Final local evidence on the Eval-cache head: 881 focused/compiler tests pass on
Python 3.12; Python 3.10 `-O` passes with the pre-existing SQLite limit-API skip.
The source-wide 1,228-test suite remains red at 115 errors and 14 failures,
18 fewer errors than the session-parameter checkpoint and no newly failing
identities. Unsupported client/server crossings and native constructors are not
implicitly enabled by this namespace increment.
