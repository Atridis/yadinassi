# HTTP: bounded ordinary synchronous workflow (local checkpoint)

Ordinary native forty-record capture retained; calibrated local changes await
fresh source-bound native acceptance. No full HTTP compatibility claim. The source baseline is
main `f2509f0`; the official signature reference is the pinned 1C 8.3.27 EDT
platform documentation archive (SHA-256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`).

## End-to-end scope

`HTTPConnection` / `HTTPСоединение`, `HTTPRequest` / `HTTPЗапрос`, returned
`HTTPResponse` / `HTTPОтвет`, and `ByteOrderMarkUse` / `ИспользованиеByteOrderMark`.
The ordinary workflow covers GET, POST, PUT, PATCH, DELETE, HEAD and
CallHTTPMethod (including OPTIONS), mutable request headers, status and response
headers, string/binary/file bodies, writable in-memory request-body streams,
independent readonly response-body streams,
and a response output file. Resource addresses are origin-relative, beginning
with `/`; absolute URLs and authority-relative targets are refused.

Empty bodies and an unset body remain distinct. Response status codes including
404 and 302 are returned; redirects are not followed. Output files are not touched
until the complete bounded response has been received and validated. This does
not promise transactional rollback of a subsequent disk-write failure.

## Explicit implementation policy

* Response framing rejects duplicate Content-Length, Content-Length together
  with Transfer-Encoding, malformed lengths and transfer codings other than
  exact case-insensitive `chunked`. Ordinary chunked/close-delimited bodies are
  supported; truncated declared bodies are refused before output-file writes.
* One fresh connection per operation; no connection pool, cookie jar, automatic
  decompression, environment proxy or inferred credentials.
* Proxy, nonempty credentials, OS authentication, CONNECT, TRACE and unsupported
  special request headers are rejected before network access.
* TLS is **not implemented in this checkpoint**. Supplying a secure-connection
  object is rejected, never downgraded to plaintext. The native no-CA OpenSSL
  constructor's disabled-verification default is not reproduced. Verified trust
  configuration requires a separate ordinary TLS workflow.
* 8 MiB admitted request/response body; 100 admitted headers and 64 KiB aggregate
  admitted header bytes; target at most 8,192 characters/encoded bytes. The stdlib
  response parser first applies its own finite per-line/count bounds, then this
  module applies the tighter aggregate admission limit. The 64 KiB aggregate is
  not a claim about all intermediate stdlib parser allocations.
* Timeout accepts 0..60 seconds. Property value 0 is retained, but means a finite
  30-second socket-operation budget locally, **not native unlimited waiting**.
  Connect attempts, send and response reads share this budget after address
  resolution. Ordinary hostnames are supported. OS DNS resolution itself is
  outside the socket deadline; there is no whole-call wall-time guarantee.
* Existing regular-file path/read/write boundaries apply; no new filesystem
  authority, network authentication store or process privilege is introduced.

!todo: verified TLS constructors, cancellable DNS, proxy/authentication,
redirect policy, async operations, advanced transfer features and exact native
edge coercions. Unsupported cases must fail explicitly, not silently alter
security or request meaning.

## Verification status and native plan

Initial owned-loopback Python tests cover seven verbs, binary/text/file roundtrip,
encoding/BOM, statuses, duplicate response headers, readonly streams, refusal
before connect, body caps and truncated-response output-file preservation.
These are local integrity checks, not a native parity claim.

The planned native packet has 40 small ordinary observations with fixed public
payloads. A host-owned HTTP server binds loopback inside the existing isolated
network namespace; no external endpoint, DNS dependency or credential is used.
All native work is sequential in one 1C session. Synchronous method context must
match the official server availability; the ordinary all-client injector must
not be used blindly. Request/response semantics, encodings, unset/empty bodies,
status/header behavior and output-file relations need actual observation.
The new fixture lifecycle/source adapter requires independent review before the
first native dispatch. TLS policy tests are not native TLS parity evidence.

## First ordinary calibration

All forty server-side observations were acquired with verified cleanup. Four
local corrections follow those facts: request default decoding uses UTF-8 with
replacement (and ordinary BOM detection), a request stream writes into its live
bounded body, repeated response headers accumulate newest first, and file-backed
request getters return body data. `SetBodyFileName` opens an admitted regular
file immediately, as documented; send/getters read that same descriptor with the
HTTP body bound. Replacing the body or destroying the request releases it.

!todo: multiple request-view cursor relations, old-view behavior after body
replacement, and writable file-backed request streams are not native-calibrated.
The file-backed stream remains an explicitly readonly snapshot in this subset;
no global MemoryStream semantics are changed. Header ordering beyond the measured
ordinary duplicate pattern remains a compatibility edge, not an HTTP standard
recommendation. Public fixture contains only fixed source, typed output and a
minimal receipt; original failed cleanup attempts remain historical failures.
