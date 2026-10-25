# UUID scalar: local provisional candidate, not native-verified

The scalar prototype is isolated from the active ValueTree PR and based on the
`ci-build-dedup-main-v1` anticipated source snapshot. In this combined local candidate,
independent native probes/adapters are integrated as described in
[the combined-source contract](uuid-combined-provisional.md); fixtures, workflow
admission, limits and DB oracle operations remain unchanged.
No native execution or public publication has accepted these semantics.

## Bounded candidate policy

`УникальныйИдентификатор` / `UUID` is an immutable exact-type scalar. A single
string argument must contain exactly 36 ASCII characters in 8-4-4-4-12 hex
form; ASCII upper case is accepted and the display is lower case. Spaces,
braces, compact/URN forms, non-string inputs, explicit Undefined and extra
arguments are rejected. A private omitted sentinel distinguishes no argument
from explicit Undefined. Parsing never delegates to Python's permissive UUID
parser. These bounds are local provisional choices, not exhaustive native rules.

No-argument generation uses 16 random bytes with local RFC-style v4/variant bits.
This is explicitly NOT a claim about the version or entropy semantics of native
1C's default generator. Generated raw values must never enter expected/native
comparison output; only stable shape/type/round-trip/nonzero projections may.

Equality and Map/FixedMap keys use canonical scalar content, not object identity;
a UUID is distinct from its text. Zero is provisionally not filled, other values
are filled. Type/TypeOf expose the Russian name and UUID, not an assumed
UniqueIdentifier alias. Russian type presentation currently uses the unspaced
name; its exact native display remains a measurement question.

TypeDescription (including singleton/default/AdjustValue and typed cells),
internal and XML codecs, UUID ordering, extended/versioned constructors,
namespace UUIDs, database references and cross-context transport are deferred.
The codec partition explicitly refuses both the value and its Type record;
there are no invented GUIDs, Pattern tags or conversion rules.

## Required independent native observations

Use fixed zero, `01234567-89ab-4cde-8f01-23456789abcd`, and the same value ending
in `abce`. Measure constructor/Type aliases (UUID and UniqueIdentifier separately),
type presentation, uppercase canonicalization, invalid grammar/arity/Undefined,
value equality vs string, Map replacement/count/delete and FixedMap lookup,
zero/nonzero filled, descriptor singleton default/explicit Undefined/UUID/string
adjustment and typed-cell default. Do not infer composite ordering.

For generation measure only type, shape, nonzero, parse(String(x)) equality and
separate-generations inequality; do not print random UUIDs. Generator version
requires its own bounded projection and evidence before claiming native parity.
Codecs remain deferred unless independently observed. Every failure gets its own
stable error marker, not locale-dependent exception text. Local unit outputs are
not native expectations or compatibility evidence.

Official 1C examples establish the existence of the no-argument constructor:
https://v8.1c.ru/obuchenie-programmistov/primery-razrabotki/forma/kak_otkryt_neskolko_ekzemplyarov_odnoy_formy.htm
Official English guidance uses UUID() for reference identifiers and distinguishes
internal serialization from string conversion:
https://1c-dn.com/library/serialization_usage_specifics/
These references do not settle the detailed candidate behavior above.

## Regression boundaries

Focused candidate tests cover parser bounds/hostile subclasses, immutability,
static/dynamic constructors, collection lookup, scalar/map identity, filled,
codec partition and explicit deferred surfaces. The shared packaged type-smoke
program adds fixed UUID positives and retains UnknownTree as a negative control.
Its existing tree tail stays intact. No random values enter golden smoke output.
The scalar runtime alone adds no native input changes. The combined independent
probe contract explicitly re-pins values441; historical native fixture bytes
remain unchanged.
