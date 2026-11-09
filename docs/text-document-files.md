# TextDocument: ordinary local file workflow

`Прочитать / Read(FileName [, Encoding [, LineSeparator]])` and
`Записать / Write(FileName [, Encoding [, LineSeparator]])` connect the existing
in-memory document to ordinary local files. Both are procedures. A read replaces
the document; a write replaces the file and leaves the document unchanged.

```bsl
Документ = Новый ТекстовыйДокумент;
Документ.Прочитать("input.txt", "UTF-8");
Документ.ДобавитьСтроку("Новая строка");
Документ.Записать("output.txt", КодировкаТекста.UTF8);
```

The three-argument signatures and separator choices follow the published
[TextDocument.Write reference](https://yellow-erp.com/help/sh/objects/catalog63/catalog625/TextDocument/methods/Write145.html/?lang=ru).
The corresponding read contract is also described under
[TextDocument.BeginReading](https://bulzavr.ru/docs/Справка/Справка%20языковых%20конструкций/Объекты/каталог63/каталог625/TextDocument/Методы/ТекстовыйДокумент.НачатьЧтение/):
BOM detection, UTF-8 fallback and an optional separator converted to LF.
Documentation is not native execution evidence. This extension has **no new
native capture**; the earlier 44 TextDocument observations cover memory
operations only, and file-family native33 does not cover TextDocument.

## Local encoding and newline contract

- Read detects UTF-8 and UTF-16LE/BE BOMs when encoding is omitted. Without a
  BOM its fallback is UTF-8, unlike TextReader's existing ANSI fallback.
- Explicit encoding uses the existing file-family allowlist and TextEncoding
  enum. A matching BOM is removed. There is no heuristic encoding detection or
  malformed-byte substitution. Explicit mismatched BOMs follow the existing
  strict file decoder and are not a native-parity claim.
- Write defaults to UTF-8. UTF-8 and UTF-16LE/BE output has a BOM, including
  empty documents; supported single-byte codecs have none. Encoding failure
  raises an error rather than replacing unrepresentable characters.
- Separator is CRLF by default. CR, LF, CRLF and the empty string are accepted;
  other strings and non-string arguments fail. Read converts occurrences of the
  selected nonempty separator to LF. Write first folds existing CRLF to LF,
  then expands LF to the selected separator, matching the current TextWriter
  policy. Isolated CR is preserved. An empty separator leaves raw text intact.
- Writing does not add a final newline. A terminal separator remains terminal;
  reading and subsequent edits use the existing document line model.
- Explicit Undefined uses the default. Optional holes are accepted for an
  exact built-in receiver stored in a variable or exported module property,
  following the existing runtime guard. A hole in the filename position or an optional hole
  on a computed receiver is rejected before receiver/argument side effects.

These are bounded, deterministic local policies. BOM output, mixed-separator
normalization and defaults require a dedicated real-1C comparison before native
parity can be claimed. No prior fixture or result was modified to supply it.

## State integrity and file authority

Read validates options, snapshots the file through `file_io`, decodes/converts
the text and validates all document limits before changing any document state.
A missing file, decoding failure, excessive size or line count preserves the
previous text, line count and individual lines. File handles are closed before
return, including on failure.

Write validates options and fully encodes the prospective bytes, including the
BOM and byte limit, before opening/truncating the destination. Invalid options,
unrepresentable text and encoding-budget failures neither create an absent
destination nor truncate an existing file. This is not transactional filesystem
replacement: a disk, process or I/O failure after opening can leave a truncated
or partially written file. No crash-atomic or concurrent-writer guarantee is made.

The existing regular-file boundary checks the opened descriptor and rejects
directories/devices/FIFOs. File bytes are bounded to 16 MiB; document contents
remain bounded to 1,000,000 UTF-16 units and 100,000 lines. These are local budgets,
not platform limits. Paths are ordinary OS paths, not URLs; normal permissions
and filesystem effects apply. This is not a sandbox against symlink or concurrent
path changes, and no permissions, locks or network access are added.

## Still unsupported

Streams, async/callback methods, UI, UsedFileName/Encoding/LineSeparator
properties, SetFileType, codecs, typed cells and client/server transport remain
outside this slice. ANSI/OEM keep the existing Russian code-page policy; System
uses the host locale. Other ICU codecs, malformed-byte recovery, concurrent
file snapshots and native-specific diagnostics are not implemented.

`tests/test_text_document_files.py` exercises only fresh owned temporary paths.
Existing memory/native-witness tests stay separate. The packaged smoke now
checks invalid encoding before file creation instead of treating all Write calls
as unsupported. No native scenario, workflow, transport budget or provenance
module inventory is changed; the three changed runtime files retain their existing
source-bound provenance checks.
