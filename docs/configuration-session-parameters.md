# Explicit application session parameters

The owned sixteen-case acquisition passed on native 1C 8.3.27.1508 in run
`43052415203`. Its source-bound scalar observations are preserved as an immutable
test fixture. Local lifecycle/security tests supplement that native evidence.

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
The measured scalar assignment policy accepts exact values already within their
declaration constraints. Excess number fraction digits and string length are
rejected rather than silently rounded/truncated. Array-to-Boolean and Undefined
assignments are rejected without overwriting the existing value. Partial
assignments made before a handler error persist; they are not silently rolled
back by a second transaction mechanism. Other coercions remain unclaimed.

This is a **trusted explicit host** profile, not an ACL or privilege-mode
implementation. It does not simulate privileged mode, impersonation, RLS,
Query parameter binding or durable session state. Native fixture permissions
use the documented Get/Set rights; production role metadata is not implicitly
activated by admitting SessionParameter XML.
