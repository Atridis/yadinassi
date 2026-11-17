# Direct source session parameters

The direct source boundary exposes only the application's exact owned
SessionParameters object. Dot/index reads and writes use the existing typed
store with the actual executing caller. Source-family ownership, server-only
access, immutable-value validation, byte/depth/node budgets and unsupported type
errors remain in the canonical implementation.

An unset parameter invokes the registered source session initializer as generated
Python. The existing recursion guard and cleanup remain unchanged. The owner,
handler and registry binding are checked; temporary server/module scopes are
restored on success and failure. Legacy backends retain their original dispatch.
No AST evaluator or routine-dispatch fallback is used by the direct path.

Saved setters and by-reference slots revalidate the owner and active boundary
before writing. A foreign, replaced or closed store cannot use another caller's
permissions. Unknown methods and iteration are not added to the namespace.

This increment does not admit new FixedMap, FixedArray, FixedStructure or
ValueStorage constructors, reusable-module behavior, or client/server crossings.
Existing tests requiring those features remain explicit unsupported outcomes;
the namespace bridge is not a claim that all session scenarios now pass.

```sh
PYTHONPATH=tests:scripts:. python -m unittest test_python_direct_source_sessions_security
```

The full existing 63-test session namespace/type suite is not green: 43 pass and
20 retain unsupported constructor/reuse or side-dispatch requirements. Dedicated
scalar tests instead prove dot/index access, generated lazy initialization
(including zero parameters), recursion cleanup, canonical byref writes, foreign
store rejection, retained-setter revocation and class-hook tampering with VM
entry points poisoned throughout the complete test, not just startup.

Final integration on the ValueList head: 809 focused/source-adapter/compiler
checks pass on Python 3.12; Python 3.10 `-O` passes with the existing SQLite
limit-API skip. The 1,228-test source-wide suite remains red at 133 errors and
14 failures, 20 fewer failing outcomes than the document-handler checkpoint,
without newly failing test identities. Initializer class/instance replacement
is also rejected before callbacks using a definition-time identity check.
