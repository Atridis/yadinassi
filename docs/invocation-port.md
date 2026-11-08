# Scalar client/server InvocationPort v0

This opt-in host API lets **client BSL call a server-only function and continue
with its returned value across a byte transport**. The default interpreter still
uses local logical activations, without a database, child process or network.
No new CLI option, renderer event or BSL global function is introduced.

The server compiles a trusted NoContext module. Host setup explicitly maps opaque
integer endpoints to selected routines. The client receives only trusted binding
descriptors: its BSL-visible alias, endpoint, required parameter names and whether
the routine returns a value. Installed client stubs have **empty bodies**. Server
source, its routine names, database context and runtime objects are not shipped
in requests or retained in client stubs.

```python
from yadinassi import Interpreter
from yadinassi.invocation import InvocationBinding, InvocationPort, InvocationServer

server = InvocationServer('''&AtServerNoContext
Function Calculate(Val Price, Val Quantity)
    Return Price * Quantity;
EndFunction''', {1: 'Calculate'})

client = Interpreter()
port = InvocationPort(server.exchange)  # An in-process byte adapter for embedding.
port.bind(client, InvocationBinding('ServerTotal', 1, ('Price', 'Quantity')))
client.execute('Message(ServerTotal(10.25, 2) + 0.50);')  # 21
```

`exchange` is the only transport interface: one bounded `bytes` request in, one
bounded `bytes` response out. A host can instead send those bytes to its explicitly
selected child/server process. `test_invocation_port` includes an actual separate
Python process: the client computes `ServerTotal(20.10) + 0.70 = 61`, while the
server independently loads the `Calculate` body and multiplies by three. That
test does not send BSL source, select a file through the wire or share an
interpreter object across the process boundary.

## First admitted slice

- Only prebound `&AtServerNoContext` / `&НаСервереБезКонтекста` functions and
  procedures, with at most 32 required **Val / Знач** parameters. A client alias
  can differ from the actual server routine name. Bindings cannot replace an
  existing client routine or built-in.
- String, exact Decimal, Boolean, Undefined, Null and known interior whole-second
  Date values. Decimal is tagged text, never a JSON float; Dates use exact ticks.
  The existing context-copy admission and bounded scalar codec both apply.
  Collections, references, fractional/boundary Dates, default parameters and
  non-Val copyout are explicitly outside this wire profile.
- Existing client argument evaluation applies: expressions run left to right
  once, named storage is read after argument effects, then the packet is admitted
  before transport. The entire returned value/message packet is validated before
  client output or dependent BSL resumes. Server `Message` output arrives before
  the client statement using the result.
- Each server call uses a fresh NoContext activation. Local server helpers stay
  server-side. Client module variables are inaccessible. A trusted host may bind
  `database_context` only to the server; there is no database-path request field.
  Source modules contain server NoContext routine declarations only, never
  executable module initialization or client bodies.
- Binding is currently for plain `Interpreter` embedding. FormSession requires
  the separate replicated-form-state/barrier work; this API does not silently
  route shared form objects or controls across a process boundary.

## Sequencing, failures and limits

The provisional `yadinassi-invocation/0` NDJSON envelope contains exactly
`protocol`, `id`, `endpoint`, `arguments`. Responses contain the same protocol and
ID, `status`, `messages`, and either `value` or a finite `reason`. Endpoints are
integers 1..64. IDs increase within one host-owned port/server pair; a replayed ID
does not execute the routine again. Each side admits at most 4,096 calls. There
is one active exchange, no parallel queue and no reentrant dispatch.

The shared bounded JSON codec rejects duplicate keys, nonfinite/floating-point
JSON numbers, malformed UTF-8 and oversized/deep frames. Frames are at most
131,072 bytes; strings at most 8,192 UTF-8 bytes. Server text output is limited to
64 messages of 1,024 UTF-8 bytes each. These are local transport limits, not 1C
platform limits. There is no serialization of Python objects, pickle or eval.

Server exceptions become a catchable finite `server_error`, with already emitted
messages. They **do not promise rollback of earlier server/database effects**.
Unsupported or unencodable return values produce `result_unavailable`, never a
fake successful return. If a response is lost, malformed, mismatched or cannot
be delivered to client output, the port locks with `outcome_unknown`; all later
calls on that port fail before dispatch. It never retries or automatically
reconnects. Host cancellation or interruption after an exchange starts also locks
the port, including cancellation during output delivery; the original cancellation
is re-raised unchanged. Cancellation during input admission before sending does
not lock an unused port. Establishing a new port is a host decision after reconciliation, not
a safe replay operation. The invocation ID is not a database operation identity.

The host adapter owns process lifetime and whole-exchange deadlines. This layer
does not start sockets, perform authentication, enforce a BSL execution deadline
or expose a remotely accessible service. A host must connect only to its intended
server. This is the first functional transport seam, not a network deployment,
authenticated module cache, exactly-once write protocol or native RPC parity claim.

## Verification

`PYTHONPATH=tests:scripts python -m unittest test_invocation_port -v` covers the
separate-process result, exact scalar values, call sequencing and replay,
argument ordering, source/body separation, nested server helpers, finite errors,
lost/corrupted replies and existing direct local execution. Existing context,
NoContext, scalar copyback and form tests remain regression gates. No native
fixture or integration scenario is changed by this host transport slice.
