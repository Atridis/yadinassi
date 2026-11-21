# Captured BSL methods and explicit Python extensions

Plain Interpreter denies arbitrary HostFunction values injected through variables.
This is not a ban on BSL method values. Dynamic-value resolution first traverses
existing finite adapters, which validate canonical implementation, receiver owner,
policy and lifetime. The extension-origin flag reaches the generic fallback;
only that fallback rejects unregistered Python callbacks.

Two compiler/runtime-created closure families (native Array method extraction and
ErrorInfo category query extraction) use private weak provenance. The public
HostFunction constructor, matching name, copied wrapper, or copied wrapper fields
never grants this provenance. The original wrapper, callback and signature must
still match at resolution and immediately before invocation, including after
policy/argument effects. Existing close/revoke/policy checks surround invocation.
The weak registry does not keep a receiver→wrapper cycle alive. Direct named
services and ordinary scalar/collection operations do not consult the registry.

This is not a sandbox against trusted Python editing private implementation
modules or invoking private compiler factories. Explicit host extensions still
require allow_extensions=True. Owner-specific adapters remain responsible for
foreign/expired receiver rejection; provenance does not replace those checks.

Validation: 48 targeted tests pass normally and under -O. This includes the three
reported TextDocument/ErrorInfo/FixedArray regressions, Array method values,
live metadata, accumulation saved methods, UserMessage captures, extension policy,
wrapper forgery/mutation, close and weak-cycle collection. On the integrated fixture base, an additional 35 owner/security tests pass
under -O (UserMessage, live metadata and accumulation). The ErrorInfo public
constructor-monkeypatch test also passes alone in a fresh process.
