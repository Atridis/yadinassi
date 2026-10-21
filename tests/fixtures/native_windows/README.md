# Historical Windows native fixtures

These six files are genuine owner-supplied 1C 8.3.27.2342 captures, moved byte for
byte from `integrational_tests/output` at commit
`f4654d7fd4db08af51258b13deefca4ea72bf6fb`. They are independent regression and
decoder inputs, not generated interpreter expectations. Their historical metadata
remains in [integrational_tests/meta.md](../../../integrational_tests/meta.md),
and [native-testing.md](../../../docs/native-testing.md) records the capture history.
Older documentation uses the original paths when describing those commits.

The latest collections capture is the complete 200954-byte owner output (Git blob
`97e90791a4011bd7f6ef2922533f92f698557cbd`). The source-bound replay in
`scripts/native_historical_replay.py` still checks every captured byte against the
complete corresponding historical source. The other five captures and all
existing full, prefix, decoder and frozen checks retain their original coverage.

`integrational_tests/output` is now a disposable launcher destination, retained
by `.gitkeep`; generated contents are ignored by Git. Launcher runs must not
write into `tests/fixtures/native_windows`. Fresh automatic Docker CI still executes all six current scenarios
and publishes its separately validated Linux outputs and provenance. It does not
replace or relabel these Windows fixtures. Routine CI needs no manual fixture
regeneration. Do not substitute interpreter output or Linux captures for them.
