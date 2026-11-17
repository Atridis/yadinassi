# Detached source metadata in standalone direct execution

This bounded capability is separate from database metadata and SourceApplication
execution. Passing a metadata root to a standalone interpreter grants no manager,
reference, database, module, source execution, or global `Metadata` authority.

## Supported slice

An exact, constructor-origin `SourceMetadataRoot` with untouched lazy caches can
be adopted on first use. Read-only operations include `Name`, declared file child
collections, collection `Count`, `Get`, `Find`, named/numeric indexing and
iteration. Returned objects and collections retain their canonical identity.
XML scalar properties, embedded child collections, `FullName`,
`FindByFullName`, and setters are outside this initial adapter.

The root owns its detached graph. It is not tied to a SourceApplication lifetime
or exclusively to one interpreter; the same canonical root can be read by
multiple standalone interpreters. Bound calls and iterators are valid only during
the execution that created them. They do not become persistent capabilities.

## Integrity and limits

Construction provenance, source bytes and inventory, canonical method/parser
bindings, and published lazy graph identities are checked before operations.
Only guarded canonical operations may extend the admitted caches. Prepopulated
roots at first admission and later native-host cache expansion are explicitly
unsupported by this slice, rather than silently adopted. Mutation or replacement
of already admitted objects, collections, XML cache nodes or links is rejected.

This is not a general Python sandbox. Existing trusted-host responsibilities and
source import resource limits remain in force. No VM fallback is introduced.
