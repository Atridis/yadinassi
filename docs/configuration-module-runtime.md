# Explicit configuration module runtime

`managed-client-server-v1` is an opt-in, bounded host profile for executing BSL
stored in an imported configuration. It reuses the normal lexer, parser,
Interpreter, scheduler, callbacks and logical client/server transfer contract.
There is no second evaluator. Import, database creation and database opening
**never execute stored BSL**. Starting the application is a separate operation.

## Using it

```python
from yadinassi.configuration_runtime import ConfigurationApplication

application = ConfigurationApplication.from_files(files, output=print)
try:
    if application.start():
        application.execute('Message(Utilities.Calculate(2));')
        application.close()
finally:
    application.close(force=True)
```

`files` is the same path-to-bytes mapping accepted by `import_configuration`.
The existing catalog/document XML profile still applies. `CommonModule` entries
in Configuration.xml name `CommonModules/Name.xml` and require the exact
`CommonModules/Name/Ext/Module.bsl` source. The optional managed application
module is `Ext/ManagedApplicationModule.bsl`. The in-memory application also
admits configurations containing only common/application modules. The SQLite
storage profile still requires at least one supported catalog or document.

For SQLite, import with `module_runtime='managed-client-server-v1'`, then create
the database normally. `ConfigurationApplication.from_database(context)` checks
the retained source and active schema before constructing an application. This
block adds no SQLite schema version and does not activate arbitrary stored
archives merely because they contain BSL. Ordinary database use remains inert.

```text
python -m yadinassi --create-db app.sqlite --import-xml ./xml --module-runtime managed-client-server-v1
python -m yadinassi --f app.sqlite --module-runtime managed-client-server-v1 -c "Message(Utilities.Calculate(2));"
```

The execution option requires `--f` and the standalone preprocessor profile.
Without it, stored application/common-module code is not loaded. A cancelled
startup exits successfully without executing the command. A cancelled shutdown
reports cancellation and exits with code 1; this finite CLI cannot preserve a
live interactive process after returning. A host that needs cancellable close
should retain the `ConfigurationApplication` instance instead.

## Common modules and exports

* Common modules contain only procedure/function declarations, no module
  variables or main body. Imports and execution-context annotations in these
  modules are rejected. Metadata selects each compiled logical side.
* A non-global module supplies a stable, read-only named receiver. Only `Export`
  routines are callable externally; private helpers stay callable inside it.
  The receiver can be stored in BSL variables, obtained with `Eval("Name")`, and
  used in an ordinary `CallbackDescription`. It is not a general reflection
  object or a wire-serializable value.
* `Global=true` exposes exported routine names to the appropriate global
  context, not a named receiver. Conflicting global exports, module names,
  builtins and application declarations are rejected before initialization;
  native collision precedence is not guessed. Routine-local variables retain
  the interpreter's ordinary shadowing semantics.
* `ClientManagedApplication` and `Server` select separate compiled copies.
  `#If Client` / `#If Server` use the existing standalone symbol profile. This
  does not infer native thin/web/file-mode symbols from the host platform.
* `ServerCall=true` admits client calls only to a non-global server-only module.
  Same-side nested calls select their own side. Server-to-client calls and
  client calls to unexposed server modules fail before argument evaluation.
* Server crossings use the existing bounded copy-in/copy-out implementation,
  including named-variable requirements for non-`Val` parameters and atomic
  copyback after a successful return. There is no network transport or new
  claim about arbitrary native object identity/serialization.
* Common-module routines have no form context. A bound NoContext caller may
  call these verified routines without gaining access to form variables.
  The ordinary restrictions for other contextful routines remain unchanged.
* Async/Await, optional routine arguments, callbacks, exceptions and diagnostic
  frames are the existing interpreter mechanisms, not a parallel dispatch path.

`Metadata.CommonModules` / `Метаданные.ОбщиеМодули` exposes read-only lookup by
name, `Find`/`Найти`, and `Count`/`Количество`. Item properties in this slice are
Name, Global, ClientManagedApplication, Server, ServerCall and Privileged, with
Russian aliases. Other metadata reflection/ordering APIs are not implemented.

Application exports are visible to logical client common modules. Application
variables persist for that application instance; a second instance has separate
state, module receivers and scheduler. Common modules themselves have no module
variables under the official grammar.

## Explicit headless application lifetime

Construction validates metadata, source, collisions and event signatures without
running initializers. `start()` runs the application module body, then
`BeforeStart(Cancel)`, then `OnStart()` if not cancelled. The corresponding
Russian names are `ПередНачаломРаботыСистемы` and `ПриНачалеРаботыСистемы`.
Only ordinary procedures with the exact supported argument counts are admitted.
Cancellation is by reference and must remain Boolean. Startup occurs once.

`close()` invokes `BeforeExit(Cancel, WarningText)` and, if not cancelled,
`OnExit()`. Russian aliases are `ПередЗавершениемРаботыСистемы` and
`ПриЗавершенииРаботыСистемы`. Cancellation leaves the instance running for a
later retry; `last_exit_warning` retains the String warning. Server and Async
calls are unavailable during shutdown; global and structured user messages are unavailable during OnExit.
Startup/shutdown errors fail the lifetime and close its scheduler. `force=True`
closes without lifecycle handlers, for explicit host cleanup.

This is a **local headless host lifecycle**, not creation/destruction of a native
main window, form-close ordering, modal UI, user confirmation, rights management,
or a real server session. Existing UI form services must be integrated explicitly
by their host, rather than copied from a caller's form variables.
`bind_interpreter(vm)` is a host-only seam for VMs sharing this application's
scheduler; it does not expose Python objects to BSL or permit foreign families.

## Closed boundaries and evidence

The whole configuration must remain inside the existing importer profile.
Unknown executable object/manager/session modules, unknown XML behavior and
unsupported auxiliary metadata still block activation. The default importer
continues to treat CommonModules as unsupported unless the profile is requested.
No activation issue is silently cleared by this runtime.

Privileged modules, ordinary/external clients and ReturnValuesReuse other than
DontUse are rejected, not treated as harmless flags. **Executable SessionModule
remains unsupported**: official semantics always execute it in privileged server
mode and initialize session parameters before application startup. This host has
no authority model that could truthfully provide that behavior. Lazy session
parameters and their recursion/error contracts are not simulated.

The profile bounds common modules to 128 and total compiled routines to 2048,
in addition to existing source/XML limits. These are Yadinassi resource bounds,
not asserted native platform limits. It is not a hostile-code sandbox.

Local tests cover metadata failures, exact source persistence, explicit startup,
export visibility, two-side compilation, nested/repeated calls, unavailable
contexts, copyback/error handling, Eval, callbacks, Async/Await, state isolation,
NoContext calls, lifecycle cancellation/failure, and SQLite/CLI reopen. Local
success is not native GUI/security/lifecycle parity evidence. Existing native
context-transfer probes remain unchanged; this block makes no unmeasured
collision, shutdown unwind, user-rights or SessionModule claims.

Official contract references:

* [1C:Enterprise Developer Guide 8.3.27](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/),
  sections 4.2.3.1, 4.2.3.3, 4.2.3.4 and 5.5.2.
* [Module types](https://1c-dn.com/library/tutorials/practical_developer_guide_theory_module_types/).
* Official EDT 2026.2 Syntax Helper: CommonModule metadata properties; global
  events BeforeStart, OnStart, BeforeExit, OnExit and SessionParametersSetting.
  The English Server property translation has a contradictory negative; its
  Russian text and the Developer Guide describe server-side availability.
