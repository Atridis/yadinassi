# Accumulation metadata loader control

This is exactly one diagnostic case, not a replacement for the 16-case
accumulation-register acquisition and not native semantic or runtime parity.
No existing acquisition inputs, workflow, or runtime behavior are changed.
The dedicated temporary workflow is owner-only and restricted to the exact
Draft branch codex/accumulation-loader-control. Never mark this PR ready or
merge it; close it after the diagnostic result is verified.

After the existing approved disposable NativeSmoke bootstrap prerequisite:

1. Dump the fresh bootstrap configuration.
2. Apply the same source-owned Document and AccumulationRegister declarations,
   preserving UUIDs, generated types, properties, recorder link and existing
   rights. Deterministically remove all register Resource/Attribute/Dimension
   children and the document ObjectModule.bsl. No other changes or extra grants.
3. Run LoadConfigFromFiles once and, only on success, DumpConfigToFiles once.
4. Verify the exact file set and strict semantic XML signatures, including all
   authored properties, generated type IDs and recorder link. Preserve bootstrap
   modules and rights. ConfigDumpInfo.xml remains export bookkeeping only.

There is no UpdateDBCfg after this control's load and no post-load Enterprise,
observer, movement, query, posting, or balance execution. The known bootstrap
itself retains its existing setup and simple-smoke prerequisite; it is not a
second accumulation control. A successful control proves only that this exact
reduced source loaded and survived the strict redump, not that fields or
accumulation behavior work. A Designer-added property is not silently ignored.

The profile, transport and report schemas are loader-control-specific. All
native measurement, semantic measurement and runtime parity acceptance flags
are always false, including successful runs. Only diagnostic_control_passed may
be true. The CLI exit status describes this diagnostic, never parity acceptance.
No raw native console text, native XML, database, modules, or observer output is
exported. Failure diagnostics use bounded fixed vocabulary, exit status and
boolean source-presence facts only.

The host retains the same pinned image, nonce, source inventory, read-only
mount, nonroot/no-network constraints, bounded process budget, private session
bus, process census, registry credential removal, ownership-checked container
cleanup and private-payload cleanup. Source and host provenance are rechecked
before the public summary is emitted. There is no artifact export option. The temporary workflow uploads only the
bounded diagnostic summary. Execution or publication requires exact-count
notification by the coordinator; this implementation does not run either.
