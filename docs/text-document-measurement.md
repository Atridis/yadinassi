# TextDocument: initial in-memory measurement plan (historical)

This document records the **measurement-only** revision `72dad51`, not the
current runtime status. Its native run obtained all 44 observations and failed
semantic comparison because that revision intentionally lacked TextDocument.
The later bounded implementation and exact evidence are described in
[text-document-native-alignment.md](text-document-native-alignment.md). That
measurement failure is not acceptance; a fresh complete native gate is required.

## Why this slice

`ТекстовыйДокумент / TextDocument` is a new standalone family for assembling,
inspecting and editing multiline text. It adds useful language breadth without
coupling the language track to database metadata, filesystem access or UI.
Official 1C educational material demonstrates its constructor, `LineCount`,
`GetLine` and `AddLine`:

- [1Ci: reading and importing CSV files](https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Development/Misc/Reading_and_Importing_CSV_Files_in_1C_Enterprise/).
- [1C Skills Hub: writing TXT and CSV](https://skillshub.1c-dn.com/courses/course-v1%3A1C%2BWwLF%2B2025_T1/courseware/6f81ed4446334a359dd64032a4e261ad/c623fe8bd3e24bf8ba17d9545a9b83f5/1?activate_block_id=block-v1%3A1C%2BWwLF%2B2025_T1%2Btype%40vertical%2Bblock%40e91319a6b06845cbba79de9837ed9294).

These examples are not evidence of newline normalization, empty/trailing-line
semantics, invalid indices or every mutator signature. Those are questions for
this native checkpoint. No third-party syntax mirror is treated as authoritative.

## Intended runtime scope after measurement

A zero-argument constructor and explicit RU/EN methods:

- `УстановитьТекст / SetText`, `ПолучитьТекст / GetText`;
- `КоличествоСтрок / LineCount`, `ПолучитьСтроку / GetLine`;
- `ДобавитьСтроку / AddLine`, `ВставитьСтроку / InsertLine`,
  `ЗаменитьСтроку / ReplaceLine`, `УдалитьСтроку / DeleteLine`, `Очистить / Clear`;
- `Тип / Type` and `ТипЗнч / TypeOf`; object/type displays only as observed.

No `Read`/`Write`, filesystem calls, streams, encoding selection, UI, async API,
serialization, cross-context transport, typed descriptors/cells or reflection.
Unobserved coercions, optional arguments and index behavior remain unsupported,
not guessed platform rules. Resource limits will be explicit Yadinassi policies,
not claims about native platform limits.

## Native observation route

The new fixed probes are appended to the existing values scenario, with helper
routines inserted before its executable body. Each probe dynamically executes
its own setup and operation. Setup failure is distinct from operation failure;
post-operation state is observed even after a caught operation error. Projections
are deterministic and bounded, with lossless UTF-16 code-unit representations
for text/newline content. No random identifiers, paths, native exceptions or
external resources are emitted.

The native server EPF and managed-thick-client adapter execute the entire exact
staged source. There is no added tolerance, skipped suffix or interpreter-derived
golden. The same-repository owner PR native route is unchanged. A rejected
comparison can provide concrete observations only after its runtime/source/input
identity, roundtrip and finite output evidence have been audited. A corrected
runtime then requires a new, fully successful current-head native run.

## Source and transport invariants

- Existing values441 statements and expressions remain byte-identical. An exact
  source-only inverse reconstructs their complete original source and adapters.
- The next existing UUID inverse reconstructs values402; earlier Windows replay
  continues to execute its full original source against immutable output bytes.
- Neither values441 nor values402 is admitted by the current production adapter.
  Historical replay is isolated test code, not a live source substitution.
- Runtime source inventory remains 62 because this phase adds no runtime module.
- All six scenarios, existing Map exceptions, output/private envelope/marker caps,
  permissions, images, workflow triggers, timeouts and historical fixtures remain
  unchanged. The current values source/hash/line count/message count are re-pinned
  together, with independent negative tests.

## Runtime implementation plan

After authenticated native evidence, implement one explicit `BSLTextDocument`
object module, registering its constructor and type identity through the existing
whitelists. Select the internal line representation from actual measured
empty/trailing/newline behavior, not Python `splitlines()` defaults. Mutation
preflight must check exact supported input types and resource budgets before
changing state. Use bounded integer checks before converting large Decimal
indices. Keep UTF-16 string behavior consistent with the existing string module.

Unit tests will separate observed witness cases, generic bounded algorithm
extensions, and unsupported/local resource boundaries. Add packaged smoke for the
small useful API and tests showing `Read`/`Write`, codecs, descriptors and transport
remain closed. Then run all repository checks, build and binary smoke, exact
historical replay, and fresh native/4-OS CI. Do not claim completion at the first
measurement capture.
