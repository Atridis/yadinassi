# Owned configuration XDTO packages

An explicit configuration module application can load declared `XDTOPackage`
metadata and its UTF-8 `XDTOPackages/Name/Ext/Package.bin` source. The suffix is
Designer interchange naming, not an arbitrary native binary reader. Files are
retained exactly; declaration names, metadata UUIDs and namespaces must match.
Inactive import does not grant application execution or database/UI support.

The bounded package model supports ordinary object types, ordered properties,
required/optional cardinalities, repeated properties, nillable values and direct
atomic aliases of the existing built-in scalar types. Every namespace dependency
must be declared and supplied in the same configuration. There is no network
resolver, schema location fetching, general XSD inheritance/facet support or
recursive object/import graph. Eight packages, 128 total factory types, 256
properties per object, depth 32 and 256 KiB combined package XML are local safety
limits, not measured native maxima.

The application's root, common modules and enrolled child interpreters share
one factory. A separate application owns a distinct factory; foreign types and
values do not gain compatibility merely by matching names. Scalar aliases retain
name, namespace and BaseType. The measured `base.IsDescendant(alias)` result is
true; the reverse is false. Assigning a built-in scalar value to an alias property
creates the declared alias. Assigning an alias value to its base property retains
the alias identity. Serialization of that retained-derived property is explicitly
refused before destination mutation until xsi:type / JSON type assignment has a
supported contract. Ordinary declared alias properties have XML/JSON roundtrip
coverage.

Native runs [43086017286](https://github.com/Atridis/yadinassi/actions/runs/43086017286)
and [43089477510](https://github.com/Atridis/yadinassi/actions/runs/43089477510)
record twelve observations each on Linux 8.3.27.1508. Immutable fixtures preserve
the source-bound report, actual output and provenance. They establish the observed
contracts, not a full configuration or native serialization compatibility claim.
This runtime was reconstructed after workspace loss; earlier test results do not
certify these new source bytes. Its local regression gates must pass independently.
