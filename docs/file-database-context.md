# Optional standalone file-database context

A database is optional. Existing script, `-c`, Cyrillic `-с`, `--command`, stdin
`-` and console modes continue to work without one. `--f DIRECTORY` attaches a
small immutable **location context**, not a native 1C session. The implementation
uses bounded read-only inspectors and does not require an installed 1C platform,
credentials or a native database driver. The connection-string contract below
is separate from the experimental [CONFIG-only BSL catalog metadata
view](bsl-catalog-metadata.md), whose fresh public-adapter native acceptance
is still pending.

## CLI and lazy execution

```sh
yadinassi --f "/path/to/База с пробелами" script.bsl
yadinassi --f "/path/to/База с пробелами" -c 'Message(InfoBaseConnectionString());'
yadinassi --f "/path/to/База с пробелами" - < script.bsl
yadinassi --f "/path/to/База с пробелами"
```

The directory must contain a caller-provided consistent offline `1Cv8.1CD` copy.
No snapshot or lock is created. An executed zero-argument call to
`InfoBaseConnectionString()` / `СтрокаСоединенияИнформационнойБазы()` inspects the
file header. Its recognized header and physical size must satisfy the existing
[header-inspection contract](filedb-header-inspection.md). Inspection remains
read-only and reads at most 24 header bytes per call. A recognized geometry is
not proof of database validity, transaction consistency or safe live access.

Without a context, an executed call raises the catchable diagnostic:

```text
db required for further code execution
```

For example, this remains valid without a database:

```bsl
Try
    Message(InfoBaseConnectionString());
Except
    Message(ErrorInfo().Description);
EndTry;
Message(6 * 7);
```

A missing directory, missing or unsupported `1Cv8.1CD`, or unsupported path
spelling fails only when the call actually executes. Arithmetic, parsing,
declaring a routine, and an untaken branch are not database operations. A syntax
error still reports its own source location, rather than a premature DB error.
Uncaught DB errors use the normal CLI exit code `1`; the console can continue.

An empty CLI directory is different: `--f ""` and `--f=` return usage exit code
`2` with the fixed diagnostic `yadinassi: --f requires a non-empty directory`.
This happens before context construction, source execution or database access,
including with `--help` or malformed options. A missing `--f` operand is also
an argparse usage error. Nonempty invalid paths retain the lazy behavior above.

The root/unannotated execution context remains `AtClient`. Providing `--f` does
not select a server mode or change the default Windows `native_target` profile.
The same context is passed to imported modules and supported client/server
activations; these are interpreter execution contexts, not real platform sessions.

## Python API and path subset

```python
from yadinassi import Interpreter
from yadinassi.database_context import FileDBContext

context = FileDBContext("./offline copy")
interpreter = Interpreter(database_context=context)
try:
    interpreter.execute("Message(InfoBaseConnectionString());")
finally:
    interpreter.close()
```

`FileDBContext` is immutable. Its `directory` is lexically normalized once at
construction. Ordinary relative paths are anchored to that moment's working
directory, not the source file, imported module or a later process working
directory. Construction performs no database filesystem inspection. Path
spelling checks are also deferred until the DB call.

The supported subset is ordinary host POSIX/Windows paths, including, on Windows,
drive-absolute paths using backslashes. Spaces and Unicode are preserved. The
result is `File="directory";`, with one trailing semicolon. Ordinary `.` and `..`
components are normalized lexically. This is not native canonicalization:
symlinks, physical case, native platform path rewriting and other filesystem
identity rules are not resolved or claimed. Normal filesystem path following
still applies when the bounded inspector eventually opens the file.

Double quotes, semicolons, control characters, surrogate code points, UNC and
Windows device path forms are outside this subset and rejected lazily. No
escaping or native behavior is invented for them. Drive-relative paths on Windows
are also excluded. Executing a Windows drive-absolute path on a POSIX host is
rejected lazily before inspection, not treated as a relative backslash filename.

The official [Webinst connection-string syntax](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Administrator_Guides/1C_Enterprise_8.3.24_Administrator_Guide/Chapter_8._Setting_up_web_services_for_1C_Enterprise/8.3._Publication_types/8.3.3._Webinst_utility/)
is the serialization reference for a spelling such as `File="c:\my db\demows";`.
It is not an observation of the Windows native function's exact return value.

## Authentication and future CF/DT modes

`--user` and `--psw` are recognized only to reject unsupported authentication.
Every ordinary, equals-value, empty-value and missing-value form produces exit
code `2` with the same fixed diagnostic, without echoing argument values:

```text
yadinassi: authentication options --user/--psw are not supported
```

This rejection precedes `--help`, `--version`, argparse diagnostics and source
execution, so an unrelated malformed option cannot expose credential values.
The scan is option-aware: the operand after `-c`, `-с` or `--command`, and the
contents of `--command=...`, are source code rather than authentication flags.
The `--` boundary ends option handling; a subsequent `--user` can be a literal
script filename. Long-option abbreviations are disabled. Do not supply real
credentials: the rejection does not conceal arguments from shell history or
process-list tools outside Yadinassi.

CF/DT load/dump are future separate real execution modes, for example the
proposed Python-style `dump-config <path_to_cf> --f <path_to_db> --user <user>
--psw <psw>`. This example is a design direction, **not an implemented command**.
There are no placeholder subcommands, platform `DESIGNER` passthrough, login,
configuration operations, database writes, queries or authenticated identities.

## Native evidence boundary

The independently captured Linux/amd64 8.3.27.1508 managed thick-client
measurement returned `ibc.v1:121122221122021122021122021122`. Its five direct
sites were client, server, no-context server, dual client and dual server. In
that bounded observation both aliases returned equal strings of exactly
`File="/tmp/onec-smoke/db";`, including the final semicolon. The arity probes were
dynamic calls inside the dual no-context observer, not separate static compiler
measurements at every site.

That historical source-bound measurement establishes only its observed subset.
It does not prove arbitrary path behavior, Windows native function parity, a
valid native database from a matching header, or whole137 runtime parity. The
runtime's whole137 source-bound admission is a separate verification step;
adding this API does not retroactively promote the measurement's shared-prefix
preflight. See [measurement design and provenance](infobase-context-measurement.md).

CLI tests use independently constructed recognized-header fixtures with explicit
UTF-8 source and binary LF input. They are not native database fixtures and do
not establish 1C interoperability.

```sh
python -m unittest discover -s tests -p test_database_context_cli.py -v
```
