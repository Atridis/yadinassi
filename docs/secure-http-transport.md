# Verified HTTPS, explicit authentication and proxy transport

This is one extension of the existing ordinary HTTP request/response workflow,
not a new HTTP stack. It adds four BSL types, verified HTTPS, constructor Basic
credentials, explicit Authorization headers, and explicit HTTP proxies for
ordinary HTTP and HTTPS CONNECT. Existing methods, body/encoding/stream/file
operations, status responses and resource limits remain in use.

This is a **documented local subset, not native TLS/auth/proxy parity**. The old
forty-record native HTTP capture contains no TLS, credentials or proxy. No old
capture, source digest, comparison exception or integration scenario is changed
or relabeled as evidence for these additions.

## Ordinary API workflow

```bsl
Authorities = New OSCertificationAuthorityCertificates;
Secure = New OpenSSLSecureConnection(, Authorities);
Connection = New HTTPConnection("api.example.test", , , , , 30, Secure);
Headers = New Map;
Headers.Insert("Accept", "application/json");
Request = New HTTPRequest("/v1/items", Headers);
Response = Connection.Get(Request);
Message(Response.StatusCode);
Message(Response.GetBodyAsString());
```

The example is illustrative. The interpreter does not connect until an HTTP
method is called. Credentials in runnable examples should come from the host or
application, never from checked-in source.

Russian/English type aliases:

- `ЗащищенноеСоединениеOpenSSL / OpenSSLSecureConnection(ClientCertificate,
  CertificationAuthorityCertificates)`: client certificate must be Undefined;
  the second argument must explicitly specify one of the following CA types.
  The two certificate properties are readonly.
- `СертификатыУдостоверяющихЦентровОС / OSCertificationAuthorityCertificates()`:
  Windows CA/ROOT stores and compiled-in OpenSSL server-auth trust paths. This is an explicit
  request to use those sources, not a bundled portable CA set. Availability and
  roots differ across hosts. No certificate is installed in the OS.
- `СертификатыУдостоверяющихЦентровФайл /
  FileCertificationAuthorityCertificates(FileName [, Password])`: snapshots and
  validates a certificate-only PEM file through the existing regular-file
  boundary, with a 1 MiB input cap. Empty/Undefined password is accepted;
  encrypted stores, PKCS#12, private keys and non-certificate PEM content are
  refused. Changes to the file after construction do not change its trust set.
- `ИнтернетПрокси / InternetProxy([DefaultProxy])`: omitted/Undefined/False means
  empty explicit settings. True, OS discovery and environment proxy discovery
  are refused. `Set / Установить(Protocol, Server [, Port [, User [, Password
  [, UseOSAuthentication]]]])` supports `http` and `https`, independently.
  Default proxy port is 80. `Server`, `Port`, `User`, `Password` and
  `UseOSAuthentication` (and their Russian aliases) inspect a protocol's setting.
  A missing protocol returns empty strings, port 0 and False. OS authentication
  must be omitted/Undefined/False. Bypass lists and FTP/SOCKS are not implemented.

These types participate in Type/TypeOf and ordinary dynamic New. They do not
acquire internal codecs, TypeDescription support, cross-context transfer, Python
reflection or arbitrary host API access.

## TLS policy

HTTPS is selected only by an explicit OpenSSLSecureConnection. Default port is
443; an explicit valid port wins. Without a secure object the ordinary HTTP
port default remains 80. A host is a DNS name or IPv4/IPv6 literal, without a
scheme/path/credentials or embedded port. DNS names are converted to IDNA;
bracketed IPv6 is accepted, zone identifiers are not.

Every HTTPS connection verifies the certificate chain, validity and hostname,
with TLS 1.2 as the minimum. There is no no-verify switch, plaintext fallback,
client certificate selection, revocation-policy selector or automatic retry.
Native OpenSSL construction without CA sources can disable verification; this
implementation explicitly rejects that form instead of silently emulating it.
No TLS session keys are logged through SSLKEYLOGFILE. SSL_CERT_FILE and
SSL_CERT_DIR environment overrides are ignored; selecting OS trust does not
silently select an environment-only trust bundle. Host root configuration and
compiled-in paths still differ across platforms.

File CA trust is exclusive to the supplied PEM certificates; it is not silently
combined with OS trust. No private key or credential is read while constructing
these CA objects. Client-certificate/mTLS support remains `!todo`.

## Authentication and routing

HTTPConnection's explicit User/Password arguments now generate preemptive Basic
Authorization. They are bounded strings (4096 UTF-8 bytes each), username cannot
contain `:`, control characters are refused, and a nonempty password requires a
username. Non-ASCII credentials use UTF-8 as a local policy. This is not a claim
about every native challenge/charset variant. User and Password properties expose
the values supplied by the application, as ordinary connection settings.

An application may instead supply an explicit Authorization request header,
including Bearer. It cannot combine that header with constructor credentials.
No token acquisition, credential store, challenge negotiation, NTLM/Kerberos,
OS authentication or automatic refresh is added. Basic credentials on explicitly
chosen plaintext HTTP are plaintext-equivalent on the wire: use verified HTTPS
for real credentials. Diagnostics do not include authentication values.

Proxy configuration is selected from the request's protocol at each call. A
proxy object with no matching setting leaves that protocol direct; a failed
configured proxy is never retried directly. The call snapshots its chosen
setting, so later changes do not reroute an in-flight request.

- Plain HTTP sends absolute-form targets to the explicitly configured HTTP proxy.
  The origin Host remains the target authority. Explicit proxy credentials are
  sent as Proxy-Authorization only on that proxy hop.
- HTTPS first sends CONNECT to the explicit HTTP proxy, then verifies TLS against
  the **origin** hostname inside the tunnel. CONNECT contains proxy credentials
  only. Origin headers, credentials and body are sent only after CONNECT and
  certificate verification both succeed. Proxy credentials are not copied to the
  tunneled origin request.
- A user-supplied Proxy-Authorization or Host header is rejected. Request framing
  and other existing guarded headers retain their restrictions. Generated auth
  headers count against the existing aggregate header budget.

There is no TLS-to-proxy support. Consequently proxy Basic authentication is
plaintext-equivalent to the proxy even when the origin uses HTTPS. The caller
must explicitly choose that proxy and its credentials. No proxy configuration,
credentials, browser cookies or redirects are discovered automatically.

## Lifetimes, limits and failure paths

The existing finite post-DNS socket deadline includes connect attempts, CONNECT,
TLS handshake, request send and response reads. Timeout 0 remains a local finite
30-second budget, not native unlimited waiting. OS DNS resolution still lies
outside that deadline. Each method owns and closes one connection; there is no
pool or shared TLS socket. TLS/CONNECT failures close their socket.

Body limits remain 8 MiB, response/request header admission 100 fields/64 KiB,
and origin-relative resource addresses 8192 encoded bytes. CONNECT headers have
bounded parsing and cannot introduce a response body before the TLS handshake.
Responses such as 401, 407 and 302 are ordinary responses when received from the
HTTP endpoint; a non-200 CONNECT response instead fails the tunnel. Redirects
are not followed, so credentials are never automatically sent to a new origin.

Response output files are opened only after the complete bounded response has
been accepted. A trust, hostname, proxy or transport failure preserves an old
output file and does not create a new one. Later disk-write failures retain the
existing nontransactional file-write policy.

## Verification and references

The focused suite contains 48 tests: 17 existing HTTP tests and 31 added security
and transport tests. It covers all seven HTTP verbs over actual local TLS,
CA snapshots, invalid trust/name failures, Basic and Bearer, direct and proxy
routes, CONNECT, separated auth headers, binary/file workflows, optional holes,
Type/TypeOf, resource caps and explicit rejection of unsupported operations.

TLS loopback tests generate ephemeral certificates and keys in a temporary
directory using the installed `openssl` executable. No keys are checked in or
uploaded. Those 13 tests are skipped where that executable is unavailable;
the 18 security-object tests still run there. Such a skip is not TLS execution
coverage and must be disclosed with platform results. No external host, real
credential, certificate-store change or new dependency is used by these tests.

API references, not execution evidence:

- [InternetProxy API](https://yellow-erp.com/help/sh/objects/catalog63/catalog578/InternetProxy.html/).
- [File CA constructor](https://forum-baza.ru/index.php?topic=54879.0).
- [OpenSSL certificate constructor](https://forum-baza.ru/index.php?topic=54885.0).
- [Cross-OS CA support](https://1c-dn.com/library/v8update_461169075_new_functionality_and_changes/).
- [1C secure-channel overview](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Administrator_Guides/1C_Enterprise_8.3.27_Administrator_Guide/Chapter_8.Setting_up_web_services_for_1C_Enterprise/8.9._Safety_while_using_Internet_services/8.9.2._Operations_over_a_secure_channel/?language=en).

!todo: native TLS/auth/proxy calibration, client certificates and revocation,
challenge-based authentication, async operations, cancellable DNS, automatic
redirect policy, HTTPS proxies, proxy bypass rules and unusual coercions. These
are explicit boundaries, not prerequisites for the ordinary local workflow.
