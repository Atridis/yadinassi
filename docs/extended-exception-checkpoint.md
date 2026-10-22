# Extended Raise and ErrorInfo source checkpoint

This is a source-only observation checkpoint, not native evidence and not a
claim that extended exception syntax is already implemented. It adds no runtime
implementation and creates or rewrites no expected native output.

## Small core matrix

`integrational_tests/tests/functions.bsl` retains all 88 historical messages and
appends 21 exception observations, one handler-state observation and one terminal
marker: 111 messages in total. Helpers precede the original executable body;
observations follow `reference-new.checkpoint.complete`.

The cases cover Russian and English statement and functional Raise, all five
parameters, a category alone, omitted middle slots, omitted trailing slots,
explicit Undefined defaults and empty string fields. They also cover an explicit
cause, a cause captured directly in a nested handler, bare rethrow, and propagation
through two ordinary routines in both languages. One wrapper deliberately omits
its own category while its cause has ConfigurationError, to observe whether the
category query follows the cause rather than assuming a hierarchy. A single forbidden-category
control distinguishes valid raising from parameter rejection. This is not an
exhaustive argument-validation or error-category hierarchy matrix.

The new syntax stays inside Execute strings. New APIs stay inside guarded
Execute/Eval strings; property, type and category queries use Eval. Therefore the old
interpreter can execute the entire checkpoint, report unavailable operations and
reach its marker. There is no native-only output branch or assumed native answer.

Every direct error observation catches and saves ErrorDescription and ErrorInfo
inside the dynamic Execute text, before crossing its boundary or running any
property query. The static outer handler is only a bootstrap fallback: it never
substitutes an Execute wrapper for the directly raised error. The captured value
is read after the handler. The two routine cases intentionally propagate through
the callee's Execute boundary and two ordinary routines; those observations do
not assume that native Execute unwraps or preserves a particular error layer. Fields include:

- ErrorInfo type identity in both languages.
- Description equality to the controlled message, separately from ErrorDescription presence of that controlled message. Exact formatted
  ErrorDescription text is outside this checkpoint's scope.
- Code and AdditionalInformation as internal scalar values.
- Whether Cause is Undefined, and the cause's controlled description, code and ConfigurationError membership.
- AllErrors, ScriptRuntimeError, ScriptCompileError,
  ExceptionRaisedFromScript, ConfigurationError and OtherError membership.
- Russian property and category-method aliases, including the full
  `ОшибкаВоВремяВыполненияВстроенногоЯзыка` spelling.
- ErrorInfo outside the handler and a saved value read after leaving it.

`query-error` means that a specific query failed; it is not a Boolean answer.
`info-error` means the exception-information capture failed; `execute-error`
means the dynamic text failed before reaching that capture. None of these markers is
proof that the requested Raise operation succeeded. In particular, finding the
controlled text in ErrorDescription is not sufficient: compilation diagnostics
may include the source text. Inspect type, code, details and categories together.
Description is observed as a Boolean comparison rather than publishing localized
platform diagnostics. No source path, source line, stack dump or system-error
text is printed. A missing cause intentionally produces guarded query errors
for its description and code without suppressing the other fields.

## Preserved evidence and harness

The historical Windows functions source is exactly bound to Git blob
`c83e860364555a0f6290e3b34d7cf8a8eb40df9f`; its complete 88-message output remains
blob `6df192ac9d10c07755948d7c14cfed9e2311c65f`. Offline historical replay removes
only the two named new source blocks and checks the original source and output
identities. It does not truncate, filter, replace or approve a prefix of output.
The new local checkpoint test independently executes the full current source
and checks that all original messages remain in place.

Live native execution always receives the full current source. The six-scenario
runner, all six output files, 24-file client-enabled input manifest, source/module/
output hashes and provenance checks are unchanged. No runtime or native harness
file is modified. The other substantive scenario counts remain collections 841,
values 402, numbers 421 and dates 185; their source bytes and all historical
fixture bytes are preserved.

## Native acceptance before semantic claims

Run the existing approved full native workflow from the checkpoint commit with
output export enabled. Verify measured platform/target, clean completion, input
and generated-module hashes, six fresh outputs and their provenance before
interpreting the 23-message functions suffix. Require 111 functions messages and
all pre-existing client parity checks without changing their record counts.
Read every exception observation, not only the terminal marker. Expected native
errors remain observations, never evidence of support. Keep the results tied to
the exact commit and source hash; do not synthesize or overwrite frozen fixtures.
A later runtime implementation may be compared against these real observations.

## Documentation basis

The [official 8.3.27 developer guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808880),
section 4.6.10, documents the functional five-parameter Raise form. The
[official error-information guide](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_8.3.23_Developer_Guide/Chapter_32._Debugging_and_testing_applications/32.3._Runtime_errors/32.3.3._Error_information/?language=en)
describes ErrorInfo fields and category queries. The
[official exception-raising standard](https://its.1c.ru/db/content/v8std/src/400/200/i8100790.htm)
provides Russian category and method spellings. These sources motivate the
probes; they do not determine the native observations in advance.

## Focused context follow-up after PR88

The original 111-message source was audited in native run `39840847760` for
PR88, published head `be068c8324fe00f79cea069c6863d8034db3e302`, source SHA256
`b8c1141049f3a604addcdb7e967e045a7a9e6d72258fccb68167417a622dedca`.
Direct ErrorInfo values captured inside Execute remained readable after the
handler. However, the original cause setup and handler-state capture combined
Eval(ErrorInfo()) with a nested successful Try. Their empty saved descriptions
cannot establish which construct changes the visible context, and do not prove
that saved ErrorInfo objects become invalid after leaving a handler.

This follow-up adds exactly five records after the unchanged 111-message prefix,
for 116 functions messages in total. No old helper or observation is edited:

1. Direct ErrorInfo capture in the exception handler.
2. Eval(ErrorInfo()) capture at the same location.
3. Direct capture inside a nested Try around that capture.
4. Eval capture inside that same nested Try.
5. Direct ErrorInfo capture outside any exception handler.

Each paired case immediately saves a scalar Description comparison after the
capture, before leaving the nested Try or handler. It then independently reads
the saved object after the handlers. Comparing the inside scalar with the later
Description distinguishes an initially empty capture from any subsequent
change; neither outcome is assumed. No helper call or extra handler precedes
the capture within the tested handler, apart from the deliberate nested Try in
cases 3 and 4. A surrounding static handler catches unsupported bootstrap APIs
without replacing the saved value. All new syntax/API use stays inside guarded
Execute/Eval strings, so the pre-feature runtime still completes the scenario.

The post-handler snapshots expose ErrorInfo type, the controlled Description,
an explicitly empty Description check, Cause = Undefined, and all six already
used category membership bits. The outside control also saves its empty
Description comparison immediately. No additional category/error cases, source
locations or full platform stacks are introduced. There is no new completion
record: `exception-context.outside-empty` is the fifth and final appended record.

The new exact inverse restores source Git blob
`540d0fa68f212cef2963da7e1e59565a0a56edb6`, preserving every byte of the native-audited
111-record source. Both frozen comparison routes continue through the existing
exact 88-record source/output binding; neither comparator text nor its reviewed
hash pins change. Native execution receives all 116 records. All six fixtures,
24 manifest inputs, six outputs and the other scenario/witness counts remain
unchanged. These five new observations require a fresh native run before being
used to change runtime semantics.
