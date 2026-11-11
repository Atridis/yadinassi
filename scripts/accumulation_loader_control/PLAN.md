# Full native declaration loader control, v2

Exactly one diagnostic case, not the original 16-case acquisition and not
semantic measurement or runtime parity. The previous stripped declaration
control still failed in LoadConfigFromFiles. This version tests one materially
different input: an entire native-produced public register declaration.

The dedicated workflow remains owner-only and restricted to the exact Draft
branch codex/accumulation-loader-control and existing PR #278. This temporary
diagnostic source is not intended for a Ready transition or merge.

After the unchanged approved disposable NativeSmoke bootstrap prerequisite:

1. Dump the fresh bootstrap configuration and prepare the original owned
   accumulation scaffold.
2. Replace its register with the complete byte-pinned public source from
   vanessa-opensource/add commit 2deeed6636dfbb84f42ae625fd40c8ab662bb64e.
   Keep its UTF-8 BOM, schema 2.4, Russian name, UUIDs, six generated types,
   five standard descriptors, decimal resource, string dimension and defaults.
   The exact source, attribution, provenance and full MPL-2.0 license are in
   public_source/vanessa_add. No binary configuration or module is included.
3. Make exactly three target-reference substitutions: the Configuration's
   AccumulationRegister child, the owned Document.RegisterRecords item and
   the narrow role object name. Preserve the owned Document's other bytes,
   omit its handler, and preserve all permissions and bootstrap modules.
4. Run LoadConfigFromFiles once, then DumpConfigToFiles once only on success.
   There is no post-load UpdateDBCfg, Enterprise, observer, movement, posting,
   query or balance execution. Bootstrap's existing simple smoke is only a
   prerequisite, not another accumulation control.
5. Verify the exact source file set and strict semantic XML signatures,
   including schema version, identities, generated types, all properties,
   standard descriptors, fields, recorder linkage and unchanged grants.
   Only ConfigDumpInfo.xml remains export bookkeeping.

A redump may upgrade native schema 2.4 to 2.20. The input must not be rewritten
and the verification gate must not normalize that difference. Bounded finite
input/redump schema facts distinguish this from a load failure. load_completed
and redump_verified remain separate; successful loading survives a subsequent
redump-verification failure in the diagnostic report.

The v2 profile and transport/report schemas distinguish this run from v1. All
native measurement, semantic measurement and runtime parity acceptance flags
are always false. Only diagnostic_control_passed may be true. Even success
proves only loading and verified redump of this exact source, not register
behavior. No raw native logs, XML, database, modules or outputs are exported.

The pinned image, source inventory, nonce, ownership checks, isolated mounts,
process limits and census, session bus, credential cleanup, container removal,
private-payload cleanup, provenance checks and workflow policy are unchanged.
The existing workflow uploads only a bounded JSON summary. Tests, native
execution and publication wait for the coordinator's exact-count notice.
