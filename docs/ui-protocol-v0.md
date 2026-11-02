# Experimental headless catalog browser: yadinassi-ui/0

**Unstable host protocol, not a BSL form API or a finished application MVP.**
This first UI increment has no GUI, network listener, catalog object writer,
managed-form metadata loader, or new `yadinassi` CLI flags. It can read an admitted
offline `.1CD`, list catalogs/records, open a card and follow a fixed catalog
reference. `canEdit=false`, `canWrite=false`; `CatalogRepository.commit()` always
raises `write_unsupported`. No sidecar, overlay or in-memory Save success exists.

## Try the source-tree examples

Use the existing development environment from README; no extra dependencies:

```sh
python scripts/ui_catalog_client.py "/path/to/consistent-offline-copy"
```

The independent client starts `scripts/ui_catalog_bridge.py` as a child process,
prints the inventory, first catalog page and first card, then closes. It uses
only JSON and pipes, not private interpreter objects or a BSL handler API.
It validates response identities/revisions but trusts the host's JSON decoder
behavior; it is an example client, not a hardened parser for hostile servers.
The bridge accepts the offline directory **from its host command line only**.
No protocol message can select another filesystem path. The examples are not
new packaged entry points and do not launch a browser. Their output can include
the selected database's names/data; do not publish it with private databases.

For raw protocol exploration:

```sh
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"ui.hello","params":{"protocol":"yadinassi-ui/0"}}' \
  | python scripts/ui_catalog_bridge.py "/path/to/consistent-offline-copy"
```

`FileDBContext` remains read-only. Caller-provided offline consistency is still
required: unchanged stat fields are not a lock or snapshot guarantee. The host
repository pins a source stat generation across reads and rejects detectable
replacement/change, including after a failed initial read. Existing reader limits,
schema admission and native-order restrictions are not weakened.

## Framing and requests

One UTF-8 JSON object per LF-delimited line. Escaped newlines inside strings are
allowed; literal extra lines, CR/CRLF, BOM, duplicate keys, nonfinite JSON numbers
and JSON floating-point numbers are rejected. Decimal values use tagged strings.
Limits apply before dispatch: 131072 bytes per frame, 8192 bytes per string,
8192 JSON nodes, depth 16, cumulative string bytes 131072. The bridge reads at
most frame-limit + 1 bytes; an oversized line ends that bridge with an error,
rather than draining unbounded input. These are local limits, not 1C limits.

This restricted JSON-RPC 2.0 profile admits only single-object requests, not
batches. IDs must be positive integers <= 2147483647, strictly increasing in a
session. Accepted IDs are consumed even when the requested navigation fails;
reusing an ID never repeats an action. At most 4096 admitted requests are allowed.
Renderer notifications are ignored without a reply or action. There is no
request queue, parallel execution or reentrancy. One host must serialize calls.

Every request has exactly `jsonrpc`, `id`, `method`, `params`:

| Method | Exact params |
| --- | --- |
| `ui.hello` | `{ "protocol": "yadinassi-ui/0" }` |
| `ui.snapshot` | `{}` |
| `ui.event` | Fields below |

All events require `formId="catalog-browser"`, integer `baseRevision`, and one
of these exact event names/extra fields:

| Event | Extra fields | Meaning |
| --- | --- | --- |
| `selectCatalog` | `catalog`: metadata UUID | Read catalog and display first page |
| `openCard` | `reference`: tagged CatalogRef | Open a real record in the selected catalog |
| `followReference` | `field`: metadata field name | Follow that field of the current card |
| `page` | `offset`, `limit` | Show list page; clears the open card |
| `close` | none | Close the session |

These are host navigation events, **not invented 1C event/method names**. Unknown
fields, methods and events are rejected. No handler name, arbitrary BSL source,
eval, Python object, executable path, database path or Write action is accepted.

`openCard` checks the catalog identity and requires an existing nonempty reference.
An absent BSL reference can have scalar defaults, but that is not an existing UI
record. `followReference` resolves the field internally, validates its declared
catalog identity and rejects empty/missing targets. The renderer cannot substitute
a different target in that operation.

## Responses, revisions and bounded state

A successful hello produces its result first, followed by `ui.open`:

```json
{"jsonrpc":"2.0","id":1,"result":{"protocol":"yadinassi-ui/0","revision":0}}
```

`ui.open.params` contains `formId`, `revision`, `capabilities`, `state`. Inventory
state has `kind="catalogs"` and at most 128 catalog identity/name records. Inventory
discovery alone does not prove row support: each entry says `rowSupport="not-checked"`.
The repository proves row admission only when selected; capabilities explicitly
say `rowSupport="checked-on-selection"`. Unsupported input is not silently
converted into a generic schema or interpreted as proof of corruption.

A successful navigation increments revision exactly once. Its result contains
the new revision, followed by `ui.patch` with `formId`, `baseRevision`, `revision`,
and a replacement bounded `state` fragment. List state has a page with catalog
identity/name, offset, limit, total and summary rows (reference/code/description/
deletion mark). Card state additionally contains typed values, field names/kinds,
qualifiers, target catalog IDs and `readOnly=true`.

Default pages contain 8 rows; request limits are 1..64 and must also fit the frame
budget. A larger page can be refused with `message_limit`; retry with a new ID
and smaller page. Paging projects an already bounded reader snapshot; it is NOT
native DynamicList/query pagination or an arbitrary-size database cursor.

Navigation and complete response encoding finish before session state/revision
are committed. Failures emit only an error, leave navigation/revision unchanged
and do not publish a partial view. This is host navigation atomicity, **not** an
invented rollback rule for future BSL event handlers or database transactions.

`ui.snapshot` returns the complete current bounded snapshot inside `result`, with
no notification/revision change. It resynchronizes the same known session; this
version does not restore sessions after process restart or implement connection
authentication. A close returns an acknowledgement and `ui.close` with old/new
revisions. Later requests fail `closed`. EOF terminates the example bridge.

Stale `baseRevision` is rejected before any row read. Nested entry fails `busy`
without consuming an outer request ID. JSON-RPC parse/invalid-request/unknown-method
errors use -32700/-32600/-32601; finite application rejection reasons use -32000.
Responses never expose exception text, local paths, physical slots or traceback.
Metadata/catalog admission failures include `capability="not-established"` and
guidance to check offline consistency and the supported schema, not a corruption
claim. There is no automatic reconnect retry of a state-changing request.

## Typed scalar codec

`encode_value` / `decode_value` use exact types, no coercion:

| Host value | Wire representation |
| --- | --- |
| Undefined (`None`) | `{ "type": "Undefined" }` |
| BSL Null | `{ "type": "Null" }` |
| String | `{ "type": "String", "value": "text" }` |
| Boolean | `{ "type": "Boolean", "value": true }` |
| Decimal | `{ "type": "Number", "value": "12.50" }` |
| Known BSLDate | `{ "type": "Date", "ticks": "12345" }` |
| CatalogRef | `{ "type": "CatalogRef", "catalog": "metadata-uuid", "record": "record-uuid" }` |

UUID strings must be canonical lowercase; catalog UUID cannot be zero, record UUID
can be zero. They are distinct logical identities, not generated native type UUIDs,
physical bytes or Python object IDs. Resolution is scoped to the repository's
metadata, not a global identity registry.

Numbers retain canonical `str(Decimal)` including scale/signed zero; finite values
are limited to 128 coefficient digits and exponent magnitude 4096. A local
512-byte Decimal storage preflight rejects oversized host coefficients before
copying their digits; the wire decoder bounds input text first. Dates retain
100-microsecond ticks from 0001-01-01, without timezone conversion or JS Date.
Unknown boundary Dates are refused. This UI codec does **not** expand the existing
BSL cross-context Date/Null/reference transfer contract. Arrays/Structures,
arbitrary host objects and unsupported BSL types remain outside the scalar codec.

## Verification and next boundary

`test_ui_protocol`, `test_ui_catalog_view`, `test_ui_browser` cover codec bounds,
malformed messages, identities, revisions, reconnect snapshot, reentrancy, source
changes, encoding failure, EOF/oversize framing and an independent subprocess
client. Integration uses existing owned captured CONFIG/rows in **synthetic page
transport** through real FileDBContext. It is not a retained native `.1CD`, a new
native run, a form-event parity claim, or write acceptance. Tests verify unchanged
file bytes after navigation.

The next increment is measured BSL FormRuntime with explicitly bound handlers;
the current navigation prototype does not define that API. See
[the application MVP plan and native form probe boundary](ui-catalog-mvp.md).
