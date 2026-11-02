# Ordinary XDTO factory workflow measurement

One closed `xdto-family-v1` packet (`xdto_family`) observes 40 ordinary cases.
Initial native acquisition contains forty successful actions on managed client
and server; local runtime and synthetic wire tests are not native goldens.
The immutable minimal capture is under tests/fixtures/xdto_family/native-initial.

## Primary source

Verified official EDT archive SHA256:
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
Pages: `nl/en/html/SyntaxHelperContext/objects/catalog63/catalog1015/` for
XDTOFactory, XDTODataObject, XDTODataValue, XDTOList, XDTOObjectType,
XDTOValueType, XDTOProperty, XDTOPropertyCollection, XDTOPackage and
XDTOPackageCollection; global `CreateXDTOFactory3409.html`.
The APIs are documented since 8.1, factory JSON since 8.3.7, qualification flags
since 8.3.8, and item `Factory()` since 8.3.22. Intended platform target is
8.3.27.1508; actual acquisition version and contexts must be retained separately.

`CreateXDTOFactory(path)` accepts an XML schema filename. `Factory.Type(uri,name)`
resolves types. `Create(valueType,value)` creates typed scalars;
`Create(objectType)` creates objects. Value wrappers expose `Value` and
`LexicalValue`; object and value `Type()`/`Factory()` are methods, while an object
type's `Properties` is a property. Object `Properties()` is a method. Collections
use documented `Count`/`Get`, not DOM-style `Item`. List mutators' returned typed
items are observed rather than assumed to match Python list behavior.

## Owned schema and case map

The single fixed nonsecret XSD defines namespace `urn:packet`, named `Child`
with required string `code`, named `Box` with optional scalar `title`, `qty`,
`flag`, repeated `item:Child` and `tag:string`, optional string attribute `id`,
and global element `box`. Sequence order is explicit. There are no imports,
includes, DTDs, recursion, mixed content, choice or inheritance. The XML Schema
namespace URI is an identifier, not a retrieval endpoint.

| Cases | Coverage |
| --- | --- |
| 1–8 | Type/package/root-property metadata; ordered/sequenced/open/mixed/abstract flags; property bounds/form/qualification/owner |
| 9–16 | String and astral Unicode, boolean, decimal, integer, date/dateTime lexical conversion, empty string and factory identity |
| 17–20 | Dynamic property access, Get/GetXDTO/Set, unset versus empty, optional fields and attributes |
| 21–26 | Repeated scalar list Add/Insert/Set/Delete/Clear/Unset, typed return values and list-view behavior |
| 27–28 | Nested object ownership, owning property, object type/factory and root owner |
| 29–32 | XML roundtrip: escaping/Unicode/attribute, numbers/booleans, repeated scalar and nested object |
| 33–36 | JSON roundtrip: Unicode/typed object, numbers/booleans/attribute, repeated scalar and nested object |
| 37–40 | Omitted XML values, present-empty JSON value, valid object/scalar validation and public type identities |

The schema is written once to a freshly generated, collision-checked owned root,
then the factory is created and the exact schema file removed. Only an empty
owned directory is removed. The remaining observations use that in-memory
factory, thereby also exercising independence from the deleted source file.
Factory setup failure produces fixed action-error records through the ordinary
observer; it cannot export raw errors or paths. Tests inject factory failure,
an existing root and an unexpected child; no recursive cleanup is allowed.

XML and JSON roundtrips pass explicit expected XDTO types. They inspect semantic
content, not platform-specific namespace prefixes, indentation or property order.
Callbacks and arbitrary expression evaluation are outside the packet. Simple
property-name paths are used; general XPath is not introduced.

## Wire and source identity

Source SHA256:
`c317011c5fb651fe313eed07cf9587ab14e3f474857ef54d3646a9ae52e5376a`.
Source: 7621 UTF-8 bytes, below unchanged 8192-byte source limit.
Two observer controls plus forty ordered `XF-01`–`XF-40` records encode at most
40 UTF-16 units per result using lowercase four-digit hex. Maximum complete
output is 7130 bytes below unchanged 8192-byte output limit. Action-error and
observer-error are distinct bounded tokens. Acceptance requires all forty
successful actions and exact observer controls; syntactically valid unavailable
records are not semantic acceptance. No expected native answers are encoded in
the wire contract.

`!todo`: advanced XSD, imports, external entities, network resources, recursive
models, inheritance, mixed/choice content, serializer mappings, callbacks and
arbitrary XPath are deferred. No credentials, permissions, environment overrides,
new CI triggers or host timeout changes are requested. The single closed profile is integrated into the existing native workflow;
actual acquisition is pending. No public capture is yet a native golden.

## Initial measured calibration

The original40 capture is retained byte-for-byte (SHA256
`6646c0e7d22b770b580fb19a037b2612c54e2364224b078cbe4a767ef8697a16`).
It measured two differences: case05 metadata index0 is attribute `id`, not the
first sequence element; case25 empty-list `IsSet` is false. All other38
observations matched. The runtime now replays the entire capture exactly; a
fresh native run on the corrected runtime is still required. Packet source and
all resource caps are unchanged.

Private acquisition audit verified authenticated archive digests, exact source,
generated server/client modules, runtime manifest and cleanup. The outer
transport envelope is not archived: strict validation was rerun on an envelope
reconstructed from the authenticated summary/output. The public minimal fixture
contains only fixed source, bounded observations and source/output digests; no
nonce, installation data, credentials, run paths or raw exceptions.
