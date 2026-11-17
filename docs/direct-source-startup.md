# Direct source-host startup

This is a bounded `SourceApplication` integration, not permission to run arbitrary
`Interpreter` subclasses and not full source-host compatibility. The ordinary
`python_direct._admit_vm` gate is unchanged. Unsupported work never selects the
legacy VM implicitly.

## Connected paths

* Exact `_SourceInterpreter` owned by the current `SourceApplication`, including
  startup and the synchronous session initializer. Existing source/profile
  parsing, session-before-application order, cancellation and failed-start cleanup
  remain authoritative.
* Same-side named and global common modules through the existing source XML
  admission. Privileged modules, duplicate global exports and unavailable module
  sides still fail. Unused modules are not compiled.
* Generated source procedures/functions, optional arguments, live by-reference
  arguments and application exports. Registry/layout/signature/native-constructor
  checks happen before arguments and again before invocation. Module identity is
  rechecked after argument effects. Each execution binds fresh closures to owned
  state; no old AST dispatcher or generator runner is used.
* Read-only source metadata and the two canonical metadata-property enum domains.
  Namespaces are explicit, not generic Python attribute reflection.
* Existing registered host functions and narrow context-aware source template,
  temporary-storage, transaction and host-session markers. These still use their
  original ownership/effect checks. Template and temporary-storage admission and
  arity checks precede argument effects.

## Scope and lifetime

The existing source-transaction and safe-mode execution contexts enclose source
execution. Each generated source routine, including same-module calls, gets its
own existing safe-mode routine frame. A callee cannot remove its caller's safe
mode; frames unwind on return and error. The opt-in compiler switch does not
change ordinary direct generated code.

Current application/family generation, scheduler, namespace identity, side,
compilation profile and transaction/safe-mode context are checked at boundaries.
Close/revocation is not catchable as an ordinary BSL error. Host by-reference
arguments are activation-scoped; retained references cannot operate after the
activation, even during a later execution. Reentrant host `execute` is refused.
Source module capability does not create a database or storage grant.

## Deliberate remaining limits

Source object/form interpreter subclasses, source manager/storage/query
receivers, client/server crossings, async/dual/NoContext routines and reusable
common-module results are not connected by this slice. Dynamic `Execute` is
rejected during source admission: its independent safe-mode frame is not yet
implemented here. `Eval` remains unsupported. Collection and constructor gaps
outside this integration remain unchanged. Some later failures are therefore
expected even when startup now succeeds.

## Verification

On the final local source slice, 145 focused tests pass on Python 3.12 and the
same 145 pass under Python 3.10 `-O`. They include startup/global-module/metadata
contracts, dedicated hostile-boundary regressions and existing direct default,
persistent-routine and Execute tests. Independent review's two pre-argument
admission findings were fixed and covered by tests. After rebasing onto the
HTTP protocol commit `2900ac37`, the combined 154-test source/HTTP selection also
passes in both modes; the source-only outcome counts below remain unchanged.

An unfiltered `test_source_*.py` discovery is still red. With Python 3.12, the
unchanged `e242b35c` baseline runs 1,228 tests with 885 errors and 22 failures.
The candidate runs the same 1,228 tests with 570 errors and 97 failures. These
are unittest outcome counts, including subtest failures, not a claim that every
remaining failure has the same cause. Query construction, source forms and
storage namespaces are substantial next gaps. No test, assertion or CI gate was
removed or relaxed. Full light, native 1C comparison and merge readiness are not
claimed by these focused results.

Reproduce from the repository root with installed project dependencies:

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_scopes test_python_direct_source \
  test_configuration_source_runtime test_source_global_modules \
  test_source_metadata_children test_source_metadata_properties \
  test_source_metadata_references test_python_direct_execute \
  test_python_direct_default test_python_direct_persistent
PYTHONPATH=tests:scripts:. python -m unittest discover -s tests -p 'test_source_*.py'
```
