# Bounded Format number measurement

`format-numbers-v1` adds 48 fixed observations of `Формат` / `Format`, with
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
7,010 bytes within the unchanged 8,192-byte output limit. A larger result is an
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
