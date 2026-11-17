# Direct HTTP/file protocol

Base593c1dbd native run44103604012 HTTP job134109996689 failed with empty host
output. Summary artifact14337411357 accepted native observations (1838bytes,
SHA256 d159e9a8b3a11329b453871870e44794478edd30a4ea4681ffa1e31ecb91d971).
The unchanged owned-loopback replay reproduced `constructor File` rejection.

The direct bridge now exposes a finite canonical constructor set: File,
BinaryData, BinaryDataBuffer, HTTPRequest and HTTPConnection. Only the two HTTP
constructors accept omitted optional arguments, as None; required first arguments
and unrelated constructor omissions still fail before argument effects. Canonical
factory identity is checked at binding and immediately after argument evaluation,
so an argument callback cannot substitute another implementation.

Exact HTTP/file/buffer/body-stream receivers use their existing public methods;
private Python attributes and subclasses remain excluded. File path/regular-file,
external-access, HTTP header/body/framing/timeout, credential and TLS checks remain
inside the existing implementations, unchanged. This slice neither adds TLS/proxy
constructors to direct nor claims TLS/client-context parity.

The HTTP header validator additionally accepts the exact direct Map representation,
using its typed entries under the same string/count/token/duplicate/size checks.
Headers keep caller Map identity, including mutations checked again at send time.
There is no conversion, snapshot or general equivalence between direct/canonical
Maps. Plain dicts and subclasses are rejected.

`replay.py` runs the original source against an owned loopback server and isolated
temporary files, and compares all40 observations plus two controls byte-for-byte
with the unchanged checked-in native fixture. That fixture hash also matches the
accepted current CI native output above. This is local replay against existing
native evidence, not a new1C execution or full-CI green claim. External hosts,
async, new TLS/proxy support and unrelated file/stream constructors remain outside
this iteration. Source-host and layout code was not changed.

Validation:107 selected tests PASS on Python3.12 normal and Python3.10 optimized,
including HTTP40, original client138 and CatalogQuery24 replays, constructor
admission, Execute and default direct controls. Independent30 optimized tests PASS;
review found a constructor implementation-mutation gap, now fixed and covered by
three pre-invocation rejection cases. No remaining review blockers.
