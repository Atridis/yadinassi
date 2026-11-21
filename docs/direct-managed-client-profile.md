# Managed compilation profile on the direct client path

Baseline: `3bd91286d1a879715f1237e944e51c24374de389`.

The exact six-scenario client preflight calls `verify_client_interpreter` with
`compilation_profile='managed-thick-file'` and an exclusively owned SQLite fixture.
The existing frontend understands this profile, but direct admission previously
required `standalone` before inspecting any source. The public verifier reported
`FullError('interpreter_failed')`; the child showed the generic context rejection.

Direct client execution now accepts either existing, explicit compilation profile.
The frontend still selects conditional branches before direct compilation. Managed
`Client` and `Server` compilation symbols are both true; this does **not** change
the execution side or grant a server invocation. Canonical client-mask behavior is
135 (standalone remains 5). Source, execute_program and prepared routes execute
that result without Interpreter.block/call_routine. Prepared contracts remain
profile-bound and reject cross-profile execution before effects.

No runtime-side checks were removed: configuration owners, server/NoContext
entry, server declarations, server/NoContext/dual routines, server initialization,
legacy routine registries and restricted transaction contexts still reject.
The generic context diagnostic no longer says that SQLite database context is
unsupported: the existing exact host-selected SQLite path remains allowed.
No VM fallback, alternate parser, hidden source rewrite or new dispatcher exists.

## Actual scenario progression

The unchanged `integrational_tests/tests/dates.bsl` and `numbers.bsl` now complete
under the managed profile with **185** and **427** messages. Their outputs match
the same unchanged sources under standalone direct execution. This is a host
execution/profile check, not native parity.

| Source | Source SHA256 | Output SHA256 (UTF-8 messages plus newlines) |
|---|---|---|
| dates.bsl | `392761c5ce8f599d569400672b07590184f147c9e4d5cd3f07decee1cffb029e` | `52f79fb5d2c0d4f4120ad74ce1f2108c61d3b854d187d62a21f85c0d2ac19e2a` |
| numbers.bsl | `65075fff9adc854a317c74821052a9f9afa2b064d5fbb55b21dbab1ecb87556d` | `a695f37be76fd975890a737b367be32e914e38faa3714f500581a058186c2cd8` |

The other original sources remain blocked: collections by FixedStructure;
functions, strings and values by Execute. They were not rewritten.

**The complete native six-scenario preflight is still blocked.** Re-running the
exact isolated client child with the original source and owned SQLite fixture
now reaches `server declarations are not integrated`. It still emits no witness
values and the verifier still raises `interpreter_failed`. Its source has four
Var nodes, 104 routines (43 client, 42 server, five server-NoContext and 14 dual
variants), one client assignment and one ServerInitializer. It also uses a later
separate `execute("ВычислитьПробу()")`, so persistent routines are another required
contract. Admitting these as ordinary client functions would be incorrect.
Server state lifetime, copyback/transfer, NoContext and dual dispatch need separate
implementation and original-witness validation. This change does not claim any
of those observations passed or that the native CI gate is fixed.

## Reproduce and validate

```sh
PYTHONPATH=tests:scripts:. python -B -m unittest test_python_direct_managed_profile
PYTHONPATH=tests:scripts:. python -B -O -m unittest test_python_direct_managed_profile
```

72 combined tests passed normal and `-O`: managed-profile regressions, direct
default, prepared API/admission, SQLite bridge and frontend managed truth-table
checks. They include exact mask selection, prepared profile mismatch, invalid
profile, server/NoContext/dual rejection before effects, two original full
scenarios, the exact whole witness's next rejection, real SQLite write/readback
and continued explicit-transaction refusal. Independent review passed 63 combined
tests under `-O`, additionally checking server initializer refusal before effects;
no blockers. No full CI/native-parity claim.
