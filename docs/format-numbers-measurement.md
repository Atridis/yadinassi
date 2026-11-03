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
is separately recorded; acquisition and supported runtime parity are different gates.
Matching all-action-error outputs cannot pass: the first four numeric controls
must succeed, and any observer-error blocks availability.

Synthetic tests cover exact inputs, lossless output, closed dispatch, cold
staging, actual producer/host envelope validation, generated client capture,
source mutation, unavailable controls and complete report-size upper bounds.
These tests do not provide native expected results. A genuine capture must be
reviewed before runtime implementation or a compatibility claim.

## Acquired supplementary scope and required runtime lane

The original 48-case source remains the required profile, SHA-256
`a7f8e3c6105d4a7f28ef08a0865abcf01f7465f236fffe189c2da7272df04d84`.
A temporary append-only 56-case measurement was published in PR #163 head
`b0808e2731fd936dcdfe9cd45b00c14b58249c5c` and acquired by run `41185012239`.
Its exact source SHA-256 is
`604a647404ee84b5e98a07b9bad646b568ce6e8645d063b176459294377b8344`; capture SHA-256
`c73b57a240afa1e27852369d88d7a6d92d3be125f2888456d960f40808c67d0d`.
Both are preserved with provenance under `tests/fixtures/format_numbers/`.
Original 48 source/output prefixes were unchanged. The temporary extension
stayed within the same 8192-byte bound (rectangular maximum 8170 bytes).

The six additional numeric/grammar witnesses are replayed offline; two wider
native controls (ND and DF) are deliberately unsupported and explicitly tested
as a policy gap. Restoring the original required lane does not discard those
observations or claim equivalence on the wider 56-case surface. See
[bounded runtime scope](format-numbers-runtime.md).
