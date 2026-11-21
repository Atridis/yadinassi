# Lightweight Table sorting and historic order

The lightweight string key orders the 33 Russian letters alphabetically
(`Е`, `Ё`, `Ж`) and treats their uppercase and lowercase forms as equivalent.
Other characters are unchanged in the key; this is not a locale collation.
Equal keys retain input order. Single-column sorting passes its key function
directly to Python's `sorted` and replaces the rows only after success.

Blocking `test_native_target_sort` checks all 96 Python orders, record/cell/owner
and metadata preservation, numeric ordering and callback rejection. The readonly
`cells` snapshot contract is checked separately, not excused as collation.

`python -m tests.compatibility_native_table_sort` validates the unchanged fixture
and all 96 actual cases, then reports exact historic ordering differences. The
dedicated **Совместимость с 1С: известные расхождения** job in **Test and build**
publishes the first 10 examples in the run Summary and all differences in a
`compatibility-differences-*` artifact. The Summary shows only text keys for both implementations.
The full artifact adds row IDs to distinguish equal keys. The job is
informational and is not a dependency of the required verdict or release. Missing coverage, fixture/data corruption and execution
errors fail the diagnostic step and are labeled incomplete in the Summary,
not mistaken for zero differences. The job currently lists this exact-order
difference at low priority; it does not suppress other failing tests.

For the strict oracle use
`python -m unittest tests.compatibility_native_table_sort -v`.
It remains red on historical mismatches. Runtime and fixtures are unchanged.

## New Latin diacritics capture (not an oracle yet)

The separate `integrational_tests/manual_probes/value_table_latin_sort.bsl`
probe uses 26 keys, including
`A/a/Á/á`, accent, umlaut, tilde and caron variants, `ł`, `ß/ss`, a bare space
and hyphen, trailing whitespace and precomposed/decomposed `á` and `ä`.
It builds a fresh ValueTable for each order. In addition to ascending and
descending, two ascending passes use opposite explicit ID tie-breakers to
distinguish equal primary sort keys from merely unstable row order.

Run from the repository root in PowerShell. Stage the existing launcher and
this one probe in a temporary directory so no previous output is overwritten:

```powershell
$probe = Join-Path ([IO.Path]::GetTempPath()) ("yadinassi-latin-sort-" + [guid]::NewGuid())
New-Item -ItemType Directory "$probe\tests" -Force | Out-Null
Copy-Item integrational_tests\test_launcher.py $probe
Copy-Item integrational_tests\launcher_1c $probe -Recurse
Copy-Item integrational_tests\manual_probes\value_table_latin_sort.bsl "$probe\tests"
python "$probe\test_launcher.py" --bd "C:\Bases\TestBase" --path-1c "C:\Program Files\1cv8\8.3.27.2342\bin"
```

Keep `$probe\output\value_table_latin_sort.out` along with platform version, OS,
infobase/session locale and compatibility mode. Each record lists original row IDs and
the actual UTF-16 code units in decimal (`7:97+769` is the decomposed form of
`á`, `3:32` is a space). A usable capture ends with `|complete`, contains the
input and four sorted records, each with `|same-rows`, and has no `.err`.
Local yadinassi execution checks the capture shape and row preservation only.
Do not treat its order as native evidence or replace the historical Windows
fixture. The hosted six-scenario native run is unchanged.
