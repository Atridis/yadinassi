# Terminal omitted arguments: measurement only

This checkpoint prepares nine ordinary-language observations in the existing
`integrational_tests/tests/functions.bsl` object-module scenario. It does not
change the parser or runtime, introduce another scenario, or claim native parity.
Native expected outcomes are **unknown** until a complete source-bound capture
has been independently checked.

## Question and primary reference

The [8.3.27 Developer Guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293),
section 4.7.4.4, distinguishes an explicitly skipped position from an absent
right-hand parameter. A skipped ordinary BSL formal uses its declared default,
or Undefined; an absent required formal is an arity error. Its three-formal
example `MyProcedure(, ,);` describes two skipped positions and an omitted third
parameter. Therefore a final comma must not automatically be assumed to add
another explicit argument node. Native measurements will resolve that count.

This is not constructor or host-API optional-parameter evidence. Those have
separate contracts. No form, server-transfer, database, RPC or event semantics
are introduced by these observations.

## Finite cases

The helpers have two formals with defaults, two required formals, or one required
formal. Tick increments an argument counter; target routines increment a separate
body counter. Undefined is encoded as zero only inside the pair-value helper.

1. `Defaults()`: genuine zero-argument, all-default control.
2. `Required()`: absent required parameters.
3. `Required(,)`: one-comma count discriminator.
4. `Required(,,)`: complementary two-comma discriminator.
5. `Defaults(5,)`: terminal omission with a declared default.
6. `Defaults(5,Undefined)`: explicit Undefined versus the preceding default.
7. `One(Tick(),)`: one formal, terminal comma and observable effects.
8. `One(Tick(),2,)`: excess arity under either count interpretation, with effects.
9. `Required(Tick(),,)`: repeated terminal punctuation and a required final formal.

Every disputed call is a literal string executed inside Try/Except. Consequently
an invalid dynamic call produces a finite error record rather than poisoning the
outer native module's compilation. Each record contains success/error, argument
and body counters, and a two-digit result initialized to 99. No error descriptions,
paths or private diagnostics are emitted. Digit-range violations fail the whole
collector instead of creating an unbounded token.

One additional output line contains `omit.v1:` and nine five-character records,
53 ASCII characters in total. There are no loops or external inputs. Current
interpreter tests verify only packaging and retention, not invented native values.

Execute evidence applies to that language entry path. Once a valid terminal
spelling is established, final implementation acceptance must also include one
literal direct positive call; no new compile-negative framework is needed.

## Capture, mismatch and preservation

The ordinary six-scenario launcher compiles and runs the entire current
functions.bsl. Its existing post-create directive stays first, and declarations
remain before routines and executable statements. All previous 136 initialization
records and 18 post-create observations remain. The new line is between them,
not after the complete post-create output.

The unmodified interpreter still rejects terminal commas, but the probe catches
those errors and completes with its own finite observations. The full-source host
comparison can consequently report a normal `mismatched` result. Existing native
output export allows complete, validated captures on such rejection, only after
all source, module, process, nonce, version, transport and cleanup gates pass.
The workflow stays failed for rejected parity; capture is not acceptance.
An interpreter crash or timeout is not interchangeable with a normal mismatch.

No changes are made to client135, its private reader, dense dual token, protocol
schemas, scenario inventory or size limits. The new native result is obtained
through the existing functions.out artifact and provenance, not a new payload.

The three new source sections have an exact inverse for old checkpoint and
Windows replay. Both the complete measurement source and restored baseline are
hash-bound. The latter is the full prior source, SHA-256
`21d53297530d86c260b75659f7fdab2e35acddf82e53ab9056f9991a4195a3ab`,
git blob `0393cf93cf5380b0231a9b36ce067e3af682d532`.
The inverse is never applied by live native comparison. Frozen native outputs
remain untouched and are compared in full; no output is truncated to a prefix.

After capture: audit the source-bound records, implement only the measured
argument-count/default behavior, add focused parser/runtime regressions, then
require whole-current-source native parity and the existing release gates.
