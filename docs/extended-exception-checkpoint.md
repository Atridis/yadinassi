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
