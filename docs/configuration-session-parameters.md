# Explicit application session parameters (provisional)

This coherent language block is under implementation. Local contract tests are
not native evidence; the owned sixteen-case acquisition is prepared separately.

The existing explicit `managed-client-server-v1` application profile admits
bounded `SessionParameter` declarations and `Ext/SessionModule.bsl`. Import,
construction and database opening remain inert. Only explicit application
`start()` runs initialization. Parameter values live in RAM for that application,
not in SQLite, the shared metadata cache or another application.

## Lifecycle

* Startup invokes `SessionParametersSetting(Undefined)` before client application
  code/events. Russian alias: `УстановкаПараметровСеанса`.
* First reading an unset declared parameter invokes the handler with an array
  containing its declared name. If it remains unset, reading raises an error.
  Unset is not false, zero or an empty string.
* Successful initialization is retained. Recursive initialization is bounded;
  errors cannot leave an initialization lock behind.
* SessionModule contains private procedures/functions, not exports, module
  variables, imports, context annotations or executable top-level statements.
  It can call already admitted server common modules through the normal VM.
* Closing/failing/cancelling the application invalidates its parameter handles.
  Creating another application starts another independent session.

`SessionParameters` / `ПараметрыСеанса` supports named properties and String
indexes only in an active server context. Managed client code calls an admitted
server common module; client/global availability is not inferred from native
thick-client descriptions. Capturing a namespace does not bypass this check.
Separate client/server process hosts initialize parameters only in the server
application. No new network transport or serialization capability is added.

`Metadata.SessionParameters` exposes the declared ordered names, qualified Type
descriptors and FullName lookup without reading or initializing any values.
These metadata objects are read-only; they grant no access to session state.

## Closed first profile

Boolean, bounded String, bounded Number and DateTime declarations are admitted.
Other types, composites, mutable collections and references remain rejected.
The current local assignment policy accepts exact scalar values already within
their declaration constraints. Undefined, coercion and truncation/rounding await
the prepared native observation; do not treat the provisional policy as native
parity. Partial assignments made before a handler error are not silently rolled
back by a second transaction mechanism.

This is a **trusted explicit host** profile, not an ACL or privilege-mode
implementation. It does not simulate privileged mode, impersonation, RLS,
Query parameter binding or durable session state. Native fixture permissions
use the documented Get/Set rights; production role metadata is not implicitly
activated by admitting SessionParameter XML.
