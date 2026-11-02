# Ordinary HTTP workflow measurement

One closed server-context packet, `scripts/HTTPFamily.bsl`, exposes
`HTTPFamily(Port, OwnedRoot)`. It is not an all-client tree injector. Native
execution, publication and test execution remain separately coordinated with the
owner. Local runtime behavior is provisional; no native answers are claimed.

## Primary API and context

Official EDT archive SHA256:
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
The inspected pages are under
`catalog63/catalog578/catalog2125/{HTTPConnection,HTTPRequest,HTTPResponse}`
and `catalog2/catalog2088/ByteOrderMarkUse` in SyntaxHelperContext.

Synchronous Get/Post/Put/Patch/Delete/Head/CallHTTPMethod pages document server
and external-connection availability; do not infer their availability in a
managed client from the availability of request/response constructors. The host
must record actual server execution context and platform version separately.
`HTTPRequest.GetBodyAsStream` is documented as a writable request-body stream;
`HTTPResponse.GetBodyAsStream` as a readable response-body stream. The packet
observes ordinary writes and resulting body relations, not just method presence.

`SetBodyFromString(text[, encoding, ByteOrderMarkUse])` does not automatically set
Content-Type. Default encoding is UTF-8; the BOM enum offers Auto, Use, DontUse.
The explicit-endian UTF-16LE/BE Auto behavior differs from generic UTF-16 and is
observed rather than guessed. Request file-backed bodies and response bodies
written to an output file expose filename relations instead of assumed in-memory
bodies. Paths themselves never enter output.

## Closed fixture route table

The owner provides the HTTP server; this packet does not create a server or open
any external endpoint. The only connection host is the literal `127.0.0.1`, with a
supplied integer port in 1024–65535 and a finite ten-second connection timeout.
No credentials, proxy, TLS or OS authentication are supplied.

| Method / exact target | Fixed response |
| --- | --- |
| GET `/text` | 200, UTF-8 `я😀`, matching charset |
| GET `/latin` | 200, windows-1251 bytes for `Привет`, matching charset |
| GET `/binary` | 200, exact bytes `00 ff 41` |
| GET `/empty` | 204, no body |
| GET `/missing` | 404, ASCII `missing` |
| GET `/headers` | 200, ASCII `ok`, `X-Fixture: owned`, duplicate `X-Dup: a` and `X-Dup: b` |
| GET `/query?a=1` | 200, ASCII `query` |
| HEAD `/text` | 200, same representation headers, no transmitted body |
| POST/PUT/PATCH/DELETE `/echo` | 200, exact request bytes, `X-Method` equal to the fixed verb |
| OPTIONS `/verbs` | 200, ASCII `OPTIONS` |
| GET `/redirect` | 302, ASCII `redirect`, `Location: /text` |

The fixture supplies bounded Content-Length and Content-Type and closes each
connection. Echo responses use application/octet-stream; the Unicode POST reads
with explicit UTF-8. There are no unrestricted routes, arbitrary addresses or
DNS requests. The redirect target remains within the same owned loopback server:
its returned status/body reveal native automatic behavior. The packet implements
no manual redirect-follow. The fixed returned status/body and bounded total
request count are retained; there is no raw request log or general redirect
policy claim. A native follow is not silently normalized into local no-follow.

## Forty observations

| Cases | Coverage |
| --- | --- |
| 1–4 | Connection properties, request defaults, constructor-header alias relation, resource-address mutation |
| 5–7 | Unset string/binary/file body distinctions |
| 8–13 | Default string/Unicode and explicit UTF-8/UTF-16LE/UTF-16BE/windows-1251 encodings, BOM choices |
| 14–18 | Empty string, exact binary data, body replacement, header mutation, request stream write/body relation |
| 19–28 | Response type/status, text/binary/charset, explicit decoding, empty and 404 response, duplicate headers, query and HEAD |
| 29–34 | POST/PUT/PATCH/DELETE/OPTIONS and same-fixture redirect behavior |
| 35–36 | Response stream read/capabilities and independent-versus-shared cursor relation |
| 37–40 | File-backed request getters/send, GET/POST output-file bytes and in-memory/filename relations |

All data are fixed public training values. Each file case refuses existing
`http-in.bin` or `http-out.bin`, writes only these exact names under the supplied
owned root, and removes only these exact files on success or error. It never
recursively deletes the root or unrelated children. The host must verify the
root's ownership, absence of symlink substitutions, pre/post fixture contents,
and final cleanup. This is an isolated fixture, not a filesystem operation on
user data.

## Source and wire contract

Source SHA256:
`83ed3c4e5263580df0b30c2bd3b7f44d602e913ee79ee47eaa4cd623de6f3702`.
Source is 6785 UTF-8 bytes under the unchanged 8192-byte packet bound. Supplied
port/root invocation material must be separately source-bound and validated by
the owner; it must not overwrite this public source identity.

The contract `native_1c_http_family_contract.py` validates exactly two observer
controls and forty ordered `HT-01`–`HT-40` records. Each successful result is a
string of at most 40 UTF-16 units encoded using lowercase four-digit hex. Empty,
NBSP, quote, semicolon and astral Unicode controls are explicit. Maximum complete
output is 7130 bytes under the unchanged 8192-byte output bound. Fixed
`action-error` and `observer-error` tokens never expose exception text. Acceptance
requires all forty ordinary actions and observer controls. Valid framing alone
is not successful measurement; no expected native semantic answers are embedded
in the wire grammar.

`!todo`: async operations, general redirects, external hosts, auth/TLS/proxy,
malformed protocol inputs, connection races and exotic encodings remain outside
this packet. No permissions, network mode, environment override, native session
count or CI trigger changes are introduced. Existing Docker network isolation
remains unchanged; the owner coordinates one owned loopback fixture inside the
approved training session.

## First native attempt: failed owned fixture cleanup

PR193 initial source completed the fixed observer with verified source/module,
entered/completed markers, 18 loopback requests, a quiet native process and a
stopped fixture server. The owned fixture directory was not empty, so the
producer correctly refused output export and parity. Raw forty observations
were not retained; this does **not** establish forty successful API calls or
a particular leftover filename. The initial failure remains preserved privately.

The next source revision adds only a failed-only inventory projection: up to
32 entry/kind counts, a two-bit exact known-file presence mask, and a truncation
flag. Unknown names, paths, contents and error text never leave the container.
No unknown file is deleted and no cleanup or acceptance condition is bypassed.
