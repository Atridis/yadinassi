# Bounded Format number measurement

`format-numbers-v1` contains 56 fixed observations of `Формат` / `Format`, with
separate empty-string and UTF-16 calibration records. This is a measurement
profile, not a Format implementation or evidence of native compatibility.

The inputs cover fractional digits (`ЧДЦ/NFD`), decimal separators (`ЧРД/NDS`),
grouping (`ЧГ/NG`, `ЧРГ/NGS`), zero presentation (`ЧН/NZ`), positive and negative
rounding, aliases, parameter order, quoted/duplicate parameters and explicit ru
locale. Missing and explicit-empty zero presentation are separate cases.
String, Boolean, Date, Undefined and Null are dispatcher controls, not promised
runtime support. Default results depend on the measured session locale.

Each expression executes once. Action failures and observer failures are
separate. Results use the existing bounded UTF-16 style `S<count>:<hex units>`;
NBSP, spaces, empty text and surrogate pairs remain distinguishable. Each result
is limited to 32 code units, without truncation. The rectangular maximum is
8,170 bytes within the unchanged 8,192-byte output limit. A larger result is an
observer failure that blocks acceptance, not a native semantic answer.

The existing isolated client/server measurement runner stages exactly 22
source files for this profile. The source hash, generated modules, shell/host
profile selectors, report schemas and artifacts are bound independently. The
client wrapper also captures output emitted inside the fixed observer helper;
the existing tree profiles retain their unchanged generation path. Only this
profile extends the capture alphabet with its `|` separator.

CI adds one fixed matrix row, with `native-1c-format-numbers-summary` and
`native-1c-format-numbers-outputs` artifacts. The ordinary six-domain inventory
and comparators, native image, timeouts, report caps and credentials remain
unchanged. Valid framing is not native authenticity. Acquisition still requires
the authenticated source/run and both native contexts; interpreter comparison
is separately recorded and is expected to fail while Format is unimplemented.
Matching all-action-error outputs cannot pass: the first four numeric controls
must succeed, and any observer-error blocks availability.

Synthetic tests cover exact inputs, lossless output, closed dispatch, cold
staging, actual producer/host envelope validation, generated client capture,
source mutation, unavailable controls and complete report-size upper bounds.
These tests do not provide native expected results. A genuine capture must be
reviewed before runtime implementation or a compatibility claim.

## Supplemental discrimination (cases 49–56)

The original 48-case source is retained byte-for-byte as the prefix (SHA-256
`a7f8e3c6105d4a7f28ef08a0865abcf01f7465f236fffe189c2da7272df04d84`). Its
accepted Linux 8.3.27.1508 capture belongs to PR #163 head
`ffe286b4d94ceeae14c36f948594b3c958ea81b8`, run `41184098782`; raw output SHA-256
`543fa283c906e7d430e8100cf23fdf376f4d552f8d7efd196fe87fb8a858c63b`.
That capture is evidence for the original cases only, not this extended source.

Eight appended cases distinguish three unrelated unknown-name/value shapes,
recognized native numeric/date directives (not implemented by the pending
runtime), repeated/secondary digit grouping, and mixed-case duplicate aliases.
No expected native results are encoded. The same profile/job and finite wire
contract are reused; output budget remains 8192 bytes. New source identity and
58 records (two calibrations plus 56 cases) require a fresh authenticated run.
