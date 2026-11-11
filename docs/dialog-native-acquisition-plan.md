# Owned asynchronous dialog acquisition plan

Status: source candidate only. Nothing here is measured native parity.

## API contract to verify

Native names are `ShowQueryBox` / `ПоказатьВопрос` and `ShowMessageBox` /
`ПоказатьПредупреждение`. `ShowQuestion` and `ShowWarning` are not the native
English aliases and must not silently be presented as such.

Question positional arguments: completion description, text, buttons, optional
seconds, default button, title, timeout button. Question completion accepts
`(Result, AdditionalParameters)`. Warning arguments: completion description
(optional), text, optional seconds, title. Warning completion accepts only
`(AdditionalParameters)`; do not inject an Undefined result argument.

References inspected during design:
- https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/
- https://forum-baza.ru/index.php?topic=48618.0
- https://forum-baza.ru/index.php?topic=48620.0
- https://github.com/1c-syntax/1c-syntax/blob/master/1c.YAML-tmLanguage

## Small closed measurement

Six real native completion observations, not calls to callbacks from the driver:
1. OK question, explicit timeout return OK.
2. OKCancel question, default OK but timeout return Cancel.
3. YesNo question, default Yes but timeout return No.
4. YesNoCancel question, default Yes but timeout return Cancel.
5. Warning, timeout closes native warning, one-argument callback.
6. YesNo question with timeout button omitted; observe returned finite code.

One-second native timeout is an input, not a wall-clock timing assertion.
Publish only ordinal, callback count, finite return-code label, captured
AdditionalParameters identity flag and finite event order. At most six records,
4096 bytes and 120 seconds total. Explicit client module variables are required.
The runner must impose a bounded idle watchdog, produce entered/completed markers,
and continue outside completion, not open a new dialog reentrantly from it.
The candidate BSL is intentionally not yet a runnable acquisition route.

Use a new owned one-form EPF, pinned source hashes, secure bounded reads of known
executable modules, EPF before/after hash, existing network-none readonly sandbox
and process/cleanup guards. Designer XML serializer equivalence is not a gate.
Do not modify or reuse the protected form-results oracle as new evidence.

## Boundaries

The existing runner provides a private display but no reviewed controlled GUI
click/keyboard route. This workspace has no xdotool or wmctrl executable. That
is not proof of what the pinned image contains, and no installation is proposed.
Timeout completion can be measured without GUI automation. Button clicking,
window-close, Escape and Enter/default-button semantics cannot be inferred from
these observations. Do not claim them or emulate native input by directly calling
QuestionDone/WarningDone. A host subset may reject timeout even when timeout is
used solely to obtain real native callbacks for signature/type/identity evidence.

Before running anything: finalize separate route and offline contracts, collect
exact test count, obtain parent review and notification. Proposed native count
is six; no tests, native execution, browser, installation or CI has run.
