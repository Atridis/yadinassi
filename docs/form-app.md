# Run a replicated form application

The opt-in form launcher joins the detached form API to an actual browser and
an owned, persistent Python server process. The browser renders controls; a
local logical client executes client BSL; only the child executes server BSL
and opens the optional SQLite database. Plain `yadinassi` and the existing
catalog editor keep their defaults.

## Try it

From a source checkout with the project dependencies installed:

```sh
python -m yadinassi.ui.form_app examples/forms/estimate --open-browser
```

Edit Price and Quantity, then Calculate. The client sends pending scalar form
changes to the server, receives the result and updated form, and resumes its
client command before the browser sees the new snapshot. The server and client
never share a Python form or interpreter object.

For an actual persisted record, create a new owned example database explicitly:

```sh
python -m yadinassi --create-db products.sqlite --import-xml examples/forms/product-intake/configuration
python -m yadinassi.ui.form_app examples/forms/product-intake --f products.sqlite --open-browser
```

Enter a code, description and amount, then Create product. Server BSL performs
`CatalogObject.Write`; a successful save disables the fields and command. The
example is a single new-product intake form, not an existing-record editor or
an optimistic-concurrency implementation. Backend uniqueness/qualifier errors
remain errors. A failed write does not claim that earlier independent effects
were rolled back. The example never creates a database implicitly.

Installed Python entry point: `yadinassi-form PACKAGE_DIRECTORY [--f FILE]`.
The frozen executable selects this mode only with its first argument
`--form-ui`; its owned child uses `--form-ui-runtime`. Example packages are
repository source examples, not bundled user data.

## Trusted local package

A directory contains four fixed UTF-8 files:

- `client.bsl`: client-only module, without server bodies.
- `client.json`: `yadinassi-form-app/0` or `/1`, trusted client handler descriptors and
  remote endpoint signatures. Each binding has `name`, integer `endpoint`,
  `parameters` and exact Boolean `isFunction`.
- `server.bsl`: server-only module. Code and database handles stay in the child.
- `server.json`: the same protocol, handler signatures, endpoint/routine map,
  lifecycle bindings, and scalar attribute definitions. Version `/1` also requires
  fixed `tables` schemas; `/0` scalar packages remain supported unchanged.

The two JSON manifests in each example are complete templates. Each attribute
has `name`, `type`, `title`, `value`; types are String, Number, Boolean or Date.
Values use the existing exact tagged scalar codec, so Number values are decimal
strings, not JSON numbers. This first loader uses default TypeDescription
qualifiers. The richer Python embedding API remains available for custom host
schemas. Lifecycle/handler/source checks are inherited from the replicated core.

The client process reads only client files; the child reads only server files.
Neither manifest nor module source is sent to the browser. The browser cannot
choose source, file paths, database, procedure names, endpoints or signatures.
The package is trusted executable application code, not an uploaded form,
untrusted-code sandbox, signed deployment package or native 1C form import.
Package files are read once during process startup; stop/restart to deploy new
source. Do not edit a package during startup.

## Events, failures and shutdown

Browser requests select only `hello`, read-only `snapshot`, or a `change`,
`command`, `cell`, `select`, or ordinary `close` event with exact UI revision and an existing control.
A repeated hello reattaches to the same session without repeating OnOpen.
A stale click returns current state without executing again. Response snapshots
contain only bounded display data, messages and a finite error code.

A completed handler mutation survives a later handler error. The authoritative
snapshot is returned even on a known failure. Lost/malformed server responses
set the session's uncertain flag and prohibit further events. There is no
reconnect, write replay, exactly-once guarantee or automatic recovery of uncertain
database effects. Reconcile the backend before starting another session.

The pipe exchange has a 30-second deadline for its combined write/read. The
launcher owns its child; shutdown closes stdin, then terminates/kills an owned
child if it does not finish within the bounded waits. Closing a clean form
stops the listener. A cancelled close leaves it open. Ctrl+C stops the launcher
and discards unsent edits without running close callbacks; this is host teardown,
not proof that previously sent writes were undone. Killing the browser alone
does not automatically terminate the launcher or discard its client session.

The listener binds only `127.0.0.1` on an ephemeral port. Exact Host, Origin,
Content-Type and per-launch capability checks protect the finite `/rpc` route.
The capability begins in the URL fragment, is removed from browser history and
kept only in memory. Reopen the original launch URL to reattach after a full
page reload; there is no local-storage token. Static routes cannot serve package
files or database bytes. This is local-only HTTP, not an authenticated remote
server/TLS deployment. BSL remains trusted and retains its existing capabilities.

## Scope and verification

Flat scalar fields, checkboxes, labels, buttons and cancelable close are admitted.
Dates, Undefined and Null are initially display-only in the renderer. Decimal
inputs retain exact text and never pass through binary floating-point parsing.
Fixed scalar tables are supported by version `/1` packages, with row identities,
selection and cell editing. See [the order-intake guide](form-tables.md) for the
complete browser-to-SQLite example and explicit limits. No reference controls,
browser BSL engine, NoContext manifest endpoints,
async dialogs or network deployment are added. Existing host APIs retain their
broader composition options. This launcher establishes no new native 1C event
ordering, cancellation or replication parity.

`tests/test_form_app.py` covers package separation/admission, calculation,
revision/replay protection, lifecycle errors, interrupted processes, loopback
HTTP boundaries and an actual separate-process SQLite save/readback. Renderer
contract tests live under `frontend/form/test`; the deterministic asset build is
`node frontend/form/build.mjs`. Test outcomes belong to the exact candidate's CI
and PR evidence, not this reusable guide.
