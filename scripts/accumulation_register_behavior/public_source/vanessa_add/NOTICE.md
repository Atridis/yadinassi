# Native XML sources and modified acquisition fixture

The two XML files in this directory are unmodified Source Code Forms from
vanessa-opensource/add and its contributors, at commit
`2deeed6636dfbb84f42ae625fd40c8ab662bb64e`:

- [РегистрНакопленияОстатки.xml](https://github.com/vanessa-opensource/add/blob/2deeed6636dfbb84f42ae625fd40c8ab662bb64e/lib/CF/83xdd/AccumulationRegisters/РегистрНакопленияОстатки.xml)
- [РегистрНакопления2.xml](https://github.com/vanessa-opensource/add/blob/2deeed6636dfbb84f42ae625fd40c8ab662bb64e/lib/CF/83xdd/AccumulationRegisters/РегистрНакопления2.xml)

They retain the original UTF-8 BOM, schema version 2.4, names, IDs and content.
`SOURCE.json` records the upstream commit, Git blobs, byte counts, SHA-256 pins,
license and precise derivation changes. No binary configuration, module or form
has been copied.

`../../AccumulationRegister.xml` is a **modified MPL-2.0 derivative**, not a
newly authored independent declaration. Its complete header, standard attribute
descriptors and Resource/Dimension wrappers come from the first file. Only the
Attribute wrapper comes from the second file. `../../native_source.py` reproduces
the reviewed substitutions: original owned names/identities, scalar field types,
empty synonyms and the intended command/totals-splitting controls. No external
catalog-reference dimension from the second source is installed. The unmodified
upstream files and derivation tool are source-review inputs only, not mounted
native input or an extension of any runtime metadata grant.

This Source Code Form is subject to the terms of the Mozilla Public License,
v. 2.0. The complete upstream license is included in `LICENSE`. If a copy of the
MPL was not distributed with this file, you can obtain one at
https://mozilla.org/MPL/2.0/.

The repository's MIT license does not replace the MPL-2.0 license of these XML
sources or their modified XML derivative. The owned document, handler and
sixteen-observation source are unchanged. This fixture is acquisition input,
not accepted native evidence or runtime parity.
